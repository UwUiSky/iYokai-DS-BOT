"""
core/repositories/leveling_repo.py
=====================================
Persistenza di XP, livelli, coin e classifiche.
- leveling_totals: lo stato per utente (XP e coin di sempre, livello,
  attese di daily/work, conteggio dei minuti vocali, decadimento).
- leveling_activity: una riga per utente e per mese (period_key) con
  quanto guadagnato in quel mese. La classifica mensile legge da qui e
  non serve nessun azzeramento: un mese nuovo è una chiave nuova.
Le funzioni *_in lavorano su una connessione di chi chiama, per mettere
più movimenti di coin nella stessa transazione.
Funzioni coperte: SPEC §15.1–15.3, §15.15
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

import asyncpg

from core.leveling_logic import (
    NOMI_TEMI_RANK_CARD,
    colore_valido,
    apply_weekly_personal_decay,
    can_earn_text_xp,
    compute_voice_minute,
    did_level_up,
    monete_dopo_modifica,
    xp_dopo_modifica,
    level_for_xp,
    period_key,
    TEXT_XP_AMOUNT,
    TEXT_XP_COOLDOWN_SECONDS,
    LevelingSettings,
    xp_con_moltiplicatore,
)


@dataclass(frozen=True)
class TextXpResult:
    granted: bool
    new_xp_total: int
    leveled_up: bool
    new_level: int
    previous_level: int | None = None  # il livello prima del guadagno, se si sa


@dataclass(frozen=True)
class VoiceMinuteGrant:
    xp_granted: int
    coins_granted: int
    leveled_up: bool
    new_level: int
    previous_level: int | None = None  # il livello prima del minuto, se si sa


@dataclass(frozen=True)
class UserTotals:
    guild_id: int
    user_id: int
    xp_total: int
    level: int
    coins_total: int
    last_daily_at: datetime | None
    last_work_at: datetime | None


@dataclass(frozen=True)
class LeaderboardEntry:
    user_id: int
    amount: int


@dataclass(frozen=True)
class ModificaXp:
    xp_prima: int
    livello_prima: int
    xp_dopo: int
    livello_dopo: int


@dataclass(frozen=True)
class ModificaMonete:
    prima: int
    dopo: int


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS leveling_totals (
            guild_id                  BIGINT NOT NULL,
            user_id                   BIGINT NOT NULL,
            xp_total                  BIGINT NOT NULL DEFAULT 0,
            level                     INTEGER NOT NULL DEFAULT 0,
            coins_total                BIGINT NOT NULL DEFAULT 0,
            last_text_xp_at           TIMESTAMPTZ,
            last_daily_at             TIMESTAMPTZ,
            last_work_at              TIMESTAMPTZ,
            voice_channel_id          BIGINT,
            voice_consecutive_minutes INTEGER NOT NULL DEFAULT 0,
            voice_minutes_today       INTEGER NOT NULL DEFAULT 0,
            voice_activity_date       DATE,
            last_weekly_decay_period  TEXT,
            PRIMARY KEY (guild_id, user_id)
        );

        -- Aggiunta dopo la creazione iniziale della tabella (decadimento
        -- settimanale dei coin personali, SPEC.md §15.15) — idempotente,
        -- sicura da rilanciare su un database già esistente.
        ALTER TABLE leveling_totals
            ADD COLUMN IF NOT EXISTS last_weekly_decay_period TEXT;

        CREATE TABLE IF NOT EXISTS leveling_activity (
            guild_id   BIGINT NOT NULL,
            user_id    BIGINT NOT NULL,
            period_key TEXT NOT NULL,
            xp         BIGINT NOT NULL DEFAULT 0,
            coins      BIGINT NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, user_id, period_key)
        );

        -- Le classifiche ordinano per xp/coins DESC filtrando su
        -- guild_id (e, per quella mensile, anche su period_key):
        -- questi indici servono esattamente quella query.
        CREATE INDEX IF NOT EXISTS idx_leveling_totals_guild_xp
            ON leveling_totals (guild_id, xp_total DESC);
        CREATE INDEX IF NOT EXISTS idx_leveling_totals_guild_coins
            ON leveling_totals (guild_id, coins_total DESC);
        CREATE INDEX IF NOT EXISTS idx_leveling_activity_guild_period_xp
            ON leveling_activity (guild_id, period_key, xp DESC);
        CREATE INDEX IF NOT EXISTS idx_leveling_activity_guild_period_coins
            ON leveling_activity (guild_id, period_key, coins DESC);
        """
    )


