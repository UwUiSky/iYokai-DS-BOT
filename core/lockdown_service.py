"""
core/lockdown_service.py
========================
Il lavoro con Discord del blocco totale e del panico (NF-29, #100): chiudere
i canali, il livello di verifica e gli inviti, salvare cio' che c'era prima
e riaprire tutto com'era. Lo usano i comandi (`/mod blocco`, `/security
panico`) e, se il server lo ha acceso, anti-nuke e anti-raid.
Funzioni coperte: SPEC §23 (NF-29), catalogo SIC-011..015

Regole:
- una riga con i permessi di prima si scrive PRIMA di toccare il canale: se il
  bot si ferma a meta' (riavvio, errore), `togli` riapre comunque;
- un solo blocco per server (riga unica nel database + un lock per server);
- `togli` durante un blocco ancora in corso lo ferma al gruppo successivo;
- 500 canali: lavoro a gruppi di 8 con una pausa, un errore su un canale non
  ferma gli altri; il riepilogo arriva nel canale, non solo nella risposta
  (il token dell'interazione dura 15 minuti, LIMITI Parte 4 n. 8).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import discord

from core import channel_router as router
from core.bounded_cache import BoundedCache
from core.lockdown_logic import (
    GRANDEZZA_GRUPPO,
    MAX_MOTIVO,
    PAUSA_TRA_GRUPPI,
    STATO_ATTIVO,
    STATO_IN_CORSO,
    STATO_IN_RIAPERTURA,
    TIPO_BLOCCO,
    TIPO_PANICO,
    Esito,
    blocca,
    canali_da_bloccare,
    gia_bloccato,
    ripristina,
    stato_prima,
    testo_riepilogo,
)
from core.repositories.lockdown_repo import lockdown_repo
from core.repositories.security_repo import security_repo

logger = logging.getLogger("iyokai.lockdown")

_blocchi: BoundedCache[tuple[int, int], asyncio.Lock] = BoundedCache(max_size=5000)
# Server in cui qualcuno ha chiesto «togli» mentre il blocco era ancora in corso.
_da_fermare: set[int] = set()
# Server in panico -> True se in panico /mod e /modban sono riservati (SIC-012). Cache in memoria:
# si legge a ogni comando di moderazione, non si interroga il database ogni volta.
_panico: dict[int, bool] = {}
_lavori: set[asyncio.Task] = set()


def _blocco(guild_id: int) -> asyncio.Lock:
    # Un lock appartiene al ciclo di eventi che lo ha usato per primo: la chiave lo tiene distinto.
    chiave = (id(asyncio.get_running_loop()), guild_id)
    blocco = _blocchi.get(chiave)
    if blocco is None:
        blocco = asyncio.Lock()
        _blocchi.set(chiave, blocco)
    return blocco


def _motivo(prefisso: str, motivo: str) -> str:
    return f"{prefisso}: {motivo}"[:MAX_MOTIVO]


async def carica_panici() -> None:
    """All'avvio del cog: rimette in memoria i server rimasti in panico."""
    _panico.clear()
    for stato in await lockdown_repo.panici_attivi():
        _panico[stato.guild_id] = stato.solo_proprietario


def in_panico(guild_id: int) -> bool:
    return guild_id in _panico


def panico_riservato(guild_id: int) -> bool:
    """True se in questo server, adesso, i comandi di moderazione sono solo per proprietario e fidati."""
    return _panico.get(guild_id, False)


def _inviti_chiusi(guild: discord.Guild) -> bool:
    return "INVITES_DISABLED" in (guild.features or [])


async def _chiudi_ingressi(guild: discord.Guild, motivo: str) -> tuple[bool, bool]:
    """
    Livello di verifica al massimo e inviti chiusi. Salva PRIMA cio' che c'era.
    Restituisce (verifica toccata, inviti toccati).
    """
    verifica = guild.verification_level != discord.VerificationLevel.highest
    inviti = not _inviti_chiusi(guild)
    await lockdown_repo.salva_server(
        guild.id,
        verifica_prima=guild.verification_level.name if verifica else None,
        inviti_chiusi_da_noi=inviti,
    )
    if not verifica and not inviti:
        return False, False
    modifiche: dict = {}
    if verifica:
        modifiche["verification_level"] = discord.VerificationLevel.highest
    if inviti:
        modifiche["invites_disabled"] = True
    try:
        await guild.edit(reason=motivo, **modifiche)
    except discord.HTTPException as errore:
        logger.warning("Ingressi non chiusi (server %s): %s", guild.id, errore)
        await lockdown_repo.salva_server(guild.id, verifica_prima=None, inviti_chiusi_da_noi=False)
        return False, False
    return verifica, inviti


