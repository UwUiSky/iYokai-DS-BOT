"""
core/repositories/log_webhook_repo.py
=====================================
Webhook dei canali di log (tabella `log_webhooks`, migrazione 0361, #113, D33): uno per canale, token cifrato.
Il token si legge in chiaro solo con `get`, per mandare i log.
Funzioni coperte: #113
"""

from __future__ import annotations

import asyncpg

from core.oauth_crypto import decrypt_token, encrypt_token


class ChiaveNonConfigurata(RuntimeError):
    """`OAUTH_ENCRYPTION_KEY` manca: il token non si può salvare in modo sicuro."""


def _aad(guild_id: int, channel_id: int) -> bytes:
    return f"log_webhook:{guild_id}:{channel_id}".encode()


class LogWebhookRepository:
    def __init__(self, pool_provider, chiave_provider) -> None:
        self._pool_provider = pool_provider
        self._chiave_provider = chiave_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def chiave_presente(self) -> bool:
        return bool(self._chiave_provider())

    async def get(self, guild_id: int, channel_id: int) -> tuple[int, str] | None:
        """(id del webhook, token in chiaro), o None se non c'è o il token non si legge più."""
        riga = await self._pool.fetchrow(
            "SELECT webhook_id, encrypted_token FROM log_webhooks WHERE guild_id = $1 AND channel_id = $2",
            guild_id, channel_id,
        )
        if riga is None:
            return None
        try:
            return riga["webhook_id"], decrypt_token(riga["encrypted_token"], self._chiave_provider(), _aad(guild_id, channel_id))
        except Exception:  # noqa: BLE001 - chiave cambiata o riga rovinata: se ne crea uno nuovo
            return None

    async def salva(self, guild_id: int, channel_id: int, webhook_id: int, token: str) -> None:
        chiave = self._chiave_provider()
        if not chiave:
            raise ChiaveNonConfigurata("OAUTH_ENCRYPTION_KEY non è impostata: il token non si salva.")
        await self._pool.execute(
            """
            INSERT INTO log_webhooks (guild_id, channel_id, webhook_id, encrypted_token) VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, channel_id) DO UPDATE
                SET webhook_id = EXCLUDED.webhook_id, encrypted_token = EXCLUDED.encrypted_token, created_at = now()
            """,
            guild_id, channel_id, webhook_id, encrypt_token(token, chiave, _aad(guild_id, channel_id)),
        )

    async def elimina(self, guild_id: int, channel_id: int) -> None:
        await self._pool.execute("DELETE FROM log_webhooks WHERE guild_id = $1 AND channel_id = $2", guild_id, channel_id)

    async def elimina_server(self, guild_id: int) -> list[tuple[int, int, str | None]]:
        """
        Toglie i webhook del server (log spenti). Restituisce (canale, id webhook, token in chiaro o None se
        non si legge più) per poterli cancellare anche su Discord.
        """
        righe = await self._pool.fetch(
            "DELETE FROM log_webhooks WHERE guild_id = $1 RETURNING channel_id, webhook_id, encrypted_token", guild_id
        )
        risultato = []
        for r in righe:
            try:
                token = decrypt_token(r["encrypted_token"], self._chiave_provider(), _aad(guild_id, r["channel_id"]))
            except Exception:  # noqa: BLE001
                token = None
            risultato.append((r["channel_id"], r["webhook_id"], token))
        return risultato


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


def _get_chiave() -> str:
    from core.config import config

    return config.OAUTH_ENCRYPTION_KEY


log_webhook_repo = LogWebhookRepository(pool_provider=_get_pool, chiave_provider=_get_chiave)
