"""
cogs/user_app/supporto.py
=========================
Assistenza di iYokai da qualsiasi server (SPEC §B.9): `/supporto apri|rispondi|elenco` di iYokai App.
La richiesta apre un thread nel canale dello staff (core/support_service.py); le risposte dello staff
arrivano in DM. Senza `SUPPORT_CHANNEL_ID` l'app rimanda al server di supporto. Si carica solo sul client
dell'app (core/user_app_bot.py).
Funzioni coperte: SPEC §B.9 (NF-36, #107)
Dipende da: core/support_service.py
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.config import config
from core.i18n import lingua_interazione, t, testo_per
from core.repositories.user_app_repo import user_app_repo
from core.support_service import (
    RichiestaNonTrovata,
    SupportoNonAttivo,
    TroppeRichieste,
    apri_richiesta,
    risposta_dell_utente,
)
from core.user_app_bot import e_istanza_app

INSTALLAZIONE = app_commands.AppInstallationType(guild=False, user=True)
OVUNQUE = app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True)


class SupportoCog(commands.Cog):
    supporto = app_commands.Group(
        name="supporto", description="Chiedi aiuto allo staff di iYokai da qualsiasi server.",
        allowed_installs=INSTALLAZIONE, allowed_contexts=OVUNQUE,
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _staff(self) -> discord.Client | None:
        return getattr(self.bot, "bot_principale", None)

    async def _spento(self, interaction: discord.Interaction) -> None:
        testo = await testo_per(interaction, "app_assistenza_spenta")
        if config.SUPPORT_SERVER_URL:
            testo += "\n" + config.SUPPORT_SERVER_URL
        await interaction.followup.send(testo, ephemeral=True)

    @supporto.command(name="apri", description="Apri una richiesta di assistenza con lo staff di iYokai.")
    @app_commands.describe(oggetto="Di cosa si tratta, in breve", testo="Spiega il problema")
    async def apri(
        self, interaction: discord.Interaction, oggetto: app_commands.Range[str, 3, 80], testo: app_commands.Range[str, 10, 1500]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        if self._staff() is None:
            await self._spento(interaction)
            return
        try:
            aperta = await apri_richiesta(
                self._staff(), config.SUPPORT_CHANNEL_ID, interaction.user.id, interaction.user.display_name, oggetto, testo
            )
        except TroppeRichieste:
            await interaction.followup.send(await testo_per(interaction, "app_assistenza_troppe"), ephemeral=True)
        except SupportoNonAttivo:
            await self._spento(interaction)
        else:
            await interaction.followup.send(await testo_per(interaction, "app_assistenza_aperta", numero=aperta.numero), ephemeral=True)

    @supporto.command(name="rispondi", description="Scrivi allo staff nella tua richiesta aperta.")
    @app_commands.describe(numero="Il numero della richiesta", testo="Cosa vuoi aggiungere")
    async def rispondi(
        self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 2_147_483_647],
        testo: app_commands.Range[str, 1, 1500],
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        if self._staff() is None:
            await self._spento(interaction)
            return
        try:
            await risposta_dell_utente(self._staff(), interaction.user.id, numero, testo)
        except RichiestaNonTrovata:
            await interaction.followup.send(await testo_per(interaction, "app_assistenza_non_trovata"), ephemeral=True)
        except SupportoNonAttivo:
            await self._spento(interaction)
        else:
            await interaction.followup.send(await testo_per(interaction, "app_assistenza_inviata", numero=numero), ephemeral=True)

    @supporto.command(name="elenco", description="Le tue ultime richieste di assistenza.")
    async def elenco(self, interaction: discord.Interaction) -> None:
        righe = await user_app_repo.richieste_utente(interaction.user.id)
        lingua = await lingua_interazione(interaction)
        if not righe:
            await interaction.response.send_message(t("app_assistenza_nessuna", lingua), ephemeral=True)
            return
        corpo = "\n".join(
            f"`{r['id']}` · {t('app_stato_richiesta_' + r['stato'], lingua)} · {discord.utils.format_dt(r['created_at'], 'R')} · {r['oggetto'][:60]}"
            for r in righe
        )
        embed = discord.Embed(title=t("app_assistenza_titolo", lingua), description=corpo, color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Solo sul client dell'app: il bot principale non riceve questi comandi."""
    if e_istanza_app(bot):
        await bot.add_cog(SupportoCog(bot))
