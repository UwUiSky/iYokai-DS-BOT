"""
core/repositories/module_subscription_repo.py
==================================================
Sblocco premium PER MODULO via pagamento mensile o annuale (SPEC.md
§3.1 — richiesto esplicitamente dall'utente: "per ora attivi solo
sblocco tramite nitro boost, pagamento mensile|annuale"). Nessun
gateway di pagamento reale integrato qui (Discord non ne fornisce
uno nativo utilizzabile da un bot normale, e questo progetto non
processa mai pagamenti — vedi core/premium_purchase_service.py per
lo stesso principio applicato al premium via cassa di server):
il pagamento avviene FUORI dal bot (PayPal, bonifico, ecc.), e
l'OWNER concede l'abbonamento a mano con `/owner premium-grant` dopo
averlo incassato — stesso schema "owner concede manualmente" già
usato per whitelist/blacklist in questo stesso cog.

Una riga per (guild_id, module_name): uno stesso server può avere
abbonamenti diversi attivi su moduli diversi, mai un unico switch
globale come whitelist/nitro boost (quelli sbloccano TUTTI i moduli
insieme, questo resta scoped al singolo modulo per design, come
esplicitamente previsto da SPEC.md §3.1 "per modulo").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class ModuleSubscription:
    guild_id: int
    module_name: str
    expires_at: datetime

    def is_active(self, now: datetime) -> bool:
        return self.expires_at > now


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS module_subscriptions (
            guild_id     BIGINT NOT NULL,
            module_name  TEXT NOT NULL,
            expires_at   TIMESTAMPTZ NOT NULL,
            granted_by   BIGINT,
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (guild_id, module_name)
        );
        """
    )


class ModuleSubscriptionRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def _row_to_subscription(self, row) -> ModuleSubscription:
        return ModuleSubscription(
            guild_id=row["guild_id"],
            module_name=row["module_name"],
            expires_at=row["expires_at"],
        )

    async def grant(
        self,
        guild_id: int,
        module_name: str,
        duration_days: int,
        granted_by: int | None = None,
        now: datetime | None = None,
    ) -> datetime:
        """
        Estende la scadenza di `duration_days` a partire dal MASSIMO
        tra `now` e la scadenza attuale — stesso pattern già usato da
        `GuildPremiumRepository.record_purchase` (§15.15): abbonamenti
        concessi in momenti diversi si accumulano invece di
        accavallarsi (un rinnovo anticipato non spreca i giorni
        restanti). Restituisce la nuova scadenza.
        """
        from datetime import timedelta

        adesso = now or _utcnow()

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                scadenza_attuale = await conn.fetchval(
                    "SELECT expires_at FROM module_subscriptions WHERE guild_id = $1 AND module_name = $2 FOR UPDATE",
                    guild_id,
                    module_name,
                )
                base = max(scadenza_attuale, adesso) if scadenza_attuale is not None else adesso
                nuova_scadenza = base + timedelta(days=duration_days)

                await conn.execute(
                    """
                    INSERT INTO module_subscriptions (guild_id, module_name, expires_at, granted_by)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (guild_id, module_name) DO UPDATE
                        SET expires_at = EXCLUDED.expires_at,
                            granted_by = EXCLUDED.granted_by,
                            updated_at = now()
                    """,
                    guild_id,
                    module_name,
                    nuova_scadenza,
                    granted_by,
                )
                return nuova_scadenza

    async def revoke(self, guild_id: int, module_name: str) -> bool:
        result = await self._pool.execute(
            "DELETE FROM module_subscriptions WHERE guild_id = $1 AND module_name = $2",
            guild_id,
            module_name,
        )
        return result.endswith(" 1")

    async def is_active(self, guild_id: int, module_name: str, now: datetime | None = None) -> bool:
        adesso = now or _utcnow()
        expires_at = await self._pool.fetchval(
            "SELECT expires_at FROM module_subscriptions WHERE guild_id = $1 AND module_name = $2",
            guild_id,
            module_name,
        )
        return expires_at is not None and expires_at > adesso

    async def list_for_guild(self, guild_id: int) -> list[ModuleSubscription]:
        rows = await self._pool.fetch(
            "SELECT * FROM module_subscriptions WHERE guild_id = $1 ORDER BY module_name",
            guild_id,
        )
        return [self._row_to_subscription(r) for r in rows]


def _utcnow() -> datetime:
    from datetime import timezone

    return datetime.now(timezone.utc)


def _get_pool():
    from core.database import db
    return db.pool


module_subscription_repo = ModuleSubscriptionRepository(pool_provider=_get_pool)
