"""
core/tag_eliminazione.py
========================
Tutto ciò che va tolto quando un tag viene eliminato: errori dello script, inneschi, comandi e menu del server.
Se c'erano comandi o menu, l'albero si rimonta e la sync si mette in coda.
Funzioni coperte: catalogo #128 (B25-B28)
"""

from __future__ import annotations

import logging

from core.repositories.slash_server_repo import slash_server_repo
from core.repositories.tag_inneschi_repo import tag_inneschi_repo
from core.repositories.tag_script_repo import tag_script_repo

logger = logging.getLogger("iyokai.tag_eliminazione")


async def pulisci_tag_eliminato(bot, guild_id: int, nome: str) -> None:
    """Non lancia: il tag è già eliminato, una pulizia fallita si scrive nel log."""
    tolti = 0
    try:
        await tag_script_repo.togli_errori(guild_id, nome)
        await tag_inneschi_repo.togli_per_tag(guild_id, nome)
        tolti = await slash_server_repo.togli_per_tag(guild_id, nome)
    except Exception:
        logger.warning("Pulizia del tag %s non completa.", nome, exc_info=True)
    if not tolti:
        return
    cog = bot.get_cog("SlashServerCog")
    if cog is not None:
        try:
            await cog.dopo_tag_eliminato(guild_id)
        except Exception:
            logger.warning("Sync dei comandi del server %s dopo l'eliminazione del tag non riuscita.", guild_id, exc_info=True)
