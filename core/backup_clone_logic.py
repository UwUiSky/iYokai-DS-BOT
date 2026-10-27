"""
core/backup_clone_logic.py
==========================
Clonazione del server per il Backup System: ruoli, canali, emoji,
sticker, suoni e webhook, una chiamata alla volta (mai in parallelo).
Ruoli e canali già presenti nella destinazione (server da modello) si
riusano per nome; il resto si crea. Sui presenti si aggiunge e si aggiorna,
non si toglie (permessi ed etichette solo del backup restano); i ruoli si
mettono solo sotto quello del Creator. Ciò che supera i limiti della
destinazione (emoji, sticker, suoni, webhook, bitrate) viene adattato o
saltato e contato nel riepilogo, senza far fallire il backup.
Funzioni coperte: SPEC §11.3–§11.8, M 12.3–M 12.8
"""

from __future__ import annotations

import io
import logging
from collections import Counter
from dataclasses import dataclass

import discord

from core.backup_mirror_logic import NOME_CANALE_OFFUSCATO

logger = logging.getLogger("iyokai.backup_clone")

# Suoni della soundboard per livello di boost (0, 1, 2, 3).
TETTO_SUONI_PER_BOOST = (8, 24, 36, 48)
MAX_SUONI_SOUNDBOARD = TETTO_SUONI_PER_BOOST[0]

# Un forum ha al massimo 20 etichette.
MAX_ETICHETTE_FORUM = 20

# LIM-28: un canale ha al massimo 15 webhook; uno resta libero per il mirror.
MAX_WEBHOOK_PER_CANALE = 15
MAX_WEBHOOK_COPIATI = MAX_WEBHOOK_PER_CANALE - 1
NOME_WEBHOOK_MIRROR = "iYokai Mirror"

MOTIVO = "Clonazione backup iYokai"


def _permessi_consentiti(target_guild, permessi: discord.Permissions) -> discord.Permissions:
    """Un bot può dare solo i permessi che ha: il resto si toglie (Discord darebbe 403)."""
    me = getattr(target_guild, "me", None)
    if me is None or me.guild_permissions.administrator:
        return permessi
    return discord.Permissions(permessi.value & me.guild_permissions.value)


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
    espressioni_senza_permesso: bool = False
    posizioni_ruoli_fallite: bool = False
    ruoli_non_aggiornati: int = 0
    permessi_ridotti: int = 0
    messaggi_copiati: int = 0
    messaggi_saltati: int = 0
    messaggi_falliti: int = 0
    canali_messaggi_saltati: int = 0
    messaggi_interrotti: bool = False


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

    tetto = _posizione_del_bot(target_guild)
    ordine: dict = {}
    creati_ora = False
    for indice, ruolo in enumerate(ruoli_da_clonare, start=1):
        riusato = esistenti.pop(ruolo.name, None)
        if riusato is not None and tetto is not None and riusato.position >= tetto:
            # sopra il ruolo del Creator: Discord rifiuterebbe; si usa com'è
            riepilogo.ruoli_non_aggiornati += 1
            mappa_id[ruolo.id] = riusato.id
            continue
        permessi = _permessi_consentiti(target_guild, ruolo.permissions)
        if permessi != ruolo.permissions:
            riepilogo.permessi_ridotti += 1
        if riusato is not None:
            # Si cambiano solo i campi diversi: permessi, colore, separato, menzionabile.
            diversi = {}
            if riusato.permissions != permessi:
                diversi["permissions"] = permessi
            if riusato.colour != ruolo.colour:
                diversi["colour"] = ruolo.colour
            if riusato.hoist != ruolo.hoist:
                diversi["hoist"] = ruolo.hoist
            if riusato.mentionable != ruolo.mentionable:
                diversi["mentionable"] = ruolo.mentionable
            if diversi:
                try:
                    await riusato.edit(reason=MOTIVO, **diversi)
                except discord.Forbidden:
                    # ruolo sopra quello del Creator: si usa com'è e si va avanti
                    riepilogo.ruoli_non_aggiornati += 1
            nuovo_ruolo = riusato
            riepilogo.ruoli_riusati += 1
        else:
            creati_ora = True
            nuovo_ruolo = await target_guild.create_role(
                name=ruolo.name,
                permissions=permessi,
                colour=ruolo.colour,
                hoist=ruolo.hoist,
                mentionable=ruolo.mentionable,
                reason=MOTIVO,
            )
        mappa_id[ruolo.id] = nuovo_ruolo.id
        ordine[nuovo_ruolo] = indice

    # M 12.4: la gerarchia si imposta alla fine, in un'unica chiamata. Un ruolo
    # oltre il ruolo del Creator farebbe rifiutare tutta la chiamata: resta fuori.
    if tetto is not None:
        ammessi = {r: posto for r, posto in ordine.items() if posto < tetto}
        if len(ammessi) < len(ordine):
            riepilogo.posizioni_ruoli_fallite = True
        ordine = ammessi
    if ordine and (creati_ora or any(r.position != posto for r, posto in ordine.items())):
        try:
            await target_guild.edit_role_positions(ordine, reason=MOTIVO)
        except discord.HTTPException:
            logger.warning("Posizioni dei ruoli non impostate: il ruolo del bot è troppo in basso?")
            riepilogo.posizioni_ruoli_fallite = True

    return mappa_id


