"""
core/premium_entitlement_service.py
===================================
Legge gli abbonamenti Discord (app premium) e li trasforma in accesso premium per il server (NF-22, #93).
Un abbonamento di server sblocca tutti i moduli premium finché dura. Gli abbonamenti di utente (senza server) si
ignorano. Il pagamento esterno resta `/owner premium grant`.
Funzioni coperte: SPEC §3 (NF-22)
Dipende da: core/repositories/entitlement_repo.py, core/migrations/0131_entitlements.sql
"""

from __future__ import annotations

import dataclasses
import logging

from core.repositories.entitlement_repo import Entitlement, entitlement_repo

logger = logging.getLogger("iyokai.premium")


def da_discord(diritto, sku_ammesso: int = 0) -> Entitlement | None:
    """
    Il nostro `Entitlement` dal diritto di Discord (`discord.Entitlement`), o None se non riguarda un server
    o è di un SKU diverso da quello venduto (`sku_ammesso`, 0 = tutti).
    """
    guild_id = getattr(diritto, "guild_id", None)
    if not guild_id:
        return None
    if sku_ammesso and diritto.sku_id != sku_ammesso:
        return None
    return Entitlement(
        entitlement_id=diritto.id,
        guild_id=guild_id,
        user_id=getattr(diritto, "user_id", None),
        sku_id=diritto.sku_id,
        starts_at=getattr(diritto, "starts_at", None),
        ends_at=getattr(diritto, "ends_at", None),
        deleted=bool(getattr(diritto, "deleted", False)),
    )


async def registra_evento(diritto, *, eliminato: bool = False) -> bool:
    """Evento create/update/delete di Discord. True se il diritto riguarda un server e lo abbiamo registrato."""
    from core.config import config

    voce = da_discord(diritto, config.PREMIUM_SKU_ID)
    if voce is None:
        return False
    if eliminato:
        voce = dataclasses.replace(voce, deleted=True)
    await entitlement_repo.salva(voce)
    logger.info("Abbonamento Discord %s del server %s: %s.", voce.entitlement_id, voce.guild_id, "chiuso" if voce.deleted else "registrato")
    return True


async def allinea_con_discord(bot) -> int:
    """
    All'avvio: legge da Discord tutti i diritti non scaduti, li salva, e chiude quelli che Discord non elenca più
    (persi mentre il bot era spento). Se la lettura si interrompe a metà non chiude niente. Restituisce quanti
    diritti ha registrato.
    """
    from core.config import config

    trovati: list[Entitlement] = []
    ids_visti: set[int] = set()
    async for diritto in bot.entitlements(exclude_ended=True):
        ids_visti.add(diritto.id)  # anche quelli di SKU diverso: non vanno chiusi da noi
        voce = da_discord(diritto, config.PREMIUM_SKU_ID)
        if voce is not None:
            trovati.append(voce)
    for voce in trovati:
        await entitlement_repo.salva(voce)
    await entitlement_repo.chiudi_non_piu_attivi(ids_visti)
    return len(trovati)


async def server_ha_abbonamento(guild_id: int) -> bool:
    """True se il server ha un abbonamento Discord in corso."""
    return await entitlement_repo.attivo_per_server(guild_id)


async def abbonamenti_del_server(guild_id: int) -> list[Entitlement]:
    return await entitlement_repo.elenco_server(guild_id)
