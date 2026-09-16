"""
core/cog_manager.py
=====================
Scopre automaticamente tutti i cog dentro la cartella cogs/ e li
carica all'avvio. Così, per aggiungere un nuovo modulo, basta
creare il file dentro la sottocartella giusta (es.
cogs/moderation/ban.py) — non serve registrarlo a mano da nessuna
parte.

Ogni file .py dentro cogs/ (nei sottopacchetti) che espone una
funzione `setup(bot)` viene trattato come un cog e caricato.
"""

from __future__ import annotations

import pkgutil
import importlib
import logging

from discord.ext import commands

logger = logging.getLogger("yokai.cog_manager")


def discover_cog_modules(package_name: str = "cogs") -> list[str]:
    """
    Cammina ricorsivamente dentro il pacchetto `cogs` e restituisce
    la lista dei percorsi di modulo (es. "cogs.moderation.ban") di
    ogni file .py trovato, escludendo i file che iniziano con "_"
    (utili per __init__.py o per moduli di supporto non-cog).
    """
    package = importlib.import_module(package_name)
    modules: list[str] = []

    for module_info in pkgutil.walk_packages(
        package.__path__, prefix=f"{package_name}."
    ):
        # Salta i pacchetti (cartelle), interessano solo i file .py
        if module_info.ispkg:
            continue
        # Salta moduli "privati" (es. cogs/moderation/_helpers.py)
        short_name = module_info.name.rsplit(".", 1)[-1]
        if short_name.startswith("_"):
            continue
        modules.append(module_info.name)

    return modules


async def load_all_cogs(bot: commands.Bot) -> None:
    """
    Carica tutti i cog scoperti. Se UNO fallisce, lo logga e
    continua con gli altri — un cog rotto non deve impedire
    l'avvio di tutto il resto del bot.
    """
    modules = discover_cog_modules()
    loaded = 0
    failed = 0

    for module_path in modules:
        try:
            await bot.load_extension(module_path)
            logger.info("Cog caricato: %s", module_path)
            loaded += 1
        except Exception:
            logger.exception("Impossibile caricare il cog: %s", module_path)
            failed += 1

    logger.info("Caricamento cog completato: %d ok, %d falliti", loaded, failed)
