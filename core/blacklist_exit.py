"""
core/blacklist_exit.py
======================
Un server in blacklist fa uscire TUTTI i bot: il principale e i worker
musicali (M 13.2, REVIEW §12, SPEC 17.5).
"""

from __future__ import annotations

import logging

import discord

logger = logging.getLogger("iyokai.blacklist")


def _bot_da_far_uscire(bot) -> list:
    """Il bot principale e, se c'è la flotta musicale, i suoi worker."""
    bots = [bot]
    flotta = getattr(bot, "music_fleet", None)
    if flotta is not None:
        bots.extend(flotta.worker_bots)
    return bots


async def esci_da_server_in_blacklist(bot, guild_id: int, guild=None) -> int:
    """
    Fa lasciare il server `guild_id` a ogni bot che ci è dentro. Un bot che
    fallisce (Discord giù, già uscito) non ferma gli altri. Restituisce
    quanti bot sono usciti. `guild` è l'oggetto già in mano al bot principale
    (l'evento di ingresso), usato al posto della ricerca nella sua cache.
    """
    usciti = 0
    for client in _bot_da_far_uscire(bot):
        server = guild if (client is bot and guild is not None) else client.get_guild(guild_id)
        if server is None:
            continue
        try:
            await server.leave()
            usciti += 1
        except discord.HTTPException:
            logger.warning(
                "Uscita dal server %s non riuscita per un bot (blacklist).", guild_id, exc_info=True
            )
    return usciti
