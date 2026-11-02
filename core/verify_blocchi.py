"""
core/verify_blocchi.py
======================
Blocchi della verifica web e ticket in privato (D65): ogni volta che la verifica non va (VPN/proxy, paese,
controlli del server) si ricorda server e motivo, e il testo per la persona la invita a scrivere in privato
al bot. Quel messaggio apre il ticket ModMail con lo staff del server, con il motivo allegato
(`cogs/tickets/modmail.py`). L'invito c'è solo se il ModMail di quel server è pronto.
Funzioni coperte: SPEC §4.2 (blocchi e ticket, D65)
Dipende da: core/repositories/verify_blocchi_repo.py, cogs/tickets/modmail.py (che legge la tabella)
"""

from __future__ import annotations

import logging

import discord

from core.database import db
from core.i18n import testo_guild

logger = logging.getLogger("iyokai.verify_blocchi")


async def modmail_pronto(guild: discord.Guild) -> bool:
    """Il server ha il ModMail acceso e una categoria dove aprire i ticket."""
    try:
        from cogs.tickets.tickets import MODULE_TICKETS
        from core.repositories.modmail_repo import modmail_repo

        return await db.is_module_active_for_guild(guild.id, MODULE_TICKETS) and await modmail_repo.categoria(guild.id) is not None
    except Exception:  # il ModMail non è raggiungibile: niente invito, la verifica resta com'è
        logger.warning("Stato del ModMail non leggibile nel server %s.", guild.id, exc_info=True)
        return False


async def dopo_blocco(guild: discord.Guild, user_id: int, testo: str) -> str:
    """Il testo per la persona bloccata, con l'invito a scrivere in privato; il blocco si ricorda per il ticket."""
    if not await modmail_pronto(guild):
        return testo
    from core.repositories.verify_blocchi_repo import verify_blocchi_repo

    try:
        await verify_blocchi_repo.registra(user_id, guild.id, testo)
    except Exception:
        logger.warning("Blocco della verifica non salvato nel server %s.", guild.id, exc_info=True)
        return testo
    invito = await testo_guild(guild, "verify_blocco_ticket", server=guild.name)
    return f"{testo}\n{invito}"
