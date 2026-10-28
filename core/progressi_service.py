"""
core/progressi_service.py
=========================
Missioni, serie, traguardi e stagione (D49). I server li accendono con
`/economia progressi`; spenti, i punti di aggancio del livellamento non fanno nulla.
Gli eventi si contano in memoria e si scrivono ogni 20 secondi. Le ricompense in monete
passano da `leveling_repo.add_coins`, dopo una scrittura atomica che le dà una volta sola.
Funzioni coperte: SPEC §23.17 (D49)
Dipende da: core/repositories/progressi_repo.py, core/progressi_logic.py
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone

from core.bot_ready import attendi_bot_pronto
from core.leveling_logic import period_key
from core.progressi_logic import (
    EVENTO_DAILY,
    MISSIONE_PER_CHIAVE,
    MISSIONI,
    STAGIONE_GRADINI,
    Statistiche,
    bonus_serie,
    gradini_raggiunti,
    premio_gradini,
    traguardi_raggiunti,
)
from core.repositories.progressi_repo import ProgressiRepository

logger = logging.getLogger("iyokai.progressi")

SETTING_ATTIVO = "progressi_attivi"
PAUSA_SCRITTURA_SECONDI = 20.0
MAX_PENDENTI = 20_000  # voci diverse in attesa: oltre, gli eventi nuovi si perdono (tetto della memoria)


def _pool():
    from core.database import db

    return db.pool


progressi_repo = ProgressiRepository(pool_provider=_pool)

_pendenti: dict[tuple[int, int, str], int] = {}
_lavoratore: asyncio.Task | None = None
_bot = None


def _oggi() -> date:
    return datetime.now(timezone.utc).date()


async def attivo(guild_id: int) -> bool:
    """L'impostazione del server (spenta di base). La legge dalla cache delle impostazioni."""
    from core.database import db

    return (await db.get_guild_setting(guild_id, SETTING_ATTIVO)) is True


async def imposta_attivo(guild_id: int, acceso: bool, da: int | None = None) -> None:
    """Punto unico (D16): lo usano il comando e, in futuro, il pannello."""
    from core.database import db

    await db.set_guild_setting(guild_id, SETTING_ATTIVO, acceso, changed_by=da)


# ---------------------------------------------------------------- conteggio degli eventi
async def registra(guild_id: int, user_id: int, evento: str, quantita: int = 1) -> None:
    """Un evento di livellamento (messaggio con XP, minuto in vocale). Non solleva mai."""
    await registra_molti(guild_id, [user_id], evento, quantita)


async def registra_molti(guild_id: int, user_ids: list[int], evento: str, quantita: int = 1) -> None:
    if not user_ids or evento not in MISSIONE_PER_CHIAVE:
        return
    try:
        if not await attivo(guild_id):
            return
        for user_id in user_ids:
            chiave = (guild_id, user_id, evento)
            if chiave not in _pendenti and len(_pendenti) >= MAX_PENDENTI:
                continue
            _pendenti[chiave] = _pendenti.get(chiave, 0) + quantita
    except Exception:
        logger.warning("Progressi: evento non contato (server %s)", guild_id, exc_info=True)


async def svuota(guild_id: int | None = None, user_id: int | None = None) -> None:
    """Scrive gli eventi in attesa (tutti, o solo quelli di un utente: prima di un riscatto)."""
    scelti = [
        (chiave, n) for chiave, n in list(_pendenti.items())
        if (guild_id is None or chiave[0] == guild_id) and (user_id is None or chiave[1] == user_id)
    ]
    if not scelti:
        return
    giorno = _oggi()
    for chiave, _ in scelti:
        _pendenti.pop(chiave, None)
    righe = [
        (g, u, giorno, evento, n, MISSIONE_PER_CHIAVE[evento].obiettivo)
        for (g, u, evento), n in scelti
    ]
    try:
        await progressi_repo.aggiungi_progressi(righe)
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
    while True:
        await asyncio.sleep(PAUSA_SCRITTURA_SECONDI)
        await svuota()


# ---------------------------------------------------------------- serie e traguardi
async def dopo_riscossione(guild_id: int, user_id: int, colonna: str) -> None:
    """Dopo `/level daily` o `/level work` riuscito. Solo il giornaliero conta (serie, bonus, missione)."""
    if colonna != "last_daily_at":
        return
    try:
        if not await attivo(guild_id):
            return
        serie, _, nuovo_giorno = await progressi_repo.registra_riscossione(guild_id, user_id, _oggi())
        if nuovo_giorno:
            bonus = bonus_serie(serie)
            if bonus:
                from core.repositories.leveling_repo import leveling_repo

                await leveling_repo.add_coins(guild_id, user_id, bonus)
        await registra(guild_id, user_id, EVENTO_DAILY)
        await valuta_traguardi(guild_id, user_id)
    except Exception:
        logger.warning("Progressi: riscossione non registrata (server %s)", guild_id, exc_info=True)


async def statistiche(guild_id: int, user_id: int, livello: int | None = None) -> Statistiche:
    if livello is None:
        from core.repositories.leveling_repo import leveling_repo

        livello = (await leveling_repo.get_totals(guild_id, user_id)).level
    _, record, _ = await progressi_repo.serie_di(guild_id, user_id)
    return Statistiche(
        livello=livello,
        record_serie=record,
        missioni_completate=await progressi_repo.missioni_completate(guild_id, user_id),
        stagioni_complete=await progressi_repo.stagioni_complete(guild_id, user_id),
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
    """Le missioni di oggi finite e non ancora riscosse: ogni premio una sola volta."""
    await svuota(guild_id, user_id)
    monete, quanti = await progressi_repo.riscatta_missioni(
        guild_id, user_id, _oggi(), [(m.chiave, m.obiettivo, m.premio) for m in MISSIONI]
    )
    nuovi = await valuta_traguardi(guild_id, user_id) if quanti else []
    return EsitoRiscatto(monete, quanti, tuple(nuovi))


async def riscatta_stagione(guild_id: int, user_id: int) -> EsitoRiscatto:
    """I gradini della stagione del mese raggiunti e non ancora riscossi."""
    mese = period_key()
    raggiunti = gradini_raggiunti(await progressi_repo.xp_del_mese(guild_id, user_id, mese))
    esito = await progressi_repo.riscatta_gradini(guild_id, user_id, mese, raggiunti, premio_gradini)
    if esito is None:
        return EsitoRiscatto(0, 0)
    nuovi = await valuta_traguardi(guild_id, user_id) if raggiunti >= STAGIONE_GRADINI else []
    return EsitoRiscatto(esito[1], esito[0], tuple(nuovi))
