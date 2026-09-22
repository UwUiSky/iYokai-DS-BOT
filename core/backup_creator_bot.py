"""
core/backup_creator_bot.py
==============================
Bot minimale iYokai Creator (SPEC.md §11.1). Nessun comando proprio,
nessun cog caricato — esiste solo per creare nuovi server e clonarci
dentro il contenuto del server principale (core/backup_orchestrator.
py), poi cedere la proprietà e uscire di nuovo. Il token è già
dichiarato in config.py (YOKAI_CREATOR_TOKEN) da prima di questa
sessione, mai usato finora.

Resta SEMPRE sotto il limite di 10 server (creare senza mai
restare) — è l'unico motivo per cui è un'applicazione Discord
separata invece di far creare i server direttamente al bot
principale: Main deve poter gestire più di 10 server
contemporaneamente, Creator no, e i due ruoli non devono
interferire tra loro.
"""

from __future__ import annotations

import discord
from discord.ext import commands


class BackupCreatorBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        # command_prefix non verrà mai usato davvero (nessun comando
        # testuale, nessuno slash command proprio) — richiesto solo
        # perché commands.Bot lo esige al costruttore.
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
