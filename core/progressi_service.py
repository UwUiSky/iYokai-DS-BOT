"""
core/progressi_service.py
=========================
Missioni (giorno, settimana, server), serie con protezione e promemoria, traguardi e pass di 90 giorni
(D49, D51). I server li accendono con `/admin-livelli progressi`; spenti, i punti di aggancio del
livellamento non fanno nulla. Gli eventi (con gli XP) si contano in memoria e si scrivono ogni 20
secondi (e a mezzanotte UTC, nel loro giorno). Ogni premio esce da una scrittura atomica, una volta sola.
Funzioni coperte: SPEC §23.17 (D49, D51)
Dipende da: core/repositories/progressi_repo.py, core/progressi_logic.py
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone

import discord

from core.bot_ready import attendi_bot_pronto
from core.progressi_logic import (
    EVENTI,
    EVENTO_DAILY,
    MISSIONI_GIORNO,
    MISSIONI_SERVER,
    MISSIONI_SETTIMANA,
    OBIETTIVO_SERVER_BASE,
    OBIETTIVO_SERVER_MAX,
    OBIETTIVO_SERVER_MIN,
    SCUDO_PREZZO,
    Statistiche,
    giorno_del_periodo,
    lunedi_di,
    minimo_partecipazione,
    missioni_dell_evento,
    obiettivo_server,
    serve_promemoria,
    stagione_di,
    testo_promemoria,
    traguardi_raggiunti,
)
from core.repositories.progressi_repo import EsitoPass, ProgressiRepository

logger = logging.getLogger("iyokai.progressi")

SETTING_ATTIVO = "progressi_attivi"
SETTING_OBIETTIVO_SERVER = "progressi_obiettivo_server"
PAUSA_SCRITTURA_SECONDI = 20.0
CONTROLLI_PROMEMORIA_OGNI = 90  # giri di scrittura: 90 x 20 s = ogni 30 minuti
MAX_PENDENTI = 20_000  # voci diverse in attesa: oltre, gli eventi nuovi si perdono (tetto della memoria)


def _pool():
    from core.database import db

    return db.pool


progressi_repo = ProgressiRepository(pool_provider=_pool)

_pendenti: dict[tuple[int, int, str], list[int]] = {}  # (server, utente, evento) -> [quantità, XP]
_giorno_pendenti: date | None = None  # il giorno (UTC) degli eventi in attesa
_lavoratore: asyncio.Task | None = None
_bot = None


def _adesso() -> datetime:
    return datetime.now(timezone.utc)


def _oggi() -> date:
    return _adesso().date()


async def attivo(guild_id: int) -> bool:
    """L'impostazione del server (spenta di base). La legge dalla cache delle impostazioni."""
    from core.database import db

    return (await db.get_guild_setting(guild_id, SETTING_ATTIVO)) is True


async def imposta_attivo(guild_id: int, acceso: bool, da: int | None = None) -> None:
    """Punto unico (D16): lo usano il comando e, in futuro, il pannello."""
    from core.database import db

    await db.set_guild_setting(guild_id, SETTING_ATTIVO, acceso, changed_by=da)


async def obiettivo_server_base(guild_id: int) -> int:
    from core.database import db

    valore = await db.get_guild_setting(guild_id, SETTING_OBIETTIVO_SERVER)
    if isinstance(valore, int) and not isinstance(valore, bool) and valore > 0:
        return max(OBIETTIVO_SERVER_MIN, min(OBIETTIVO_SERVER_MAX, valore))
    return OBIETTIVO_SERVER_BASE


async def imposta_obiettivo_server(guild_id: int, messaggi: int, da: int | None = None) -> None:
    """Punto unico (D16): quanti messaggi deve scrivere il server in una settimana (le altre missioni ne seguono)."""
    from core.database import db

    if not OBIETTIVO_SERVER_MIN <= messaggi <= OBIETTIVO_SERVER_MAX:
        raise ValueError(f"L'obiettivo va da {OBIETTIVO_SERVER_MIN} a {OBIETTIVO_SERVER_MAX}.")
    await db.set_guild_setting(guild_id, SETTING_OBIETTIVO_SERVER, messaggi, changed_by=da)


# ---------------------------------------------------------------- conteggio degli eventi
async def registra(guild_id: int, user_id: int, evento: str, quantita: int = 1, xp: int = 0) -> None:
    """Un evento di livellamento (messaggio con XP, minuto in vocale). Non solleva mai."""
    await registra_molti(guild_id, [user_id], evento, quantita, xp)


