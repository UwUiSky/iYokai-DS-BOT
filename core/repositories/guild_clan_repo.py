"""
core/repositories/guild_clan_repo.py
========================================
Persistenza delle gilde/clan: gilde, membri con il loro ruolo, tesoreria
con lo storico dei movimenti, XP di gilda (totale e del mese). Un utente
sta in una sola gilda per server (vincolo unico, migrazione 0018).
Ogni operazione sui coin ha il controllo dentro la scrittura.
Una gilda ha un ID globale, non per server: i trasferimenti di
tesoreria tra gilde dello stesso capo possono attraversare server
diversi.
Funzioni coperte: SPEC §15.14
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

import asyncpg

from core.guild_clan_boost_logic import extend_boost_expiry
from core.guild_clan_logic import CREATION_DEFICIT, apply_monthly_treasury_decay
from core.repositories.leveling_repo import spend_coins_in

ROLE_OWNER = "owner"
ROLE_CO_OWNER = "co_owner"
ROLE_ADMIN = "admin"
ROLE_MOD = "mod"
ROLE_MEMBER = "member"

REASON_DONATION = "donation"
REASON_CHANNEL_UNLOCK = "channel_unlock"
REASON_CHANNEL_UNLOCK_REFUND = "channel_unlock_refund"
REASON_MONTHLY_DECAY = "monthly_decay"
REASON_CREATION_DEFICIT = "creation_deficit"
REASON_TREASURY_TRANSFER_IN = "treasury_transfer_in"
REASON_TREASURY_TRANSFER_OUT = "treasury_transfer_out"
REASON_GUILD_BOOST = "guild_boost"
# Scritto dal worker vocale: una riga al minuto per ogni membro in vocale.
REASON_VOICE_TICK = "voice_tick"

DEFAULT_MAX_MEMBERS = 50

# Accredito in tesoreria ($2) che rende ufficiale la gilda quando il
# saldo torna a zero o sopra: stessa regola di
# core.guild_clan_logic.is_creation_deficit_covered, scritta in SQL per
# stare nella stessa UPDATE dell'accredito.
_ACCREDITA_E_UFFICIALIZZA = (
    "treasury_balance = treasury_balance + $2, "
    "officialized = officialized OR (treasury_balance + $2 >= 0)"
)
MAX_MEMBERS_CEILING = 999


class EsitoRuolo(str, Enum):
    """Com'è andato il cambio di ruolo (set_member_role)."""

    FATTO = "fatto"
    CO_OWNER_GIA_PRESO = "co_owner_gia_preso"
    TETTO_RAGGIUNTO = "tetto_raggiunto"


class EsitoIngresso(str, Enum):
    """Com'è andato l'ingresso di un utente in una gilda (add_member)."""

    ENTRATO = "entrato"
    GIA_IN_UNA_GILDA = "gia_in_una_gilda"
    GILDA_PIENA = "gilda_piena"
    GILDA_INESISTENTE = "gilda_inesistente"


