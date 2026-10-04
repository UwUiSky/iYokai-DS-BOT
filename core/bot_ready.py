"""
core/bot_ready.py
=================
Attesa "il bot è pronto" sicura anche prima del login, per i
`before_loop` dei servizi periodici di core/. `wait_until_ready()` prima
del login solleva RuntimeError e discord.ext.tasks chiude il loop per
sempre; `is_ready()` invece risponde solo False.
Funzioni coperte: REVIEW.md BUG-19.
"""

from __future__ import annotations

import asyncio

import discord

INTERVALLO_SECONDI = 1.0


async def attendi_bot_pronto(bot: discord.Client, intervallo: float = INTERVALLO_SECONDI) -> None:
    """Aspetta che il bot sia pronto, controllando ogni `intervallo` secondi."""
    while not bot.is_ready():
        await asyncio.sleep(intervallo)
