"""
cogs/utility/log_webhook.py
===========================
`/admin-log webhook`: accende o spegne i log via webhook del server (#113, D33). Le righe di log escono da un webhook
del canale, raggruppate fino a 10 in un messaggio; i webhook hanno limiti di frequenza propri, separati da quelli
del bot. Serve il permesso «Gestisci webhook» e la chiave di cifratura del bot; senza, i log escono dal canale come prima.
`a_nome_utente` (D74, #160, spento di base): i log dei messaggi modificati e cancellati escono col nome e l'avatar dell'utente.
Funzioni coperte: SPEC §E, #113, #160
Dipende da: core/log_webhook.py
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.i18n import testo_per
from core.log_webhook import SETTING_LOG_WEBHOOK, acceso, imposta_a_nome_utente, spegni_server
from core.repositories.log_webhook_repo import log_webhook_repo


class LogWebhookCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "admin-log", nome="webhook",
        descrizione="Manda i log da un webhook del canale, raggruppati, con limiti suoi.",
    )
    @app_commands.describe(
        attivo="Sì per accendere, no per spegnere (e cancellare i webhook creati)",
        a_nome_utente="Sì: i log dei messaggi escono col nome e l'avatar di chi ha scritto (base: no)",
    )
    async def webhook(
        self, interaction: discord.Interaction, attivo: bool | None = None, a_nome_utente: bool | None = None
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(await testo_per(interaction, "accesso_solo_server"), ephemeral=True)
            return
        if attivo is None and a_nome_utente is None:
            await interaction.response.send_message(await testo_per(interaction, "logwh_scegli"), ephemeral=True)
            return
        if attivo:
            if not log_webhook_repo.chiave_presente():
                await interaction.response.send_message(await testo_per(interaction, "logwh_chiave_mancante"), ephemeral=True)
                return
            if not guild.me.guild_permissions.manage_webhooks:
                await interaction.response.send_message(await testo_per(interaction, "logwh_permesso"), ephemeral=True)
                return
        if a_nome_utente and attivo is not True and not await acceso(guild.id):
            await interaction.response.send_message(await testo_per(interaction, "logwh_nome_serve_webhook"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        risposte: list[str] = []
        if attivo is not None:
            await db.set_guild_setting(guild.id, SETTING_LOG_WEBHOOK, attivo, interaction.user.id)
            if attivo:
                risposte.append(await testo_per(interaction, "logwh_acceso"))
            else:
                quanti = await spegni_server(guild, self.bot)
                risposte.append(await testo_per(interaction, "logwh_spento", quanti=quanti))
        if a_nome_utente is not None:
            await imposta_a_nome_utente(guild.id, a_nome_utente, interaction.user.id)
            risposte.append(await testo_per(interaction, "logwh_nome_acceso" if a_nome_utente else "logwh_nome_spento"))
        await interaction.followup.send("\n".join(risposte), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LogWebhookCog(bot))