async def registra_molti(guild_id: int, user_ids: list[int], evento: str, quantita: int = 1, xp: int = 0) -> None:
    global _giorno_pendenti
    if not user_ids or evento not in EVENTI:
        return
    try:
        if not await attivo(guild_id):
            return
        oggi = _oggi()
        if _pendenti and _giorno_pendenti != oggi:
            await svuota()  # mezzanotte: gli eventi di ieri restano di ieri
        _giorno_pendenti = oggi
        for user_id in user_ids:
            chiave = (guild_id, user_id, evento)
            if chiave not in _pendenti and len(_pendenti) >= MAX_PENDENTI:
                continue
            voce = _pendenti.setdefault(chiave, [0, 0])
            voce[0] += quantita
            voce[1] += xp
    except Exception:
        logger.warning("Progressi: evento non contato (server %s)", guild_id, exc_info=True)


async def svuota(guild_id: int | None = None, user_id: int | None = None) -> None:
    """Scrive gli eventi in attesa (tutti, o solo quelli di un utente: prima di un riscatto)."""
    scelti = [
        (chiave, tuple(voce)) for chiave, voce in list(_pendenti.items())
        if (guild_id is None or chiave[0] == guild_id) and (user_id is None or chiave[1] == user_id)
    ]
    if not scelti:
        return
    giorno = _giorno_pendenti or _oggi()
    for chiave, _ in scelti:
        _pendenti.pop(chiave, None)
    righe = [
        (g, u, giorno_del_periodo(m, giorno), m.chiave, n, m.obiettivo)
        for (g, u, evento), (n, _) in scelti
        for m in missioni_dell_evento(evento)
    ]
    stagione = stagione_di(giorno)[0]
    righe_xp = [(g, u, stagione, xp) for (g, u, _), (_, xp) in scelti if xp > 0]
    try:
        await progressi_repo.aggiungi_progressi(righe)
        await progressi_repo.aggiungi_xp_pass(righe_xp)
    except Exception:
        logger.warning("Progressi: scrittura non riuscita, eventi persi", exc_info=True)


def avvia(bot) -> None:
    global _bot, _lavoratore
    if _lavoratore is not None:
        _lavoratore.cancel()
    _bot = bot
    _lavoratore = asyncio.create_task(_lavora())


async def ferma() -> None:
    global _bot, _lavoratore
    if _lavoratore is not None:
        _lavoratore.cancel()
        try:
            await _lavoratore
        except asyncio.CancelledError:
            pass
        await svuota()
    _bot, _lavoratore = None, None


async def _lavora() -> None:
    await attendi_bot_pronto(_bot)
    giri = 0
    while True:
        await asyncio.sleep(PAUSA_SCRITTURA_SECONDI)
        await svuota()
        giri += 1
        if giri % CONTROLLI_PROMEMORIA_OGNI == 0:
            try:
                await manda_promemoria(_bot)
            except Exception:
                logger.warning("Progressi: promemoria della serie non inviati", exc_info=True)


# ---------------------------------------------------------------- serie e traguardi
async def dopo_riscossione(guild_id: int, user_id: int, colonna: str) -> None:
    """Dopo `/monete daily` o `/monete work` riuscito. Solo il giornaliero conta (serie, premi estetici, missione)."""
    if colonna != "last_daily_at":
        return
    try:
        if not await attivo(guild_id):
            return
        esito = await progressi_repo.registra_riscossione(guild_id, user_id, _adesso())
        if esito.contata:
            await progressi_repo.regala_premi_serie(guild_id, user_id, esito.serie)
        await registra(guild_id, user_id, EVENTO_DAILY)
        await valuta_traguardi(guild_id, user_id)
    except Exception:
        logger.warning("Progressi: riscossione non registrata (server %s)", guild_id, exc_info=True)


async def compra_scudo(guild_id: int, user_id: int) -> str:
    """«ok», «pieno» o «saldo»: la protezione della serie costa SCUDO_PREZZO monete."""
    return await progressi_repo.compra_scudo(guild_id, user_id, SCUDO_PREZZO)


async def imposta_promemoria(guild_id: int, user_id: int, acceso: bool) -> None:
    await progressi_repo.imposta_promemoria(guild_id, user_id, acceso)


