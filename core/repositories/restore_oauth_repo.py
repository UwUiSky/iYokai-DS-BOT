"""
core/repositories/restore_oauth_repo.py
============================================
Persistenza dei token OAuth2 altrui usati per il restore massivo
(SPEC.md §11.11) — SEMPRE cifrati a riposo (core/oauth_crypto.py,
AES-256-GCM), mai in chiaro nel DB, con la retention concordata
esplicitamente con l'utente:

- Uscita SPONTANEA dell'utente dal server main → il token resta,
  ma da quel momento decorre una scadenza (90 giorni, controllata
  da purge_expired_left, non da qui): se non viene usato prima,
  va cancellato.
- KICK → il token viene PRESERVATO senza scadenza, ma marcato
  "kicked_flagged": se l'utente rientra nel server, il chiamante
  (listener on_member_join) può avvisare gli admin in chat.
- BAN → il token viene PRESERVATO senza scadenza, marcato
  "banned_blacklisted": serve a impedire che un futuro restore lo
  riutilizzi per far rientrare qualcuno che è stato bannato (il
  chiamante controlla lo status prima di usare un token).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import asyncpg

from core.oauth_crypto import decrypt_token, encrypt_token

STATUS_ACTIVE = "active"
STATUS_KICKED_FLAGGED = "kicked_flagged"
STATUS_BANNED_BLACKLISTED = "banned_blacklisted"


@dataclass(frozen=True)
class RestoreOAuthToken:
    source_guild_id: int
    user_id: int
    # SEC-16: repr=False — decifrati in memoria dopo la lettura dal
    # repository, un log di debug con questo oggetto non deve
    # stamparli in chiaro.
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    expires_at: datetime
    status: str
    granted_at: datetime
    left_at: datetime | None


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS restore_oauth_tokens (
            source_guild_id         BIGINT NOT NULL,
            user_id                 BIGINT NOT NULL,
            encrypted_access_token  TEXT NOT NULL,
            encrypted_refresh_token TEXT NOT NULL,
            expires_at              TIMESTAMPTZ NOT NULL,
            status                  TEXT NOT NULL DEFAULT 'active',
            granted_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            left_at                 TIMESTAMPTZ,
            PRIMARY KEY (source_guild_id, user_id)
        );

        CREATE INDEX IF NOT EXISTS idx_restore_oauth_tokens_status
            ON restore_oauth_tokens (status);
        """
    )


class RestoreOAuthRepository:
    def __init__(self, pool_provider, encryption_key_provider) -> None:
        self._pool_provider = pool_provider
        self._encryption_key_provider = encryption_key_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    @property
    def _key(self) -> str:
        return self._encryption_key_provider()

    def _row_to_token(self, row) -> RestoreOAuthToken:
        return RestoreOAuthToken(
            source_guild_id=row["source_guild_id"],
            user_id=row["user_id"],
            access_token=decrypt_token(row["encrypted_access_token"], self._key),
            refresh_token=decrypt_token(row["encrypted_refresh_token"], self._key),
            expires_at=row["expires_at"],
            status=row["status"],
            granted_at=row["granted_at"],
            left_at=row["left_at"],
        )

    async def save_token(
        self,
        source_guild_id: int,
        user_id: int,
        access_token: str,
        refresh_token: str,
        expires_at: datetime,
    ) -> bool:
        """
        Salva/aggiorna un token — cifrato PRIMA di lasciare questo
        metodo, non dopo. Un nuovo consenso dell'utente riporta lo
        stato a 'active' e azzera left_at (rifà da capo il conto dei
        90 giorni se in precedenza era uscito e poi è rientrato/ha
        ri-autorizzato).

        SEC-19: l'unica eccezione è chi è 'banned_blacklisted' — la
        riga non viene toccata e il metodo restituisce False: un
        nuovo consenso non cancella un ban. True in tutti gli altri
        casi.
        """
        cifrato_access = encrypt_token(access_token, self._key)
        cifrato_refresh = encrypt_token(refresh_token, self._key)
        risultato = await self._pool.execute(
            """
            INSERT INTO restore_oauth_tokens
                (source_guild_id, user_id, encrypted_access_token,
                 encrypted_refresh_token, expires_at, status, left_at)
            VALUES ($1, $2, $3, $4, $5, $6, NULL)
            ON CONFLICT (source_guild_id, user_id) DO UPDATE SET
                encrypted_access_token = EXCLUDED.encrypted_access_token,
                encrypted_refresh_token = EXCLUDED.encrypted_refresh_token,
                expires_at = EXCLUDED.expires_at,
                status = EXCLUDED.status,
                left_at = NULL
            WHERE restore_oauth_tokens.status <> $7
            """,
            source_guild_id,
            user_id,
            cifrato_access,
            cifrato_refresh,
            expires_at,
            STATUS_ACTIVE,
            STATUS_BANNED_BLACKLISTED,
        )
        # "INSERT 0 1" se la riga è stata scritta, "INSERT 0 0" se il
        # WHERE ha fermato l'aggiornamento.
        return risultato.endswith(" 1")

    async def get_token(self, source_guild_id: int, user_id: int) -> RestoreOAuthToken | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM restore_oauth_tokens WHERE source_guild_id = $1 AND user_id = $2",
            source_guild_id,
            user_id,
        )
        return self._row_to_token(row) if row is not None else None

    async def mark_left_voluntarily(self, source_guild_id: int, user_id: int) -> None:
        await self._pool.execute(
            "UPDATE restore_oauth_tokens SET left_at = now() "
            "WHERE source_guild_id = $1 AND user_id = $2 AND status = $3",
            source_guild_id,
            user_id,
            STATUS_ACTIVE,
        )

    async def mark_kicked(self, source_guild_id: int, user_id: int) -> None:
        await self._pool.execute(
            "UPDATE restore_oauth_tokens SET status = $3 "
            "WHERE source_guild_id = $1 AND user_id = $2",
            source_guild_id,
            user_id,
            STATUS_KICKED_FLAGGED,
        )

    async def mark_banned(self, source_guild_id: int, user_id: int) -> None:
        await self._pool.execute(
            "UPDATE restore_oauth_tokens SET status = $3 "
            "WHERE source_guild_id = $1 AND user_id = $2",
            source_guild_id,
            user_id,
            STATUS_BANNED_BLACKLISTED,
        )

    async def delete_token(self, source_guild_id: int, user_id: int) -> None:
        await self._pool.execute(
            "DELETE FROM restore_oauth_tokens WHERE source_guild_id = $1 AND user_id = $2",
            source_guild_id,
            user_id,
        )

    async def purge_expired_voluntary_leaves(self, retention_days: int = 90) -> int:
        """
        Cancella i token di chi è uscito SPONTANEAMENTE più di
        retention_days fa (default 90, SPEC.md §11.11) — mai quelli
        di chi è stato kickato/bannato (status diverso da 'active',
        left_at sempre NULL per loro: la UPDATE condition sopra lo
        garantisce). Restituisce quanti ne sono stati cancellati.
        """
        risultato = await self._pool.execute(
            """
            DELETE FROM restore_oauth_tokens
            WHERE status = $1
              AND left_at IS NOT NULL
              AND left_at < now() - ($2 || ' days')::interval
            """,
            STATUS_ACTIVE,
            str(retention_days),
        )
        return int(risultato.split()[-1])


def _get_pool():
    from core.database import db
    return db.pool


def _get_encryption_key() -> str:
    from core.config import config
    return config.OAUTH_ENCRYPTION_KEY


restore_oauth_repo = RestoreOAuthRepository(
    pool_provider=_get_pool, encryption_key_provider=_get_encryption_key
)
