"""
core/lockdown_service.py
========================
Il lavoro con Discord del blocco totale e del panico (NF-29, #100): chiudere
i canali, il livello di verifica e gli inviti, salvare cio' che c'era prima
e riaprire tutto com'era. Lo usano i comandi (`/mod-canali blocco`, `/admin-sicurezza
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
from core.moderazione_traduci import traducibile
from core.permission_risk_logic import CRITICAL_PERMISSIONS
from core.lockdown_logic import (
    NOME_CANALE_AVVISO,
    opzioni_valide,
    permessi_pericolosi_da_togliere,
    GRANDEZZA_GRUPPO,
    MAX_MOTIVO,
    MAX_SBLOCCO_MINUTI,
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
from core.blocchi_deboli import BlocchiDeboli

logger = logging.getLogger("iyokai.lockdown")

_blocchi = BlocchiDeboli()
# Server in cui qualcuno ha chiesto «togli» mentre il blocco era ancora in corso.
_da_fermare: set[int] = set()
# Server in panico -> True se in panico i gruppi mod-… sono riservati (SIC-012). Cache in memoria:
# si legge a ogni comando di moderazione, non si interroga il database ogni volta.
_panico: dict[int, bool] = {}
_lavori: set[asyncio.Task] = set()
# MOD-095: server -> «kick» o «ban» per chi entra durante il blocco. In memoria, riletto all'avvio.
_ingressi: dict[int, str] = {}


def modo_ingressi(guild_id: int) -> str | None:
    return _ingressi.get(guild_id)


def _blocco(guild_id: int) -> asyncio.Lock:
    # Un lock appartiene al ciclo di eventi che lo ha usato per primo: la chiave lo tiene distinto.
    chiave = (id(asyncio.get_running_loop()), guild_id)
    return _blocchi.prendi(chiave)


def _motivo(prefisso: str, motivo: str) -> str:
    return f"{prefisso}: {motivo}"[:MAX_MOTIVO]


async def carica_panici() -> None:
    """All'avvio del cog: rimette in memoria i server rimasti in panico."""
    _panico.clear()
    _ingressi.clear()
    for stato in await lockdown_repo.panici_attivi():
        _panico[stato.guild_id] = stato.solo_proprietario
    for stato in await lockdown_repo.stati_con_opzioni():
        if stato.opzioni.get("ingressi"):
            _ingressi[stato.guild_id] = stato.opzioni["ingressi"]


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


async def _senza_eccezioni(lavoro, canale_id: int) -> str:
    """Un errore imprevisto su un canale (database, bug) e' un canale «fallito»: gli altri proseguono."""
    try:
        return await lavoro
    except Exception:
        logger.exception("Errore imprevisto sul canale %s", canale_id)
        return "fallito"


