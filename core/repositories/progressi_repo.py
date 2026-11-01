"""
core/repositories/progressi_repo.py
===================================
Tabelle progress_missioni, progress_serie, progress_traguardi, progress_stagione e
progress_server_riscatti. Ogni premio esce con una scrittura atomica che lo dà una volta sola.
Funzioni coperte: SPEC §23.17 (D49, D51)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import asyncpg

from core.progressi_logic import (
    PASS_LIVELLI,
    PASS_PREZZO_PREMIUM,
    SCUDI_MAX,
    EsitoSerie,
    aggiorna_serie,
    livelli_raggiunti,
    monete_livelli,
    oggetti_livelli,
    premi_serie_raggiunti,
)
from core.repositories.leveling_repo import add_coins_in, spend_coins_in
from core.repositories.profile_repo import regala_oggetti_in


@dataclass(frozen=True)
class EsitoPass:
    monete: int = 0
    livelli_liberi: int = 0
    livelli_premium: int = 0
    oggetti: tuple[str, ...] = field(default_factory=tuple)

    @property
    def vuoto(self) -> bool:
        return self.livelli_liberi == 0 and self.livelli_premium == 0


class ProgressiRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ---- missioni ----
    async def aggiungi_progressi(self, righe: list[tuple[int, int, date, str, int, int]]) -> None:
        """(server, utente, giorno, chiave, quantità, obiettivo): il progresso si ferma all'obiettivo."""
        if not righe:
            return
        await self._pool.executemany(
            """
            INSERT INTO progress_missioni (guild_id, user_id, giorno, chiave, progresso)
            VALUES ($1, $2, $3, $4, LEAST($5::int, $6::int))
            ON CONFLICT (guild_id, user_id, giorno, chiave) DO UPDATE
                SET progresso = LEAST(progress_missioni.progresso + $5::int, $6::int)
            """,
            righe,
        )

    async def missioni_di(self, guild_id: int, user_id: int, giorno: date) -> dict[str, tuple[int, bool]]:
        righe = await self._pool.fetch(
            "SELECT chiave, progresso, riscattata FROM progress_missioni "
            "WHERE guild_id = $1 AND user_id = $2 AND giorno = $3",
            guild_id, user_id, giorno,
        )
        return {r["chiave"]: (r["progresso"], r["riscattata"]) for r in righe}

    async def riscatta_missioni(
        self, guild_id: int, user_id: int, giorno: date, missioni: list[tuple[str, int, int]]
    ) -> tuple[int, int]:
        """
        `missioni` = (chiave, obiettivo, premio). Segna come riscosse quelle finite e le paga, nella
        stessa transazione: un premio esce una sola volta. Restituisce (monete, quante).
        """
        monete = quanti = 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for chiave, obiettivo, premio in missioni:
                    riga = await conn.fetchrow(
                        """
                        UPDATE progress_missioni SET riscattata = TRUE
                        WHERE guild_id = $1 AND user_id = $2 AND giorno = $3 AND chiave = $4
                          AND NOT riscattata AND progresso >= $5
                        RETURNING 1
                        """,
                        guild_id, user_id, giorno, chiave, obiettivo,
                    )
                    if riga is not None:
                        monete += premio
                        quanti += 1
                if monete:
                    await add_coins_in(conn, guild_id, user_id, monete)
        return monete, quanti

    async def missioni_completate(self, guild_id: int, user_id: int) -> int:
        return await self._pool.fetchval(
            "SELECT count(*) FROM progress_missioni WHERE guild_id = $1 AND user_id = $2 AND riscattata",
            guild_id, user_id,
        )

    # ---- missioni di tutto il server ----
    async def totale_server(self, guild_id: int, settimana: date, chiave_personale: str, minimo: int) -> tuple[int, int]:
        """(totale della settimana, quanti hanno fatto almeno `minimo`). Ognuno conta fino alla sua missione personale."""
        riga = await self._pool.fetchrow(
            "SELECT COALESCE(sum(progresso), 0) AS totale, count(*) FILTER (WHERE progresso >= $4) AS quanti "
            "FROM progress_missioni WHERE guild_id = $1 AND giorno = $2 AND chiave = $3",
            guild_id, settimana, chiave_personale, minimo,
        )
        return int(riga["totale"]), int(riga["quanti"])

    async def server_riscattate(self, guild_id: int, user_id: int, settimana: date) -> set[str]:
        righe = await self._pool.fetch(
            "SELECT chiave FROM progress_server_riscatti WHERE guild_id = $1 AND user_id = $2 AND settimana = $3",
            guild_id, user_id, settimana,
        )
        return {r["chiave"] for r in righe}

    async def riscatta_server(
        self, guild_id: int, user_id: int, settimana: date, chiave: str, chiave_personale: str,
        obiettivo: int, minimo: int, premio: int,
    ) -> int:
        """Paga il premio se il server ha raggiunto l'obiettivo e chi chiede ha partecipato. Una volta sola."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                totale = await conn.fetchval(
                    "SELECT COALESCE(sum(progresso), 0) FROM progress_missioni "
                    "WHERE guild_id = $1 AND giorno = $2 AND chiave = $3",
                    guild_id, settimana, chiave_personale,
                )
                mio = await conn.fetchval(
                    "SELECT progresso FROM progress_missioni "
                    "WHERE guild_id = $1 AND user_id = $2 AND giorno = $3 AND chiave = $4",
                    guild_id, user_id, settimana, chiave_personale,
                )
                if totale < obiettivo or (mio or 0) < minimo:
                    return 0
                nuovo = await conn.fetchval(
                    "INSERT INTO progress_server_riscatti (guild_id, user_id, settimana, chiave) "
                    "VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING RETURNING 1",
                    guild_id, user_id, settimana, chiave,
                )
                if nuovo is None:
                    return 0
                await add_coins_in(conn, guild_id, user_id, premio)
        return premio

    async def missioni_server_riscattate(self, guild_id: int, user_id: int) -> int:
        return await self._pool.fetchval(
            "SELECT count(*) FROM progress_server_riscatti WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        )

    async def missioni_settimana_riscattate(self, guild_id: int, user_id: int) -> int:
        """Il massimo di missioni della settimana riscosse in una stessa settimana (per «settimana piena»)."""
        return await self._pool.fetchval(
            "SELECT COALESCE(max(n), 0) FROM (SELECT count(*) AS n FROM progress_missioni "
            "WHERE guild_id = $1 AND user_id = $2 AND riscattata AND chiave LIKE 'sett\\_%' GROUP BY giorno) s",
            guild_id, user_id,
        )

    # ---- serie ----
    async def registra_riscossione(self, guild_id: int, user_id: int, adesso: datetime) -> EsitoSerie:
        """Una riscossione giornaliera: serie, record e scudi si aggiornano nella stessa transazione."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO progress_serie (guild_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    guild_id, user_id,
                )
                riga = await conn.fetchrow(
                    "SELECT serie, record, ultima_at, scudi FROM progress_serie "
                    "WHERE guild_id = $1 AND user_id = $2 FOR UPDATE",
                    guild_id, user_id,
                )
                esito = aggiorna_serie(riga["serie"], riga["record"], riga["ultima_at"], riga["scudi"], adesso)
                if esito.contata:
                    await conn.execute(
                        "UPDATE progress_serie SET serie = $3, record = $4, scudi = $5, ultima_at = $6, "
                        "ultimo_giorno = $7, scudi_usati = scudi_usati + $8, promemoria_inviato_at = NULL "
                        "WHERE guild_id = $1 AND user_id = $2",
                        guild_id, user_id, esito.serie, esito.record, esito.scudi, adesso, adesso.date(),
                        esito.scudi_usati,
                    )
        return esito

    async def serie_di(self, guild_id: int, user_id: int) -> tuple[int, int, datetime | None, int, bool]:
        """(serie, record, ultima riscossione, scudi, promemoria chiesto)."""
        riga = await self._pool.fetchrow(
            "SELECT serie, record, ultima_at, scudi, promemoria FROM progress_serie "
            "WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id,
        )
        return (riga["serie"], riga["record"], riga["ultima_at"], riga["scudi"], riga["promemoria"]) if riga else (
            0, 0, None, 0, False
        )

    async def scudi_usati(self, guild_id: int, user_id: int) -> int:
        return int(await self._pool.fetchval(
            "SELECT scudi_usati FROM progress_serie WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        ) or 0)

    async def compra_scudo(self, guild_id: int, user_id: int, prezzo: int) -> str:
        """«ok», «pieno» (ne ha già il massimo) o «saldo» (monete insufficienti). Addebito e scudo insieme."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO progress_serie (guild_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    guild_id, user_id,
                )
                scudi = await conn.fetchval(
                    "SELECT scudi FROM progress_serie WHERE guild_id = $1 AND user_id = $2 FOR UPDATE",
                    guild_id, user_id,
                )
                if scudi >= SCUDI_MAX:
                    return "pieno"
                if not await spend_coins_in(conn, guild_id, user_id, prezzo):
                    return "saldo"
                await conn.execute(
                    "UPDATE progress_serie SET scudi = scudi + 1 WHERE guild_id = $1 AND user_id = $2",
                    guild_id, user_id,
                )
        return "ok"

    async def imposta_promemoria(self, guild_id: int, user_id: int, acceso: bool) -> None:
        await self._pool.execute(
            "INSERT INTO progress_serie (guild_id, user_id, promemoria) VALUES ($1, $2, $3) "
            "ON CONFLICT (guild_id, user_id) DO UPDATE SET promemoria = EXCLUDED.promemoria",
            guild_id, user_id, acceso,
        )

    async def da_avvisare(self, limite: int = 100) -> list[tuple[int, int, int, datetime, int]]:
        """Chi ha chiesto il promemoria, ha una serie e non è ancora stato avvisato per l'ultima riscossione."""
        righe = await self._pool.fetch(
            "SELECT guild_id, user_id, serie, ultima_at, scudi FROM progress_serie "
            "WHERE promemoria AND promemoria_inviato_at IS NULL AND serie > 0 AND ultima_at IS NOT NULL "
            "AND ultima_at <= now() - interval '20 hours' AND ultima_at >= now() - interval '84 hours' "
            "LIMIT $1",
            limite,
        )
        return [(r["guild_id"], r["user_id"], r["serie"], r["ultima_at"], r["scudi"]) for r in righe]

    async def segna_avvisato(self, guild_id: int, user_id: int) -> None:
        await self._pool.execute(
            "UPDATE progress_serie SET promemoria_inviato_at = now() WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id,
        )

    async def regala_premi_serie(self, guild_id: int, user_id: int, serie: int) -> list[str]:
        """Dà gli oggetti estetici delle tappe superate (7, 14, 30, 60, 100 giorni). Restituisce i nuovi."""
        oggetti = premi_serie_raggiunti(serie)
        if not oggetti:
            return []
        async with self._pool.acquire() as conn:
            return await regala_oggetti_in(conn, guild_id, user_id, oggetti)

    # ---- traguardi ----
    async def segna_traguardi(self, guild_id: int, user_id: int, chiavi: list[str]) -> list[str]:
        """Salva i traguardi e restituisce solo quelli nuovi."""
        nuovi: list[str] = []
        for chiave in chiavi:
            riga = await self._pool.fetchrow(
                "INSERT INTO progress_traguardi (guild_id, user_id, chiave) VALUES ($1, $2, $3) "
                "ON CONFLICT DO NOTHING RETURNING chiave",
                guild_id, user_id, chiave,
            )
            if riga is not None:
                nuovi.append(chiave)
        return nuovi

    async def traguardi_di(self, guild_id: int, user_id: int) -> set[str]:
        righe = await self._pool.fetch(
            "SELECT chiave FROM progress_traguardi WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        )
        return {r["chiave"] for r in righe}

    # ---- pass di 90 giorni ----
    async def aggiungi_xp_pass(self, righe: list[tuple[int, int, str, int]]) -> None:
        """(server, utente, stagione, XP guadagnati)."""
        if not righe:
            return
        await self._pool.executemany(
            "INSERT INTO progress_stagione (guild_id, user_id, stagione, xp) VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (guild_id, user_id, stagione) DO UPDATE SET xp = progress_stagione.xp + EXCLUDED.xp",
            righe,
        )

    async def stato_pass(self, guild_id: int, user_id: int, stagione: str) -> tuple[int, int, int, bool]:
        """(XP, livelli liberi riscossi, livelli premium riscossi, traccia premium aperta)."""
        riga = await self._pool.fetchrow(
            "SELECT xp, riscattati, riscattati_premium, premium FROM progress_stagione "
            "WHERE guild_id = $1 AND user_id = $2 AND stagione = $3",
            guild_id, user_id, stagione,
        )
        return (riga["xp"], riga["riscattati"], riga["riscattati_premium"], riga["premium"]) if riga else (0, 0, 0, False)

    async def sblocca_premium(self, guild_id: int, user_id: int, stagione: str, pagando: bool) -> str:
        """«ok», «gia» (era già aperta) o «saldo». Con `pagando` costa PASS_PREZZO_PREMIUM, altrimenti è il boost."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO progress_stagione (guild_id, user_id, stagione) VALUES ($1, $2, $3) "
                    "ON CONFLICT DO NOTHING",
                    guild_id, user_id, stagione,
                )
                aperta = await conn.fetchval(
                    "SELECT premium FROM progress_stagione WHERE guild_id = $1 AND user_id = $2 AND stagione = $3 "
                    "FOR UPDATE",
                    guild_id, user_id, stagione,
                )
                if aperta:
                    return "gia"
                if pagando and not await spend_coins_in(conn, guild_id, user_id, PASS_PREZZO_PREMIUM):
                    return "saldo"
                await conn.execute(
                    "UPDATE progress_stagione SET premium = TRUE WHERE guild_id = $1 AND user_id = $2 AND stagione = $3",
                    guild_id, user_id, stagione,
                )
        return "ok"

    async def riscatta_pass(self, guild_id: int, user_id: int, stagione: str) -> EsitoPass:
        """Paga i livelli raggiunti e non riscossi (libera e, se aperta, premium) e dà gli oggetti. Una volta sola."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                riga = await conn.fetchrow(
                    "SELECT xp, riscattati, riscattati_premium, premium FROM progress_stagione "
                    "WHERE guild_id = $1 AND user_id = $2 AND stagione = $3 FOR UPDATE",
                    guild_id, user_id, stagione,
                )
                if riga is None:
                    return EsitoPass()
                raggiunti = livelli_raggiunti(riga["xp"])
                liberi = max(0, raggiunti - riga["riscattati"])
                premium = max(0, raggiunti - riga["riscattati_premium"]) if riga["premium"] else 0
                if liberi == 0 and premium == 0:
                    return EsitoPass()
                monete = monete_livelli(riga["riscattati"], raggiunti, False) if liberi else 0
                oggetti: list[str] = []
                if premium:
                    monete += monete_livelli(riga["riscattati_premium"], raggiunti, True)
                    oggetti = await regala_oggetti_in(
                        conn, guild_id, user_id, oggetti_livelli(riga["riscattati_premium"], raggiunti)
                    )
                await conn.execute(
                    "UPDATE progress_stagione SET riscattati = GREATEST(riscattati, $4), "
                    "riscattati_premium = CASE WHEN premium THEN GREATEST(riscattati_premium, $4) "
                    "ELSE riscattati_premium END WHERE guild_id = $1 AND user_id = $2 AND stagione = $3",
                    guild_id, user_id, stagione, raggiunti,
                )
                if monete:
                    await add_coins_in(conn, guild_id, user_id, monete)
        return EsitoPass(monete, liberi, premium, tuple(oggetti))

    async def stagioni_complete(self, guild_id: int, user_id: int) -> int:
        return await self._pool.fetchval(
            "SELECT count(*) FROM progress_stagione WHERE guild_id = $1 AND user_id = $2 AND riscattati >= $3",
            guild_id, user_id, PASS_LIVELLI,
        )

    async def ha_aperto_premium(self, guild_id: int, user_id: int) -> bool:
        return bool(await self._pool.fetchval(
            "SELECT EXISTS (SELECT 1 FROM progress_stagione WHERE guild_id = $1 AND user_id = $2 AND premium)",
            guild_id, user_id,
        ))

    # ---- profilo globale (solo numeri positivi, solo i propri) ----
    async def profilo_globale(self, user_id: int) -> tuple[int, int, int, int]:
        """(server con un livello, livello massimo, serie record, traguardi diversi)."""
        livelli = await self._pool.fetchrow(
            "SELECT count(*) AS n, COALESCE(max(level), 0) AS massimo FROM leveling_totals "
            "WHERE user_id = $1 AND xp_total > 0",
            user_id,
        )
        record = await self._pool.fetchval(
            "SELECT COALESCE(max(record), 0) FROM progress_serie WHERE user_id = $1", user_id
        )
        traguardi = await self._pool.fetchval(
            "SELECT count(DISTINCT chiave) FROM progress_traguardi WHERE user_id = $1", user_id
        )
        return livelli["n"], livelli["massimo"], record, traguardi
