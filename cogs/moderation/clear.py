"""
cogs/moderation/clear.py
===========================
Cancellazione di massa dei messaggi, con filtri opzionali. Modulo
CANDIDATO PREMIUM (MODULE_CLEAR), come da schema.

Nota sul limite dei 14 giorni: discord.py gestisce già da solo la
differenza tra bulk-delete (messaggi più recenti di 14 giorni, veloce,
un'unica chiamata per gruppi fino a 100) e cancellazione singola
(messaggi più vecchi, una richiesta alla volta, molto più lenta) —
non serve reimplementare questa logica qui, `channel.purge()` la fa
già internamente. Il limite resta comunque REALE: cancellare molti
messaggi vecchi può richiedere diversi secondi per via del rate limit
sulle cancellazioni singole.

Nessun filtro per "contenuto testuale" (es. "contiene parola X"):
richiederebbe il Message Content Intent, che nel progetto resta
disattivato di default (vedi main.py) finché un modulo non lo
giustifica esplicitamente in fase di richiesta della verifica
Discord — un filtro di clear non vale quella spesa.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import PremiumModule, registry, requires_module
from cogs.moderation._shared import MODULE_CLEAR, ensure_module_enabled

MAX_CLEAR_AMOUNT = 200


class ModerationClearCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="clear", description="Cancella un numero di messaggi, con filtri opzionali."
    )
    @app_commands.describe(
        amount="Quanti messaggi cancellare (max 200)",
        member="Cancella solo i messaggi di questo utente",
        bots_only="Cancella solo i messaggi inviati da bot",
        attachments_only="Cancella solo i messaggi con allegati",
    )
    @requires_module(MODULE_CLEAR)
    async def clear(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, MAX_CLEAR_AMOUNT],
        member: discord.Member | None = None,
        bots_only: bool = False,
        attachments_only: bool = False,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CLEAR):
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                "Questo comando funziona solo su canali testuali.", ephemeral=True
            )
            return

        def check(message: discord.Message) -> bool:
            if member is not None and message.author.id != member.id:
                return False
            if bots_only and not message.author.bot:
                return False
            if attachments_only and not message.attachments:
                return False
            return True

        # Risponde SUBITO in modo ephemeral, prima di iniziare la
        # cancellazione: se ci sono molti messaggi vecchi (>14 giorni)
        # l'operazione può richiedere diversi secondi, e Discord
        # scade l'interazione dopo 3 secondi se non si risponde prima.
        await interaction.response.defer(ephemeral=True)

        try:
            eliminati = await interaction.channel.purge(limit=amount, check=check)
        except discord.Forbidden:
            await interaction.followup.send(
                "Non ho i permessi per cancellare messaggi in questo canale.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"{len(eliminati)} messaggi cancellati.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_CLEAR,
            display_name="Moderazione — Clear avanzato",
            description="Cancellazione di massa dei messaggi con filtri.",
            premium_capable=True,
        )
    )
    await bot.add_cog(ModerationClearCog(bot))