def _posizione_del_bot(target_guild) -> int | None:
    """Posizione del ruolo più alto del Creator: i ruoli si mettono solo sotto. None se non si sa."""
    me = getattr(target_guild, "me", None)
    ruolo = getattr(me, "top_role", None)
    if ruolo is None or getattr(target_guild, "owner_id", None) == getattr(me, "id", 0):
        return None
    return ruolo.position


def _overwrite_consentito(
    target_guild, overwrite: discord.PermissionOverwrite
) -> discord.PermissionOverwrite:
    """Come i ruoli: nell'overwrite restano solo i permessi che il Creator ha (sia consentiti sia negati)."""
    consentiti, negati = overwrite.pair()
    return discord.PermissionOverwrite.from_pair(
        _permessi_consentiti(target_guild, consentiti), _permessi_consentiti(target_guild, negati)
    )


def remap_permission_overwrites(
    source_overwrites: dict,
    role_id_map: dict[int, int],
    target_guild: discord.Guild,
    riepilogo: "RiepilogoCopia | None" = None,
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

        ridotto = _overwrite_consentito(target_guild, overwrite)
        if riepilogo is not None and ridotto.pair() != overwrite.pair():
            riepilogo.permessi_ridotti += 1
        overwrite = ridotto

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
    canali_esistenti: dict[tuple, list] = {}
    for c in getattr(target_guild, "channels", []):
        if isinstance(c, discord.CategoryChannel) or _famiglia(c) is None:
            continue
        canali_esistenti.setdefault((_famiglia(c), c.name), []).append(c)

    offuscate: set[int] = set()
    categorie_ordinate = sorted(source_guild.categories, key=lambda c: c.position)
    for categoria in categorie_ordinate:
        if categoria.name == NOME_CANALE_OFFUSCATO:
            riepilogo.canali_offuscati += 1
            offuscate.add(categoria.id)
            continue
        overwrites = remap_permission_overwrites(categoria.overwrites, role_id_map, target_guild, riepilogo)
        nuova_categoria = cat_esistenti.pop(categoria.name, None)
        if nuova_categoria is not None:
            await _allinea(nuova_categoria, {"overwrites": _con_presenti(nuova_categoria, overwrites)})
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

        if canale.name == NOME_CANALE_OFFUSCATO or (
            canale.category is not None and canale.category.id in offuscate
        ):
            riepilogo.canali_offuscati += 1
            continue

        famiglia = _famiglia(canale)
        if famiglia is None:
            continue  # tipi di canale non gestiti (annunci di thread, directory, ecc.)

        categoria_destinazione = None
        if canale.category is not None:
            categoria_destinazione = mappa_categorie.get(canale.category.id)

        overwrites = remap_permission_overwrites(canale.overwrites, role_id_map, target_guild, riepilogo)
        campi = _campi_canale(canale, famiglia, target_guild)

        nuovo_canale = _prendi_esistente(canali_esistenti, famiglia, canale.name, categoria_destinazione)
        if nuovo_canale is not None:
            # Il canale presente si allinea all'originale: si cambiano solo i campi diversi
            # (anche la categoria: un canale spostato non si duplica).
            if famiglia == "forum":
                campi["available_tags"] = _etichette_unite(nuovo_canale, campi["available_tags"])
            await _allinea(
                nuovo_canale,
                {
                    **campi,
                    "overwrites": _con_presenti(nuovo_canale, overwrites),
                    "category": categoria_destinazione,
                },
            )
            riepilogo.canali_riusati += 1
        else:
            nuovo_canale = await _crea_canale(
                target_guild, famiglia, canale, campi, categoria_destinazione, overwrites
            )

        mappa_id[canale.id] = nuovo_canale.id

    return mappa_id


def _famiglia(canale) -> str | None:
    """'voce', 'stage', 'forum' o 'testo' per i canali che sappiamo copiare, altrimenti None."""
    if isinstance(canale, discord.StageChannel):
        return "stage"
    if isinstance(canale, discord.VoiceChannel):
        return "voce"
    if isinstance(canale, discord.ForumChannel):
        return "forum"
    if isinstance(canale, discord.TextChannel):
        return "testo"
    return None


def _etichette_forum(canale) -> list:
    """Etichette del forum da ricreare (le emoji personalizzate di un altro server si lasciano)."""
    etichette = []
    for t in getattr(canale, "available_tags", None) or []:
        emoji = t.emoji if (t.emoji is not None and getattr(t.emoji, "id", None) is None) else None
        etichette.append(discord.ForumTag(name=t.name, emoji=emoji, moderated=t.moderated))
    return etichette


def _etichette_unite(presente, volute: list) -> list:
    """Le etichette già nel forum restano con il loro id (i post le tengono): si aggiorna
    «moderata» e si aggiungono le mancanti, fino a 20 (limite di Discord)."""
    per_nome = {t.name: t for t in volute}
    unite = []
    for t in getattr(presente, "available_tags", None) or []:
        voluta = per_nome.pop(t.name, None)
        if voluta is not None and voluta.moderated != t.moderated:
            aggiornata = discord.ForumTag(name=t.name, emoji=t.emoji, moderated=voluta.moderated)
            aggiornata.id = getattr(t, "id", 0)
            t = aggiornata
        unite.append(t)
    for t in per_nome.values():
        if len(unite) >= MAX_ETICHETTE_FORUM:
            break
        unite.append(t)
    return unite


def _con_presenti(canale, voluti: dict) -> dict:
    """11.17: gli overwrite che ci sono solo nel backup restano; quelli dell'originale si aggiornano."""
    try:
        presenti = dict(canale.overwrites)
    except Exception:
        presenti = {}
    return {**presenti, **voluti}


def _campi_canale(canale, famiglia: str, target_guild) -> dict:
    """Campi propri del tipo di canale, pronti per create_* e per edit."""
    tetto = int(getattr(target_guild, "bitrate_limit", 96000))
    if famiglia == "voce":
        return {"bitrate": min(canale.bitrate, tetto), "user_limit": canale.user_limit}
    if famiglia == "stage":
        return {"bitrate": min(canale.bitrate, tetto), "user_limit": canale.user_limit}
    if famiglia == "forum":
        return {
            "topic": canale.topic or "",
            "nsfw": canale.nsfw,
            "slowmode_delay": canale.slowmode_delay,
            "available_tags": _etichette_forum(canale),
        }
    return {"topic": canale.topic or "", "nsfw": canale.nsfw, "slowmode_delay": canale.slowmode_delay}


def _prendi_esistente(esistenti: dict, famiglia: str, nome: str, categoria):
    """Toglie e restituisce un canale presente con lo stesso tipo e nome: prima quello nella
    categoria giusta, poi un altro (che andrà spostato)."""
    candidati = esistenti.get((famiglia, nome))
    if not candidati:
        return None
    for c in candidati:
        if getattr(c, "category", None) is categoria or (
            categoria is not None and getattr(getattr(c, "category", None), "id", None) == categoria.id
        ):
            candidati.remove(c)
            return c
    return candidati.pop(0)


def _valore_attuale(canale, chiave: str):
    """Valore di un campo del canale presente, già confrontabile; _ASSENTE se non si legge."""
    try:
        valore = getattr(canale, chiave)
    except Exception:
        return _ASSENTE
    if chiave == "category":
        return getattr(valore, "id", None)
    if chiave == "overwrites":
        return {k.id: v.pair() for k, v in valore.items()}
    if chiave == "available_tags":
        return [(t.name, t.moderated) for t in valore]
    return valore


def _valore_voluto(chiave: str, valore):
    if chiave == "category":
        return getattr(valore, "id", None)
    if chiave == "overwrites":
        return {k.id: v.pair() for k, v in valore.items()}
    if chiave == "available_tags":
        return [(t.name, t.moderated) for t in valore]
    return valore


_ASSENTE = object()


async def _allinea(canale, voluti: dict) -> None:
    """Cambia solo i campi diversi; se niente cambia non chiama Discord."""
    diversi = {}
    for chiave, valore in voluti.items():
        if _valore_attuale(canale, chiave) != _valore_voluto(chiave, valore):
            diversi[chiave] = valore
    if diversi:
        await canale.edit(reason=MOTIVO, **diversi)


async def _crea_canale(target_guild, famiglia, canale, campi, categoria, overwrites):
    comuni = {"name": canale.name, "category": categoria, "overwrites": overwrites, "reason": MOTIVO}
    if famiglia == "voce":
        # LIM-28: il server di backup può avere meno boost dell'originale.
        return await target_guild.create_voice_channel(**comuni, **campi)
    if famiglia == "stage":
        return await target_guild.create_stage_channel(**comuni, **campi)
    if famiglia == "forum":
        return await target_guild.create_forum(**comuni, **campi)
    return await target_guild.create_text_channel(**comuni, **campi)


def conta_canali_non_visibili(source_guild: discord.Guild) -> int:
    """
    M 12.8 (LIM-38): canali che il bot non vede e quindi non può copiare.
    Con il permesso Amministratore (o Vedere i canali ovunque) il numero è 0.
    """
    me = source_guild.me
    return sum(1 for c in source_guild.channels if not c.permissions_for(me).view_channel)


def tetto_suoni(livello_boost: int) -> int:
    """Suoni della soundboard consentiti dal livello di boost (8, 24, 36, 48)."""
    return TETTO_SUONI_PER_BOOST[max(0, min(int(livello_boost or 0), 3))]


def _puo_creare_espressioni(target_guild) -> bool:
    """Senza essere proprietario serve il permesso «Creare espressioni» (o Amministratore)."""
    me = getattr(target_guild, "me", None)
    if me is None:
        return True
    permessi = me.guild_permissions
    return bool(permessi.administrator or permessi.create_expressions)


def _nomi_presenti(target_guild, attributo: str) -> Counter:
    return Counter(e.name for e in getattr(target_guild, attributo, None) or [])


async def clone_emoji(
    source_guild: discord.Guild,
    target_guild: discord.Guild,
    riepilogo: RiepilogoCopia | None = None,
) -> int:
    """
    Clona le emoji personalizzate (SPEC.md §11.5). Quelle con un nome già
    presente non si ripetono. Il limite (separato tra statiche e animate)
    conta anche le emoji già presenti. Senza il permesso «Creare
    espressioni» non prova e lo scrive nel riepilogo. Restituisce quante
    ne ha saltate.
    """
    riepilogo = riepilogo or RiepilogoCopia()
    if not _puo_creare_espressioni(target_guild):
        riepilogo.espressioni_senza_permesso = True
        return len(source_guild.emojis)
    presenti = getattr(target_guild, "emojis", None) or []
    nomi = Counter(e.name for e in presenti)
    creati = {False: 0, True: 0}
    for e in presenti:
        creati[bool(e.animated)] += 1
    saltate = 0
    for emoji in source_guild.emojis:
        if nomi[emoji.name] > 0:
            nomi[emoji.name] -= 1
            continue
        if creati[emoji.animated] >= target_guild.emoji_limit:
            saltate += 1
            continue
        try:
            immagine = await emoji.read()
            await target_guild.create_custom_emoji(name=emoji.name, image=immagine, reason=MOTIVO)
        except discord.HTTPException:
            logger.warning("Emoji '%s' saltata: Discord l'ha rifiutata.", emoji.name)
            saltate += 1
            continue
        creati[emoji.animated] += 1
    return saltate


async def clone_stickers(
    source_guild: discord.Guild,
    target_guild: discord.Guild,
    riepilogo: RiepilogoCopia | None = None,
) -> int:
    """Clona gli sticker (SPEC.md §11.6), come le emoji: niente doppioni
    per nome, limite che conta i presenti, permesso controllato.
    Restituisce quanti ne ha saltati."""
    riepilogo = riepilogo or RiepilogoCopia()
    if not _puo_creare_espressioni(target_guild):
        riepilogo.espressioni_senza_permesso = True
        return len(source_guild.stickers)
    nomi = _nomi_presenti(target_guild, "stickers")
    creati = len(getattr(target_guild, "stickers", None) or [])
    saltati = 0
    for sticker in source_guild.stickers:
        if nomi[sticker.name] > 0:
            nomi[sticker.name] -= 1
            continue
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
                reason=MOTIVO,
            )
        except discord.HTTPException:
            logger.warning("Sticker '%s' saltato: Discord l'ha rifiutato.", sticker.name)
            saltati += 1
            continue
        creati += 1
    return saltati


