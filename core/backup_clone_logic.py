"""
core/backup_clone_logic.py
==========================
Clonazione del server per il Backup System: ruoli, canali, emoji,
sticker, suoni e webhook, una chiamata alla volta (mai in parallelo).
Ruoli e canali già presenti nella destinazione (server da modello) si
riusano per nome; il resto si crea. Ciò che supera i limiti della
destinazione (emoji, sticker, suoni, webhook, bitrate) viene adattato o
saltato e contato nel riepilogo, senza far fallire il backup.
Funzioni coperte: SPEC §11.3–§11.8, M 12.3–M 12.8
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import discord

from core.backup_mirror_logic import NOME_CANALE_OFFUSCATO

logger = logging.getLogger("iyokai.backup_clone")

# Il server di backup può non avere boost: limite base della soundboard.
MAX_SUONI_SOUNDBOARD = 8

# LIM-28: un canale ha al massimo 15 webhook; uno resta libero per il mirror.
MAX_WEBHOOK_PER_CANALE = 15
MAX_WEBHOOK_COPIATI = MAX_WEBHOOK_PER_CANALE - 1
NOME_WEBHOOK_MIRROR = "iYokai Mirror"

MOTIVO = "Clonazione backup iYokai"


@dataclass
class RiepilogoCopia:
    """Cosa è stato riusato, adattato o saltato durante la copia."""

    ruoli_riusati: int = 0
    canali_riusati: int = 0
    canali_offuscati: int = 0
    canali_non_visibili: int = 0
    webhook_saltati: int = 0
    mirror_non_creati: int = 0
    emoji_saltate: int = 0
    sticker_saltati: int = 0
    suoni_saltati: int = 0
    posizioni_ruoli_fallite: bool = False


async def clone_roles(
    source_guild: discord.Guild,
    target_guild: discord.Guild,
    riepilogo: RiepilogoCopia | None = None,
) -> dict[int, int]:
    """
    Clona i ruoli del server sorgente nel server di destinazione.

    @everyone non viene CREATO (esiste già di default in ogni
    server, Discord non permette di crearne un secondo) — ma i suoi
    PERMESSI vengono comunque applicati esplicitamente al server di
    destinazione: l'amministratore del server originale potrebbe
    averli personalizzati rispetto al default di Discord (es. tolto
    "Invia messaggi" di default a tutti), e quella scelta va
    preservata nel backup, non persa silenziosamente.

    I ruoli "managed" (creati da un'integrazione o da un bot, es. il
    ruolo automatico di un bot musicale) vengono saltati — Discord
    non permette di crearli manualmente, si ricreano da soli quando
    l'integrazione/il bot viene reinvitato.

    Restituisce la mappa ID_ruolo_originale -> ID_ruolo_clonato
    (include anche @everyone, mappato al default_role già esistente
    nel server di destinazione), necessaria per rimappare gli
    overwrite di permessi sui canali (clone_categories_and_channels).

    I ruoli si creano dal più basso al più alto, poi le posizioni
    vengono impostate esplicitamente (M 12.4).
    """
    riepilogo = riepilogo or RiepilogoCopia()
    mappa_id: dict[int, int] = {}

    await target_guild.default_role.edit(
        permissions=source_guild.default_role.permissions,
        reason="Clonazione backup iYokai — permessi di @everyone",
    )
    mappa_id[source_guild.default_role.id] = target_guild.default_role.id

    # M 12.3: un modello di server ha già ruoli. Si riusano per nome (una
    # sola volta ciascuno); i permessi si allineano a quelli dell'originale.
    esistenti = {
        r.name: r for r in target_guild.roles if not r.is_default() and not r.managed
    }

    ruoli_da_clonare = sorted(
        (ruolo for ruolo in source_guild.roles if not ruolo.is_default() and not ruolo.managed),
        key=lambda r: r.position,
    )

    ordine: dict = {}
    for indice, ruolo in enumerate(ruoli_da_clonare, start=1):
        riusato = esistenti.pop(ruolo.name, None)
        if riusato is not None:
            if riusato.permissions != ruolo.permissions:
                await riusato.edit(permissions=ruolo.permissions, reason=MOTIVO)
            nuovo_ruolo = riusato
            riepilogo.ruoli_riusati += 1
        else:
            nuovo_ruolo = await target_guild.create_role(
                name=ruolo.name,
                permissions=ruolo.permissions,
                colour=ruolo.colour,
                hoist=ruolo.hoist,
                mentionable=ruolo.mentionable,
                reason=MOTIVO,
            )
        mappa_id[ruolo.id] = nuovo_ruolo.id
        ordine[nuovo_ruolo] = indice

    # M 12.4: la gerarchia si imposta alla fine, in un'unica chiamata.
    if ordine:
        try:
            await target_guild.edit_role_positions(ordine, reason=MOTIVO)
        except discord.HTTPException:
            logger.warning("Posizioni dei ruoli non impostate: il ruolo del bot è troppo in basso?")
            riepilogo.posizioni_ruoli_fallite = True

    return mappa_id


def remap_permission_overwrites(
    source_overwrites: dict,
    role_id_map: dict[int, int],
    target_guild: discord.Guild,
) -> dict:
    """
    Converte gli overwrite di permessi (canale/categoria) dal server
    originale al server clonato. Solo quelli per RUOLO vengono
    riportati (i ruoli clonati hanno ID diversi da quelli originali,
    serve la mappa per trovare il ruolo giusto nel server nuovo) —
    gli overwrite per singolo UTENTE vengono saltati: un server
    appena clonato non ha ancora nessun membro (il restore utenti è
    un passo separato, §11.11), non esiste nessun Member a cui
    applicarli.
    """
    nuovi_overwrites = {}
    for destinatario, overwrite in source_overwrites.items():
        if not isinstance(destinatario, discord.Role):
            continue  # overwrite per singolo utente, saltato

        if destinatario.is_default():
            # @everyone esiste già nel server di destinazione, non
            # passa dalla mappa dei ruoli clonati.
            nuovi_overwrites[target_guild.default_role] = overwrite
            continue

        nuovo_id = role_id_map.get(destinatario.id)
        if nuovo_id is None:
            continue  # ruolo non clonato (managed, o rimosso nel frattempo)

        nuovo_ruolo = target_guild.get_role(nuovo_id)
        if nuovo_ruolo is not None:
            nuovi_overwrites[nuovo_ruolo] = overwrite

    return nuovi_overwrites


async def clone_categories_and_channels(
    source_guild: discord.Guild,
    target_guild: discord.Guild,
    role_id_map: dict[int, int],
    riepilogo: RiepilogoCopia | None = None,
) -> dict[int, int]:
    """
    Clona categorie e canali (testuali e vocali) del server sorgente
    nel server di destinazione, preservando l'ordine e gli overwrite
    di permessi per ruolo (rimappati tramite remap_permission_
    overwrites — serve la mappa già prodotta da clone_roles).

    Le CATEGORIE vanno create per prime: un canale dentro una
    categoria ha bisogno dell'oggetto categoria già esistente sul
    lato destinazione per essere assegnato correttamente.

    M 12.3: categorie e canali già presenti nella destinazione (server da
    modello) si riusano per nome (e categoria); il resto si crea.
    M 12.8: i canali offuscati (``___hidden___``) si saltano e si contano.

    Restituisce la mappa ID_canale_originale -> ID_canale_clonato
    (categorie incluse) — utile a chi chiama per ulteriori passaggi
    (es. §11.9 mirror messaggi, che deve sapere in quale canale
    clonato inoltrare ogni messaggio del canale originale).
    """
    riepilogo = riepilogo or RiepilogoCopia()
    mappa_id: dict[int, int] = {}
    mappa_categorie: dict[int, discord.CategoryChannel] = {}

    # Canali già presenti: ognuno si riusa una volta sola.
    cat_esistenti = {c.name: c for c in getattr(target_guild, "categories", [])}
    canali_esistenti = {
        (_famiglia(c), c.name, c.category.name if c.category else None): c
        for c in getattr(target_guild, "channels", [])
        if not isinstance(c, discord.CategoryChannel)
    }

    categorie_ordinate = sorted(source_guild.categories, key=lambda c: c.position)
    for categoria in categorie_ordinate:
        if categoria.name == NOME_CANALE_OFFUSCATO:
            riepilogo.canali_offuscati += 1
            continue
        overwrites = remap_permission_overwrites(categoria.overwrites, role_id_map, target_guild)
        nuova_categoria = cat_esistenti.pop(categoria.name, None)
        if nuova_categoria is not None:
            await nuova_categoria.edit(overwrites=overwrites, reason=MOTIVO)
            riepilogo.canali_riusati += 1
        else:
            nuova_categoria = await target_guild.create_category(
                name=categoria.name, overwrites=overwrites, reason=MOTIVO
            )
        mappa_id[categoria.id] = nuova_categoria.id
        mappa_categorie[categoria.id] = nuova_categoria

    canali_ordinati = sorted(source_guild.channels, key=lambda c: c.position)
    for canale in canali_ordinati:
        if isinstance(canale, discord.CategoryChannel):
            continue  # già clonate sopra

        if canale.name == NOME_CANALE_OFFUSCATO:
            riepilogo.canali_offuscati += 1
            continue

        categoria_destinazione = None
        if canale.category is not None:
            categoria_destinazione = mappa_categorie.get(canale.category.id)

        overwrites = remap_permission_overwrites(canale.overwrites, role_id_map, target_guild)

        chiave = (_famiglia(canale), canale.name, canale.category.name if canale.category else None)
        if chiave[0] is None:
            continue  # tipi di canale non gestiti (forum, stage, ecc.) — fuori scope qui

        nuovo_canale = canali_esistenti.pop(chiave, None)
        if nuovo_canale is not None:
            await nuovo_canale.edit(overwrites=overwrites, reason=MOTIVO)
            riepilogo.canali_riusati += 1
        elif isinstance(canale, discord.VoiceChannel):
            nuovo_canale = await target_guild.create_voice_channel(
                name=canale.name,
                category=categoria_destinazione,
                overwrites=overwrites,
                # LIM-28: il server di backup può avere meno boost dell'originale.
                bitrate=min(canale.bitrate, int(target_guild.bitrate_limit)),
                user_limit=canale.user_limit,
                reason=MOTIVO,
            )
        else:
            nuovo_canale = await target_guild.create_text_channel(
                name=canale.name,
                category=categoria_destinazione,
                overwrites=overwrites,
                topic=canale.topic or "",
                nsfw=canale.nsfw,
                slowmode_delay=canale.slowmode_delay,
                reason=MOTIVO,
            )

        mappa_id[canale.id] = nuovo_canale.id

    return mappa_id


def _famiglia(canale) -> str | None:
    """'voce' o 'testo' per i canali che sappiamo copiare, altrimenti None."""
    if isinstance(canale, discord.VoiceChannel):
        return "voce"
    if isinstance(canale, discord.TextChannel):
        return "testo"
    return None


def conta_canali_non_visibili(source_guild: discord.Guild) -> int:
    """
    M 12.8 (LIM-38): canali che il bot non vede e quindi non può copiare.
    Con il permesso Amministratore (o Vedere i canali ovunque) il numero è 0.
    """
    me = source_guild.me
    return sum(1 for c in source_guild.channels if not c.permissions_for(me).view_channel)


async def clone_emoji(source_guild: discord.Guild, target_guild: discord.Guild) -> int:
    """
    Clona le emoji personalizzate (SPEC.md §11.5): scarica ogni
    immagine e la ricarica nel server di destinazione. Il limite di
    Discord è separato per emoji statiche e animate: quelle oltre il
    limite, o rifiutate da Discord, vengono saltate (non fanno fallire
    il backup). Restituisce quante ne ha saltate.
    """
    saltate = 0
    creati = {False: 0, True: 0}
    for emoji in source_guild.emojis:
        if creati[emoji.animated] >= target_guild.emoji_limit:
            saltate += 1
            continue
        try:
            immagine = await emoji.read()
            await target_guild.create_custom_emoji(
                name=emoji.name, image=immagine, reason="Clonazione backup iYokai"
            )
        except discord.HTTPException:
            logger.warning("Emoji '%s' saltata: Discord l'ha rifiutata.", emoji.name)
            saltate += 1
            continue
        creati[emoji.animated] += 1
    return saltate


async def clone_stickers(source_guild: discord.Guild, target_guild: discord.Guild) -> int:
    """Clona gli sticker personalizzati (SPEC.md §11.6). Quelli oltre il
    limite del server di destinazione, o rifiutati da Discord, vengono
    saltati. Restituisce quanti ne ha saltati."""
    saltati = 0
    creati = 0
    for sticker in source_guild.stickers:
        if creati >= target_guild.sticker_limit:
            saltati += 1
            continue
        try:
            immagine = await sticker.read()
            file_sticker = discord.File(io.BytesIO(immagine), filename=f"{sticker.name}.png")
            await target_guild.create_sticker(
                name=sticker.name,
                description=sticker.description,
                emoji=sticker.emoji,
                file=file_sticker,
                reason="Clonazione backup iYokai",
            )
        except discord.HTTPException:
            logger.warning("Sticker '%s' saltato: Discord l'ha rifiutato.", sticker.name)
            saltati += 1
            continue
        creati += 1
    return saltati


async def clone_soundboard(source_guild: discord.Guild, target_guild: discord.Guild) -> int:
    """Clona i suoni della soundboard (SPEC.md §11.7). Il server nuovo ha
    il limite base (MAX_SUONI_SOUNDBOARD): i suoni oltre il limite, o
    rifiutati da Discord, vengono saltati. Restituisce quanti ne ha
    saltati."""
    saltati = 0
    creati = 0
    for suono in source_guild.soundboard_sounds:
        if creati >= MAX_SUONI_SOUNDBOARD:
            saltati += 1
            continue
        try:
            audio = await suono.read()
            await target_guild.create_soundboard_sound(
                name=suono.name,
                sound=audio,
                volume=suono.volume,
                emoji=suono.emoji,
                reason="Clonazione backup iYokai",
            )
        except discord.HTTPException:
            logger.warning("Suono '%s' saltato: Discord l'ha rifiutato.", suono.name)
            saltati += 1
            continue
        creati += 1
    return saltati


async def clone_webhooks(
    source_guild: discord.Guild,
    target_guild: discord.Guild,
    channel_id_map: dict[int, int],
    riepilogo: RiepilogoCopia | None = None,
) -> None:
    """
    Clona i webhook (SPEC.md §11.8) — solo nome e canale di
    destinazione (rimappato tramite channel_id_map, già prodotta da
    clone_categories_and_channels): l'URL del webhook stesso è
    univoco per ogni webhook creato, non può essere "copiato",
    quindi qualunque integrazione esterna che punta al vecchio URL
    andrà comunque riconfigurata a mano con il nuovo — non
    automatizzabile da qui.

    M 12.6 (LIM-28): al massimo MAX_WEBHOOK_COPIATI per canale (uno dei 15
    resta per il mirror); quelli già presenti con lo stesso nome non si
    ripetono. Gli altri si contano in ``riepilogo.webhook_saltati``.
    """
    riepilogo = riepilogo or RiepilogoCopia()
    nomi_presenti: dict[int, set[str]] = {}
    totale: dict[int, int] = {}
    webhook_sorgente = await source_guild.webhooks()
    for webhook in webhook_sorgente:
        nuovo_channel_id = channel_id_map.get(webhook.channel_id)
        if nuovo_channel_id is None:
            continue  # il canale originale non è stato clonato (tipo non gestito)

        nuovo_canale = target_guild.get_channel(nuovo_channel_id)
        if nuovo_canale is None:
            continue

        if nuovo_channel_id not in nomi_presenti:
            gia = await nuovo_canale.webhooks()
            nomi_presenti[nuovo_channel_id] = {w.name for w in gia}
            totale[nuovo_channel_id] = len(gia)

        if webhook.name in nomi_presenti[nuovo_channel_id]:
            continue
        if totale[nuovo_channel_id] >= MAX_WEBHOOK_COPIATI:
            riepilogo.webhook_saltati += 1
            continue

        await nuovo_canale.create_webhook(name=webhook.name, reason=MOTIVO)
        nomi_presenti[nuovo_channel_id].add(webhook.name)
        totale[nuovo_channel_id] += 1


async def create_mirror_webhooks(
    target_guild: discord.Guild,
    channel_id_map: dict[int, int],
    riepilogo: RiepilogoCopia | None = None,
) -> dict[int, str]:
    """
    Crea, in OGNI canale testuale clonato, un webhook dedicato al
    mirroring in tempo reale dei messaggi (SPEC.md §11.9) — diverso
    da clone_webhooks() qui sopra: quello copia i webhook che
    esistevano GIÀ nel server originale (integrazioni esterne),
    questo ne crea di NUOVI, di proprietà di iYokai, per inoltrare i
    messaggi man mano che arrivano.

    M 12.6: se il canale ha già un "iYokai Mirror" con il suo token lo
    riusa; se il canale è pieno (15 webhook) salta quel canale e lo conta.

    Restituisce channel_id_ORIGINALE -> URL_webhook: la chiave è
    l'ID del canale del server MAIN (non del backup), perché è così
    che il listener on_message riceverà i messaggi da inoltrare — non
    ha alcun bisogno di sapere l'ID del canale clonato.

    Solo i canali testuali hanno un webhook (i canali vocali non
    possono ricevere messaggi testuali "veri" da mirrorare).
    """
    riepilogo = riepilogo or RiepilogoCopia()
    mappa_webhook: dict[int, str] = {}
    for canale_originale_id, nuovo_canale_id in channel_id_map.items():
        nuovo_canale = target_guild.get_channel(nuovo_canale_id)
        if not isinstance(nuovo_canale, discord.TextChannel):
            continue

        webhook = next(
            (
                w
                for w in await nuovo_canale.webhooks()
                if w.name == NOME_WEBHOOK_MIRROR and w.token
            ),
            None,
        )
        if webhook is None:
            try:
                webhook = await nuovo_canale.create_webhook(
                    name=NOME_WEBHOOK_MIRROR,
                    reason="Mirroring messaggi in tempo reale (backup iYokai)",
                )
            except discord.HTTPException:
                logger.warning("Mirror non creato nel canale %s (webhook al massimo?).", nuovo_canale_id)
                riepilogo.mirror_non_creati += 1
                continue
        mappa_webhook[canale_originale_id] = webhook.url

    return mappa_webhook
