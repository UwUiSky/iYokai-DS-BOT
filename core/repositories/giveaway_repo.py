"""
core/repositories/giveaway_repo.py
======================================
Persistenza dei giveaway (SPEC.md §15.5, §23.6): giveaway, partecipazioni
con biglietti, conteggio dei messaggi, giveaway programmati e modelli.
Funzioni coperte: SPEC §15.5, §23.6 (NF-28)
Le partecipazioni sono
persistite (non in memoria come i drop, core/drop_logic.py) perché
un giveaway dura ore o giorni — deve sopravvivere a un riavvio del
bot, ed è per questo che il pulsante "Partecipa" è una VIEW
PERSISTENTE (custom_id fisso, registrata di nuovo ad ogni avvio in
main.py), non effimera come quella dei drop.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime

import asyncpg

from core.bounded_cache import BoundedCache
from core.giveaway_logic import MAX_MODELLI_PER_SERVER

# Quanto vale la risposta "questo server ha giveaway che contano i messaggi":
# la chiede ogni messaggio.
SECONDI_DI_CACHE_CONTEGGIO = 60


class ModelloPieno(Exception):
    """Il server ha già 25 modelli."""


@dataclass(frozen=True)
class Giveaway:
    id: int
    guild_id: int
    channel_id: int
    message_id: int | None
    prize: str
    winners_count: int
    min_level: int
    required_role_id: int | None
    ends_at: datetime
    ended: bool
    created_by: int
    min_messages: int = 0
    bypass_role_id: int | None = None
    bonus_role_id: int | None = None
    bonus_entries: int = 0
    starts_at: datetime | None = None
    started: bool = True
    duration_seconds: int | None = None
    errore: str | None = None


@dataclass(frozen=True)
class Modello:
    guild_id: int
    name: str
    prize: str
    winners_count: int
    duration_minutes: int
    min_level: int = 0
    required_role_id: int | None = None
    min_messages: int = 0
    bypass_role_id: int | None = None
    bonus_role_id: int | None = None
    bonus_entries: int = 0


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS giveaways (
            id                SERIAL PRIMARY KEY,
            guild_id          BIGINT NOT NULL,
            channel_id        BIGINT NOT NULL,
            message_id        BIGINT,
            prize             TEXT NOT NULL,
            winners_count     INTEGER NOT NULL DEFAULT 1,
            min_level         INTEGER NOT NULL DEFAULT 0,
            required_role_id  BIGINT,
            ends_at           TIMESTAMPTZ NOT NULL,
            ended             BOOLEAN NOT NULL DEFAULT false,
            created_by        BIGINT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS giveaway_entries (
            giveaway_id   INTEGER NOT NULL,
            user_id       BIGINT NOT NULL,
            PRIMARY KEY (giveaway_id, user_id)
        );

        CREATE INDEX IF NOT EXISTS idx_giveaways_due
            ON giveaways (ended, ends_at);
        """
    )


class GiveawayRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider
        self._cache_conteggio: BoundedCache[int, tuple[float, bool]] = BoundedCache(max_size=5_000)
        self._ultimo_conteggio: BoundedCache[tuple[int, int], float] = BoundedCache(max_size=20_000)

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def _row_to_giveaway(self, row) -> Giveaway:
        return Giveaway(
            id=row["id"],
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            message_id=row["message_id"],
            prize=row["prize"],
            winners_count=row["winners_count"],
            min_level=row["min_level"],
            required_role_id=row["required_role_id"],
            ends_at=row["ends_at"],
            ended=row["ended"],
            created_by=row["created_by"],
            min_messages=row["min_messages"],
            bypass_role_id=row["bypass_role_id"],
            bonus_role_id=row["bonus_role_id"],
            bonus_entries=row["bonus_entries"],
            starts_at=row["starts_at"],
            started=row["started"],
            duration_seconds=row["duration_seconds"],
            errore=row["errore"],
        )

    async def create_giveaway(
        self,
        guild_id: int,
        channel_id: int,
        prize: str,
        winners_count: int,
        min_level: int,
        required_role_id: int | None,
        ends_at: datetime,
        created_by: int,
        *,
        min_messages: int = 0,
        bypass_role_id: int | None = None,
        bonus_role_id: int | None = None,
        bonus_entries: int = 0,
        starts_at: datetime | None = None,
        duration_seconds: int | None = None,
    ) -> int:
        """
        Con `starts_at` il giveaway è programmato: resta fermo (started=false)
        finché il worker non lo fa partire, e `ends_at` si calcola allora da
        `duration_seconds`.
        """
        row = await self._pool.fetchrow(
            """
            INSERT INTO giveaways
                (guild_id, channel_id, prize, winners_count, min_level,
                 required_role_id, ends_at, created_by, min_messages,
                 bypass_role_id, bonus_role_id, bonus_entries, starts_at,
                 started, duration_seconds)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            RETURNING id
            """,
            guild_id, channel_id, prize, winners_count, min_level,
            required_role_id, ends_at, created_by, min_messages,
            bypass_role_id, bonus_role_id, bonus_entries, starts_at,
            starts_at is None, duration_seconds,
        )
        self._cache_conteggio.delete(guild_id)
        return row["id"]

    async def set_message_id(self, giveaway_id: int, message_id: int) -> None:
        await self._pool.execute(
            "UPDATE giveaways SET message_id = $2 WHERE id = $1", giveaway_id, message_id
        )

    async def get_giveaway(self, giveaway_id: int) -> Giveaway | None:
        row = await self._pool.fetchrow("SELECT * FROM giveaways WHERE id = $1", giveaway_id)
        return self._row_to_giveaway(row) if row is not None else None

    async def get_due_giveaways(self, now: datetime) -> list[Giveaway]:
        """Giveaway non ancora conclusi la cui scadenza è passata —
        pronti per l'estrazione dei vincitori."""
        rows = await self._pool.fetch(
            "SELECT * FROM giveaways WHERE ended = false AND started = true AND ends_at <= $1", now
        )
        return [self._row_to_giveaway(r) for r in rows]

    async def get_active_giveaways(self) -> list[Giveaway]:
        """Tutti i giveaway non ancora conclusi, indipendentemente
        dalla scadenza — usata all'avvio del bot per ri-registrare
        le view persistenti dei pulsanti "Partecipa" ancora validi."""
        rows = await self._pool.fetch(
            "SELECT * FROM giveaways WHERE ended = false AND started = true"
        )
        return [self._row_to_giveaway(r) for r in rows]

    async def mark_ended(self, giveaway_id: int) -> bool:
        """
        Conclude il giveaway. Vero solo per chi lo conclude davvero: se due giri
        del worker arrivano insieme, uno solo riceve True (e annuncia i vincitori).
        """
        result = await self._pool.execute(
            "UPDATE giveaways SET ended = true WHERE id = $1 AND ended = false", giveaway_id
        )
        return result.endswith(" 1")

    async def segna_errore(self, giveaway_id: int, errore: str) -> None:
        """
        Un programmato che non riesce a partire torna "da partire" ma con il
        motivo scritto: il worker lo salta, lo staff lo vede e può annullarlo.
        """
        await self._pool.execute(
            "UPDATE giveaways SET started = false, errore = $2 WHERE id = $1 AND ended = false",
            giveaway_id,
            errore[:300],
        )

    async def list_scheduled(self, guild_id: int) -> list[Giveaway]:
        """I giveaway programmati del server non ancora partiti (anche quelli in errore)."""
        rows = await self._pool.fetch(
            "SELECT * FROM giveaways WHERE guild_id = $1 AND started = false AND ended = false "
            "ORDER BY starts_at, id",
            guild_id,
        )
        return [self._row_to_giveaway(r) for r in rows]

    async def cancel_scheduled(self, guild_id: int, giveaway_id: int) -> bool:
        """Annulla un programmato del server prima che parta. Falso se non c'è (o è già partito)."""
        result = await self._pool.execute(
            "DELETE FROM giveaways WHERE id = $1 AND guild_id = $2 AND started = false AND ended = false",
            giveaway_id,
            guild_id,
        )
        return result.endswith(" 1")

    async def add_entry(self, giveaway_id: int, user_id: int, tickets: int = 1) -> bool:
        """Restituisce True se la partecipazione è nuova, False se
        l'utente aveva già partecipato (nessun errore, nessuna riga
        duplicata, biglietti invariati — ON CONFLICT DO NOTHING)."""
        result = await self._pool.execute(
            """
            INSERT INTO giveaway_entries (giveaway_id, user_id, tickets)
            VALUES ($1, $2, $3)
            ON CONFLICT (giveaway_id, user_id) DO NOTHING
            """,
            giveaway_id,
            user_id,
            tickets,
        )
        return result.endswith(" 1")

    async def has_entered(self, giveaway_id: int, user_id: int) -> bool:
        row = await self._pool.fetchrow(
            "SELECT 1 FROM giveaway_entries WHERE giveaway_id = $1 AND user_id = $2",
            giveaway_id,
            user_id,
        )
        return row is not None

    async def get_weighted_entries(self, giveaway_id: int) -> list[tuple[int, int]]:
        """I partecipanti con i loro biglietti: coppie (utente, biglietti)."""
        rows = await self._pool.fetch(
            "SELECT user_id, tickets FROM giveaway_entries WHERE giveaway_id = $1", giveaway_id
        )
        return [(r["user_id"], r["tickets"]) for r in rows]

    async def get_giveaways_to_start(self, now: datetime) -> list[Giveaway]:
        """Giveaway programmati la cui ora di partenza è arrivata."""
        rows = await self._pool.fetch(
            "SELECT * FROM giveaways WHERE started = false AND ended = false AND errore IS NULL "
            "AND starts_at <= $1",
            now,
        )
        return [self._row_to_giveaway(r) for r in rows]

    async def claim_start(self, giveaway_id: int, now: datetime) -> Giveaway | None:
        """
        Fa partire un giveaway programmato e ne fissa la scadenza (partenza +
        durata). Una sola scrittura condizionata: se due giri del worker
        arrivano insieme, parte una volta sola (l'altro riceve None).
        """
        row = await self._pool.fetchrow(
            """
            UPDATE giveaways
            SET started = true,
                ends_at = $2::timestamptz + make_interval(secs => COALESCE(duration_seconds, 0))
            WHERE id = $1 AND started = false AND ended = false
            RETURNING *
            """,
            giveaway_id,
            now,
        )
        if row is not None:
            self._cache_conteggio.delete(row["guild_id"])
        return self._row_to_giveaway(row) if row is not None else None

    async def _server_conta_messaggi(self, guild_id: int) -> bool:
        voce = self._cache_conteggio.get(guild_id)
        if voce is not None and time.monotonic() - voce[0] < SECONDI_DI_CACHE_CONTEGGIO:
            return voce[1]
        presente = await self._pool.fetchval(
            "SELECT EXISTS (SELECT 1 FROM giveaways WHERE guild_id = $1 AND ended = false "
            "AND started = true AND min_messages > 0)",
            guild_id,
        )
        self._cache_conteggio.set(guild_id, (time.monotonic(), bool(presente)))
        return bool(presente)

    async def count_message(
        self, guild_id: int, user_id: int, cooldown_seconds: float = 0
    ) -> None:
        """
        Un messaggio in più per ogni giveaway aperto del server che chiede un
        numero di messaggi. Se il server non ne ha, non scrive nulla (la
        risposta resta in memoria per un minuto). Con `cooldown_seconds` un
        messaggio conta solo se è passato quel tempo dall'ultimo contato di
        quell'utente (lo stesso attesa dell'XP: niente conteggio a raffica).
        """
        if not await self._server_conta_messaggi(guild_id):
            return
        if cooldown_seconds > 0:
            adesso = time.monotonic()
            ultimo = self._ultimo_conteggio.get((guild_id, user_id))
            if ultimo is not None and adesso - ultimo < cooldown_seconds:
                return
            self._ultimo_conteggio.set((guild_id, user_id), adesso)
        await self._pool.execute(
            """
            INSERT INTO giveaway_message_counts (giveaway_id, user_id, n)
            SELECT id, $2, 1 FROM giveaways
            WHERE guild_id = $1 AND ended = false AND started = true AND min_messages > 0
            ON CONFLICT (giveaway_id, user_id)
                DO UPDATE SET n = giveaway_message_counts.n + 1
            """,
            guild_id,
            user_id,
        )

    async def message_count(self, giveaway_id: int, user_id: int) -> int:
        return (
            await self._pool.fetchval(
                "SELECT n FROM giveaway_message_counts WHERE giveaway_id = $1 AND user_id = $2",
                giveaway_id,
                user_id,
            )
            or 0
        )

    async def save_template(
        self,
        guild_id: int,
        name: str,
        *,
        prize: str,
        winners_count: int,
        duration_minutes: int,
        min_level: int = 0,
        required_role_id: int | None = None,
        min_messages: int = 0,
        bypass_role_id: int | None = None,
        bonus_role_id: int | None = None,
        bonus_entries: int = 0,
    ) -> None:
        """Salva o aggiorna un modello. Al massimo 25 per server (ModelloPieno)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Il blocco sul server evita che due salvataggi insieme superino il tetto.
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtext('giveaway_templates'), $1)",
                    guild_id % 2**31,
                )
                esiste = await conn.fetchval(
                    "SELECT 1 FROM giveaway_templates WHERE guild_id = $1 AND name = $2",
                    guild_id, name,
                )
                if not esiste:
                    quanti = await conn.fetchval(
                        "SELECT count(*) FROM giveaway_templates WHERE guild_id = $1", guild_id
                    )
                    if quanti >= MAX_MODELLI_PER_SERVER:
                        raise ModelloPieno()
                await conn.execute(
                    """
                    INSERT INTO giveaway_templates
                        (guild_id, name, prize, winners_count, duration_minutes, min_level,
                         required_role_id, min_messages, bypass_role_id, bonus_role_id, bonus_entries)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (guild_id, name) DO UPDATE SET
                        prize = EXCLUDED.prize, winners_count = EXCLUDED.winners_count,
                        duration_minutes = EXCLUDED.duration_minutes, min_level = EXCLUDED.min_level,
                        required_role_id = EXCLUDED.required_role_id,
                        min_messages = EXCLUDED.min_messages,
                        bypass_role_id = EXCLUDED.bypass_role_id,
                        bonus_role_id = EXCLUDED.bonus_role_id,
                        bonus_entries = EXCLUDED.bonus_entries
                    """,
                    guild_id, name, prize, winners_count, duration_minutes, min_level,
                    required_role_id, min_messages, bypass_role_id, bonus_role_id, bonus_entries,
                )

    async def get_template(self, guild_id: int, name: str) -> Modello | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM giveaway_templates WHERE guild_id = $1 AND name = $2", guild_id, name
        )
        return Modello(**dict(row)) if row is not None else None

    async def list_templates(self, guild_id: int) -> list[Modello]:
        rows = await self._pool.fetch(
            "SELECT * FROM giveaway_templates WHERE guild_id = $1 ORDER BY name", guild_id
        )
        return [Modello(**dict(r)) for r in rows]

    async def delete_template(self, guild_id: int, name: str) -> bool:
        result = await self._pool.execute(
            "DELETE FROM giveaway_templates WHERE guild_id = $1 AND name = $2", guild_id, name
        )
        return result.endswith(" 1")

    async def count_entries(self, giveaway_id: int) -> int:
        row = await self._pool.fetchrow(
            "SELECT COUNT(*) AS n FROM giveaway_entries WHERE giveaway_id = $1", giveaway_id
        )
        return row["n"]


def _get_pool():
    from core.database import db
    return db.pool


giveaway_repo = GiveawayRepository(pool_provider=_get_pool)