async def clone_soundboard(
    source_guild: discord.Guild,
    target_guild: discord.Guild,
    riepilogo: RiepilogoCopia | None = None,
) -> int:
    """Clona i suoni della soundboard (SPEC.md §11.7). Il tetto dipende dal
    boost della destinazione (8, 24, 36, 48) e conta i suoni già presenti;
    nomi già presenti non si ripetono. Restituisce quanti ne ha saltati."""
    riepilogo = riepilogo or RiepilogoCopia()
    if not _puo_creare_espressioni(target_guild):
        riepilogo.espressioni_senza_permesso = True
        return len(source_guild.soundboard_sounds)
    nomi = _nomi_presenti(target_guild, "soundboard_sounds")
    creati = len(getattr(target_guild, "soundboard_sounds", None) or [])
    tetto = tetto_suoni(getattr(target_guild, "premium_tier", 0))
    saltati = 0
    for suono in source_guild.soundboard_sounds:
        if nomi[suono.name] > 0:
            nomi[suono.name] -= 1
            continue
        if creati >= tetto:
            saltati += 1
            continue
        try:
            audio = await suono.read()
            await target_guild.create_soundboard_sound(
                name=suono.name, sound=audio, volume=suono.volume, emoji=suono.emoji, reason=MOTIVO
            )
        except discord.HTTPException:
            logger.warning("Suono '%s' saltato: Discord l'ha rifiutato.", suono.name)
            saltati += 1
            continue
        creati += 1
    return saltati


