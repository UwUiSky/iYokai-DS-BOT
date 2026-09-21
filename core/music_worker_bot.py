"""
core/music_worker_bot.py
============================
Bot minimale per le 5 istanze Music worker (SPEC.md §9.1). Nessun
comando proprio, nessun cog caricato — i comandi arrivano SOLO dal
bot principale (cogs/music/player.py), che instrada verso l'istanza
giusta tramite core/music_fleet.py. Il worker esiste solo per avere
una propria connessione al gateway voce di Discord: ogni bot può
stare in un solo canale vocale per server alla volta, quindi serve
un token separato per ogni sessione musicale simultanea nello stesso
server — è l'unica ragione d'essere di questa classe.
"""

from __future__ import annotations

import discord
from discord.ext import commands


class MusicWorkerBot(commands.Bot):
    def __init__(self, worker_index: int) -> None:
        intents = discord.Intents.default()
        intents.voice_states = True
        # command_prefix non verrà mai usato davvero (nessun comando
        # testuale, nessuno slash command proprio) — richiesto solo
        # perché commands.Bot lo esige al costruttore.
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.worker_index = worker_index
