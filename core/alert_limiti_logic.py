"""
core/alert_limiti_logic.py
==========================
Quanti avvisi può avere un server: un tetto per tipo e uno in tutto, più alti con il premium (ALR-041).
I servizi esterni hanno quote (LIM-16, LIM-46): il tetto le protegge. Funzioni coperte: SPEC §10.9 (#129 ALR-041)
"""

from __future__ import annotations

TETTO_TIPO_BASE = 25
TETTO_TOTALE_BASE = 50
MOLTIPLICATORE_PREMIUM = 4  # 100 per tipo, 200 in tutto


async def server_premium(guild_id: int, bot=None) -> bool:
    from core.premium import guild_has_premium_access

    try:
        return await guild_has_premium_access(guild_id, "feed_alerts", bot=bot)
    except Exception:  # un controllo premium che si rompe non deve bloccare gli avvisi: vale il piano gratuito
        return False


async def tetti(guild_id: int, bot=None) -> tuple[int, int]:
    """(tetto per tipo, tetto in tutto) del server."""
    m = MOLTIPLICATORE_PREMIUM if await server_premium(guild_id, bot) else 1
    return TETTO_TIPO_BASE * m, TETTO_TOTALE_BASE * m


async def tetto_e_pieno(guild_id: int, bot=None) -> tuple[int, bool]:
    """(tetto per tipo da passare al repository, True se il server ha già il massimo di avvisi in tutto)."""
    from core.repositories.alert_gestione_repo import alert_gestione_repo

    per_tipo, totale = await tetti(guild_id, bot)
    return per_tipo, len(await alert_gestione_repo.elenco(guild_id)) >= totale