async def _blocca_canale(guild: discord.Guild, canale, permessi: tuple[str, ...], motivo: str) -> str:
    everyone = guild.default_role
    overwrite = canale.overwrites_for(everyone)
    prima = stato_prima(overwrite, permessi)
    if gia_bloccato(prima):
        return "saltato"
    await lockdown_repo.salva_canale(guild.id, canale.id, prima)
    try:
        await canale.set_permissions(everyone, overwrite=blocca(overwrite, permessi), reason=motivo)
    except discord.HTTPException as errore:
        logger.warning("Canale %s non bloccato (server %s): %s", canale.id, guild.id, errore)
        return "fallito"
    return "bloccato"


async def _in_gruppi(elementi: list, lavoro) -> list[str]:
    """Esegue `lavoro(elemento)` a gruppi, con pausa; si ferma se arriva «togli»."""
    esiti: list[str] = []
    for inizio in range(0, len(elementi), GRANDEZZA_GRUPPO):
        gruppo = elementi[inizio : inizio + GRANDEZZA_GRUPPO]
        esiti += await asyncio.gather(*(lavoro(e) for e in gruppo))
        if inizio + GRANDEZZA_GRUPPO < len(elementi):
            await asyncio.sleep(PAUSA_TRA_GRUPPI)
    return esiti


async def attiva(
    guild: discord.Guild,
    *,
    tipo: str,
    avviato_da: int,
    motivo: str,
    riepilogo_in: discord.abc.Messageable | None = None,
) -> Esito:
    """Blocca il server. Mai solleva per un singolo canale; il riepilogo va anche nel canale."""
    async with _blocco(guild.id):
        config = await lockdown_repo.get_config(guild.id)
        adesso = datetime.now(timezone.utc)
        finisce = None
        if tipo == TIPO_PANICO and config.sblocco_auto_minuti:
            finisce = adesso + timedelta(minutes=config.sblocco_auto_minuti)
        creato = await lockdown_repo.crea_stato(
            guild.id, tipo=tipo, avviato_da=avviato_da, motivo=motivo[:MAX_MOTIVO],
            finisce_il=finisce, solo_proprietario=config.solo_proprietario and tipo == TIPO_PANICO,
        )
        if not creato:
            return Esito(False, "Il server e' gia' bloccato (o un blocco e' rimasto a meta'). Usa «togli» per riaprire.")
        if tipo == TIPO_PANICO:
            _panico[guild.id] = config.solo_proprietario
        razon = _motivo("Panico" if tipo == TIPO_PANICO else "Blocco totale", motivo)
        verifica, inviti = await _chiudi_ingressi(guild, razon)

        piano = canali_da_bloccare(guild.channels, config.categorie_escluse)
        esiti: list[str] = []
        for inizio in range(0, len(piano), GRANDEZZA_GRUPPO):
            if guild.id in _da_fermare:
                break
            gruppo = piano[inizio : inizio + GRANDEZZA_GRUPPO]
            esiti += await asyncio.gather(*(_blocca_canale(guild, c, p, razon) for c, p in gruppo))
            await asyncio.sleep(PAUSA_TRA_GRUPPI)
        if guild.id in _da_fermare:
            return Esito(False, "Blocco interrotto da «togli»: i canali gia' toccati si riaprono adesso.",
                         bloccati=esiti.count("bloccato"))
        bloccati, falliti = esiti.count("bloccato"), esiti.count("fallito")
        saltati = len(guild.channels) - bloccati - falliti
        await lockdown_repo.imposta_stato(guild.id, STATO_ATTIVO)
        testo = testo_riepilogo(
            tipo=tipo, bloccati=bloccati, saltati=saltati, falliti=falliti,
            verifica=verifica, inviti=inviti, finisce_il=finisce,
        )
    await _annuncia(guild, testo, config.ruoli_avviso, riepilogo_in, titolo_ping=tipo == TIPO_PANICO)
    return Esito(True, testo, bloccati=bloccati, saltati=saltati, falliti=falliti)