# Utenti con saldo > 1 non ancora decaduti nel periodo $1. Equivale a
# "last_weekly_decay_period IS DISTINCT FROM $1", ma scritta con IS NULL,
# < e > perché solo così Postgres può cercare nell'indice parziale
# idx_leveling_totals_weekly_decay_due invece di leggere tutta la tabella
# a ogni giro orario. In più: solo righe nate prima di $2 (chi è appena
# arrivato non decade); le righe senza data sono quelle di prima della
# migrazione 0019 e valgono come vecchie.
CONDIZIONE_DA_DECADERE = """
    coins_total > 1
      AND (
          last_weekly_decay_period IS NULL
          OR last_weekly_decay_period < $1
          OR last_weekly_decay_period > $1
      )
      AND (created_at IS NULL OR created_at < $2)
"""

QUERY_UTENTI_DA_DECADERE = (
    "SELECT guild_id, user_id FROM leveling_totals WHERE " + CONDIZIONE_DA_DECADERE
)

# Un solo UPDATE per server (PERF-6). Il 10% è arrotondato "al pari" nei
# casi di mezzo (5, 15, 25...) come fa round() di Python in
# core.leveling_logic.apply_weekly_personal_decay: un test confronta le due
# strade su centinaia di saldi.
QUERY_DECADIMENTO_DEL_SERVER = (
    """
    WITH da_decadere AS (
        SELECT user_id, coins_total AS prima,
               GREATEST(
                   coins_total - CASE WHEN coins_total % 10 = 5
                                      THEN 2 * round(coins_total::numeric / 20)
                                      ELSE round(coins_total::numeric / 10) END,
                   1
               )::bigint AS dopo
        FROM leveling_totals
        WHERE guild_id = $3 AND
    """
    + CONDIZIONE_DA_DECADERE
    + """
        ORDER BY user_id
        FOR UPDATE
    ), aggiornati AS (
        UPDATE leveling_totals AS t
        SET coins_total = d.dopo, last_weekly_decay_period = $1
        FROM da_decadere AS d
        WHERE t.guild_id = $3 AND t.user_id = d.user_id
        RETURNING d.prima - d.dopo AS tolti
    )
    SELECT count(*) AS utenti, COALESCE(sum(tolti), 0) AS tolti FROM aggiornati
    """
)



# ----------------------------------------------------------------------
# Movimenti di coin su una connessione già aperta. Servono a chi deve
# mettere più scritture nella stessa transazione (acquisto dello shop,
# premi dalla cassa): il controllo del saldo sta dentro la UPDATE.
# ----------------------------------------------------------------------
async def spend_coins_in(
    conn: asyncpg.Connection, guild_id: int, user_id: int, amount: int
) -> bool:
    """Toglie `amount` coin solo se il saldo basta. False se non basta."""
    if amount <= 0:
        raise ValueError("L'importo da spendere deve essere positivo.")
    saldo = await conn.fetchval(
        """
        UPDATE leveling_totals SET coins_total = coins_total - $3
        WHERE guild_id = $1 AND user_id = $2 AND coins_total >= $3
        RETURNING coins_total
        """,
        guild_id,
        user_id,
        amount,
    )
    return saldo is not None


async def add_coins_in(
    conn: asyncpg.Connection, guild_id: int, user_id: int, amount: int
) -> int:
    """Aggiunge coin (saldo e classifica del mese). Restituisce il nuovo saldo."""
    saldo = await conn.fetchval(
        """
        INSERT INTO leveling_totals (guild_id, user_id, coins_total)
        VALUES ($1, $2, $3)
        ON CONFLICT (guild_id, user_id) DO UPDATE
            SET coins_total = leveling_totals.coins_total + $3
        RETURNING coins_total
        """,
        guild_id,
        user_id,
        amount,
    )
    await conn.execute(
        """
        INSERT INTO leveling_activity (guild_id, user_id, period_key, coins)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (guild_id, user_id, period_key) DO UPDATE
            SET coins = leveling_activity.coins + $4
        """,
        guild_id,
        user_id,
        period_key(),
        amount,
    )
    return saldo


