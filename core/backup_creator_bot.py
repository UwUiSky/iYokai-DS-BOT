"""
core/backup_creator_bot.py
==========================
Bot minimale iYokai Creator (SPEC.md §11.1, D8). Nessun comando proprio:
entra nel server di backup creato da un admin, lo porta allo stato corrente
del server principale e lo tiene aggiornato (core/backup_orchestrator.py).
Ha un'applicazione separata perché i limiti di frequenza di Discord valgono
per ogni bot: il lavoro pesante di copia non rallenta il bot principale.
Funzioni coperte: SPEC §11.1, M 12.2
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
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            # SEC-7: stesso allowed_mentions sicuro del bot principale.
            allowed_mentions=discord.AllowedMentions(
                everyone=False, roles=False, users=True, replied_user=False
            ),
        )
