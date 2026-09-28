"""
tests/support/full_tree.py
==============================
Carica TUTTI i cog in un unico bot di test, come fa il bot vero, e
restituisce il bot con l'albero comandi completo.
"""

from __future__ import annotations

import importlib

import discord
from discord.ext import commands

from core.cog_manager import discover_cog_modules
from core.database import db


async def build_full_bot() -> tuple[commands.Bot, list[tuple[str, str]]]:
    """
    Crea un bot, chiama setup() di ogni cog e restituisce
    (bot, cog_falliti). Il chiamante deve aver già connesso il
    database globale `core.database.db`.

    Usa importlib.import_module + setup() e non bot.load_extension:
    load_extension ri-esegue ogni modulo e sostituirebbe le classi e
    i singleton già importati dagli altri test.
    """
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    falliti: list[tuple[str, str]] = []
    for modulo_path in sorted(discover_cog_modules()):
        try:
            modulo = importlib.import_module(modulo_path)
            await modulo.setup(bot)
        except Exception as exc:
            falliti.append((modulo_path, f"{type(exc).__name__}: {exc}"))
    return bot, falliti


async def close_full_bot(bot: commands.Bot) -> None:
    """Scarica i cog (ferma i loop avviati) e chiude il bot di test."""
    for nome in list(bot.cogs):
        await bot.remove_cog(nome)
    await bot.close()


async def connect_db_if_needed() -> bool:
    """Connette il database globale se serve. Restituisce True se l'ha connesso lui."""
    if db._pool is not None:
        return False
    await db.connect()
    await db.run_migrations()
    return True