async def _in_gruppi(elementi: list, lavoro) -> list[str]:
    """Esegue `lavoro(elemento)` a gruppi, con pausa."""
    esiti: list[str] = []
    for inizio in range(0, len(elementi), GRANDEZZA_GRUPPO):
        gruppo = elementi[inizio : inizio + GRANDEZZA_GRUPPO]
        esiti += await asyncio.gather(*(_senza_eccezioni(lavoro(e), e.channel_id) for e in gruppo))
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
    durata_minuti: int | None = None,
    canali: list | None = None,
    nascondi: bool = False,
    ingressi: str | None = None,
    ruoli: bool = False,
) -> Esito:
    """Blocca il server. Con `durata_minuti` (MOD-093, al massimo un giorno) si riapre da solo. Mai solleva per un singolo canale; il riepilogo va anche nel canale."""
    async with _blocco(guild.id):
        config = await lockdown_repo.get_config(guild.id)
        adesso = datetime.now(timezone.utc)
        finisce = None
        if tipo == TIPO_PANICO and config.sblocco_auto_minuti:
            finisce = adesso + timedelta(minutes=config.sblocco_auto_minuti)
        if durata_minuti:
            finisce = adesso + timedelta(minutes=min(durata_minuti, MAX_SBLOCCO_MINUTI))
        creato = await lockdown_repo.crea_stato(
            guild.id, tipo=tipo, avviato_da=avviato_da, motivo=motivo[:MAX_MOTIVO],
            finisce_il=finisce, solo_proprietario=config.solo_proprietario and tipo == TIPO_PANICO,
        )
        if not creato:
            return Esito(False, "Il server e' gia' bloccato (o un blocco e' rimasto a meta'). Usa «togli» per riaprire.")
        if tipo == TIPO_PANICO:
            _panico[guild.id] = config.solo_proprietario
        razon = _motivo("Panico" if tipo == TIPO_PANICO else "Blocco totale", motivo)
        # MOD-091/092: con canali scelti il server resta com'è (verifica e inviti non si toccano).
        opzioni = opzioni_valide(nascondi, ingressi, ruoli, solo_canali=canali is not None)
        await lockdown_repo.salva_opzioni(guild.id, opzioni)
        if opzioni["ingressi"]:
            _ingressi[guild.id] = opzioni["ingressi"]
        verifica, inviti = (False, False) if canali is not None else await _chiudi_ingressi(guild, razon)

        piano = canali_da_bloccare(
            guild.channels if canali is None else canali,
            () if canali is not None else config.categorie_escluse, nascondi,
        )
        esiti: list[str] = []
        for inizio in range(0, len(piano), GRANDEZZA_GRUPPO):
            if guild.id in _da_fermare:
                break
            gruppo = piano[inizio : inizio + GRANDEZZA_GRUPPO]
            esiti += await asyncio.gather(
                *(_senza_eccezioni(_blocca_canale(guild, c, p, razon), c.id) for c, p in gruppo)
            )
            await asyncio.sleep(PAUSA_TRA_GRUPPI)
        if guild.id in _da_fermare:
            return Esito(False, "Blocco interrotto da «togli»: i canali gia' toccati si riaprono adesso.",
                         bloccati=esiti.count("bloccato"))
        bloccati, falliti = esiti.count("bloccato"), esiti.count("fallito")
        saltati = len(guild.channels) - bloccati - falliti
        extra = []
        if opzioni["ruoli"]:
            toccati = await _togli_permessi_ai_ruoli(guild, razon)
            extra.append(f"Ruoli a cui ho tolto i permessi pericolosi: {toccati}.")
        if nascondi:
            avviso = await _crea_canale_avviso(guild, motivo, razon)
            if avviso is not None:
                opzioni["avviso"] = avviso
                await lockdown_repo.salva_opzioni(guild.id, opzioni)
                extra.append(f"Canale per i membri: <#{avviso}>.")
        if opzioni["ingressi"]:
            extra.append(f"Chi entra viene {'espulso' if opzioni['ingressi'] == 'kick' else 'bannato'} finché dura il blocco.")
        await lockdown_repo.imposta_stato(guild.id, STATO_ATTIVO)
        testo = testo_riepilogo(
            tipo=tipo, bloccati=bloccati, saltati=saltati, falliti=falliti,
            verifica=verifica, inviti=inviti, finisce_il=finisce,
        )
        if canali is not None:
            testo = testo.replace("Ingressi: livello di verifica invariato.", "Ingressi: invariati.")
        testo = "\n".join([testo, *extra])[:1900]
    await _annuncia(guild, testo, config.ruoli_avviso, riepilogo_in, titolo_ping=tipo == TIPO_PANICO)
    return Esito(True, testo, bloccati=bloccati, saltati=saltati, falliti=falliti)


async def togli(
    guild: discord.Guild, *, riepilogo_in: discord.abc.Messageable | None = None, ritenta: bool = False
) -> Esito:
    """
    Riapre tutto com'era. Si puo' richiamare finche' restano canali da riaprire.
    Con `ritenta` (sblocco automatico che riprova ogni minuto) l'annuncio nel canale
    degli allarmi arriva solo a riapertura riuscita: il fallimento era gia' stato annunciato.
    """
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
                era_vuoto = overwrite.is_empty()  # niente da togliere: cancellarlo darebbe 404 e il blocco non si chiuderebbe mai
                nuovo = ripristina(overwrite, riga.prima)
                try:
                    if nuovo is None and era_vuoto:
                        pass
                    elif (nuovo.pair() if nuovo is not None else None) != prima_coppia:
                        await canale.set_permissions(everyone, overwrite=nuovo, reason=razon)
                except discord.HTTPException as errore:
                    logger.warning("Canale %s non riaperto (server %s): %s", riga.channel_id, guild.id, errore)
                    return "fallito"
                await lockdown_repo.segna_ripristinato(guild.id, riga.channel_id)
                return "riaperto"

            esiti = await _in_gruppi(righe, _riapri)
            server_ok = await _riapri_ingressi(guild, stato, razon)
            ruoli_ok = await _rimetti_permessi_ai_ruoli(guild, razon)
            await _togli_canale_avviso(guild, stato, razon)
            server_ok = server_ok and ruoli_ok
            falliti = esiti.count("fallito")
            if falliti == 0 and server_ok:
                await lockdown_repo.elimina_blocco(guild.id)
                _panico.pop(guild.id, None)
                _ingressi.pop(guild.id, None)
            testo = (
                f"Blocco tolto: {esiti.count('riaperto')} canali riaperti."
                if falliti == 0 and server_ok
                else f"Riaperti {esiti.count('riaperto')} canali; {falliti} canali"
                f"{'' if server_ok else ' e le impostazioni del server'} non sono riuscito a riaprirli. "
                "Rilancia «togli» dopo aver controllato i miei permessi."
            )
    finally:
        _da_fermare.discard(guild.id)
    riuscito = falliti == 0 and server_ok
    if riuscito or not ritenta:
        await _annuncia(guild, testo, (), riepilogo_in, titolo_ping=False)
    return Esito(riuscito, testo, bloccati=esiti.count("riaperto"), falliti=falliti)


