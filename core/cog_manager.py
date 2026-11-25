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

logger = logging.getLogger("iyokai.cog_manager")


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


async def carica_cog(bot: commands.Bot, module_path: str) -> bool:
    """Carica un cog. True se è andato bene; un errore si scrive nel log e non si propaga."""
    try:
        await bot.load_extension(module_path)
    except commands.ExtensionAlreadyLoaded:
        return True
    except Exception:
        logger.exception("Impossibile caricare il cog: %s", module_path)
        return False
    logger.info("Cog caricato: %s", module_path)
    return True


async def load_all_cogs(bot: commands.Bot) -> list[str]:
    """
    Carica tutti i cog scoperti. Se UNO fallisce, lo logga e continua con gli altri.
    Restituisce i moduli che NON si sono caricati: chi chiama non deve sincronizzare i
    comandi con Discord finché la lista non è vuota (la sync toglierebbe ai server i
    comandi del modulo mancante) e deve riprovare a caricarli (core/avvio_sicuro.py).
    """
    falliti: list[str] = []
    caricati = 0
    for module_path in discover_cog_modules():
        if await carica_cog(bot, module_path):
            caricati += 1
        else:
            falliti.append(module_path)

    logger.info("Caricamento cog completato: %d ok, %d falliti", caricati, len(falliti))
    return falliti
