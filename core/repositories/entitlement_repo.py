"""
core/repositories/entitlement_repo.py
=====================================
Abbonamenti Discord (app premium) per server, tabella `premium_entitlements` (migrazione 0131).
Funzioni coperte: SPEC §3 (NF-22)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import asyncpg

from core.premium_cache import invalida_cache_premium


@dataclass(frozen=True)
class Entitlement:
    entitlement_id: int
    guild_id: int
    user_id: int | None
    sku_id: int
    starts_at: datetime | None
    ends_at: datetime | None
    deleted: bool


def _adesso() -> datetime:
    return datetime.now(timezone.utc)


class EntitlementRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    @staticmethod
    def _da_riga(riga) -> Entitlement:
        return Entitlement(
            entitlement_id=riga["entitlement_id"],
            guild_id=riga["guild_id"],
            user_id=riga["user_id"],
            sku_id=riga["sku_id"],
            starts_at=riga["starts_at"],
            ends_at=riga["ends_at"],
            deleted=riga["deleted"],
        )

    async def salva(self, voce: Entitlement) -> None:
        """Inserisce o aggiorna un diritto di Discord (eventi create/update/delete e allineamento)."""
        await self._pool.execute(
            """
            INSERT INTO premium_entitlements (entitlement_id, guild_id, user_id, sku_id, starts_at, ends_at, deleted)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (entitlement_id) DO UPDATE SET
                guild_id = EXCLUDED.guild_id, user_id = EXCLUDED.user_id, sku_id = EXCLUDED.sku_id,
                starts_at = EXCLUDED.starts_at, ends_at = EXCLUDED.ends_at, deleted = EXCLUDED.deleted,
                updated_at = now()
            """,
            voce.entitlement_id, voce.guild_id, voce.user_id, voce.sku_id, voce.starts_at, voce.ends_at, voce.deleted,
        )
        invalida_cache_premium(voce.guild_id)

    async def chiudi_non_piu_attivi(self, ids_attivi: set[int], aggiornati_prima_di: datetime | None = None) -> list[int]:
        """
        Dopo aver letto da Discord TUTTI i diritti attivi: segna eliminati quelli nostri che Discord non elenca più
        (persi mentre il bot era spento). Restituisce i server toccati.
        """
        righe = await self._pool.fetch(
            """
            UPDATE premium_entitlements SET deleted = TRUE, updated_at = now()
            WHERE NOT deleted AND (ends_at IS NULL OR ends_at > now()) AND NOT (entitlement_id = ANY($1::bigint[]))
              AND ($2::timestamptz IS NULL OR updated_at < $2)
            RETURNING guild_id
            """,
            list(ids_attivi),
            aggiornati_prima_di,
        )
        server = sorted({r["guild_id"] for r in righe})
        for guild_id in server:
            invalida_cache_premium(guild_id)
        return server

    async def attivo_per_server(self, guild_id: int, adesso: datetime | None = None) -> bool:
        return bool(
            await self._pool.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM premium_entitlements
                    WHERE guild_id = $1 AND NOT deleted
                      AND (starts_at IS NULL OR starts_at <= $2) AND (ends_at IS NULL OR ends_at > $2)
                )
                """,
                guild_id,
                adesso or _adesso(),
            )
        )

    async def elenco_server(self, guild_id: int) -> list[Entitlement]:
        righe = await self._pool.fetch(
            "SELECT * FROM premium_entitlements WHERE guild_id = $1 ORDER BY starts_at DESC NULLS LAST LIMIT 25",
            guild_id,
        )
        return [self._da_riga(r) for r in righe]


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


entitlement_repo = EntitlementRepository(pool_provider=_get_pool)
