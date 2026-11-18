"""
core/repositories/rischio_repo.py
=================================
Banca, guadagni con pausa, colpo e furto. Ogni azione è una transazione sola: la pausa si prende con
una scrittura condizionata, le righe dei saldi si bloccano (in ordine di ID quando sono due) e i
movimenti di monete sono UPDATE con il controllo dentro. Le multe vanno alla cassa del server o alla vittima:
nessuna moneta nasce o sparisce per un doppio clic.
Funzioni coperte: ECO-004, ECO-029, ECO-030, ECO-031, ECO-032, ECO-040, ECO-041
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import asyncpg

from core.repositories.guild_chest_repo import REASON_RISCHIO_MULTA, deposit_in
from core.repositories.leveling_repo import add_coins_in
from core.rischio_logic import SALDO_MINIMO_FURTO, PROTEZIONE_VITTIMA, importo_furto, multa_furto

_PAUSA = (
    "INSERT INTO economia_pause (guild_id, user_id, chiave, ultima_at) VALUES ($1, $2, $3, now()) "
    "ON CONFLICT (guild_id, user_id, chiave) DO UPDATE SET ultima_at = now() "
    "WHERE economia_pause.ultima_at <= now() - make_interval(secs => $4) RETURNING 1"
)
_RIGA = "INSERT INTO leveling_totals (guild_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING"


class EsitoFurto(str, Enum):
    PAUSA = "pausa"
    POCHI_CONTANTI = "pochi_contanti"
    PROTETTO = "protetto"
    RIUSCITO = "riuscito"
    FALLITO = "fallito"


@dataclass(frozen=True)
class Furto:
    esito: EsitoFurto
    importo: int = 0


@dataclass(frozen=True)
class Banca:
    contanti: int
    banca: int


class RischioRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ---------------------------------------------------------------- banca (ECO-004)
    async def banca(self, guild_id: int, user_id: int) -> Banca:
        riga = await self._pool.fetchrow(
            "SELECT coins_total, banca_total FROM leveling_totals WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        )
        return Banca(riga["coins_total"], riga["banca_total"]) if riga else Banca(0, 0)

    async def deposita(self, guild_id: int, user_id: int, importo: int) -> Banca | None:
        """Contanti -> banca in una UPDATE sola, solo se i contanti bastano."""
        if importo <= 0:
            raise ValueError("L'importo deve essere positivo.")
        riga = await self._pool.fetchrow(
            "UPDATE leveling_totals SET coins_total = coins_total - $3, banca_total = banca_total + $3 "
            "WHERE guild_id = $1 AND user_id = $2 AND coins_total >= $3 RETURNING coins_total, banca_total",
            guild_id, user_id, importo,
        )
        return Banca(riga["coins_total"], riga["banca_total"]) if riga else None

    async def preleva(self, guild_id: int, user_id: int, importo: int) -> Banca | None:
        """Banca -> contanti in una UPDATE sola. Rifiutato se la banca non basta o se sfora il tetto al saldo."""
        if importo <= 0:
            raise ValueError("L'importo deve essere positivo.")
        riga = await self._pool.fetchrow(
            "UPDATE leveling_totals SET coins_total = coins_total + $3, banca_total = banca_total - $3 "
            "WHERE guild_id = $1 AND user_id = $2 AND banca_total >= $3 AND ("
            "(SELECT NULLIF(tetto_saldo, 0) FROM leveling_settings WHERE guild_id = $1) IS NULL OR "
            "coins_total + $3 <= (SELECT NULLIF(tetto_saldo, 0) FROM leveling_settings WHERE guild_id = $1)) "
            "RETURNING coins_total, banca_total",
            guild_id, user_id, importo,
        )
        return Banca(riga["coins_total"], riga["banca_total"]) if riga else None

    # ---------------------------------------------------------------- guadagni con pausa
    async def guadagna(self, guild_id: int, user_id: int, chiave: str, pausa_s: int, importo: int) -> int | None:
        """
        Prende la pausa e accredita `importo` (anche 0: «oggi niente») nella stessa transazione.
        Restituisce il saldo, o None se la pausa non è finita.
        """
        if importo < 0 or pausa_s <= 0:
            raise ValueError("Importo o pausa non validi.")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                if await conn.fetchval(_PAUSA, guild_id, user_id, chiave, float(pausa_s)) is None:
                    return None
                if importo == 0:
                    await conn.execute(_RIGA, guild_id, user_id)
                    return await conn.fetchval(
                        "SELECT coins_total FROM leveling_totals WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
                    )
                return await add_coins_in(conn, guild_id, user_id, importo)

    async def pausa_rimasta(self, guild_id: int, user_id: int, chiave: str, pausa_s: int) -> int:
        resto = await self._pool.fetchval(
            "SELECT CEIL(EXTRACT(EPOCH FROM ultima_at + make_interval(secs => $4) - now())) FROM economia_pause "
            "WHERE guild_id = $1 AND user_id = $2 AND chiave = $3", guild_id, user_id, chiave, float(pausa_s),
        )
        return max(0, int(resto or 0))

    # ---------------------------------------------------------------- colpo (ECO-030/032)
    async def colpo(
        self, guild_id: int, user_id: int, chiave: str, pausa_s: int, riuscito: bool, importo: int
    ) -> tuple[int, int] | None:
        """
        Esito di un colpo. Riuscito: +importo. Fallito: multa fino ai contanti (mai sotto zero), versata alla
        cassa del server. Restituisce (variazione col segno, saldo) o None se la pausa non è finita.
        """
        if importo <= 0 or pausa_s <= 0:
            raise ValueError("Importo o pausa non validi.")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(_RIGA, guild_id, user_id)
                await conn.fetchval(
                    "SELECT coins_total FROM leveling_totals WHERE guild_id = $1 AND user_id = $2 FOR UPDATE", guild_id, user_id
                )
                if await conn.fetchval(_PAUSA, guild_id, user_id, chiave, float(pausa_s)) is None:
                    return None
                if riuscito:
                    return importo, await add_coins_in(conn, guild_id, user_id, importo)
                multa = await conn.fetchval(
                    "WITH v AS (SELECT coins_total AS prima FROM leveling_totals WHERE guild_id = $1 AND user_id = $2), "
                    "u AS (UPDATE leveling_totals SET coins_total = coins_total - LEAST(coins_total, $3) "
                    "WHERE guild_id = $1 AND user_id = $2 RETURNING coins_total) "
                    "SELECT (SELECT prima FROM v) - (SELECT coins_total FROM u)",
                    guild_id, user_id, importo,
                )
                if multa > 0:
                    await deposit_in(conn, guild_id, multa, REASON_RISCHIO_MULTA)
                saldo = await conn.fetchval(
                    "SELECT coins_total FROM leveling_totals WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
                )
                return -multa, saldo

    # ---------------------------------------------------------------- furto (ECO-031)
    async def furto(
        self, guild_id: int, ladro: int, vittima: int, riuscito: bool, percentuale: int, pausa_s: int
    ) -> Furto:
        """
        Un furto sui soli contanti. Le due righe si bloccano in ordine di ID; la pausa del ladro e la
        protezione della vittima si prendono con scritture condizionate; tutto o niente.
        Riuscito: la quota va al ladro. Fallito: il ladro paga una multa alla vittima.
        """
        if ladro == vittima:
            raise ValueError("Non ci si deruba da soli.")
        try:
            return await self._furto(guild_id, ladro, vittima, riuscito, percentuale, pausa_s)
        except _Protetto:  # la transazione è annullata: anche la pausa del ladro non resta scritta
            return Furto(EsitoFurto.PROTETTO)

    async def _furto(
        self, guild_id: int, ladro: int, vittima: int, riuscito: bool, percentuale: int, pausa_s: int
    ) -> Furto:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for u in sorted((ladro, vittima)):
                    await conn.execute(_RIGA, guild_id, u)
                righe = await conn.fetch(
                    "SELECT user_id, coins_total FROM leveling_totals WHERE guild_id = $1 AND user_id = ANY($2::bigint[]) "
                    "ORDER BY user_id FOR UPDATE",
                    guild_id, [ladro, vittima],
                )
                cash = {r["user_id"]: r["coins_total"] for r in righe}
                quota = importo_furto(cash[vittima], percentuale)
                if quota <= 0 or cash[ladro] < SALDO_MINIMO_FURTO:
                    return Furto(EsitoFurto.POCHI_CONTANTI)
                if await conn.fetchval(_PAUSA, guild_id, ladro, "furto", float(pausa_s)) is None:
                    return Furto(EsitoFurto.PAUSA)
                if await conn.fetchval(_PAUSA, guild_id, vittima, "derubato", float(PROTEZIONE_VITTIMA)) is None:
                    raise _Protetto()
                if riuscito:
                    await conn.execute(
                        "UPDATE leveling_totals SET coins_total = coins_total - $3 WHERE guild_id = $1 AND user_id = $2",
                        guild_id, vittima, quota,
                    )
                    await add_coins_in(conn, guild_id, ladro, quota, classifica=False)
                    return Furto(EsitoFurto.RIUSCITO, quota)
                multa = multa_furto(quota, cash[ladro])
                if multa > 0:
                    await conn.execute(
                        "UPDATE leveling_totals SET coins_total = coins_total - $3 WHERE guild_id = $1 AND user_id = $2",
                        guild_id, ladro, multa,
                    )
                    await add_coins_in(conn, guild_id, vittima, multa, classifica=False)
                return Furto(EsitoFurto.FALLITO, multa)

    # ---------------------------------------------------------------- lavori (ECO-029)
    async def turni(self, guild_id: int, user_id: int) -> int:
        return int(
            await self._pool.fetchval(
                "SELECT turni FROM economia_lavoro WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
            )
            or 0
        )

    async def segna_turno(self, guild_id: int, user_id: int) -> int:
        return await self._pool.fetchval(
            "INSERT INTO economia_lavoro (guild_id, user_id, turni) VALUES ($1, $2, 1) "
            "ON CONFLICT (guild_id, user_id) DO UPDATE SET turni = economia_lavoro.turni + 1 RETURNING turni",
            guild_id, user_id,
        )

    async def dimettiti(self, guild_id: int, user_id: int) -> int:
        """Si ricomincia da stagista. Restituisce i turni persi."""
        return int(
            await self._pool.fetchval(
                "WITH v AS (SELECT turni FROM economia_lavoro WHERE guild_id = $1 AND user_id = $2 FOR UPDATE), "
                "u AS (DELETE FROM economia_lavoro WHERE guild_id = $1 AND user_id = $2) SELECT COALESCE((SELECT turni FROM v), 0)",
                guild_id, user_id,
            )
            or 0
        )


class _Protetto(Exception):
    pass


def _get_pool():
    from core.database import db

    return db.pool


_repo = RischioRepository(pool_provider=_get_pool)
rischio_repo = _repo