async def togli(guild: discord.Guild, *, riepilogo_in: discord.abc.Messageable | None = None) -> Esito:
    """Riapre tutto com'era. Si puo' richiamare finche' restano canali da riaprire."""
    _da_fermare.add(guild.id)
    try:
        async with _blocco(guild.id):
            stato = await lockdown_repo.get_stato(guild.id)
            if stato is None:
                return Esito(False, "Non c'e' nessun blocco da togliere.")
            await lockdown_repo.imposta_stato(guild.id, STATO_IN_RIAPERTURA)
            razon = _motivo("Fine del blocco", stato.motivo or "riapertura")
            righe = await lockdown_repo.canali_da_ripristinare(guild.id)
            everyone = guild.default_role

            async def _riapri(riga) -> str:
                canale = guild.get_channel(riga.channel_id)
                if canale is None:  # il canale non esiste piu'
                    await lockdown_repo.segna_ripristinato(guild.id, riga.channel_id)
                    return "saltato"
                overwrite = canale.overwrites_for(everyone)
                prima_coppia = overwrite.pair()
                nuovo = ripristina(overwrite, riga.prima)
                try:
                    if (nuovo.pair() if nuovo is not None else None) != prima_coppia:
                        await canale.set_permissions(everyone, overwrite=nuovo, reason=razon)
                except discord.HTTPException as errore:
                    logger.warning("Canale %s non riaperto (server %s): %s", riga.channel_id, guild.id, errore)
                    return "fallito"
                await lockdown_repo.segna_ripristinato(guild.id, riga.channel_id)
                return "riaperto"

            esiti = await _in_gruppi(righe, _riapri)
            server_ok = await _riapri_ingressi(guild, stato, razon)
            falliti = esiti.count("fallito")
            if falliti == 0 and server_ok:
                await lockdown_repo.elimina_blocco(guild.id)
                _panico.pop(guild.id, None)
            testo = (
                f"Blocco tolto: {esiti.count('riaperto')} canali riaperti."
                if falliti == 0 and server_ok
                else f"Riaperti {esiti.count('riaperto')} canali; {falliti} canali"
                f"{'' if server_ok else ' e le impostazioni del server'} non sono riuscito a riaprirli. "
                "Rilancia «togli» dopo aver controllato i miei permessi."
            )
    finally:
        _da_fermare.discard(guild.id)
    await _annuncia(guild, testo, (), riepilogo_in, titolo_ping=False)
    return Esito(falliti == 0 and server_ok, testo, bloccati=esiti.count("riaperto"), falliti=falliti)


async def _riapri_ingressi(guild: discord.Guild, stato, motivo: str) -> bool:
    modifiche: dict = {}
    # Il livello si rimette solo se e' ancora quello messo da noi: se l'ha cambiato
    # qualcun altro (o l'anti-raid) nel frattempo, non lo si calpesta.
    if stato.verifica_prima and guild.verification_level == discord.VerificationLevel.highest:
        modifiche["verification_level"] = discord.VerificationLevel[stato.verifica_prima]
    if stato.inviti_chiusi_da_noi and _inviti_chiusi(guild):
        modifiche["invites_disabled"] = False
    if not modifiche:
        return True
    try:
        await guild.edit(reason=motivo, **modifiche)
    except discord.HTTPException as errore:
        logger.warning("Ingressi non riaperti (server %s): %s", guild.id, errore)
        return False
    return True


async def _annuncia(
    guild: discord.Guild, testo: str, ruoli_avviso, riepilogo_in, *, titolo_ping: bool
) -> None:
    """Riepilogo nel canale del comando e negli allarmi (con il ping dei ruoli scelti, SIC-013)."""
    if riepilogo_in is not None:
        try:
            await riepilogo_in.send(testo, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass
    try:
        impostazioni = await security_repo.get_settings(guild.id)
        dest = await router.destinazione(guild, router.TIPO_ALLARMI, impostazioni.alert_channel_id)
    except Exception:  # gli allarmi non devono fermare il blocco
        logger.exception("Canale allarmi non letto (server %s)", guild.id)
        return
    if dest is None:
        return
    ping = ""
    menzioni = discord.AllowedMentions.none()
    if titolo_ping and ruoli_avviso:
        ping = " ".join(f"<@&{r}>" for r in ruoli_avviso) + "\n"
        menzioni = discord.AllowedMentions(
            everyone=False, users=False, replied_user=False, roles=[discord.Object(id=r) for r in ruoli_avviso]
        )
    await router.invia_a(dest, guild, router.TIPO_ALLARMI, content=(ping + testo)[:2000], allowed_mentions=menzioni)


async def _panico_in_background(guild: discord.Guild, motivo: str) -> None:
    try:
        await attiva(guild, tipo=TIPO_PANICO, avviato_da=guild.me.id, motivo=motivo)
    except Exception:
        logger.exception("Panico automatico fallito (server %s)", guild.id)


async def panico_automatico(guild: discord.Guild, motivo: str) -> None:
    """
    Chiamata da anti-nuke e anti-raid quando riconoscono un attacco (SIC-011).
    Parte solo se il server ha acceso «automatico»; non solleva mai: la difesa
    che l'ha chiamata deve proseguire in ogni caso.
    """
    try:
        config = await lockdown_repo.get_config(guild.id)
        if not config.automatico or in_panico(guild.id) or await lockdown_repo.get_stato(guild.id):
            return
        lavoro = asyncio.create_task(_panico_in_background(guild, motivo))
        _lavori.add(lavoro)
        lavoro.add_done_callback(_lavori.discard)
    except Exception:
        logger.exception("Panico automatico non partito (server %s)", guild.id)
