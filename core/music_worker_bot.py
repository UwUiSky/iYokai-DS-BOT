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

# F2 (#64): M 8.12 solo gli intent `guilds` e `voice_states`, nessun
# messaggio tenuto in memoria; M 8.13 AutoShardedBot (oltre 2.500 server).

from __future__ import annotations

import discord
from discord.ext import commands


class MusicWorkerBot(commands.AutoShardedBot):
    def __init__(self, worker_index: int) -> None:
        # LIM-49: il worker non legge i messaggi. Gli intent sono solo
        # questi due: `guilds` (vede i server e i canali) e
        # `voice_states` (entra e resta in vocale).
        intents = discord.Intents(guilds=True, voice_states=True)
        # command_prefix non verrà mai usato davvero (nessun comando
        # testuale, nessuno slash command proprio) — richiesto solo
        # perché commands.Bot lo esige al costruttore.
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            max_messages=None,
            # SEC-7: nessun comando proprio, ma il worker può comunque
            # inviare messaggi (es. "ora in riproduzione") — stesso
            # allowed_mentions sicuro del bot principale.
            allowed_mentions=discord.AllowedMentions(
                everyone=False, roles=False, users=True, replied_user=False
            ),
        )
        self.worker_index = worker_index
