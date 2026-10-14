"""
core/repositories/whitelabel_repo.py
====================================
Bot con marchio proprio: token cifrato e stato (tabella `whitelabel_bots`, migrazione 0133, NF-38).
Il token si legge in chiaro solo con `get_con_token`, per avviare il client.
Funzioni coperte: SPEC §23 (NF-38)
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from core.oauth_crypto import OAuthEncryptionNotConfigured, decrypt_token, encrypt_token


class ChiaveNonConfigurata(RuntimeError):
    """`OAUTH_ENCRYPTION_KEY` manca: il token non si può salvare in modo sicuro."""


@dataclass(frozen=True)
class Marchio:
    guild_id: int
    bot_user_id: int
    application_id: int
    bot_name: str
    status_text: str | None
    enabled: bool
    last_state: str
    last_error: str | None
    created_by: int


class WhitelabelRepository:
    def __init__(self, pool_provider, chiave_provider) -> None:
        self._pool_provider = pool_provider
        self._chiave_provider = chiave_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def _chiave(self) -> str:
        chiave = self._chiave_provider()
        if not chiave:
            raise ChiaveNonConfigurata("OAUTH_ENCRYPTION_KEY non è impostata: il token non si salva.")
        return chiave

    @staticmethod
    def _da_riga(riga) -> Marchio:
        return Marchio(
            guild_id=riga["guild_id"],
            bot_user_id=riga["bot_account_id"],
            application_id=riga["application_id"],
            bot_name=riga["bot_name"],
            status_text=riga["status_text"],
            enabled=riga["enabled"],
            last_state=riga["last_state"],
            last_error=riga["last_error"],
            created_by=riga["created_by"],
        )

    async def salva(
        self, guild_id: int, token: str, bot_user_id: int, application_id: int, bot_name: str, created_by: int
    ) -> None:
        """Collega (o ricollega) il bot del server. Un token già usato da un altro server solleva UniqueViolationError."""
        try:
            cifrato = encrypt_token(token, self._chiave())
        except OAuthEncryptionNotConfigured as exc:
            raise ChiaveNonConfigurata(str(exc)) from exc
        await self._pool.execute(
            """
            INSERT INTO whitelabel_bots
                (guild_id, encrypted_token, bot_account_id, application_id, bot_name, created_by)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (guild_id) DO UPDATE SET
                encrypted_token = EXCLUDED.encrypted_token, bot_account_id = EXCLUDED.bot_account_id,
                application_id = EXCLUDED.application_id, bot_name = EXCLUDED.bot_name,
                created_by = EXCLUDED.created_by, enabled = TRUE, last_state = 'fermo', last_error = NULL,
                updated_at = now()
            """,
            guild_id, cifrato, bot_user_id, application_id, bot_name, created_by,
        )

    async def get(self, guild_id: int) -> Marchio | None:
        riga = await self._pool.fetchrow("SELECT * FROM whitelabel_bots WHERE guild_id = $1", guild_id)
        return None if riga is None else self._da_riga(riga)

    async def get_con_token(self, guild_id: int) -> tuple[Marchio, str] | None:
        riga = await self._pool.fetchrow("SELECT * FROM whitelabel_bots WHERE guild_id = $1", guild_id)
        if riga is None:
            return None
        return self._da_riga(riga), decrypt_token(riga["encrypted_token"], self._chiave())

    async def elenco_abilitati(self) -> list[Marchio]:
        righe = await self._pool.fetch("SELECT * FROM whitelabel_bots WHERE enabled ORDER BY guild_id")
        return [self._da_riga(r) for r in righe]

    async def imposta_stato(self, guild_id: int, stato: str, errore: str | None = None) -> None:
        await self._pool.execute(
            "UPDATE whitelabel_bots SET last_state = $2, last_error = $3, updated_at = now() WHERE guild_id = $1",
            guild_id, stato, (errore or None) and errore[:200],
        )

    async def imposta_abilitato(self, guild_id: int, abilitato: bool) -> bool:
        esito = await self._pool.execute(
            "UPDATE whitelabel_bots SET enabled = $2, updated_at = now() WHERE guild_id = $1", guild_id, abilitato
        )
        return esito.endswith(" 1")

    async def imposta_testo_stato(self, guild_id: int, testo: str | None) -> bool:
        esito = await self._pool.execute(
            "UPDATE whitelabel_bots SET status_text = $2, updated_at = now() WHERE guild_id = $1", guild_id, testo
        )
        return esito.endswith(" 1")

    async def elimina(self, guild_id: int) -> bool:
        esito = await self._pool.execute("DELETE FROM whitelabel_bots WHERE guild_id = $1", guild_id)
        return esito.endswith(" 1")


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


def _get_chiave() -> str:
    from core.config import config

    return config.OAUTH_ENCRYPTION_KEY


whitelabel_repo = WhitelabelRepository(pool_provider=_get_pool, chiave_provider=_get_chiave)