async def refund_coins_in(
    conn: asyncpg.Connection, guild_id: int, user_id: int, amount: int
) -> None:
    """
    Restituisce coin spesi poco prima. Tocca solo il saldo: un rimborso
    non è un guadagno e non deve contare nella classifica del mese.
    """
    await conn.execute(
        """
        INSERT INTO leveling_totals (guild_id, user_id, coins_total)
        VALUES ($1, $2, $3)
        ON CONFLICT (guild_id, user_id) DO UPDATE
            SET coins_total = leveling_totals.coins_total + $3
        """,
        guild_id,
        user_id,
        amount,
    )


class LevelingRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def get_totals(self, guild_id: int, user_id: int) -> UserTotals:
        row = await self._pool.fetchrow(
            """
            SELECT xp_total, level, coins_total, last_daily_at, last_work_at
            FROM leveling_totals WHERE guild_id = $1 AND user_id = $2
            """,
            guild_id,
            user_id,
        )
        if row is None:
            return UserTotals(guild_id, user_id, 0, 0, 0, None, None)
        return UserTotals(
            guild_id=guild_id,
            user_id=user_id,
            xp_total=row["xp_total"],
            level=row["level"],
            coins_total=row["coins_total"],
            last_daily_at=row["last_daily_at"],
            last_work_at=row["last_work_at"],
        )

    async def _add_period_activity(
        self, conn: asyncpg.Connection, guild_id: int, user_id: int, xp: int, coins: int
    ) -> None:
        if xp == 0 and coins == 0:
            return
        await conn.execute(
            """
            INSERT INTO leveling_activity (guild_id, user_id, period_key, xp, coins)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (guild_id, user_id, period_key) DO UPDATE
                SET xp = leveling_activity.xp + EXCLUDED.xp,
                    coins = leveling_activity.coins + EXCLUDED.coins
            """,
            guild_id,
            user_id,
            period_key(),
            xp,
            coins,
        )

    async def add_text_xp(
        self,
        guild_id: int,
        user_id: int,
        amount: int = TEXT_XP_AMOUNT,
        cooldown_seconds: int = TEXT_XP_COOLDOWN_SECONDS,
        max_level: int = 0,
    ) -> TextXpResult:
        """
        Assegna `amount` XP testuale se l'attesa (`cooldown_seconds`, per
        server) lo consente. Tutto dentro
        una transazione per evitare che due messaggi arrivati quasi
        insieme (stesso utente, connessioni diverse del bot in un
        futuro multi-processo) leggano lo stesso "last_text_xp_at"
        prima che l'uno o l'altro lo aggiorni.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                sql_riga = """
                    SELECT xp_total, last_text_xp_at FROM leveling_totals
                    WHERE guild_id = $1 AND user_id = $2 FOR UPDATE
                    """
                row = await conn.fetchrow(sql_riga, guild_id, user_id)
                if row is None:
                    # Riga nuova: si crea (vuota) prima di scrivere, così chi arriva
                    # insieme (XP vocale) la trova e aspetta, invece di sovrascriverla.
                    await conn.execute(
                        "INSERT INTO leveling_totals (guild_id, user_id) VALUES ($1, $2) "
                        "ON CONFLICT DO NOTHING",
                        guild_id,
                        user_id,
                    )
                    row = await conn.fetchrow(sql_riga, guild_id, user_id)
                xp_before = row["xp_total"] if row else 0
                last_xp_at = row["last_text_xp_at"] if row else None

                now = datetime.now(timezone.utc)
                # Un moltiplicatore che porta l'XP a 0 non fa partire l'attesa.
                if amount <= 0 or not can_earn_text_xp(last_xp_at, now, cooldown_seconds):
                    return TextXpResult(
                        granted=False, new_xp_total=xp_before, leveled_up=False,
                        new_level=level_for_xp(xp_before, max_level),
                    )

                xp_after = xp_before + amount
                leveled_up, new_level = did_level_up(xp_before, xp_after, max_level)

                await conn.execute(
                    """
                    INSERT INTO leveling_totals (guild_id, user_id, xp_total, level, last_text_xp_at)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (guild_id, user_id) DO UPDATE
                        SET xp_total = $3, level = $4, last_text_xp_at = $5
                    """,
                    guild_id,
                    user_id,
                    xp_after,
                    new_level,
                    now,
                )
                await self._add_period_activity(conn, guild_id, user_id, amount, 0)

                return TextXpResult(
                    granted=True, new_xp_total=xp_after, leveled_up=leveled_up,
                    new_level=new_level, previous_level=level_for_xp(xp_before, max_level),
                )

    async def add_voice_minutes(
        self,
        guild_id: int,
        presenze: list[tuple[int, int, bool]],
        impostazioni: LevelingSettings | None = None,
        moltiplicatori: dict[int, float] | None = None,
    ) -> dict[int, VoiceMinuteGrant | None]:
        """
        Registra un minuto di presenza vocale per tutti i presenti di un
        server, in UNA transazione (PERF-4): una lettura bloccante delle
        righe e una scrittura per tutti, non una transazione a testa.
        `presenze` è una lista di (utente, canale corrente, idoneo).
        Se `idoneo` è False (una delle regole anti-farm non è
        soddisfatta) il canale corrente viene comunque tracciato — serve
        per sapere se il PROSSIMO minuto idoneo è un cambio di canale —
        ma non si assegna nulla e il risultato per quell'utente è None.
        Il rollover del contatore giornaliero (mezzanotte UTC) vale per
        tutti, idonei o no. `impostazioni` cambia XP e monete di ogni
        minuto (NF-15); `moltiplicatori` ({utente: fattore}) moltiplica
        solo l'XP. Restituisce {utente: VoiceMinuteGrant | None}.
        """
        impostazioni = impostazioni or LevelingSettings()
        moltiplicatori = moltiplicatori or {}
        tetto = impostazioni.max_level
        if not presenze:
            return {}
        # Giorno in UTC, non nell'ora locale della macchina: il tetto
        # giornaliero deve azzerarsi alla stessa ora per tutti.
        today = datetime.now(timezone.utc).date()
        ordinati = sorted(presenze)  # in ordine di utente: nessuno stallo tra giri
        risultati: dict[int, VoiceMinuteGrant | None] = {}
        scritture = []

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                sql_righe = """
                    SELECT user_id, xp_total, voice_channel_id, voice_consecutive_minutes,
                           voice_minutes_today, voice_activity_date
                    FROM leveling_totals
                    WHERE guild_id = $1 AND user_id = ANY($2::bigint[])
                    ORDER BY user_id FOR UPDATE
                    """
                id_utenti = [u for u, _, _ in ordinati]
                righe = {r["user_id"]: r for r in await conn.fetch(sql_righe, guild_id, id_utenti)}
                mancanti = [u for u in id_utenti if u not in righe]
                if mancanti:
                    # Righe nuove: si creano (vuote, in ordine di utente) prima di
                    # scrivere, così un messaggio arrivato insieme non viene
                    # sovrascritto; poi si rileggono sotto blocco.
                    await conn.execute(
                        "INSERT INTO leveling_totals (guild_id, user_id) "
                        "SELECT $1, u FROM unnest($2::bigint[]) AS u ORDER BY u "
                        "ON CONFLICT DO NOTHING",
                        guild_id,
                        mancanti,
                    )
                    righe = {r["user_id"]: r for r in await conn.fetch(sql_righe, guild_id, id_utenti)}
                for user_id, canale, idoneo in ordinati:
                    row = righe.get(user_id)
                    xp_before = row["xp_total"] if row else 0
                    stored_consecutive = row["voice_consecutive_minutes"] if row else 0
                    # Un nuovo giorno azzera i minuti di oggi, a prescindere
                    # dall'idoneità di questo specifico minuto.
                    minutes_today = (
                        row["voice_minutes_today"]
                        if row and row["voice_activity_date"] == today
                        else 0
                    )
                    if not idoneo:
                        risultati[user_id] = None
                        scritture.append(
                            (guild_id, user_id, xp_before, level_for_xp(xp_before, tetto), 0,
                             canale, stored_consecutive, minutes_today)
                        )
                        continue

                    changed_channel = (row["voice_channel_id"] if row else None) != canale
                    result = compute_voice_minute(stored_consecutive, minutes_today, changed_channel)
                    if result.xp_granted > 0:  # minuto che conta: valgono i numeri del server
                        result = replace(
                            result,
                            xp_granted=xp_con_moltiplicatore(
                                impostazioni.voice_xp_per_minute, moltiplicatori.get(user_id, 1.0)
                            ),
                            coins_granted=impostazioni.voice_coins_per_minute,
                        )
                    xp_after = xp_before + result.xp_granted
                    leveled_up, new_level = did_level_up(xp_before, xp_after, tetto)
                    scritture.append(
                        (guild_id, user_id, xp_after, new_level, result.coins_granted,
                         canale, result.new_consecutive_minutes, result.new_minutes_today)
                    )
                    risultati[user_id] = VoiceMinuteGrant(
                        xp_granted=result.xp_granted,
                        coins_granted=result.coins_granted,
                        leveled_up=leveled_up,
                        new_level=new_level,
                        previous_level=level_for_xp(xp_before, tetto),
                    )

                await conn.executemany(
                    """
                    INSERT INTO leveling_totals
                        (guild_id, user_id, xp_total, level, coins_total,
                         voice_channel_id, voice_consecutive_minutes,
                         voice_minutes_today, voice_activity_date)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::date)
                    ON CONFLICT (guild_id, user_id) DO UPDATE
                        SET xp_total = EXCLUDED.xp_total,
                            level = EXCLUDED.level,
                            coins_total = leveling_totals.coins_total + EXCLUDED.coins_total,
                            voice_channel_id = EXCLUDED.voice_channel_id,
                            voice_consecutive_minutes = EXCLUDED.voice_consecutive_minutes,
                            voice_minutes_today = EXCLUDED.voice_minutes_today,
                            voice_activity_date = EXCLUDED.voice_activity_date
                    """,
                    [riga + (today,) for riga in scritture],
                )
                for user_id, grant in risultati.items():
                    if grant is not None:
                        await self._add_period_activity(
                            conn, guild_id, user_id, grant.xp_granted, grant.coins_granted
                        )
        return risultati

    async def _riga_bloccata(self, conn, guild_id: int, user_id: int, colonna: str) -> int:
        """Il valore di `colonna` con la riga bloccata (creata vuota se manca)."""
        sql = f"SELECT {colonna} FROM leveling_totals WHERE guild_id = $1 AND user_id = $2 FOR UPDATE"
        valore = await conn.fetchval(sql, guild_id, user_id)
        if valore is None:
            await conn.execute(
                "INSERT INTO leveling_totals (guild_id, user_id) VALUES ($1, $2) "
                "ON CONFLICT DO NOTHING",
                guild_id,
                user_id,
            )
            valore = await conn.fetchval(sql, guild_id, user_id)
        return valore

    async def modifica_xp(
        self, guild_id: int, user_id: int, azione: str, valore: int, max_level: int = 0
    ) -> ModificaXp:
        """
        Modifica fatta dallo staff (LIV-064..067): una lettura bloccante e una
        scrittura nella stessa transazione. Non conta come attività del mese.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                xp_prima = await self._riga_bloccata(conn, guild_id, user_id, "xp_total")
                xp_dopo = xp_dopo_modifica(xp_prima, azione, valore, max_level)
                livello_dopo = level_for_xp(xp_dopo, max_level)
                await conn.execute(
                    "UPDATE leveling_totals SET xp_total = $3, level = $4 "
                    "WHERE guild_id = $1 AND user_id = $2",
                    guild_id,
                    user_id,
                    xp_dopo,
                    livello_dopo,
                )
        return ModificaXp(xp_prima, level_for_xp(xp_prima, max_level), xp_dopo, livello_dopo)

    async def modifica_monete(
        self, guild_id: int, user_id: int, azione: str, valore: int
    ) -> ModificaMonete:
        """
        Modifica del saldo fatta dallo staff (ECO-009, ECO-011): mai sotto zero,
        una sola transazione con la riga bloccata. Non conta nella classifica del mese.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                prima = await self._riga_bloccata(conn, guild_id, user_id, "coins_total")
                dopo = monete_dopo_modifica(prima, azione, valore)
                await conn.execute(
                    "UPDATE leveling_totals SET coins_total = $3 WHERE guild_id = $1 AND user_id = $2",
                    guild_id,
                    user_id,
                    dopo,
                )
        return ModificaMonete(prima, dopo)

    async def get_xp_position(self, guild_id: int, user_id: int) -> int | None:
        """
        Posizione in classifica XP di sempre (1 = primo). A pari XP la
        posizione è la stessa. None se l'utente non ha nessuna riga.
        """
        return await self._pool.fetchval(
            """
            SELECT 1 + (
                SELECT count(*) FROM leveling_totals
                WHERE guild_id = $1 AND xp_total > t.xp_total
            )
            FROM leveling_totals AS t WHERE t.guild_id = $1 AND t.user_id = $2
            """,
            guild_id,
            user_id,
        )

    async def get_coins_position(self, guild_id: int, user_id: int) -> int | None:
        """Posizione per coin (1 = più ricco); a pari coin la stessa. None se non ha nessuna riga."""
        return await self._pool.fetchval(
            """
            SELECT 1 + (
                SELECT count(*) FROM leveling_totals
                WHERE guild_id = $1 AND coins_total > t.coins_total
            )
            FROM leveling_totals AS t WHERE t.guild_id = $1 AND t.user_id = $2
            """,
            guild_id,
            user_id,
        )

    # Ritenzione (NF-04): `rank_card_prefs` è per utente, senza server: dato
    # personale di profilo. Va nel registro dei dati (esporta/cancella, F5);
    # finché il registro non c'è nessuno lo ripulisce.
    async def get_rank_card_prefs(self, user_id: int) -> tuple[str | None, str | None]:
        """(colore, tema) scelti per la propria rank card; None dove non scelti."""
        riga = await self._pool.fetchrow(
            "SELECT colore, tema FROM rank_card_prefs WHERE user_id = $1", user_id
        )
        return (riga["colore"], riga["tema"]) if riga else (None, None)

    async def set_rank_card_prefs(
        self, user_id: int, colore: str | None = None, tema: str | None = None
    ) -> None:
        """Cambia solo ciò che viene dato (colore '#RRGGBB' maiuscolo; tema scuro, chiaro, notte)."""
        if colore is not None and colore_valido(colore) != colore:
            raise ValueError("Il colore deve essere nel formato #RRGGBB.")
        if tema is not None and tema not in NOMI_TEMI_RANK_CARD:
            raise ValueError(f"Tema sconosciuto: {tema}")
        await self._pool.execute(
            """
            INSERT INTO rank_card_prefs (user_id, colore, tema) VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE
                SET colore = COALESCE($2, rank_card_prefs.colore),
                    tema = COALESCE($3, rank_card_prefs.tema)
            """,
            user_id,
            colore,
            tema,
        )

    async def reset_rank_card_prefs(self, user_id: int) -> None:
        await self._pool.execute("DELETE FROM rank_card_prefs WHERE user_id = $1", user_id)

    async def add_coins(self, guild_id: int, user_id: int, amount: int) -> int:
        """Aggiunge (o sottrae, con amount negativo) coin. Restituisce il nuovo saldo."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                return await add_coins_in(conn, guild_id, user_id, amount)

    async def gioca(
        self,
        guild_id: int,
        user_id: int,
        puntata: int,
        restituzione: int,
        attesa_secondi: int = 0,
    ) -> int | None:
        """
        Chiude una partita con le monete (NF-40): toglie la puntata e dà la
        restituzione in UNA scrittura, solo se il saldo copre la puntata e
        se è passata l'attesa dall'ultima partita (`attesa_secondi`, decisa
        qui nella stessa UPDATE: due partite insieme non passano entrambe).
        Restituisce il nuovo saldo, o None (senza scrivere) se non si può.
        Le vincite dei giochi non contano nella classifica del mese.
        """
        if puntata <= 0 or restituzione < 0 or attesa_secondi < 0:
            raise ValueError("Puntata, restituzione o attesa non valide.")
        return await self._pool.fetchval(
            """
            UPDATE leveling_totals
            SET coins_total = coins_total - $3 + $4, ultima_partita_at = NOW()
            WHERE guild_id = $1 AND user_id = $2 AND coins_total >= $3
              AND (ultima_partita_at IS NULL
                   OR ultima_partita_at <= NOW() - make_interval(secs => $5))
            RETURNING coins_total
            """,
            guild_id,
            user_id,
            puntata,
            restituzione,
            float(attesa_secondi),
        )

    async def attesa_partita_rimasta(
        self, guild_id: int, user_id: int, attesa_secondi: int
    ) -> int:
        """Secondi che mancano alla prossima partita (0 se si può giocare)."""
        resto = await self._pool.fetchval(
            """
            SELECT CEIL(EXTRACT(EPOCH FROM
                ultima_partita_at + make_interval(secs => $3) - NOW()))
            FROM leveling_totals WHERE guild_id = $1 AND user_id = $2
            """,
            guild_id,
            user_id,
            float(attesa_secondi),
        )
        return max(0, int(resto or 0))

    async def transfer_coins(
        self, guild_id: int, from_user_id: int, to_user_id: int, amount: int
    ) -> bool:
        """
        Trasferisce coin da un utente all'altro, atomicamente e solo
        se il mittente ha saldo sufficiente. Restituisce False (senza
        scrivere nulla) se il saldo non basta — mai un saldo negativo.
        """
        if amount <= 0:
            raise ValueError("L'importo da trasferire deve essere positivo.")

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Le due righe si bloccano sempre nello stesso ordine
                # (ID più basso per primo): così A→B e B→A partiti
                # insieme si mettono in fila invece di bloccarsi a
                # vicenda.
                saldi = await conn.fetch(
                    """
                    SELECT user_id, coins_total FROM leveling_totals
                    WHERE guild_id = $1 AND user_id = ANY($2::bigint[])
                    ORDER BY user_id
                    FOR UPDATE
                    """,
                    guild_id,
                    [from_user_id, to_user_id],
                )
                saldo = next(
                    (r["coins_total"] for r in saldi if r["user_id"] == from_user_id), 0
                )

                if saldo < amount:
                    return False

                await conn.execute(
                    """
                    INSERT INTO leveling_totals (guild_id, user_id, coins_total)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (guild_id, user_id) DO UPDATE
                        SET coins_total = leveling_totals.coins_total + $3
                    """,
                    guild_id,
                    from_user_id,
                    -amount,
                )
                await conn.execute(
                    """
                    INSERT INTO leveling_totals (guild_id, user_id, coins_total)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (guild_id, user_id) DO UPDATE
                        SET coins_total = leveling_totals.coins_total + $3
                    """,
                    guild_id,
                    to_user_id,
                    amount,
                )
                return True

    async def spend_coins(self, guild_id: int, user_id: int, amount: int) -> bool:
        """
        Sottrae coin solo se il saldo basta, con una sola UPDATE che
        contiene il controllo. Restituisce False (senza scrivere nulla)
        se il saldo non basta: mai un saldo negativo.
        """
        async with self._pool.acquire() as conn:
            return await spend_coins_in(conn, guild_id, user_id, amount)

    async def list_guilds_needing_weekly_decay(
        self, period: str, created_before: datetime
    ) -> list[int]:
        """
        Gli id dei server con almeno un saldo da far decadere (stesse
        regole di QUERY_UTENTI_DA_DECADERE: saldo > 1, periodo non ancora
        coperto, riga nata prima di `created_before` — il primo
        decadimento arriva dopo una settimana intera, non entro un'ora
        dal primo guadagno). Vale per QUALUNQUE membro con coin, in un
        clan o no (SPEC.md §15.15).
        """
        rows = await self._pool.fetch(
            "SELECT DISTINCT guild_id FROM leveling_totals WHERE " + CONDIZIONE_DA_DECADERE,
            period,
            created_before,
        )
        return [r["guild_id"] for r in rows]

    async def apply_weekly_decay_guild(
        self, guild_id: int, period: str, created_before: datetime
    ) -> tuple[int, int]:
        """
        Decadimento settimanale del 10% per TUTTI i saldi di un server, con
        un solo UPDATE (PERF-6). La percentuale è calcolata dal database
        sul saldo bloccato (FOR UPDATE), non passata dal chiamante: una
        spesa o un guadagno nel frattempo non falsano il risultato. Le
        coin tolte vanno nella cassa del server nella STESSA transazione.
        Restituisce (utenti toccati, coin tolte).
        """
        from core.repositories.guild_chest_repo import (  # import tardivo: la cassa usa questo modulo
            REASON_WEEKLY_PERSONAL_DECAY,
            deposit_in,
        )

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                riga = await conn.fetchrow(
                    QUERY_DECADIMENTO_DEL_SERVER, period, created_before, guild_id
                )
                utenti, tolti = riga["utenti"], int(riga["tolti"])
                if tolti > 0:
                    await deposit_in(conn, guild_id, tolti, REASON_WEEKLY_PERSONAL_DECAY)
                return utenti, tolti

    async def claim_daily(
        self, guild_id: int, user_id: int, amount: int, cooldown_seconds: int, now: datetime
    ) -> bool:
        """Riscuote il premio giornaliero. Vedi _riscuoti_premio."""
        return await self._riscuoti_premio(
            "last_daily_at", guild_id, user_id, amount, cooldown_seconds, now
        )

    async def claim_work(
        self, guild_id: int, user_id: int, amount: int, cooldown_seconds: int, now: datetime
    ) -> bool:
        """Riscuote il premio del lavoro. Vedi _riscuoti_premio."""
        return await self._riscuoti_premio(
            "last_work_at", guild_id, user_id, amount, cooldown_seconds, now
        )

    async def _riscuoti_premio(
        self,
        colonna: str,
        guild_id: int,
        user_id: int,
        amount: int,
        cooldown_seconds: int,
        now: datetime,
    ) -> bool:
        """
        Accredita `amount` coin e segna l'ora della riscossione, ma solo
        se l'attesa è finita. Il controllo sta DENTRO la scrittura (una
        sola istruzione con WHERE): due richieste arrivate insieme non
        possono riscuotere tutte e due (BUG-14). Restituisce False, senza
        scrivere nulla, se l'attesa non è ancora finita.
        """
        if colonna not in ("last_daily_at", "last_work_at"):
            raise ValueError(f"Colonna non ammessa: {colonna}")

        scaduto_prima_di = now - timedelta(seconds=cooldown_seconds)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                riga = await conn.fetchrow(
                    f"""
                    INSERT INTO leveling_totals (guild_id, user_id, coins_total, {colonna})
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (guild_id, user_id) DO UPDATE
                        SET coins_total = leveling_totals.coins_total + $3, {colonna} = $4
                        WHERE leveling_totals.{colonna} IS NULL
                           OR leveling_totals.{colonna} <= $5
                    RETURNING coins_total
                    """,
                    guild_id,
                    user_id,
                    amount,
                    now,
                    scaduto_prima_di,
                )
                if riga is None:
                    return False
                await self._add_period_activity(conn, guild_id, user_id, 0, amount)
                return True

    async def top_xp_alltime(self, guild_id: int, limit: int = 10) -> list[LeaderboardEntry]:
        rows = await self._pool.fetch(
            """
            SELECT user_id, xp_total AS amount FROM leveling_totals
            WHERE guild_id = $1 AND xp_total > 0
            ORDER BY xp_total DESC LIMIT $2
            """,
            guild_id,
            limit,
        )
        return [LeaderboardEntry(r["user_id"], r["amount"]) for r in rows]

    async def top_coins_alltime(self, guild_id: int, limit: int = 10) -> list[LeaderboardEntry]:
        rows = await self._pool.fetch(
            """
            SELECT user_id, coins_total AS amount FROM leveling_totals
            WHERE guild_id = $1 AND coins_total > 0
            ORDER BY coins_total DESC LIMIT $2
            """,
            guild_id,
            limit,
        )
        return [LeaderboardEntry(r["user_id"], r["amount"]) for r in rows]

    async def top_xp_period(
        self, guild_id: int, limit: int = 10, period: str | None = None
    ) -> list[LeaderboardEntry]:
        rows = await self._pool.fetch(
            """
            SELECT user_id, xp AS amount FROM leveling_activity
            WHERE guild_id = $1 AND period_key = $2 AND xp > 0
            ORDER BY xp DESC LIMIT $3
            """,
            guild_id,
            period or period_key(),
            limit,
        )
        return [LeaderboardEntry(r["user_id"], r["amount"]) for r in rows]

    async def top_coins_period(
        self, guild_id: int, limit: int = 10, period: str | None = None
    ) -> list[LeaderboardEntry]:
        rows = await self._pool.fetch(
            """
            SELECT user_id, coins AS amount FROM leveling_activity
            WHERE guild_id = $1 AND period_key = $2 AND coins > 0
            ORDER BY coins DESC LIMIT $3
            """,
            guild_id,
            period or period_key(),
            limit,
        )
        return [LeaderboardEntry(r["user_id"], r["amount"]) for r in rows]


def _get_pool():
    from core.database import db
    return db.pool


leveling_repo = LevelingRepository(pool_provider=_get_pool)