class _FondatoreGiaInUnaGilda(Exception):
    """Interna a create_clan: annulla la transazione della creazione."""


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
    total_voice_ticks: int
    guild_boost_expires_at: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class ClanMember:
    clan_id: int
    user_id: int
    role: str
    joined_at: datetime
    boost_expires_at: datetime | None
    last_text_xp_at: datetime | None


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
        ALTER TABLE clans ADD COLUMN IF NOT EXISTS total_voice_ticks BIGINT NOT NULL DEFAULT 0;
        ALTER TABLE clans ADD COLUMN IF NOT EXISTS guild_boost_expires_at TIMESTAMPTZ;

        CREATE TABLE IF NOT EXISTS clan_members (
            clan_id     INTEGER NOT NULL,
            user_id     BIGINT NOT NULL,
            role        TEXT NOT NULL,
            joined_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (clan_id, user_id)
        );

        ALTER TABLE clan_members ADD COLUMN IF NOT EXISTS boost_expires_at TIMESTAMPTZ;
        ALTER TABLE clan_members ADD COLUMN IF NOT EXISTS last_text_xp_at TIMESTAMPTZ;

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

        -- Classifica MENSILE di gilda (SPEC.md §15.10, variante
        -- mancante rispetto a clans.total_xp che è cumulativo per
        -- sempre) — stesso pattern di leveling_activity per la
        -- classifica personale: un periodo è semplicemente una nuova
        -- riga (period_key), NESSUN reset schedulato, il totale
        -- cumulativo in clans.total_xp resta l'unica fonte "di
        -- sempre" e non viene mai toccato da questa tabella.
        CREATE TABLE IF NOT EXISTS clan_monthly_xp (
            clan_id     INTEGER NOT NULL,
            guild_id    BIGINT NOT NULL,
            period_key  TEXT NOT NULL,
            xp_gained   BIGINT NOT NULL DEFAULT 0,
            PRIMARY KEY (clan_id, period_key)
        );

        CREATE INDEX IF NOT EXISTS idx_clan_monthly_xp_classifica
            ON clan_monthly_xp (guild_id, period_key, xp_gained DESC);
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
            total_voice_ticks=row["total_voice_ticks"],
            guild_boost_expires_at=row["guild_boost_expires_at"],
            created_at=row["created_at"],
        )

    def _row_to_member(self, row) -> ClanMember:
        return ClanMember(
            clan_id=row["clan_id"],
            user_id=row["user_id"],
            role=row["role"],
            joined_at=row["joined_at"],
            boost_expires_at=row["boost_expires_at"],
            last_text_xp_at=row["last_text_xp_at"],
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
    ) -> int | None:
        """
        Il saldo tesoreria parte a -CREATION_DEFICIT (in deficit) —
        il clan esiste già (categoria/canali possono essere creati
        subito), ma non è 'ufficializzato' finché il saldo non torna
        a >= 0 entro officialize_deadline. Il founder viene aggiunto
        automaticamente come owner nella stessa transazione: un clan
        senza il suo stesso owner tra i membri sarebbe uno stato
        incoerente anche solo per un istante.

        Restituisce None, senza scrivere nulla, se nel server esiste
        già una gilda con lo stesso tag o se il fondatore fa già parte
        di una gilda del server: lo decidono i vincoli unici, così due
        creazioni arrivate insieme non passano tutte e due.
        """
        try:
            return await self._create_clan(
                guild_id, tag, name, owner_id, officialize_deadline, max_members
            )
        except _FondatoreGiaInUnaGilda:
            return None

    async def _create_clan(
        self,
        guild_id: int,
        tag: str,
        name: str,
        owner_id: int,
        officialize_deadline: datetime,
        max_members: int,
    ) -> int | None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                clan_id = await conn.fetchval(
                    """
                    INSERT INTO clans
                        (guild_id, tag, name, owner_id, treasury_balance,
                         officialize_deadline, max_members)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (guild_id, tag) DO NOTHING
                    RETURNING id
                    """,
                    guild_id, tag, name, owner_id, -CREATION_DEFICIT,
                    officialize_deadline, max_members,
                )
                if clan_id is None:
                    return None

                fondatore = await conn.fetchval(
                    """
                    INSERT INTO clan_members (clan_id, user_id, role, guild_id)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (guild_id, user_id) DO NOTHING
                    RETURNING user_id
                    """,
                    clan_id, owner_id, ROLE_OWNER, guild_id,
                )
                if fondatore is None:
                    raise _FondatoreGiaInUnaGilda

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
        """Rende ufficiale la gilda. Donazioni e trasferimenti lo fanno
        da soli; questo serve al controllo delle scadenze per le gilde
        con il debito già coperto rimaste "non ufficiali"."""
        await self._pool.execute("UPDATE clans SET officialized = true WHERE id = $1", clan_id)

    async def get_unofficialized_expired(self, now: datetime) -> list[Clan]:
        """Clan ancora non ufficializzati la cui finestra di 24h è
        scaduta. Chi chiama guarda il saldo: debito coperto, la gilda
        va resa ufficiale; debito aperto, va cancellata."""
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

    async def unlock_channel(self, clan_id: int, expected_unlocked: int, cost: int) -> bool:
        """
        Compra il prossimo canale extra: toglie `cost` dalla tesoreria e
        aumenta di uno i canali sbloccati, con UNA sola UPDATE che
        contiene i controlli (BUG-14). Riesce solo se il saldo basta e
        se i canali sbloccati sono ancora `expected_unlocked`: così un
        doppio clic non compra due canali al prezzo del primo. False,
        senza scrivere nulla, in caso contrario.
        """
        if cost <= 0:
            raise ValueError("Il costo del canale deve essere positivo.")

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                aggiornato = await conn.fetchval(
                    """
                    UPDATE clans
                    SET treasury_balance = treasury_balance - $3,
                        channels_unlocked = channels_unlocked + 1
                    WHERE id = $1 AND channels_unlocked = $2 AND treasury_balance >= $3
                    RETURNING id
                    """,
                    clan_id, expected_unlocked, cost,
                )
                if aggiornato is None:
                    return False
                await conn.execute(
                    """
                    INSERT INTO clan_treasury_ledger (clan_id, user_id, amount, reason)
                    VALUES ($1, NULL, $2, $3)
                    """,
                    clan_id, -cost, REASON_CHANNEL_UNLOCK,
                )
                return True

    async def refund_channel_unlock(self, clan_id: int, cost: int) -> None:
        """
        Annulla un unlock_channel appena fatto, quando Discord non ha
        creato il canale: restituisce il costo alla tesoreria e toglie
        il canale dal conteggio. Il rimborso resta nello storico.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE clans
                    SET treasury_balance = treasury_balance + $2,
                        channels_unlocked = GREATEST(channels_unlocked - 1, 0)
                    WHERE id = $1
                    """,
                    clan_id, cost,
                )
                await conn.execute(
                    """
                    INSERT INTO clan_treasury_ledger (clan_id, user_id, amount, reason)
                    VALUES ($1, NULL, $2, $3)
                    """,
                    clan_id, cost, REASON_CHANNEL_UNLOCK_REFUND,
                )

    async def add_voice_ticks(self, clan_id: int, count: int = 1) -> None:
        """Accredita `count` tick vocali ACCUMULATI dalla gilda (uno
        al minuto per membro attivo, indipendentemente dal
        decadimento/tetto giornaliero che riducono solo il guadagno
        XP/coin — la presenza in vocale conta comunque) — usata dal
        requisito ore vocali per lo sblocco canali extra, MAI dalla
        ricompensa XP/coin (quella resta `add_xp`/`apply_treasury_
        delta`)."""
        if count <= 0:
            raise ValueError("count deve essere positivo.")
        await self._pool.execute(
            "UPDATE clans SET total_voice_ticks = total_voice_ticks + $2 WHERE id = $1",
            clan_id, count,
        )

    async def set_guild_boost_expiry(self, clan_id: int, expires_at: datetime) -> None:
        """Nuova scadenza del boost DI GILDA (SPEC.md §15.14, ×2 su
        XP/coin per TUTTI i membri finché attivo) — il chiamante
        calcola la scadenza con `extend_boost_expiry` PRIMA di
        chiamare questo metodo (che qui scrive solo, non decide)."""
        await self._pool.execute(
            "UPDATE clans SET guild_boost_expires_at = $2 WHERE id = $1", clan_id, expires_at
        )

    # ----------------------------------------------------------------
    # Membri
    # ----------------------------------------------------------------
    async def add_member(
        self, clan_id: int, user_id: int, role: str = ROLE_MEMBER
    ) -> EsitoIngresso:
        """
        Fa entrare un utente nella gilda, con i controlli dentro la
        stessa transazione: la riga della gilda è bloccata mentre si
        contano i posti (due ingressi insieme non superano il tetto), e
        "una sola gilda per server" lo decide il vincolo unico su
        (guild_id, user_id).
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                gilda = await conn.fetchrow(
                    "SELECT guild_id, max_members FROM clans WHERE id = $1 FOR UPDATE", clan_id
                )
                if gilda is None:
                    return EsitoIngresso.GILDA_INESISTENTE

                presenti = await conn.fetchval(
                    "SELECT COUNT(*) FROM clan_members WHERE clan_id = $1", clan_id
                )
                if presenti >= gilda["max_members"]:
                    return EsitoIngresso.GILDA_PIENA

                entrato = await conn.fetchval(
                    """
                    INSERT INTO clan_members (clan_id, user_id, role, guild_id)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (guild_id, user_id) DO NOTHING
                    RETURNING user_id
                    """,
                    clan_id, user_id, role, gilda["guild_id"],
                )
                if entrato is None:
                    return EsitoIngresso.GIA_IN_UNA_GILDA
                return EsitoIngresso.ENTRATO

    async def remove_member(self, clan_id: int, user_id: int) -> bool:
        """Toglie il membro dalla gilda. Se era il co-owner, il posto si libera."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE clans SET co_owner_id = NULL WHERE id = $1 AND co_owner_id = $2",
                    clan_id, user_id,
                )
                result = await conn.execute(
                    "DELETE FROM clan_members WHERE clan_id = $1 AND user_id = $2",
                    clan_id, user_id,
                )
                return result.endswith(" 1")

    async def set_member_role(
        self, clan_id: int, user_id: int, role: str, max_with_role: int | None = None
    ) -> EsitoRuolo:
        """
        Cambia il ruolo di un membro. Il tetto (`max_with_role`, per
        admin e mod) si controlla qui dentro, con la riga della gilda
        bloccata: due promozioni arrivate insieme si mettono in fila e
        la seconda vede il conteggio già aggiornato. Chi ha già il
        ruolo non conta come nuovo posto. Il co-owner è uno solo: il
        posto (clans.co_owner_id) si prende con una UPDATE che riesce
        solo se è libero. Se non si può, non scrive nulla.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT 1 FROM clans WHERE id = $1 FOR UPDATE", clan_id)
                if max_with_role is not None:
                    occupati = await conn.fetchval(
                        "SELECT COUNT(*) FROM clan_members "
                        "WHERE clan_id = $1 AND role = $2 AND user_id <> $3",
                        clan_id, role, user_id,
                    )
                    if occupati >= max_with_role:
                        return EsitoRuolo.TETTO_RAGGIUNTO
                if role == ROLE_CO_OWNER:
                    posto_preso = await conn.fetchval(
                        """
                        UPDATE clans SET co_owner_id = $2
                        WHERE id = $1 AND (co_owner_id IS NULL OR co_owner_id = $2)
                        RETURNING id
                        """,
                        clan_id, user_id,
                    )
                    if posto_preso is None:
                        return EsitoRuolo.CO_OWNER_GIA_PRESO
                else:
                    await conn.execute(
                        "UPDATE clans SET co_owner_id = NULL WHERE id = $1 AND co_owner_id = $2",
                        clan_id, user_id,
                    )
                await conn.execute(
                    "UPDATE clan_members SET role = $3 WHERE clan_id = $1 AND user_id = $2",
                    clan_id, user_id, role,
                )
                return EsitoRuolo.FATTO

    async def buy_member_boost(
        self, guild_id: int, clan_id: int, user_id: int, cost: int, now: datetime
    ) -> datetime | None:
        """
        Boost individuale: toglie le coin personali e scrive la nuova
        scadenza nella stessa transazione. La scadenza si calcola sul
        valore letto con la riga bloccata, quindi due acquisti insieme
        si sommano. None (senza scrivere nulla) se le coin non bastano.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                attuale = await conn.fetchrow(
                    "SELECT boost_expires_at FROM clan_members "
                    "WHERE clan_id = $1 AND user_id = $2 FOR UPDATE",
                    clan_id, user_id,
                )
                if attuale is None:
                    return None
                if not await spend_coins_in(conn, guild_id, user_id, cost):
                    return None
                nuova = extend_boost_expiry(attuale["boost_expires_at"], now)
                await conn.execute(
                    "UPDATE clan_members SET boost_expires_at = $3 "
                    "WHERE clan_id = $1 AND user_id = $2",
                    clan_id, user_id, nuova,
                )
                return nuova

    async def buy_guild_boost(self, clan_id: int, cost: int, now: datetime) -> datetime | None:
        """
        Boost di gilda: spesa dalla tesoreria, registro e nuova scadenza
        nella stessa transazione, con la riga della gilda bloccata (due
        acquisti insieme si sommano). None se la tesoreria non basta.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                riga = await conn.fetchrow(
                    "SELECT treasury_balance, guild_boost_expires_at FROM clans "
                    "WHERE id = $1 FOR UPDATE",
                    clan_id,
                )
                if riga is None or riga["treasury_balance"] < cost:
                    return None
                nuova = extend_boost_expiry(riga["guild_boost_expires_at"], now)
                await conn.execute(
                    "UPDATE clans SET treasury_balance = treasury_balance - $2, "
                    "guild_boost_expires_at = $3 WHERE id = $1",
                    clan_id, cost, nuova,
                )
                await conn.execute(
                    "INSERT INTO clan_treasury_ledger (clan_id, user_id, amount, reason) "
                    "VALUES ($1, NULL, $2, $3)",
                    clan_id, -cost, REASON_GUILD_BOOST,
                )
                return nuova

    async def donate_from_member(
        self, guild_id: int, clan_id: int, user_id: int, amount: int
    ) -> int | None:
        """
        Donazione completa in UNA transazione: toglie le coin personali
        (UPDATE condizionata), accredita la tesoreria e scrive il
        registro. Se un passo fallisce torna tutto indietro. None se le
        coin personali non bastano. Restituisce il nuovo saldo di gilda.
        """
        if amount <= 0:
            raise ValueError("L'importo donato deve essere positivo.")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                if not await spend_coins_in(conn, guild_id, user_id, amount):
                    return None
                return await self._donate_in(conn, clan_id, user_id, amount)

    async def set_member_boost_expiry(self, clan_id: int, user_id: int, expires_at: datetime) -> None:
        """Nuova scadenza del boost INDIVIDUALE (SPEC.md §15.14, ×2
        sul proprio tick vocale di gilda finché attivo) — il
        chiamante calcola la scadenza con `extend_boost_expiry`
        PRIMA di chiamare questo metodo (che qui scrive solo)."""
        await self._pool.execute(
            "UPDATE clan_members SET boost_expires_at = $3 WHERE clan_id = $1 AND user_id = $2",
            clan_id, user_id, expires_at,
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
        utente può stare in un solo clan per server (vincolo unico su
        clan_members, migrazione 0018)."""
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
        Se la donazione copre il debito di creazione, la gilda diventa
        ufficiale nella stessa scrittura. Restituisce il nuovo saldo.
        """
        if amount <= 0:
            raise ValueError("L'importo donato deve essere positivo.")

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                return await self._donate_in(conn, clan_id, user_id, amount)

    @staticmethod
    async def _donate_in(conn: asyncpg.Connection, clan_id: int, user_id: int, amount: int) -> int:
        row = await conn.fetchrow(
            f"UPDATE clans SET {_ACCREDITA_E_UFFICIALIZZA} "
            "WHERE id = $1 RETURNING treasury_balance",
            clan_id, amount,
        )
        await conn.execute(
            "INSERT INTO clan_treasury_ledger (clan_id, user_id, amount, reason) "
            "VALUES ($1, $2, $3, $4)",
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

    async def apply_monthly_decay(self, clan_id: int, period: str) -> tuple[int, int]:
        """
        Applica il decadimento mensile del 10% (core.guild_clan_
        logic.apply_monthly_treasury_decay) e marca il periodo come
        coperto, atomicamente (FOR UPDATE) — la percentuale è
        calcolata QUI, sul saldo letto sotto lock, non passata dal
        chiamante: altrimenti tra la lettura fatta dal chiamante e
        questa scrittura il saldo potrebbe essere cambiato da una
        spesa o una donazione nel frattempo. Restituisce
        (saldo_prima, saldo_dopo) — stesso pattern di
        LevelingRepository.apply_weekly_decay: il chiamante (il
        worker) DEVE calcolare il delta da QUESTA coppia, non da un
        valore letto prima del lock, altrimenti una donazione
        avvenuta nel frattempo produrrebbe un delta sbagliato verso
        la cassa di server (bug reale trovato e corretto: il worker
        usava il saldo "stale" della lista non bloccata).
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
                return saldo_attuale, nuovo_saldo

    async def add_xp(self, clan_id: int, amount: int) -> None:
        """XP di gilda accumulata (per la classifica clan richiesta
        nei pannelli) - SEPARATA dai coin di tesoreria, un clan
        guadagna entrambi ad ogni tick vocale ma sono due assi
        diversi (l'XP non si spende mai, i coin sì). Traccia ANCHE la
        quota del mese corrente in clan_monthly_xp (SPEC.md §15.10,
        variante mensile) — il totale cumulativo qui sopra non viene
        mai azzerato, la classifica mensile vive tutta in quella
        tabella separata, stesso pattern di leveling_activity."""
        from core.leveling_logic import period_key

        if amount <= 0:
            raise ValueError("L'importo XP da aggiungere deve essere positivo.")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                guild_id = await conn.fetchval(
                    "UPDATE clans SET total_xp = total_xp + $2 WHERE id = $1 RETURNING guild_id",
                    clan_id, amount,
                )
                await conn.execute(
                    """
                    INSERT INTO clan_monthly_xp (clan_id, guild_id, period_key, xp_gained)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (clan_id, period_key)
                        DO UPDATE SET xp_gained = clan_monthly_xp.xp_gained + EXCLUDED.xp_gained
                    """,
                    clan_id, guild_id, period_key(), amount,
                )

    async def apply_text_tick(self, clan_id: int, user_id: int) -> bool:
        """
        Lato TESTUALE del guadagno ×2 di gilda (SPEC.md §15.14) —
        controparte di `clan_voice_activity_repo.apply_tick` ma per i
        messaggi: stesso cooldown del testo normale (`core.leveling_
        logic.can_earn_text_xp`, 60s) e stesso importo ×2 letterale
        (`core.guild_clan_logic.TEXT_TICK_XP`, il doppio di `core.
        leveling_logic.TEXT_XP_AMOUNT`). NIENTE coin da testo (come
        nel normale) e NESSUN boost applicato — il boost individuale
        di gilda è scoped ESPLICITAMENTE al solo tick vocale
        (confermato dall'utente in Fase 54), il boost di gilda idem.
        Tutto dentro una transazione con FOR UPDATE sulla riga membro,
        stesso pattern anti-race di `LevelingRepository.add_text_xp`.
        Restituisce True se l'XP è stata assegnata (cooldown scaduto),
        False se il messaggio è arrivato troppo presto.
        """
        from core.guild_clan_logic import TEXT_TICK_XP
        from core.leveling_logic import can_earn_text_xp
        from core.leveling_logic import period_key

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT last_text_xp_at FROM clan_members
                    WHERE clan_id = $1 AND user_id = $2 FOR UPDATE
                    """,
                    clan_id, user_id,
                )
                if row is None:
                    return False

                now = datetime.now(timezone.utc)
                if not can_earn_text_xp(row["last_text_xp_at"], now):
                    return False

                await conn.execute(
                    "UPDATE clan_members SET last_text_xp_at = $3 WHERE clan_id = $1 AND user_id = $2",
                    clan_id, user_id, now,
                )
                guild_id = await conn.fetchval(
                    "UPDATE clans SET total_xp = total_xp + $2 WHERE id = $1 RETURNING guild_id",
                    clan_id, TEXT_TICK_XP,
                )
                await conn.execute(
                    """
                    INSERT INTO clan_monthly_xp (clan_id, guild_id, period_key, xp_gained)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (clan_id, period_key)
                        DO UPDATE SET xp_gained = clan_monthly_xp.xp_gained + EXCLUDED.xp_gained
                    """,
                    clan_id, guild_id, period_key(), TEXT_TICK_XP,
                )
                return True

    async def get_clan_leaderboard(self, guild_id: int, limit: int = 10) -> list[Clan]:
        """Classifica clan del server per XP totale ALL-TIME (mai
        azzerata) — per la 'classifica clan' richiesta esplicitamente
        nei pannelli. Per la variante MENSILE vedi
        get_monthly_clan_leaderboard."""
        rows = await self._pool.fetch(
            "SELECT * FROM clans WHERE guild_id = $1 ORDER BY total_xp DESC LIMIT $2",
            guild_id, limit,
        )
        return [self._row_to_clan(r) for r in rows]

    async def get_monthly_clan_leaderboard(
        self, guild_id: int, period: str | None = None, limit: int = 10
    ) -> list[tuple[Clan, int]]:
        """
        Classifica clan del server per XP guadagnata SOLO in un
        periodo (default: il mese corrente, `core.leveling_logic.
        period_key()`) — SPEC.md §15.10, variante mensile via
        period_key, NESSUN reset schedulato (stesso pattern di
        leveling_repo.top_xp_period per la classifica personale).
        Restituisce (Clan, xp_guadagnata_nel_periodo) — un clan senza
        nessuna riga in clan_monthly_xp per quel periodo (nessuna
        attività) semplicemente non appare, non con 0.
        """
        from core.leveling_logic import period_key as _period_key

        rows = await self._pool.fetch(
            """
            SELECT c.*, m.xp_gained AS xp_gained
            FROM clan_monthly_xp m
            JOIN clans c ON c.id = m.clan_id
            WHERE m.guild_id = $1 AND m.period_key = $2 AND m.xp_gained > 0
            ORDER BY m.xp_gained DESC
            LIMIT $3
            """,
            guild_id, period or _period_key(), limit,
        )
        return [(self._row_to_clan(r), r["xp_gained"]) for r in rows]

    async def list_clans_owned_by(self, owner_id: int) -> list[Clan]:
        """TUTTI i clan (su QUALUNQUE server) di cui `owner_id` è il
        Capo Clan — NESSUNO scoping per guild_id, apposta: serve a
        `transfer_between_treasuries` per trovare l'altra gilda dello
        stesso owner anche quando è su un server diverso (i
        trasferimenti di tesoreria tra clan dello STESSO owner sono
        ammessi ANCHE cross-server, confermato esplicitamente
        dall'utente — l'unica condizione è lo stesso owner, mai lo
        stesso server)."""
        rows = await self._pool.fetch(
            "SELECT * FROM clans WHERE owner_id = $1 ORDER BY created_at", owner_id
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
                # Le due righe si bloccano sempre nello stesso ordine
                # (ID più basso per primo): così A→B e B→A partiti
                # insieme si mettono in fila invece di bloccarsi a
                # vicenda.
                righe = await conn.fetch(
                    """
                    SELECT id, treasury_balance FROM clans
                    WHERE id = ANY($1::int[]) ORDER BY id FOR UPDATE
                    """,
                    [from_clan_id, to_clan_id],
                )
                saldi = {r["id"]: r["treasury_balance"] for r in righe}
                if to_clan_id not in saldi:
                    return False
                if saldi.get(from_clan_id, 0) < amount:
                    return False

                await conn.execute(
                    "UPDATE clans SET treasury_balance = treasury_balance - $2 WHERE id = $1",
                    from_clan_id, amount,
                )
                # BUG-15: se il trasferimento copre il debito di creazione,
                # la gilda di destinazione diventa ufficiale qui, nella
                # stessa scrittura.
                await conn.execute(
                    f"UPDATE clans SET {_ACCREDITA_E_UFFICIALIZZA} WHERE id = $1",
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

    async def list_ledger(self, clan_id: int, limit: int = 5) -> list[TreasuryLedgerEntry]:
        """
        Gli ultimi movimenti della tesoreria, dal più recente. I tick
        vocali non si contano: sono una riga al minuto per membro e
        coprirebbero tutto il resto (indice parziale, migrazione 0017).
        """
        rows = await self._pool.fetch(
            """
            SELECT * FROM clan_treasury_ledger
            WHERE clan_id = $1 AND reason <> 'voice_tick'
            ORDER BY id DESC
            LIMIT $2
            """,
            clan_id, limit,
        )
        return [self._row_to_ledger_entry(r) for r in rows]

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
