"""
core/repositories/ticket_automazioni_repo.py
============================================
Regole di inattività dei pannelli (TKT-064), stato «in attesa dell'utente» dei ticket (TKT-029)
e riserva di canali pronti (TKT-035).
Tabelle: migrazione 0534 (`ticket_automazioni`, `ticket_automazioni_eseguite`, `ticket_riserva`,
colonne nuove di `tickets` e `ticket_panel_opzioni`).
"""

from __future__ import annotations

from datetime import datetime

import asyncpg

from core.ticket_autoclose_worker import MAX_REGOLE_PANNELLO, Regola


class TroppeRegole(Exception):
    """Il pannello ha già 5 regole."""


def _regola(r) -> Regola:
    return Regola(r["id"], r["panel_id"], r["chi"], r["minuti"], r["azione"], r["testo"], r["ripeti"])


class TicketAutomazioniRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ------------------------------------------------------------ regole (TKT-064)
    async def aggiungi_regola(self, panel_id: int, chi: str, minuti: int, azione: str, testo: str | None, ripeti: bool) -> Regola:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT 1 FROM ticket_panels WHERE id = $1 FOR UPDATE", panel_id)
                presenti = await conn.fetchval("SELECT count(*) FROM ticket_automazioni WHERE panel_id = $1", panel_id)
                if presenti >= MAX_REGOLE_PANNELLO:
                    raise TroppeRegole()
                r = await conn.fetchrow(
                    "INSERT INTO ticket_automazioni (panel_id, chi, minuti, azione, testo, ripeti) "
                    "VALUES ($1, $2, $3, $4, $5, $6) RETURNING *",
                    panel_id, chi, minuti, azione, testo, ripeti,
                )
        return _regola(r)

    async def regole(self, panel_id: int) -> list[Regola]:
        righe = await self._pool.fetch("SELECT * FROM ticket_automazioni WHERE panel_id = $1 ORDER BY id", panel_id)
        return [_regola(r) for r in righe]

    async def togli_regola(self, panel_id: int, regola_id: int) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM ticket_automazioni WHERE id = $1 AND panel_id = $2", regola_id, panel_id
        )
        return esito.endswith(" 1")

    async def eseguite(self, ticket_id: int) -> dict[int, datetime]:
        righe = await self._pool.fetch(
            "SELECT automazione_id, ultima_at FROM ticket_automazioni_eseguite WHERE ticket_id = $1", ticket_id
        )
        return {r["automazione_id"]: r["ultima_at"] for r in righe}

    async def segna_eseguita(self, ticket_id: int, regola_id: int, at: datetime) -> None:
        await self._pool.execute(
            "INSERT INTO ticket_automazioni_eseguite (ticket_id, automazione_id, ultima_at) VALUES ($1, $2, $3) "
            "ON CONFLICT (ticket_id, automazione_id) DO UPDATE SET ultima_at = EXCLUDED.ultima_at",
            ticket_id, regola_id, at,
        )

    # ------------------------------------------------------------ chi ha scritto (TKT-029 / TKT-064)
    async def segna_scritto(self, channel_id: int, da_utente: bool, at: datetime) -> None:
        colonna = "ultimo_utente_at" if da_utente else "ultimo_staff_at"
        await self._pool.execute(
            f"UPDATE tickets SET {colonna} = $2 WHERE channel_id = $1 AND status = 'open' "
            f"AND ({colonna} IS NULL OR {colonna} < $2)",
            channel_id, at,
        )

    async def da_controllare(self) -> list[dict]:
        """Ticket aperti di un pannello che ha l'attesa o almeno una regola, con lo stato da valutare."""
        righe = await self._pool.fetch(
            """
            SELECT t.id, t.guild_id, t.user_id, t.channel_id, t.panel_id, t.created_at, t.last_activity_at,
                   t.ultimo_utente_at, t.ultimo_staff_at, t.in_attesa_da, t.categoria_prima_attesa, t.spostato_at,
                   COALESCE(o.attesa_minuti, 0) AS attesa_minuti, o.attesa_categoria_id
            FROM tickets t
            LEFT JOIN ticket_panel_opzioni o ON o.panel_id = t.panel_id
            WHERE t.status = 'open' AND t.panel_id IS NOT NULL
              AND (COALESCE(o.attesa_minuti, 0) > 0 OR t.in_attesa_da IS NOT NULL
                   OR EXISTS (SELECT 1 FROM ticket_automazioni a WHERE a.panel_id = t.panel_id))
            ORDER BY t.id
            LIMIT 2000
            """
        )
        return [dict(r) for r in righe]

    async def segna_attesa(self, ticket_id: int, categoria_prima: int | None, at: datetime) -> None:
        await self._pool.execute(
            "UPDATE tickets SET in_attesa_da = $2, categoria_prima_attesa = $3, spostato_at = $2 WHERE id = $1",
            ticket_id, at, categoria_prima,
        )

    async def segna_ritorno(self, ticket_id: int, at: datetime) -> None:
        await self._pool.execute(
            "UPDATE tickets SET in_attesa_da = NULL, categoria_prima_attesa = NULL, spostato_at = $2 WHERE id = $1",
            ticket_id, at,
        )

    # ------------------------------------------------------------ riserva di canali (TKT-035)
    async def pannelli_con_riserva(self) -> list[dict]:
        righe = await self._pool.fetch(
            """
            SELECT p.id AS panel_id, p.guild_id, p.category_id, o.riserva_canali,
                   (SELECT count(*) FROM ticket_riserva r WHERE r.panel_id = p.id) AS presenti
            FROM ticket_panels p JOIN ticket_panel_opzioni o ON o.panel_id = p.id
            WHERE o.riserva_canali > 0 OR EXISTS (SELECT 1 FROM ticket_riserva r WHERE r.panel_id = p.id)
            """
        )
        return [dict(r) for r in righe]

    async def aggiungi_riserva(self, channel_id: int, guild_id: int, panel_id: int) -> None:
        await self._pool.execute(
            "INSERT INTO ticket_riserva (channel_id, guild_id, panel_id) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
            channel_id, guild_id, panel_id,
        )

    async def prendi_riserva(self, panel_id: int) -> int | None:
        """Toglie dalla riserva il canale più vecchio e lo dà a chi apre il ticket (uno solo lo ottiene)."""
        return await self._pool.fetchval(
            "DELETE FROM ticket_riserva WHERE channel_id = (SELECT channel_id FROM ticket_riserva "
            "WHERE panel_id = $1 ORDER BY creato_il LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING channel_id",
            panel_id,
        )

    async def togli_riserva(self, channel_id: int) -> None:
        await self._pool.execute("DELETE FROM ticket_riserva WHERE channel_id = $1", channel_id)


def _get_pool():
    from core.database import db
    return db.pool


ticket_automazioni_repo = TicketAutomazioniRepository(pool_provider=_get_pool)
