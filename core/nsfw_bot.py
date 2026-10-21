"""
core/nsfw_bot.py
================
Client dell'istanza NSFW (NF-23): applicazione Discord a parte, stesso
processo e stesso database, token `NSFW_TOKEN`. Carica solo i cog di
`cogs/nsfw/`, sincronizza il suo albero (ambito `nsfw:global`) e avvia la
pubblicazione automatica. Senza `NSFW_TOKEN` non parte e il resto del bot
va come prima.
Funzioni coperte: SPEC §16.10 (NF-23)
"""

from __future__ import annotations

import importlib
import logging

import discord
from discord.ext import commands

from core.blacklist_tree import BlacklistAwareCommandTree
from core.command_sync import StatoSyncDatabase, sincronizza_se_cambiato
from core.command_translator import TraduttoreYokai
from core.premium import handle_app_command_error

logger = logging.getLogger("iyokai.nsfw_bot")

ISTANZA_NSFW = "nsfw"
SCOPE_SYNC = "nsfw:global"
MODULI_COG = ("cogs.nsfw.ricerca",)


def intent_nsfw() -> discord.Intents:
    """Solo i server e i loro canali: niente membri, niente testo dei messaggi."""
    intents = discord.Intents.none()
    intents.guilds = True
    return intents


def e_istanza_nsfw(bot: object) -> bool:
    return getattr(bot, "istanza", None) == ISTANZA_NSFW


class NsfwBot(commands.Bot):
    istanza = ISTANZA_NSFW

    def __init__(self) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intent_nsfw(),
            help_command=None,
            tree_cls=BlacklistAwareCommandTree,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.tree.error(handle_app_command_error)

    async def carica_cog(self) -> None:
        for nome in MODULI_COG:
            await importlib.import_module(nome).setup(self)
        await self.tree.set_translator(TraduttoreYokai())

    async def setup_hook(self) -> None:
        from core.database import db
        from core.nsfw_autopost_worker import nsfw_autopost_worker
        from cogs.nsfw.ricerca import vista_pubblicazione

        await self.carica_cog()
        await sincronizza_se_cambiato(
            SCOPE_SYNC, self.tree.get_commands(), self.tree, self.tree.sync, StatoSyncDatabase(db.pool)
        )
        nsfw_autopost_worker.start(self, vista_pubblicazione)

    async def on_guild_join(self, guild: discord.Guild) -> None:
        from core.repositories.nsfw_repo import nsfw_repo

        try:
            await nsfw_repo.segna_presenza(guild.id, True)
        except Exception:
            logger.exception("Presenza NSFW non segnata (server %s)", guild.id)

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Uscito: la pubblicazione automatica si ferma subito e partono i 90 giorni (D6)."""
        from core.repositories.nsfw_repo import nsfw_repo

        try:
            await nsfw_repo.togli_autopost(guild.id)
            await nsfw_repo.segna_presenza(guild.id, False)
        except Exception:
            logger.exception("Uscita NSFW non registrata (server %s)", guild.id)