async def _togli_permessi_ai_ruoli(guild: discord.Guild, motivo: str) -> int:
    """
    MOD-096: toglie i permessi critici a ogni ruolo SOTTO il bot (mai @everyone, mai ruoli gestiti, mai ruoli pari
    o sopra il bot). Salva i bit tolti PRIMA di toccare il ruolo. Restituisce quanti ruoli sono stati toccati.
    """
    toccati = 0
    sotto = [r for r in guild.roles if not r.is_default() and not r.managed and r < guild.me.top_role]
    for inizio in range(0, len(sotto), GRANDEZZA_GRUPPO):
        for ruolo in sotto[inizio : inizio + GRANDEZZA_GRUPPO]:
            bit = permessi_pericolosi_da_togliere(ruolo.permissions, CRITICAL_PERMISSIONS)
            if not bit:
                continue
            await lockdown_repo.salva_ruolo(guild.id, ruolo.id, bit)
            try:
                await ruolo.edit(permissions=discord.Permissions(ruolo.permissions.value & ~bit), reason=motivo)
                toccati += 1
            except discord.HTTPException as errore:
                logger.warning("Ruolo %s non limitato (server %s): %s", ruolo.id, guild.id, errore)
        await asyncio.sleep(PAUSA_TRA_GRUPPI)
    return toccati


async def _rimetti_permessi_ai_ruoli(guild: discord.Guild, motivo: str) -> bool:
    """Rimette SOLO i bit tolti dal blocco: una scelta fatta a mano nel frattempo resta. False se un ruolo non si riapre."""
    ok = True
    for role_id, tolti in await lockdown_repo.ruoli_da_ripristinare(guild.id):
        ruolo = guild.get_role(role_id)
        if ruolo is None or ruolo >= guild.me.top_role:
            await lockdown_repo.segna_ruolo_ripristinato(guild.id, role_id)  # sparito o ora fuori portata: niente da fare
            continue
        try:
            await ruolo.edit(permissions=discord.Permissions(ruolo.permissions.value | tolti), reason=motivo)
        except discord.HTTPException as errore:
            logger.warning("Ruolo %s non rimesso (server %s): %s", role_id, guild.id, errore)
            ok = False
            continue
        await lockdown_repo.segna_ruolo_ripristinato(guild.id, role_id)
    return ok


async def _crea_canale_avviso(guild: discord.Guild, motivo: str, razon: str) -> int | None:
    """MOD-094: un canale che i membri vedono (solo lettura) per dire che il server è bloccato. None se non riesce."""
    try:
        canale = await guild.create_text_channel(
            NOME_CANALE_AVVISO,
            overwrites={
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=True, read_message_history=True, send_messages=False, add_reactions=False
                ),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            },
            topic="Il server è bloccato dallo staff."[:1024], reason=razon,
        )
        await canale.send(
            **await traducibile(guild, content=f"Il server è bloccato dallo staff. Motivo: {motivo}"[:2000], allowed_mentions=discord.AllowedMentions.none())
        )
    except discord.HTTPException as errore:
        logger.warning("Canale di avviso non creato (server %s): %s", guild.id, errore)
        return None
    return canale.id


async def _togli_canale_avviso(guild: discord.Guild, stato, razon: str) -> None:
    canale_id = stato.opzioni.get("avviso")
    canale = guild.get_channel(canale_id) if canale_id else None
    if canale is None or canale.name != NOME_CANALE_AVVISO:  # solo il canale che abbiamo creato noi
        return
    try:
        await canale.delete(reason=razon)
    except discord.HTTPException as errore:
        logger.warning("Canale di avviso non tolto (server %s): %s", guild.id, errore)


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
    await router.invia_a(
        dest, guild, router.TIPO_ALLARMI, **await traducibile(guild, content=(ping + testo)[:2000], allowed_mentions=menzioni)
    )


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
