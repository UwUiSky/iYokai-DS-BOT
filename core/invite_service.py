"""
core/invite_service.py
======================
Link d'invito personali «finto vanity» e storico degli inviti. Un solo punto per comandi e
pannello (D16): ottenere il proprio link, aprirlo (invito Discord vero dedicato, creato una
volta e riusato, ricreato se scade o viene cancellato), registrare chi ha invitato chi, e le
opzioni dell'admin (canale del registro, ruolo che può avere il link; acceso/spento è il modulo).
Funzioni coperte: SPEC §23 (NF-27, link personali r10)
Dipende da: core/invite_tracker.py (contatori `uses`), core/invite_links_logic.py,
core/repositories/invite_links_repo.py, core/repositories/invite_stats_repo.py
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from dataclasses import dataclass

import discord

from core import invite_links_logic as logica
from core.bounded_cache import BoundedCache
from core.config import config
from core.config_schema import ImpostazioneNonValida
from core.database import db
from core.invite_tracker import invite_tracker
from core.repositories.invite_links_repo import LinkPersonale, invite_links_repo
from core.repositories.invite_stats_repo import invite_stats_repo

logger = logging.getLogger("iyokai.invite_service")

MODULO_INVITI = "invites"
NON_CAMBIARE = object()
_blocchi: dict[str, asyncio.Lock] = {}
# Inviti visti vivi da poco: {codice: quando}. Oltre VERIFICA_VALIDA secondi si richiede a Discord
# (la cache del tracker si aggiorna solo agli ingressi e non sa se un invito è stato cancellato).
VERIFICA_VALIDA = 300
_verificati: BoundedCache[str, float] = BoundedCache(5000)


@dataclass(frozen=True)
class Opzioni:
    attivo: bool
    canale_log_id: int | None
    ruolo_link_id: int | None


@dataclass(frozen=True)
class Ingresso:
    """Come è stato attribuito un ingresso (per il registro nel canale dell'admin)."""

    tipo: str
    invitante_id: int | None
    codice: str | None


def url_pubblico() -> str:
    return (config.WEB_PANEL_PUBLIC_URL or "").rstrip("/")


def indirizzo(link: LinkPersonale) -> str | None:
    """L'indirizzo da dare al membro; None se il sito non è configurato."""
    base = url_pubblico()
    return logica.indirizzo_link(base, link.slug) if base else None


# ------------------------------------------------------------ opzioni (D16)
async def leggi_opzioni(guild_id: int) -> Opzioni:
    return Opzioni(
        attivo=await db.is_module_active_for_guild(guild_id, MODULO_INVITI),
        canale_log_id=await db.get_guild_setting(guild_id, logica.SETTING_CANALE_LOG),
        ruolo_link_id=await db.get_guild_setting(guild_id, logica.SETTING_RUOLO_LINK),
    )


async def imposta_opzioni(
    guild: discord.Guild, *, canale_log=NON_CAMBIARE, ruolo_link=NON_CAMBIARE, changed_by: int | None
) -> bool:
    """
    Cambia canale del registro e/o ruolo del link (id oppure None per toglierlo).
    Lancia ImpostazioneNonValida se il canale o il ruolo non sono di questo server.
    Restituisce True se qualcosa è cambiato.
    """
    cambi: list[tuple[str, int | None]] = []
    if canale_log is not NON_CAMBIARE:
        if canale_log is not None:
            canale = guild.get_channel(canale_log)
            if not isinstance(canale, discord.TextChannel):
                raise ImpostazioneNonValida("Il canale del registro deve essere un canale di testo di questo server.")
        cambi.append((logica.SETTING_CANALE_LOG, canale_log))
    if ruolo_link is not NON_CAMBIARE:
        if ruolo_link is not None and (ruolo_link == guild.id or guild.get_role(ruolo_link) is None):
            raise ImpostazioneNonValida("Il ruolo deve essere un ruolo di questo server (non @everyone).")
        cambi.append((logica.SETTING_RUOLO_LINK, ruolo_link))
    cambiato = False
    for chiave, valore in cambi:
        if await db.get_guild_setting(guild.id, chiave) == valore:
            continue
        if valore is None:
            await db.remove_guild_setting(guild.id, chiave, changed_by)
        else:
            await db.set_guild_setting(guild.id, chiave, valore, changed_by=changed_by)
        cambiato = True
    return cambiato


# ------------------------------------------------------- chi può, dove
def _ruoli_di(membro: discord.Member) -> set[int]:
    return {r.id for r in getattr(membro, "roles", [])}


def _puo_creare(canale, chi) -> bool:
    return chi is not None and canale.permissions_for(chi).create_instant_invite


def scegli_canale(guild: discord.Guild, membro=None):
    """
    Un canale testuale dove il bot può creare inviti e, se c'è il membro, anche lui: il bot non
    crea per lui un invito che lui non potrebbe creare (né in un canale che non vede). Prima i
    canali che vede @everyone (l'anteprima dell'invito ne mostra il nome), poi gli altri.
    """
    candidati = [guild.system_channel, guild.rules_channel, guild.public_updates_channel]
    candidati += sorted(guild.text_channels, key=lambda c: c.position)
    validi = [
        c for c in candidati
        if c is not None and _puo_creare(c, guild.me) and (membro is None or _puo_creare(c, membro))
    ]
    pubblici = [c for c in validi if c.permissions_for(guild.default_role).view_channel]
    return (pubblici or validi or [None])[0]


def _esito_canale(guild: discord.Guild, membro=None) -> str:
    if "INVITES_DISABLED" in guild.features:
        return logica.INVITI_DISABILITATI
    if scegli_canale(guild, membro) is not None:
        return logica.OK
    if membro is not None and scegli_canale(guild) is not None:
        return logica.MEMBRO_SENZA_PERMESSO
    return logica.SENZA_PERMESSO if guild.text_channels else logica.NESSUN_CANALE


async def puo_avere_il_link(guild: discord.Guild, membro) -> str:
    """OK, oppure il motivo per cui il membro non può avere o usare il link (modulo, ruolo,
    presenza, inviti in pausa, permesso «Crea invito» suo e del bot)."""
    if membro is None:
        return logica.NON_NEL_SERVER
    opzioni = await leggi_opzioni(guild.id)
    if not opzioni.attivo:
        return logica.MODULO_SPENTO
    if not logica.ruolo_ammesso(opzioni.ruolo_link_id, _ruoli_di(membro)):
        return logica.RUOLO_MANCANTE
    return _esito_canale(guild, membro)


# ------------------------------------------------------------ il link
async def _crea_slug(guild: discord.Guild, membro) -> LinkPersonale:
    base = logica.slug_base(guild.name, getattr(membro, "name", None) or membro.display_name)
    for numero in range(1, logica.MAX_TENTATIVI_SLUG + 1):
        link = await invite_links_repo.crea(logica.slug_con_suffisso(base, numero), guild.id, membro.id)
        if link is not None:
            return link
    while True:  # quasi impossibile: tutti i nomi presi, si aggiunge un pezzo casuale
        link = await invite_links_repo.crea(
            logica.slug_con_suffisso(base, 1)[: logica.MAX_SLUG - 7] + "-" + secrets.token_hex(3), guild.id, membro.id
        )
        if link is not None:
            return link


async def ottieni_link(guild: discord.Guild, membro) -> tuple[str, LinkPersonale | None]:
    """Il link personale del membro (lo crea la prima volta; non cambia più). Mai un link se non può averlo."""
    esito = await puo_avere_il_link(guild, membro)
    if esito != logica.OK:
        return esito, None
    esistente = await invite_links_repo.del_membro(guild.id, membro.id)
    if esistente is not None:
        return logica.OK, esistente
    return logica.OK, await _crea_slug(guild, membro)


def invito_cancellato(codice: str) -> None:
    """Un invito è sparito (evento di Discord): alla prossima apertura si ricontrolla."""
    _verificati.delete(codice)


async def _invito_vivo(bot, guild: discord.Guild, codice: str) -> bool:
    """Vive ed è di questo server: il sito non gira mai a un invito d'altri."""
    visto = _verificati.get(codice)
    if visto is not None and time.monotonic() - visto < VERIFICA_VALIDA:
        return True
    try:
        invito = await bot.fetch_invite(codice, with_counts=False)
    except discord.NotFound:
        invito_cancellato(codice)
        return False
    except discord.HTTPException:
        return True  # Discord non risponde: meglio un invito che forse vive che uno nuovo a ogni clic
    if getattr(getattr(invito, "guild", None), "id", guild.id) != guild.id:
        return False
    _verificati.set(codice, time.monotonic())
    return True


async def invito_discord(bot, guild: discord.Guild, link: LinkPersonale, membro=None) -> tuple[str, str | None]:
    """
    (esito, codice) dell'invito Discord dedicato al link: quello salvato se vive ancora, altrimenti
    uno nuovo (senza scadenza e senza limite d'usi, solo di quel membro, in un canale dove anche lui
    può creare inviti). Al massimo MAX_INVITI_PERSONALI inviti per server.
    """
    if len(_blocchi) > 2000:  # pulizia: tengo solo i blocchi in uso
        for chiave in [k for k, b in _blocchi.items() if not b.locked()]:
            del _blocchi[chiave]
    blocco = _blocchi.setdefault(link.slug, asyncio.Lock())
    async with blocco:
        attuale = await invite_links_repo.da_slug(link.slug)
        if attuale is None:
            return logica.NON_NEL_SERVER, None
        if attuale.discord_code and await _invito_vivo(bot, guild, attuale.discord_code):
            return logica.OK, attuale.discord_code
        esito = _esito_canale(guild, membro)
        if esito != logica.OK:
            return esito, None
        if await invite_links_repo.conta_codici(guild.id, escludi_slug=link.slug) >= logica.MAX_INVITI_PERSONALI:
            return logica.TROPPI_INVITI, None
        canale = scegli_canale(guild, membro)
        try:
            invito = await canale.create_invite(
                max_age=0, max_uses=0, unique=True, reason="Link d'invito personale (iYokai)"
            )
        except discord.Forbidden:
            return logica.SENZA_PERMESSO, None
        except discord.HTTPException:
            logger.warning("Invito personale non creato nel server %s.", guild.id)
            return logica.ERRORE_DISCORD, None
        invite_tracker.registra_invito(guild.id, invito.code, getattr(guild.me, "id", None))
        _verificati.set(invito.code, time.monotonic())
        await invite_links_repo.imposta_codice(link.slug, invito.code)
        return logica.OK, invito.code


async def apri_link(bot, slug: str) -> tuple[str, str | None]:
    """
    Cosa fa il sito quando si apre /invito/<slug>: (esito, codice Discord). Controlla ADESSO modulo,
    ruolo del proprietario del link e permessi del bot. Niente nomi nell'esito.
    """
    if not logica.slug_valido(slug):
        return logica.NON_NEL_SERVER, None
    link = await invite_links_repo.da_slug(slug)
    guild = bot.get_guild(link.guild_id) if link else None
    if link is None or guild is None:
        return logica.NON_NEL_SERVER, None
    membro = guild.get_member(link.user_id)
    if membro is None:
        try:
            membro = await guild.fetch_member(link.user_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            membro = None
    esito = await puo_avere_il_link(guild, membro)
    if esito != logica.OK:
        return esito, None
    esito, codice = await invito_discord(bot, guild, link, membro)
    if codice is not None:
        await invite_links_repo.segna_uso(slug)
    return esito, codice


async def elimina_link_membro(bot, guild_id: int, user_id: int) -> None:
    """Il membro è uscito: via il suo link e il suo invito Discord (se riesce)."""
    codice = await invite_links_repo.elimina_del_membro(guild_id, user_id)
    if codice is None:
        return
    try:
        invito = await bot.fetch_invite(codice, with_counts=False)
        await invito.delete(reason="Il membro è uscito dal server")
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        logger.info("Invito personale %s non cancellato (server %s).", codice, guild_id)


# --------------------------------------------------------------- storico
async def registra_ingresso(guild: discord.Guild, membro_id: int, trovato: tuple[str, int | None] | None) -> Ingresso:
    """
    Dall'esito del tracker (codice, creatore) al tipo di ingresso, e lo salva. Un invito personale
    vale per il membro che ne è proprietario (l'invito Discord lo ha creato il bot).
    """
    codice = trovato[0] if trovato else None
    creatore = trovato[1] if trovato else None
    personale = await invite_links_repo.da_codice(guild.id, codice) if codice else None
    vanity = getattr(guild, "vanity_url_code", None)
    tipo = logica.tipo_ingresso(
        codice, codice_vanity=vanity if isinstance(vanity, str) else None, link_personale=personale is not None
    )
    invitante = personale.user_id if personale is not None else creatore
    if invitante == membro_id:
        invitante = None  # nessuno invita se stesso
    await invite_stats_repo.record_join(guild.id, membro_id, invitante, codice, tipo)
    return Ingresso(tipo, invitante, codice)
