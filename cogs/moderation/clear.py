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

Filtri (core/clear_filter_logic.py): utente, ruolo, solo bot, solo persone,
allegati, testo contenuto o non contenuto, link, inviti, embed, menzioni,
salta i fissati. Il testo dei messaggi serve il Message Content Intent
(acceso in main.py; sotto i 10.000 utenti basta l'interruttore nel
Developer Portal, da 10.000 serve la domanda a Discord, da rifare ogni
anno). Il canale può essere diverso da quello del comando; ogni pulizia
scrive una riga nel log di moderazione (M 1.8).
Funzioni coperte: SPEC §5.4 (MOD-069, 071, 073-079, 083, 084, 086, 088)
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo

from core.premium import PremiumModule, registry, requires_module
from core.clear_filter_logic import FiltriClear, descrivi_filtri, messaggio_passa
from cogs.moderation._shared import (
    MODULE_CLEAR,
    ensure_module_enabled,
    post_to_mod_log,
    truncate_text,
)

MAX_CLEAR_AMOUNT = 200


class ModerationClearCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "mod",
        nome="clear",
        descrizione="Cancella un numero di messaggi, con filtri opzionali.",
    )
    @app_commands.describe(
        amount="Quanti messaggi controllare (max 200)",
        member="Cancella solo i messaggi di questo utente",
        bots_only="Cancella solo i messaggi inviati da bot o webhook",
        attachments_only="Cancella solo i messaggi con allegati",
        channel="Il canale da pulire (default: quello attuale)",
        humans_only="Cancella solo i messaggi di persone (non bot)",
        contains="Cancella solo i messaggi che contengono questo testo",
        not_contains="Cancella solo i messaggi che NON contengono questo testo",
        links_only="Cancella solo i messaggi con link",
        invites_only="Cancella solo i messaggi con inviti Discord",
        embeds_only="Cancella solo i messaggi con embed",
        mentions_only="Cancella solo i messaggi con menzioni",
        role="Cancella solo i messaggi di chi ha questo ruolo",
        skip_pinned="Salta i messaggi fissati",
    )
    @requires_module(MODULE_CLEAR)
    async def clear(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, MAX_CLEAR_AMOUNT],
        member: discord.Member | None = None,
        bots_only: bool = False,
        attachments_only: bool = False,
        channel: discord.TextChannel | None = None,
        humans_only: bool = False,
        contains: app_commands.Range[str, 1, 100] | None = None,
        not_contains: app_commands.Range[str, 1, 100] | None = None,
        links_only: bool = False,
        invites_only: bool = False,
        embeds_only: bool = False,
        mentions_only: bool = False,
        role: discord.Role | None = None,
        skip_pinned: bool = False,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CLEAR):
            return

        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message(
                "Questo comando funziona solo su canali testuali.", ephemeral=True
            )
            return

        filtri = FiltriClear(
            autore_id=member.id if member else None,
            solo_bot=bots_only,
            solo_persone=humans_only,
            solo_allegati=attachments_only,
            contiene=contains,
            non_contiene=not_contains,
            solo_link=links_only,
            solo_inviti=invites_only,
            solo_embed=embeds_only,
            solo_menzioni=mentions_only,
            ruolo_id=role.id if role else None,
            salta_fissati=skip_pinned,
        )
        if bots_only and humans_only:
            await interaction.response.send_message(
                "«Solo bot» e «solo persone» insieme non cancellano niente.", ephemeral=True
            )
            return

        # Risponde SUBITO in modo ephemeral, prima di iniziare la
        # cancellazione: se ci sono molti messaggi vecchi (>14 giorni)
        # l'operazione può richiedere diversi secondi, e Discord
        # scade l'interazione dopo 3 secondi se non si risponde prima.
        await interaction.response.defer(ephemeral=True)

        try:
            eliminati = await target.purge(limit=amount, check=lambda m: messaggio_passa(m, filtri))
        except discord.HTTPException:
            await interaction.followup.send(
                "Non sono riuscito a cancellare i messaggi: controlla i miei permessi in questo canale.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"{len(eliminati)} messaggi cancellati.", ephemeral=True
        )
        embed = discord.Embed(title="🧹 Clear", color=discord.Color.light_grey())
        embed.add_field(name="Canale", value=target.mention, inline=True)
        embed.add_field(name="Moderatore", value=interaction.user.mention, inline=True)
        embed.add_field(name="Cancellati", value=str(len(eliminati)), inline=True)
        embed.add_field(
            name="Filtri", value=truncate_text(descrivi_filtri(filtri), 1000), inline=False
        )
        await post_to_mod_log(interaction.guild, embed)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_CLEAR,
            display_name="Moderazione — Clear avanzato",
            category="moderation",
            description="Cancellazione di massa dei messaggi con filtri.",
            premium_capable=True,
        )
    )
    await bot.add_cog(ModerationClearCog(bot))
