"""
core/repositories/command_permission_token_repo.py
==================================================
Token OAuth2 cifrato dell'admin che ha autorizzato la scrittura dei permessi dei
comandi (tabella `command_permission_tokens`, migrazione 0039). Un token per server.
Funzioni coperte: SPEC §20 (#148)
"""

from __future__ import annotations

import asyncpg

from core.command_permissions import PermessiNonConfigurati, TokenPermessi
from core.oauth_crypto import OAuthEncryptionNotConfigured, decrypt_token, encrypt_token


class CommandPermissionTokenRepository:
    def __init__(self, pool_provider, chiave_provider) -> None:
        self._pool_provider = pool_provider
        self._chiave_provider = chiave_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def _chiave(self) -> str:
        chiave = self._chiave_provider()
        if not chiave:
            raise PermessiNonConfigurati("OAUTH_ENCRYPTION_KEY non è impostata: il token non si salva.")
        return chiave

    async def salva(self, guild_id: int, user_id: int, token: TokenPermessi) -> None:
        chiave = self._chiave()
        try:
            accesso = encrypt_token(token.access_token, chiave)
            rinnovo = encrypt_token(token.refresh_token, chiave)
        except OAuthEncryptionNotConfigured as exc:
            raise PermessiNonConfigurati(str(exc)) from exc
        await self._pool.execute(
            """
            INSERT INTO command_permission_tokens
                (guild_id, user_id, encrypted_access_token, encrypted_refresh_token, expires_at)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (guild_id) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                encrypted_access_token = EXCLUDED.encrypted_access_token,
                encrypted_refresh_token = EXCLUDED.encrypted_refresh_token,
                expires_at = EXCLUDED.expires_at,
                updated_at = now()
            """,
            guild_id, user_id, accesso, rinnovo, token.scade_il,
        )

    async def get(self, guild_id: int) -> TokenPermessi | None:
        riga = await self._pool.fetchrow(
            "SELECT * FROM command_permission_tokens WHERE guild_id = $1", guild_id
        )
        if riga is None:
            return None
        chiave = self._chiave()
        return TokenPermessi(
            access_token=decrypt_token(riga["encrypted_access_token"], chiave),
            refresh_token=decrypt_token(riga["encrypted_refresh_token"], chiave),
            scade_il=riga["expires_at"],
            user_id=riga["user_id"],
        )

    async def cancella(self, guild_id: int) -> None:
        await self._pool.execute("DELETE FROM command_permission_tokens WHERE guild_id = $1", guild_id)


def _get_pool():
    from core.database import db

    return db.pool


def _get_chiave() -> str:
    from core.config import config

    return config.OAUTH_ENCRYPTION_KEY


command_permission_token_repo = CommandPermissionTokenRepository(
    pool_provider=_get_pool, chiave_provider=_get_chiave
)