async def manda_promemoria(bot) -> int:
    """Un messaggio privato a chi l'ha chiesto, 20 ore dopo l'ultima riscossione. Una volta per riscossione."""
    mandati = 0
    adesso = _adesso()
    for guild_id, user_id, serie, ultima, scudi in await progressi_repo.da_avvisare():
        await progressi_repo.segna_avvisato(guild_id, user_id)  # anche se il messaggio non parte: niente riprove
        if not serve_promemoria(serie, ultima, scudi, adesso) or not await attivo(guild_id):
            continue
        utente = bot.get_user(user_id)
        if utente is None:
            try:
                utente = await bot.fetch_user(user_id)
            except discord.HTTPException:
                continue
        guild = bot.get_guild(guild_id)
        try:
            await utente.send(testo_promemoria(serie, ultima, scudi, adesso, guild.name if guild else "un server"))
            mandati += 1
        except discord.HTTPException:
            continue  # messaggi privati chiusi
    return mandati


async def statistiche(guild_id: int, user_id: int, livello: int | None = None) -> Statistiche:
    if livello is None:
        from core.repositories.leveling_repo import leveling_repo

        livello = (await leveling_repo.get_totals(guild_id, user_id)).level
    _, record, _, _, _ = await progressi_repo.serie_di(guild_id, user_id)
    return Statistiche(
        livello=livello,
        record_serie=record,
        missioni_completate=await progressi_repo.missioni_completate(guild_id, user_id),
        stagioni_complete=await progressi_repo.stagioni_complete(guild_id, user_id),
        scudi_usati=await progressi_repo.scudi_usati(guild_id, user_id),
        missioni_settimana=await progressi_repo.missioni_settimana_riscattate(guild_id, user_id),
        missioni_server=await progressi_repo.missioni_server_riscattate(guild_id, user_id),
        pass_premium=int(await progressi_repo.ha_aperto_premium(guild_id, user_id)),
    )


async def valuta_traguardi(guild_id: int, user_id: int) -> list[str]:
    """Salva i traguardi nuovi e li restituisce (chiavi)."""
    raggiunti = traguardi_raggiunti(await statistiche(guild_id, user_id))
    return await progressi_repo.segna_traguardi(guild_id, user_id, sorted(raggiunti))


# ---------------------------------------------------------------- riscatti
@dataclass(frozen=True)
class EsitoRiscatto:
    monete: int
    quanti: int
    traguardi_nuovi: tuple[str, ...] = ()


async def riscatta_missioni(guild_id: int, user_id: int) -> EsitoRiscatto:
    """Missioni del giorno, della settimana e del server già finite e non riscosse: ogni premio una sola volta."""
    await svuota(guild_id, user_id)
    oggi = _oggi()
    monete = quanti = 0
    for gruppo, giorno in ((MISSIONI_GIORNO, oggi), (MISSIONI_SETTIMANA, lunedi_di(oggi))):
        m, q = await progressi_repo.riscatta_missioni(
            guild_id, user_id, giorno, [(x.chiave, x.obiettivo, x.premio) for x in gruppo]
        )
        monete, quanti = monete + m, quanti + q
    base = await obiettivo_server_base(guild_id)
    for ms in MISSIONI_SERVER:
        m = await progressi_repo.riscatta_server(
            guild_id, user_id, lunedi_di(oggi), ms.chiave, ms.personale,
            obiettivo_server(ms, base), minimo_partecipazione(ms), ms.premio,
        )
        if m:
            monete, quanti = monete + m, quanti + 1
    nuovi = await valuta_traguardi(guild_id, user_id) if quanti else []
    return EsitoRiscatto(monete, quanti, tuple(nuovi))


async def riscatta_pass(guild_id: int, user_id: int) -> tuple[EsitoPass, tuple[str, ...]]:
    """I livelli del pass raggiunti e non riscossi (e gli oggetti estetici). Restituisce anche i traguardi nuovi."""
    esito = await progressi_repo.riscatta_pass(guild_id, user_id, stagione_di(_oggi())[0])
    nuovi = await valuta_traguardi(guild_id, user_id) if not esito.vuoto else []
    return esito, tuple(nuovi)


async def sblocca_premium(guild_id: int, user_id: int, booster: bool) -> tuple[str, tuple[str, ...]]:
    """Apre la traccia premium: gratis per chi ha il boost del server, altrimenti a pagamento. «ok», «gia», «saldo»."""
    esito = await progressi_repo.sblocca_premium(guild_id, user_id, stagione_di(_oggi())[0], pagando=not booster)
    nuovi = await valuta_traguardi(guild_id, user_id) if esito == "ok" else []
    return esito, tuple(nuovi)
