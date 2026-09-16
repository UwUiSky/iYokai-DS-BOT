"""
core/repositories/automod_repo.py
====================================
Persistenza della configurazione AutoMod per server: la lista di
parole vietate personalizzate e se il blocco automatico degli inviti
Discord è attivo. Non salva le REGOLE Discord in sé (quelle vivono
su Discord, lette al bisogno con guild.fetch_automod_rules()) — qui
c'è solo l'INTENZIONE dell'amministratore, che poi il sync
(core/automod_sync.py + cogs/automod/automod.py) traduce in regole
reali.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import asyncpg


@dataclass(frozen=True)
class AutomodConfig:
    guild_id: int
    custom_badwords: tuple[str, ...]
    block_invites: bool


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS automod_config (
            guild_id        BIGINT PRIMARY KEY,
            custom_badwords JSONB NOT NULL DEFAULT '[]'::jsonb,
            block_invites   BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        -- Traccia, per ogni regola AutoMod che iYokai gestisce
        -- (indicizzata per nome regola), cosa iYokai stesso ha
        -- scritto nell'ultimo sync riuscito. Serve al merge a tre
        -- vie in core/automod_sync.py per distinguere "parole
        -- aggiunte a mano dall'admin" (da preservare per sempre) da
        -- "parole che erano nostre e che ora vogliamo poter
        -- rimuovere" (altrimenti /automod badword-remove non
        -- avrebbe mai effetto sulla regola Discord reale).
        CREATE TABLE IF NOT EXISTS automod_last_synced (
            guild_id      BIGINT NOT NULL,
            rule_name     TEXT NOT NULL,
            keywords      JSONB NOT NULL DEFAULT '[]'::jsonb,
            regex_patterns JSONB NOT NULL DEFAULT '[]'::jsonb,
            synced_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (guild_id, rule_name)
        );
        """
    )


class AutomodRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def get_config(self, guild_id: int) -> AutomodConfig:
        """
        Restituisce sempre una configurazione valida, anche per un
        server che non ha mai toccato AutoMod: valori di default
        (nessuna parola, inviti non bloccati), non None — così il
        chiamante non deve gestire un caso "configurazione assente"
        separato da "configurazione vuota".
        """
        row = await self._pool.fetchrow(
            "SELECT custom_badwords, block_invites FROM automod_config WHERE guild_id = $1",
            guild_id,
        )
        if row is None:
            return AutomodConfig(guild_id=guild_id, custom_badwords=(), block_invites=False)

        badwords = json.loads(row["custom_badwords"])
        return AutomodConfig(
            guild_id=guild_id,
            custom_badwords=tuple(badwords),
            block_invites=row["block_invites"],
        )

    async def add_badword(self, guild_id: int, word: str) -> AutomodConfig:
        """
        Aggiunge una parola alla lista, senza duplicati (case
        insensitive: "Spam" e "spam" contano come la stessa parola,
        altrimenti l'admin potrebbe involontariamente popolare la
        lista di varianti ridondanti). Restituisce la configurazione
        aggiornata, comoda per il comando che risponde subito con lo
        stato risultante senza una query separata.
        """
        config = await self.get_config(guild_id)
        normalizzata = word.strip().lower()
        if not normalizzata:
            return config
        if normalizzata in {w.lower() for w in config.custom_badwords}:
            return config

        nuove_parole = list(config.custom_badwords) + [normalizzata]
        await self._save_badwords(guild_id, nuove_parole)
        return AutomodConfig(
            guild_id=guild_id, custom_badwords=tuple(nuove_parole), block_invites=config.block_invites
        )

    async def remove_badword(self, guild_id: int, word: str) -> AutomodConfig:
        config = await self.get_config(guild_id)
        normalizzata = word.strip().lower()
        nuove_parole = [w for w in config.custom_badwords if w.lower() != normalizzata]
        await self._save_badwords(guild_id, nuove_parole)
        return AutomodConfig(
            guild_id=guild_id, custom_badwords=tuple(nuove_parole), block_invites=config.block_invites
        )

    async def _save_badwords(self, guild_id: int, words: list[str]) -> None:
        await self._pool.execute(
            """
            INSERT INTO automod_config (guild_id, custom_badwords)
            VALUES ($1, $2::jsonb)
            ON CONFLICT (guild_id) DO UPDATE
                SET custom_badwords = EXCLUDED.custom_badwords,
                    updated_at = now()
            """,
            guild_id,
            json.dumps(words),
        )

    async def set_block_invites(self, guild_id: int, block: bool) -> None:
        await self._pool.execute(
            """
            INSERT INTO automod_config (guild_id, block_invites)
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE
                SET block_invites = EXCLUDED.block_invites,
                    updated_at = now()
            """,
            guild_id,
            block,
        )

    # ================================================================
    # Ultimo stato sincronizzato — vedi la nota in run_migrations()
    # ================================================================
    async def get_last_synced(
        self, guild_id: int, rule_name: str
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """
        Restituisce (keywords, regex_patterns) che iYokai aveva
        scritto nell'ultimo sync riuscito per questa regola. Tuple
        vuote se questa regola non è mai stata sincronizzata prima
        — core/automod_sync.py tratta questo caso trattando TUTTO
        il contenuto esistente come "dell'admin" (la scelta prudente).
        """
        row = await self._pool.fetchrow(
            """
            SELECT keywords, regex_patterns FROM automod_last_synced
            WHERE guild_id = $1 AND rule_name = $2
            """,
            guild_id,
            rule_name,
        )
        if row is None:
            return (), ()
        return tuple(json.loads(row["keywords"])), tuple(json.loads(row["regex_patterns"]))

    async def set_last_synced(
        self,
        guild_id: int,
        rule_name: str,
        keywords: tuple[str, ...],
        regex_patterns: tuple[str, ...],
    ) -> None:
        """
        Chiamato dal cog SOLO dopo che una create/update è andata a
        buon fine su Discord: registra cosa è stato scritto davvero,
        così il prossimo sync saprà distinguere correttamente
        "nostro" da "dell'admin".
        """
        await self._pool.execute(
            """
            INSERT INTO automod_last_synced (guild_id, rule_name, keywords, regex_patterns, synced_at)
            VALUES ($1, $2, $3::jsonb, $4::jsonb, now())
            ON CONFLICT (guild_id, rule_name) DO UPDATE
                SET keywords = EXCLUDED.keywords,
                    regex_patterns = EXCLUDED.regex_patterns,
                    synced_at = now()
            """,
            guild_id,
            rule_name,
            json.dumps(list(keywords)),
            json.dumps(list(regex_patterns)),
        )

    async def clear_last_synced(self, guild_id: int, rule_name: str) -> None:
        """Chiamato dopo che una regola è stata ELIMINATA (SyncActionType.DELETE):
        non c'è più nulla da tracciare per quel nome, finché non
        verrà eventualmente ricreata."""
        await self._pool.execute(
            "DELETE FROM automod_last_synced WHERE guild_id = $1 AND rule_name = $2",
            guild_id,
            rule_name,
        )


def _get_pool():
    from core.database import db
    return db.pool


automod_repo = AutomodRepository(pool_provider=_get_pool)
