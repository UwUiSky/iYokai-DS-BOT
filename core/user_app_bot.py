"""
core/user_app_bot.py
====================
Client di iYokai App (NF-36): applicazione Discord a parte che l'utente
installa su di sé, con un albero proprio (non tocca i 100 comandi del
principale). Stesso processo e stesso database, token `YOKAI_APP_TOKEN`:
vuoto, l'app non parte. Carica solo i cog di `cogs/user_app/`.
Funzioni coperte: SPEC §B (NF-36)
"""

from __future__ import annotations

import importlib

import discord
from discord.ext import commands

from discord import app_commands

from core.blacklist_tree import LIMITE_MENU_PER_TIPO as LIMITE_MENU, BlacklistAwareCommandTree
from core.command_sync import StatoSyncDatabase, sincronizza_se_cambiato
from core.command_translator import TraduttoreYokai
from core.premium import handle_app_command_error

ISTANZA_APP = "app"
SCOPE_SYNC = "app:global"
MODULI_COG = (
    "cogs.user_app.personal", "cogs.user_app.strumenti", "cogs.user_app.messaggi", "cogs.user_app.supporto", "cogs.user_app.risposte", "cogs.user_app.impostazioni", "cogs.user_app.divertimento", "cogs.user_app.radio", "cogs.user_app.desktop",
    "cogs.user_app.voce_app", "cogs.user_app.assistente_app",
)


# I 15 menu per tipo (LIMITI.md §1.3) li gestisce `BlacklistAwareCommandTree`, anche per il bot principale.
LIMITE_MENU_PER_TIPO = LIMITE_MENU

AlberoApp = BlacklistAwareCommandTree


def e_istanza_app(bot: object) -> bool:
    return getattr(bot, "istanza", None) == ISTANZA_APP


class UserAppBot(commands.Bot):
    istanza = ISTANZA_APP

    def __init__(self, bot_principale: discord.Client | None = None) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=discord.Intents.none(),
            help_command=None,
            tree_cls=AlberoApp,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        # Per i promemoria: se l'app non può scrivere in DM, prova il bot principale.
        self.bot_principale = bot_principale
        self.tree.error(handle_app_command_error)

    async def carica_cog(self) -> None:
        for nome in MODULI_COG:
            await importlib.import_module(nome).setup(self)
        await self.tree.set_translator(TraduttoreYokai())

    async def setup_hook(self) -> None:
        from core.database import db

        await self.carica_cog()
        await sincronizza_se_cambiato(
            SCOPE_SYNC, self.tree.get_commands(), self.tree, self.tree.sync, StatoSyncDatabase(db.pool)
        )
