"""
core/repositories/guild_clan_repo.py
========================================
Persistenza del Sistema Gilde/Clan (SPEC.md §15.14). Tre tabelle in
questo primo pezzo — la creazione/ufficializzazione, i membri con
ruolo, la tesoreria con registro movimenti (utile anche per la
classifica donazioni membri richiesta esplicitamente per i pannelli).
Il tracciamento dell'attività vocale (tick, decadimento) e i comandi
Discord arrivano in un pezzo successivo, sopra questa base.

Un clan ha un ID GLOBALE (non per server): necessario perché i
trasferimenti di tesoreria tra clan dello STESSO owner possono
attraversare server diversi (confermato esplicitamente dall'utente),
quindi due clan coinvolti in un trasferimento possono avere
guild_id diversi — servirebbe comunque un ID univoco che non dipenda
dal server per identificarli entrambi in modo non ambiguo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg

from core.guild_clan_logic import CREATION_DEFICIT, apply_monthly_treasury_decay

ROLE_OWNER = "owner"
ROLE_CO_OWNER = "co_owner"
ROLE_ADMIN = "admin"
ROLE_MOD = "mod"
ROLE_MEMBER = "member"

REASON_DONATION = "donation"
REASON_CHANNEL_UNLOCK = "channel_unlock"
REASON_MONTHLY_DECAY = "monthly_decay"
REASON_CREATION_DEFICIT = "creation_deficit"
REASON_TREASURY_TRANSFER_IN = "treasury_transfer_in"
REASON_TREASURY_TRANSFER_OUT = "treasury_transfer_out"

DEFAULT_MAX_MEMBERS = 50
MAX_MEMBERS_CEILING = 999


@dataclass(frozen=True)
class Clan:
    id: int
    guild_id: int
    tag: str
    name: str
    owner_id: int
    co_owner_id: int | None
    category_id: int | None
    treasury_balance: int
    total_xp: int
    last_decay_period: str | None
    officialized: bool
    officialize_deadline: datetime
    max_members: int
    channels_unlocked: int
    created_at: datetime


@dataclass(frozen=True)
class ClanMember:
    clan_id: int
    user_id: int
    role: str
    joined_at: datetime


@dataclass(frozen=True)
class TreasuryLedgerEntry:
    id: int
    clan_id: int
    user_id: int | None
    amount: int
    reason: str
    created_at: datetime


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS clans (
            id                    SERIAL PRIMARY KEY,
            guild_id              BIGINT NOT NULL,
            tag                   TEXT NOT NULL,
            name                  TEXT NOT NULL,
            owner_id              BIGINT NOT NULL,
            co_owner_id           BIGINT,
            category_id           BIGINT,
            treasury_balance      BIGINT NOT NULL DEFAULT 0,
            officialized          BOOLEAN NOT NULL DEFAULT false,
            officialize_deadline  TIMESTAMPTZ NOT NULL,
            max_members           INTEGER NOT NULL DEFAULT 50,
            channels_unlocked     INTEGER NOT NULL DEFAULT 0,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (guild_id, tag)
        );

        -- ADD COLUMN IF NOT EXISTS (idempotente): clans esisteva già
        -- prima che l'XP di gilda fosse aggiunta, serve poterla
        -- estendere anche su un database già popolato.
        ALTER TABLE clans ADD COLUMN IF NOT EXISTS total_xp BIGINT NOT NULL DEFAULT 0;
        ALTER TABLE clans ADD COLUMN IF NOT EXISTS last_decay_period TEXT;

        CREATE TABLE IF NOT EXISTS clan_members (
            clan_id     INTEGER NOT NULL,
            user_id     BIGINT NOT NULL,
            role        TEXT NOT NULL,
            joined_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (clan_id, user_id)
        );

        CREATE INDEX IF NOT EXISTS idx_clan_members_user ON clan_members (user_id);

        CREATE TABLE IF NOT EXISTS clan_treasury_ledger (
            id           SERIAL PRIMARY KEY,
            clan_id      INTEGER NOT NULL,
            user_id      BIGINT,
            amount       BIGINT NOT NULL,
            reason       TEXT NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_clan_treasury_ledger_clan
            ON clan_treasury_ledger (clan_id, created_at);
        """
    )


class GuildClanRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def _row_to_clan(self, row) -> Clan:
        return Clan(
            id=row["id"],
            guild_id=row["guild_id"],
            tag=row["tag"],
            name=row["name"],
            owner_id=row["owner_id"],
            co_owner_id=row["co_owner_id"],
            category_id=row["category_id"],
            treasury_balance=row["treasury_balance"],
            total_xp=row["total_xp"],
            last_decay_period=row["last_decay_period"],
            officialized=row["officialized"],
            officialize_deadline=row["officialize_deadline"],
            max_members=row["max_members"],
            channels_unlocked=row["channels_unlocked"],
            created_at=row["created_at"],
        )

    def _row_to_member(self, row) -> ClanMember:
        return ClanMember(
            clan_id=row["clan_id"],
            user_id=row["user_id"],
            role=row["role"],
            joined_at=row["joined_at"],
        )

    def _row_to_ledger_entry(self, row) -> TreasuryLedgerEntry:
        return TreasuryLedgerEntry(
            id=row["id"],
            clan_id=row["clan_id"],
            user_id=row["user_id"],
            amount=row["amount"],
            reason=row["reason"],
            created_at=row["created_at"],
        )

    # ----------------------------------------------------------------
    # Clan
    # ----------------------------------------------------------------
    async def create_clan(
        self,
        guild_id: int,
        tag: str,
        name: str,
        owner_id: int,
        officialize_deadline: datetime,
        max_members: int = DEFAULT_MAX_MEMBERS,
    ) -> int:
        """
        Il saldo tesoreria parte a -CREATION_DEFICIT (in deficit) —
        il clan esiste già (categoria/canali possono essere creati
        subito), ma non è 'ufficializzato' finché il saldo non torna
        a >= 0 entro officialize_deadline. Il founder viene aggiunto
        automaticamente come owner nella stessa transazione: un clan
        senza il suo stesso owner tra i membri sarebbe uno stato
        incoerente anche solo per un istante.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    INSERT INTO clans
                        (guild_id, tag, name, owner_id, treasury_balance,
                         officialize_deadline, max_members)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING id
                    """,
                    guild_id, tag, name, owner_id, -CREATION_DEFICIT,
                    officialize_deadline, max_members,
                )
                clan_id = row["id"]

                await conn.execute(
                    """
                    INSERT INTO clan_members (clan_id, user_id, role)
                    VALUES ($1, $2, $3)
                    """,
                    clan_id, owner_id, ROLE_OWNER,
                )

                await conn.execute(
                    """
                    INSERT INTO clan_treasury_ledger (clan_id, user_id, amount, reason)
                    VALUES ($1, NULL, $2, $3)
                    """,
                    clan_id, -CREATION_DEFICIT, REASON_CREATION_DEFICIT,
                )

        return clan_id

    async def get_clan(self, clan_id: int) -> Clan | None:
        row = await self._pool.fetchrow("SELECT * FROM clans WHERE id = $1", clan_id)
        return self._row_to_clan(row) if row is not None else None

    async def get_clan_by_tag(self, guild_id: int, tag: str) -> Clan | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM clans WHERE guild_id = $1 AND tag = $2", guild_id, tag
        )
        return self._row_to_clan(row) if row is not None else None

    async def is_tag_taken(self, guild_id: int, tag: str) -> bool:
        return await self.get_clan_by_tag(guild_id, tag) is not None

    async def list_clans(self, guild_id: int) -> list[Clan]:
        rows = await self._pool.fetch(
            "SELECT * FROM clans WHERE guild_id = $1 ORDER BY created_at", guild_id
        )
        return [self._row_to_clan(r) for r in rows]

    async def set_officialized(self, clan_id: int) -> None:
        await self._pool.execute("UPDATE clans SET officialized = true WHERE id = $1", clan_id)

    async def get_unofficialized_expired(self, now: datetime) -> list[Clan]:
        """Clan ancora non ufficializzati la cui finestra di 24h è
        scaduta — pronti per la cancellazione automatica."""
        rows = await self._pool.fetch(
            """
            SELECT * FROM clans
            WHERE officialized = false AND officialize_deadline <= $1
            """,
            now,
        )
        return [self._row_to_clan(r) for r in rows]

    async def delete_clan(self, clan_id: int) -> None:
        """Elimina il clan e tutto ciò che gli appartiene (membri,
        registro tesoreria) — usata sia per la cancellazione
        automatica (deficit non coperto) sia per 'elimina clan'/
        'chiudi gilda' volontaria."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM clan_members WHERE clan_id = $1", clan_id)
                await conn.execute(
                    "DELETE FROM clan_treasury_ledger WHERE clan_id = $1", clan_id
                )
                await conn.execute("DELETE FROM clans WHERE id = $1", clan_id)

    async def set_category_id(self, clan_id: int, category_id: int) -> None:
        await self._pool.execute(
            "UPDATE clans SET category_id = $2 WHERE id = $1", clan_id, category_id
        )

    async def increment_channels_unlocked(self, clan_id: int) -> None:
        await self._pool.execute(
            "UPDATE clans SET channels_unlocked = channels_unlocked + 1 WHERE id = $1", clan_id
        )

    # ----------------------------------------------------------------
    # Membri
    # ----------------------------------------------------------------
    async def add_member(self, clan_id: int, user_id: int, role: str = ROLE_MEMBER) -> None:
        await self._pool.execute(
            """
            INSERT INTO clan_members (clan_id, user_id, role)
            VALUES ($1, $2, $3)
            ON CONFLICT (clan_id, user_id) DO NOTHING
            """,
            clan_id, user_id, role,
        )

    async def remove_member(self, clan_id: int, user_id: int) -> bool:
        result = await self._pool.execute(
            "DELETE FROM clan_members WHERE clan_id = $1 AND user_id = $2", clan_id, user_id
        )
        return result.endswith(" 1")

    async def set_member_role(self, clan_id: int, user_id: int, role: str) -> None:
        await self._pool.execute(
            "UPDATE clan_members SET role = $3 WHERE clan_id = $1 AND user_id = $2",
            clan_id, user_id, role,
        )

    async def get_member(self, clan_id: int, user_id: int) -> ClanMember | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM clan_members WHERE clan_id = $1 AND user_id = $2", clan_id, user_id
        )
        return self._row_to_member(row) if row is not None else None

    async def list_members(self, clan_id: int) -> list[ClanMember]:
        rows = await self._pool.fetch(
            "SELECT * FROM clan_members WHERE clan_id = $1 ORDER BY joined_at", clan_id
        )
        return [self._row_to_member(r) for r in rows]

    async def count_members(self, clan_id: int) -> int:
        row = await self._pool.fetchrow(
            "SELECT COUNT(*) AS n FROM clan_members WHERE clan_id = $1", clan_id
        )
        return row["n"]

    async def count_members_with_role(self, clan_id: int, role: str) -> int:
        """Per far rispettare i tetti (max 3 admin, max 5 mod, max 1
        co-owner) prima di promuovere qualcuno."""
        row = await self._pool.fetchrow(
            "SELECT COUNT(*) AS n FROM clan_members WHERE clan_id = $1 AND role = $2",
            clan_id, role,
        )
        return row["n"]

    async def get_member_clan_in_guild(self, guild_id: int, user_id: int) -> Clan | None:
        """Il clan a cui l'utente appartiene in QUESTO server — un
        utente può stare in un solo clan per server (non specificato
        esplicitamente, ma implicito nel fatto che il tag forzato sul
        nickname non avrebbe senso con più clan contemporaneamente
        nello stesso server)."""
        row = await self._pool.fetchrow(
            """
            SELECT c.* FROM clans c
            JOIN clan_members m ON m.clan_id = c.id
            WHERE c.guild_id = $1 AND m.user_id = $2
            """,
            guild_id, user_id,
        )
        return self._row_to_clan(row) if row is not None else None

    # ----------------------------------------------------------------
    # Tesoreria
    # ----------------------------------------------------------------
    async def donate(self, clan_id: int, user_id: int, amount: int) -> int:
        """
        Membro -> gilda, l'UNICA direzione permessa per un singolo
        utente (mai il contrario, confermato esplicitamente). Non
        verifica il saldo personale del donatore: chi chiama
        (comando Discord) deve prima sottrarre le coin dal saldo
        personale tramite leveling_repo.spend_coins() — questo
        repository si occupa solo della tesoreria di destinazione.
        Restituisce il nuovo saldo.
        """
        if amount <= 0:
            raise ValueError("L'importo donato deve essere positivo.")

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "UPDATE clans SET treasury_balance = treasury_balance + $2 "
                    "WHERE id = $1 RETURNING treasury_balance",
                    clan_id, amount,
                )
                await conn.execute(
                    """
                    INSERT INTO clan_treasury_ledger (clan_id, user_id, amount, reason)
                    VALUES ($1, $2, $3, $4)
                    """,
                    clan_id, user_id, amount, REASON_DONATION,
                )
                return row["treasury_balance"]

    async def spend_from_treasury(self, clan_id: int, amount: int, reason: str) -> bool:
        """
        Spende dalla tesoreria SOLO se il saldo basta (mai un saldo
        negativo per una spesa volontaria, a differenza del deficit
        di creazione che parte apposta negativo) — usata per lo
        sblocco canali. Restituisce False senza scrivere nulla se il
        saldo non basta.
        """
        if amount <= 0:
            raise ValueError("L'importo da spendere deve essere positivo.")

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                saldo = await conn.fetchval(
                    "SELECT treasury_balance FROM clans WHERE id = $1 FOR UPDATE", clan_id
                )
                if saldo is None or saldo < amount:
                    return False

                await conn.execute(
                    "UPDATE clans SET treasury_balance = treasury_balance - $2 WHERE id = $1",
                    clan_id, amount,
                )
                await conn.execute(
                    """
                    INSERT INTO clan_treasury_ledger (clan_id, user_id, amount, reason)
                    VALUES ($1, NULL, $2, $3)
                    """,
                    clan_id, -amount, reason,
                )
                return True

    async def apply_treasury_delta(self, clan_id: int, amount: int, reason: str) -> None:
        """
        Variazione di saldo SENZA verifica di sufficienza — usata per
        il decadimento mensile (amount negativo, il saldo può solo
        scendere, non serve verificare nulla) e per accreditare i
        guadagni XP/coin di gilda dal tick periodico (amount
        positivo). Non passa da spend_from_treasury() perché quella
        rifiuterebbe operazioni non "di spesa volontaria" nel modo
        sbagliato per questi due casi.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE clans SET treasury_balance = treasury_balance + $2 WHERE id = $1",
                    clan_id, amount,
                )
                await conn.execute(
                    """
                    INSERT INTO clan_treasury_ledger (clan_id, user_id, amount, reason)
                    VALUES ($1, NULL, $2, $3)
                    """,
                    clan_id, amount, reason,
                )

    async def list_officialized_clans(self) -> list[Clan]:
        """Tutti i clan ufficializzati, indipendentemente dal
        server — usata dal worker di decadimento mensile della
        tesoreria (che gira una volta sola per l'intero bot, non
        server per server)."""
        rows = await self._pool.fetch("SELECT * FROM clans WHERE officialized = true")
        return [self._row_to_clan(r) for r in rows]

    async def apply_monthly_decay(self, clan_id: int, period: str) -> int:
        """
        Applica il decadimento mensile del 10% (core.guild_clan_
        logic.apply_monthly_treasury_decay) e marca il periodo come
        coperto, atomicamente (FOR UPDATE) — la percentuale è
        calcolata QUI, sul saldo letto sotto lock, non passata dal
        chiamante: altrimenti tra la lettura fatta dal chiamante e
        questa scrittura il saldo potrebbe essere cambiato da una
        spesa o una donazione nel frattempo. Restituisce il nuovo
        saldo.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                saldo_attuale = await conn.fetchval(
                    "SELECT treasury_balance FROM clans WHERE id = $1 FOR UPDATE", clan_id
                )
                nuovo_saldo = apply_monthly_treasury_decay(saldo_attuale)
                delta = nuovo_saldo - saldo_attuale

                await conn.execute(
                    "UPDATE clans SET treasury_balance = $2, last_decay_period = $3 WHERE id = $1",
                    clan_id, nuovo_saldo, period,
                )
                if delta != 0:
                    await conn.execute(
                        """
                        INSERT INTO clan_treasury_ledger (clan_id, user_id, amount, reason)
                        VALUES ($1, NULL, $2, $3)
                        """,
                        clan_id, delta, "monthly_decay",
                    )
                return nuovo_saldo

    async def add_xp(self, clan_id: int, amount: int) -> None:
        """XP di gilda accumulata (per la classifica clan richiesta
        nei pannelli) - SEPARATA dai coin di tesoreria, un clan
        guadagna entrambi ad ogni tick vocale ma sono due assi
        diversi (l'XP non si spende mai, i coin sì)."""
        if amount <= 0:
            raise ValueError("L'importo XP da aggiungere deve essere positivo.")
        await self._pool.execute(
            "UPDATE clans SET total_xp = total_xp + $2 WHERE id = $1", clan_id, amount
        )

    async def get_clan_leaderboard(self, guild_id: int, limit: int = 10) -> list[Clan]:
        """Classifica clan del server per XP totale — per la
        'classifica clan' richiesta esplicitamente nei pannelli."""
        rows = await self._pool.fetch(
            "SELECT * FROM clans WHERE guild_id = $1 ORDER BY total_xp DESC LIMIT $2",
            guild_id, limit,
        )
        return [self._row_to_clan(r) for r in rows]

    async def transfer_between_treasuries(
        self, from_clan_id: int, to_clan_id: int, amount: int
    ) -> bool:
        """
        Tesoreria -> tesoreria, permesso SOLO se le due tesorerie
        appartengono allo stesso owner (confermato esplicitamente
        dall'utente — anche tra clan su server diversi, ma MAI tra
        owner diversi anche nello stesso server). La verifica
        "stesso owner" è responsabilità del CHIAMANTE (comando
        Discord, che ha già in mano gli oggetti Clan di entrambi) —
        qui viene solo eseguito il movimento, atomicamente, con lo
        stesso controllo di saldo sufficiente di spend_from_treasury.
        """
        if amount <= 0:
            raise ValueError("L'importo da trasferire deve essere positivo.")
        if from_clan_id == to_clan_id:
            raise ValueError("Non si può trasferire una tesoreria verso se stessa.")

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                saldo = await conn.fetchval(
                    "SELECT treasury_balance FROM clans WHERE id = $1 FOR UPDATE", from_clan_id
                )
                if saldo is None or saldo < amount:
                    return False

                await conn.execute(
                    "UPDATE clans SET treasury_balance = treasury_balance - $2 WHERE id = $1",
                    from_clan_id, amount,
                )
                await conn.execute(
                    "UPDATE clans SET treasury_balance = treasury_balance + $2 WHERE id = $1",
                    to_clan_id, amount,
                )
                await conn.execute(
                    """
                    INSERT INTO clan_treasury_ledger (clan_id, user_id, amount, reason)
                    VALUES ($1, NULL, $2, $3)
                    """,
                    from_clan_id, -amount, REASON_TREASURY_TRANSFER_OUT,
                )
                await conn.execute(
                    """
                    INSERT INTO clan_treasury_ledger (clan_id, user_id, amount, reason)
                    VALUES ($1, NULL, $2, $3)
                    """,
                    to_clan_id, amount, REASON_TREASURY_TRANSFER_IN,
                )
                return True

    async def get_donation_leaderboard(
        self, clan_id: int, limit: int = 10
    ) -> list[tuple[int, int]]:
        """(user_id, totale_donato) ordinato per totale decrescente —
        per la 'classifica membri clan' richiesta nei pannelli.
        Somma solo le donazioni vere (reason='donation'), non i
        movimenti di sistema."""
        rows = await self._pool.fetch(
            """
            SELECT user_id, SUM(amount) AS totale
            FROM clan_treasury_ledger
            WHERE clan_id = $1 AND reason = $2 AND user_id IS NOT NULL
            GROUP BY user_id
            ORDER BY totale DESC
            LIMIT $3
            """,
            clan_id, REASON_DONATION, limit,
        )
        return [(r["user_id"], r["totale"]) for r in rows]


def _get_pool():
    from core.database import db
    return db.pool


guild_clan_repo = GuildClanRepository(pool_provider=_get_pool)
