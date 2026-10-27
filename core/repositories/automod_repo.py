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
from dataclasses import dataclass, replace

import asyncpg

from core.automod_native_logic import stessa_parola


@dataclass(frozen=True)
class AutomodConfig:
    guild_id: int
    custom_badwords: tuple[str, ...]
    block_invites: bool
    invite_allowed: tuple[str, ...] = ()  # codici d'invito da lasciar passare (AMD-026)
    invite_own: bool = False  # lascia passare gli inviti del server stesso (AMD-027)


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
        -- rimuovere" (altrimenti /automod parole remove non
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
            "SELECT custom_badwords, block_invites, invite_allowed, invite_own "
            "FROM automod_config WHERE guild_id = $1",
            guild_id,
        )
        if row is None:
            return AutomodConfig(guild_id=guild_id, custom_badwords=(), block_invites=False)

        badwords = json.loads(row["custom_badwords"])
        return AutomodConfig(
            guild_id=guild_id,
            custom_badwords=tuple(badwords),
            block_invites=row["block_invites"],
            invite_allowed=tuple(json.loads(row["invite_allowed"])),
            invite_own=row["invite_own"],
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
        return replace(config, custom_badwords=tuple(nuove_parole))

    async def remove_badword(self, guild_id: int, word: str) -> AutomodConfig:
        config = await self.get_config(guild_id)
        nuove_parole = [w for w in config.custom_badwords if not stessa_parola(w, word)]
        await self._save_badwords(guild_id, nuove_parole)
        return replace(config, custom_badwords=tuple(nuove_parole))

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

    async def set_invite_allowed(self, guild_id: int, codici: tuple[str, ...]) -> None:
        """Salva i codici d'invito da lasciar passare (AMD-026)."""
        await self._pool.execute(
            """
            INSERT INTO automod_config (guild_id, invite_allowed)
            VALUES ($1, $2::jsonb)
            ON CONFLICT (guild_id) DO UPDATE
                SET invite_allowed = EXCLUDED.invite_allowed,
                    updated_at = now()
            """,
            guild_id,
            json.dumps(list(codici)),
        )

    async def set_invite_own(self, guild_id: int, attivo: bool) -> None:
        """Lascia passare (o no) gli inviti del server stesso (AMD-027)."""
        await self._pool.execute(
            """
            INSERT INTO automod_config (guild_id, invite_own)
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE
                SET invite_own = EXCLUDED.invite_own,
                    updated_at = now()
            """,
            guild_id,
            attivo,
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

    async def get_last_synced_allow(self, guild_id: int, rule_name: str) -> tuple[str, ...]:
        """Le eccezioni che iYokai aveva scritto nell'ultimo sync (AMD-026)."""
        valore = await self._pool.fetchval(
            "SELECT allow_list FROM automod_last_synced WHERE guild_id = $1 AND rule_name = $2",
            guild_id,
            rule_name,
        )
        return tuple(json.loads(valore)) if valore else ()

    async def set_last_synced(
        self,
        guild_id: int,
        rule_name: str,
        keywords: tuple[str, ...],
        regex_patterns: tuple[str, ...],
        allow_list: tuple[str, ...] = (),
    ) -> None:
        """
        Chiamato dal cog SOLO dopo che una create/update è andata a
        buon fine su Discord: registra cosa è stato scritto davvero,
        così il prossimo sync saprà distinguere correttamente
        "nostro" da "dell'admin".
        """
        await self._pool.execute(
            """
            INSERT INTO automod_last_synced (guild_id, rule_name, keywords, regex_patterns, allow_list, synced_at)
            VALUES ($1, $2, $3::jsonb, $4::jsonb, $5::jsonb, now())
            ON CONFLICT (guild_id, rule_name) DO UPDATE
                SET keywords = EXCLUDED.keywords,
                    regex_patterns = EXCLUDED.regex_patterns,
                    allow_list = EXCLUDED.allow_list,
                    synced_at = now()
            """,
            guild_id,
            rule_name,
            json.dumps(list(keywords)),
            json.dumps(list(regex_patterns)),
            json.dumps(list(allow_list)),
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
