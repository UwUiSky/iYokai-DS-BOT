"""
core/backup_clone_logic.py
==========================
Clonazione del server per il Backup System: ruoli, canali, emoji,
sticker, suoni e webhook, una chiamata alla volta (mai in parallelo).
Emoji, sticker e suoni oltre i limiti del server di destinazione vengono
saltati e contati, senza far fallire il backup.
Funzioni coperte: SPEC §11.3–§11.8
"""

from __future__ import annotations

import io
import logging

import discord

logger = logging.getLogger("iyokai.backup_clone")

# Il server appena creato non ha boost: limite base della soundboard.
MAX_SUONI_SOUNDBOARD = 8


async def clone_roles(source_guild: discord.Guild, target_guild: discord.Guild) -> dict[int, int]:
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

    I ruoli normali vengono creati dal più basso al più alto in
    posizione: ogni nuovo ruolo creato finisce sopra i precedenti
    per comportamento di default di Discord, quindi partire dal più
    basso mantiene l'ordine finale corretto.
    """
    mappa_id: dict[int, int] = {}

    await target_guild.default_role.edit(
        permissions=source_guild.default_role.permissions,
        reason="Clonazione backup iYokai — permessi di @everyone",
    )
    mappa_id[source_guild.default_role.id] = target_guild.default_role.id

    ruoli_da_clonare = sorted(
        (ruolo for ruolo in source_guild.roles if not ruolo.is_default() and not ruolo.managed),
        key=lambda r: r.position,
    )

    for ruolo in ruoli_da_clonare:
        nuovo_ruolo = await target_guild.create_role(
            name=ruolo.name,
            permissions=ruolo.permissions,
            colour=ruolo.colour,
            hoist=ruolo.hoist,
            mentionable=ruolo.mentionable,
            reason="Clonazione backup iYokai",
        )
        mappa_id[ruolo.id] = nuovo_ruolo.id

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
) -> dict[int, int]:
    """
    Clona categorie e canali (testuali e vocali) del server sorgente
    nel server di destinazione, preservando l'ordine e gli overwrite
    di permessi per ruolo (rimappati tramite remap_permission_
    overwrites — serve la mappa già prodotta da clone_roles).

    Le CATEGORIE vanno create per prime: un canale dentro una
    categoria ha bisogno dell'oggetto categoria già esistente sul
    lato destinazione per essere assegnato correttamente.

    Restituisce la mappa ID_canale_originale -> ID_canale_clonato
    (categorie incluse) — utile a chi chiama per ulteriori passaggi
    (es. §11.9 mirror messaggi, che deve sapere in quale canale
    clonato inoltrare ogni messaggio del canale originale).
    """
    mappa_id: dict[int, int] = {}
    mappa_categorie: dict[int, discord.CategoryChannel] = {}

    categorie_ordinate = sorted(source_guild.categories, key=lambda c: c.position)
    for categoria in categorie_ordinate:
        overwrites = remap_permission_overwrites(categoria.overwrites, role_id_map, target_guild)
        nuova_categoria = await target_guild.create_category(
            name=categoria.name,
            overwrites=overwrites,
            reason="Clonazione backup iYokai",
        )
        mappa_id[categoria.id] = nuova_categoria.id
        mappa_categorie[categoria.id] = nuova_categoria

    canali_ordinati = sorted(source_guild.channels, key=lambda c: c.position)
    for canale in canali_ordinati:
        if isinstance(canale, discord.CategoryChannel):
            continue  # già clonate sopra

        categoria_destinazione = None
        if canale.category is not None:
            categoria_destinazione = mappa_categorie.get(canale.category.id)

        overwrites = remap_permission_overwrites(canale.overwrites, role_id_map, target_guild)

        if isinstance(canale, discord.VoiceChannel):
            nuovo_canale = await target_guild.create_voice_channel(
                name=canale.name,
                category=categoria_destinazione,
                overwrites=overwrites,
                bitrate=canale.bitrate,
                user_limit=canale.user_limit,
                reason="Clonazione backup iYokai",
            )
        elif isinstance(canale, discord.TextChannel):
            nuovo_canale = await target_guild.create_text_channel(
                name=canale.name,
                category=categoria_destinazione,
                overwrites=overwrites,
                topic=canale.topic or "",
                nsfw=canale.nsfw,
                slowmode_delay=canale.slowmode_delay,
                reason="Clonazione backup iYokai",
            )
        else:
            continue  # tipi di canale non gestiti (forum, stage, ecc.) — fuori scope qui

        mappa_id[canale.id] = nuovo_canale.id

    return mappa_id


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
) -> None:
    """
    Clona i webhook (SPEC.md §11.8) — solo nome e canale di
    destinazione (rimappato tramite channel_id_map, già prodotta da
    clone_categories_and_channels): l'URL del webhook stesso è
    univoco per ogni webhook creato, non può essere "copiato",
    quindi qualunque integrazione esterna che punta al vecchio URL
    andrà comunque riconfigurata a mano con il nuovo — non
    automatizzabile da qui.
    """
    webhook_sorgente = await source_guild.webhooks()
    for webhook in webhook_sorgente:
        nuovo_channel_id = channel_id_map.get(webhook.channel_id)
        if nuovo_channel_id is None:
            continue  # il canale originale non è stato clonato (tipo non gestito)

        nuovo_canale = target_guild.get_channel(nuovo_channel_id)
        if nuovo_canale is None:
            continue

        await nuovo_canale.create_webhook(name=webhook.name, reason="Clonazione backup iYokai")


async def create_mirror_webhooks(
    target_guild: discord.Guild,
    channel_id_map: dict[int, int],
) -> dict[int, str]:
    """
    Crea, in OGNI canale testuale clonato, un webhook dedicato al
    mirroring in tempo reale dei messaggi (SPEC.md §11.9) — diverso
    da clone_webhooks() qui sopra: quello copia i webhook che
    esistevano GIÀ nel server originale (integrazioni esterne),
    questo ne crea di NUOVI, di proprietà di iYokai, per inoltrare i
    messaggi man mano che arrivano.

    Restituisce channel_id_ORIGINALE -> URL_webhook: la chiave è
    l'ID del canale del server MAIN (non del backup), perché è così
    che il listener on_message riceverà i messaggi da inoltrare — non
    ha alcun bisogno di sapere l'ID del canale clonato.

    Solo i canali testuali hanno un webhook (i canali vocali non
    possono ricevere messaggi testuali "veri" da mirrorare).
    """
    mappa_webhook: dict[int, str] = {}
    for canale_originale_id, nuovo_canale_id in channel_id_map.items():
        nuovo_canale = target_guild.get_channel(nuovo_canale_id)
        if not isinstance(nuovo_canale, discord.TextChannel):
            continue

        webhook = await nuovo_canale.create_webhook(
            name="iYokai Mirror", reason="Mirroring messaggi in tempo reale (backup iYokai)"
        )
        mappa_webhook[canale_originale_id] = webhook.url

    return mappa_webhook
