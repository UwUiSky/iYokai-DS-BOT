"""
core/repositories/custom_webhook_repo.py
============================================
Persistenza dei webhook custom in RICEZIONE (SPEC.md §10.8, la parte
"webhook" — la parte RSS/Atom vive già in feed_subscription_repo.py).
Una riga per webhook creato: un token segreto univoco (l'unica cosa
che autentica una richiesta esterna in arrivo), il canale Discord di
destinazione, e un template di messaggio opzionale.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg

from core.custom_webhook_logic import DEFAULT_MESSAGE_TEMPLATE, generate_webhook_token


@dataclass(frozen=True)
class CustomWebhook:
    id: int
    guild_id: int
    channel_id: int
    token: str
    label: str
    message_template: str
    created_by: int
    created_at: datetime


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS custom_webhooks (
            id                SERIAL PRIMARY KEY,
            guild_id          BIGINT NOT NULL,
            channel_id        BIGINT NOT NULL,
            token             TEXT NOT NULL UNIQUE,
            label             TEXT NOT NULL,
            message_template  TEXT NOT NULL,
            created_by        BIGINT NOT NULL,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_custom_webhooks_guild
            ON custom_webhooks (guild_id);
        CREATE INDEX IF NOT EXISTS idx_custom_webhooks_token
            ON custom_webhooks (token);
        """
    )


class CustomWebhookRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def _row_to_webhook(self, row) -> CustomWebhook:
        return CustomWebhook(
            id=row["id"],
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            token=row["token"],
            label=row["label"],
            message_template=row["message_template"],
            created_by=row["created_by"],
            created_at=row["created_at"],
        )

    async def create_webhook(
        self,
        guild_id: int,
        channel_id: int,
        label: str,
        created_by: int,
        message_template: str | None = None,
    ) -> CustomWebhook:
        """
        Genera un token nuovo e ritenta in caso di collisione (il
        vincolo UNIQUE lo impedirebbe comunque — astronomicamente
        improbabile con `secrets.token_urlsafe(32)`, vedi core.
        custom_webhook_logic — ma un retry pulito costa nulla ed
        evita di far fallire la creazione per un evento che non
        dovrebbe mai succedere).
        """
        for _ in range(5):
            token = generate_webhook_token()
            try:
                row = await self._pool.fetchrow(
                    """
                    INSERT INTO custom_webhooks
                        (guild_id, channel_id, token, label, message_template, created_by)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING *
                    """,
                    guild_id,
                    channel_id,
                    token,
                    label,
                    message_template or DEFAULT_MESSAGE_TEMPLATE,
                    created_by,
                )
                return self._row_to_webhook(row)
            except asyncpg.UniqueViolationError:
                continue
        raise RuntimeError("Impossibile generare un token webhook univoco dopo 5 tentativi.")

    async def get_by_token(self, token: str) -> CustomWebhook | None:
        row = await self._pool.fetchrow("SELECT * FROM custom_webhooks WHERE token = $1", token)
        return self._row_to_webhook(row) if row is not None else None

    async def list_webhooks(self, guild_id: int) -> list[CustomWebhook]:
        rows = await self._pool.fetch(
            "SELECT * FROM custom_webhooks WHERE guild_id = $1 ORDER BY created_at", guild_id
        )
        return [self._row_to_webhook(r) for r in rows]

    async def has_any_webhook(self) -> bool:
        """
        SEC-14: main.py lo controlla all'avvio per decidere se avviare
        il server web che riceve i webhook — nessun motivo di tenerlo
        in ascolto se nessun server ha mai creato un webhook custom.
        """
        row = await self._pool.fetchrow("SELECT EXISTS(SELECT 1 FROM custom_webhooks) AS esiste")
        return bool(row["esiste"])

    async def remove_webhook(self, webhook_id: int, guild_id: int) -> bool:
        """
        Scoperto per guild_id, stesso motivo di feed_subscription_
        repo.remove_subscription: un server non deve poter cancellare
        il webhook di un altro server anche conoscendone l'id.
        """
        result = await self._pool.execute(
            "DELETE FROM custom_webhooks WHERE id = $1 AND guild_id = $2",
            webhook_id,
            guild_id,
        )
        return result.endswith(" 1")


def _get_pool():
    from core.database import db
    return db.pool


custom_webhook_repo = CustomWebhookRepository(pool_provider=_get_pool)
