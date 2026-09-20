"""
core/blacklist_tree.py
=========================
CommandTree personalizzata (SPEC.md §17.4/17.5) — il punto di innesto
scelto per bloccare GLOBALMENTE le interazioni di utenti/server in
blacklist, prima che qualunque comando (di qualunque cog) venga
eseguito. discord.py chiama interaction_check() su OGNI interazione
di slash command, prima del dispatch al comando specifico — un solo
punto, non serve ripetere il controllo in ogni singolo cog.

Verificato prima di scrivere questo file: sovrascrivere
interaction_check() richiede di SOTTOCLASSARE CommandTree e passare
tree_cls=... a commands.Bot(), non basta assegnare una funzione
all'istanza — l'implementazione di default in discord.py è pensata
per essere sovrascritta via ereditarietà.
"""

from __future__ import annotations

import logging

import discord

from core.bot_stats import command_counter
from core.repositories.blacklist_repo import blacklist_repo

logger = logging.getLogger("iyokai.blacklist_tree")


class BlacklistAwareCommandTree(discord.app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if await blacklist_repo.is_user_blacklisted(interaction.user.id):
            try:
                await interaction.response.send_message(
                    "Sei stato bloccato dall'uso di questo bot.", ephemeral=True
                )
            except discord.HTTPException:
                pass
            return False

        if interaction.guild is not None and await blacklist_repo.is_guild_blacklisted(
            interaction.guild.id
        ):
            # Nessuna risposta: il server intero è in blacklist, non
            # ha senso rispondere a un singolo comando al suo interno
            # (il bot dovrebbe già essere uscito da tempo — vedi
            # on_guild_join in main.py — questo è solo un secondo
            # livello di difesa se per qualche motivo è ancora dentro).
            return False

        # Contato qui, non con un hook "on_completion" dedicato: 
        # questa versione di discord.py non ne espone uno su
        # CommandTree. Conta i comandi CHE ARRIVANO al dispatch
        # (superano la blacklist), non necessariamente quelli che
        # completano senza errori — proxy ragionevole per "quanto è
        # attivo il bot", usato da /owner stats (SPEC.md §17.8).
        command_counter.record()
        return True
