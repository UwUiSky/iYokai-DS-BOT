"""
core/premium_modulo_service.py
==============================
Sblocco di UN modulo premium spendendo le monete della cassa del server (SPEC §3.1,
1.000.000 coin per 30 giorni). Un solo punto per il comando e per il futuro pannello (D16).
Funzioni coperte: SPEC §3.1 (#93)
Dipende da: core/repositories/guild_chest_repo.py, core/repositories/module_subscription_repo.py

L'addebito della cassa e lo sblocco stanno nella stessa transazione: se uno fallisce non resta
l'altro. Due richieste insieme pagano due volte e allungano due volte (è un rinnovo, non un errore).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from core.premium_cache import invalida_cache_premium
from core.premium_pricing_logic import COSTO_MODULO_IN_COIN, GIORNI_MODULO_IN_COIN
from core.repositories.guild_chest_repo import REASON_PREMIUM_MODULE, spend_in
from core.repositories.module_subscription_repo import module_subscription_repo


class EsitoSblocco(str, Enum):
    SBLOCCATO = "sbloccato"
    MODULO_SCONOSCIUTO = "modulo_sconosciuto"
    NON_PREMIUM = "non_premium"
    CASSA_INSUFFICIENTE = "cassa_insufficiente"


@dataclass(frozen=True)
class RisultatoSblocco:
    esito: EsitoSblocco
    costo: int = COSTO_MODULO_IN_COIN
    scade_il: datetime | None = None


async def sblocca_modulo_con_cassa(
    guild_id: int, module_name: str, user_id: int, now: datetime | None = None
) -> RisultatoSblocco:
    from core.database import db  # import locale per evitare cicli
    from core.premium import registry

    if registry.get(module_name) is None:
        return RisultatoSblocco(EsitoSblocco.MODULO_SCONOSCIUTO)
    if not registry.is_module_premium(module_name):
        return RisultatoSblocco(EsitoSblocco.NON_PREMIUM)

    adesso = now or datetime.now(timezone.utc)
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            if not await spend_in(conn, guild_id, COSTO_MODULO_IN_COIN, REASON_PREMIUM_MODULE):
                return RisultatoSblocco(EsitoSblocco.CASSA_INSUFFICIENTE)
            scadenza = await module_subscription_repo.grant(
                guild_id, module_name, GIORNI_MODULO_IN_COIN, user_id, adesso, conn=conn
            )
    invalida_cache_premium(guild_id)  # la transazione è chiusa
    return RisultatoSblocco(EsitoSblocco.SBLOCCATO, scade_il=scadenza)