async def _immagine_webhook(webhook) -> bytes | None:
    """11.8: l'immagine del webhook originale, se c'è e si riesce a scaricare."""
    avatar = getattr(webhook, "avatar", None)
    if avatar is None:
        return None
    try:
        return await avatar.read()
    except (discord.HTTPException, discord.NotFound):
        return None


async def clone_webhooks(
    source_guild: discord.Guild,
    target_guild: discord.Guild,
    channel_id_map: dict[int, int],
    riepilogo: RiepilogoCopia | None = None,
) -> None:
    """
    Clona i webhook (SPEC.md §11.8) — nome, immagine e canale di
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
    nomi_presenti: dict[int, Counter] = {}
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
            nomi_presenti[nuovo_channel_id] = Counter(w.name for w in gia)
            totale[nuovo_channel_id] = len(gia)

        # Un omonimo già presente copre un solo webhook dell'originale (rilanci senza doppioni).
        if nomi_presenti[nuovo_channel_id][webhook.name] > 0:
            nomi_presenti[nuovo_channel_id][webhook.name] -= 1
            continue
        if totale[nuovo_channel_id] >= MAX_WEBHOOK_COPIATI:
            riepilogo.webhook_saltati += 1
            continue

        immagine = await _immagine_webhook(webhook)
        try:
            await nuovo_canale.create_webhook(name=webhook.name, avatar=immagine, reason=MOTIVO)
        except discord.HTTPException:
            if immagine is None:
                raise
            # l'immagine è stata rifiutata: il webhook si crea comunque, senza
            await nuovo_canale.create_webhook(name=webhook.name, reason=MOTIVO)
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
