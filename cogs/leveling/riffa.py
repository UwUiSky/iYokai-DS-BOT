"""
cogs/leveling/riffa.py
======================
Riffa del server (/admin-giochi evento riffa): lo staff mette un premio pagato dalla cassa del server, chi clicca
«Partecipa» entra una volta sola, alla scadenza si estrae un vincitore e il premio passa dalla cassa al
vincitore in una transazione sola (se la cassa non basta più, la riffa è annullata e non si muove niente).
Se il bot si riavvia durante la riffa, nessuna moneta si è mossa.
Funzioni coperte: ECO-119
Dipende da: core/repositories/guild_chest_repo.py
"""

from __future__ import annotations

import logging
import secrets

import discord
from discord import app_commands
from discord.ext import commands

from cogs.leveling.evento_monete import _SG
from cogs.leveling.leveling import _comando_rifiutato
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.i18n import testo_per
from core.repositories.blacklist_repo import blacklist_repo
from core.repositories.guild_chest_repo import REASON_EVENT_WINNER_PRIZE, guild_chest_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.riffa")
NESSUNA_MENZIONE = discord.AllowedMentions.none()
MAX_PARTECIPANTI = 500


class RiffaView(BaseView):
    def __init__(self, guild_id: int, premio: int, minuti: int, moneta: str, staff_id: int) -> None:
        super().__init__(timeout=minuti * 60)
        self.guild_id, self.premio, self.moneta, self.staff_id = guild_id, premio, moneta, staff_id
        self.iscritti: set[int] = set()
        self.messaggio: discord.Interaction | None = None
        self.chiusa = False

    @discord.ui.button(label="Partecipa", emoji="🎟️", style=discord.ButtonStyle.success)
    async def partecipa(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.chiusa or interaction.user.bot:
            await interaction.response.send_message(await testo_per(interaction, "leveling_gia_fatto"), ephemeral=True)
            return
        if interaction.user.id in self.iscritti:
            await interaction.response.send_message(await testo_per(interaction, "rif_gia"), ephemeral=True)
            return
        if len(self.iscritti) >= MAX_PARTECIPANTI:
            await interaction.response.send_message(await testo_per(interaction, "rif_piena"), ephemeral=True)
            return
        self.iscritti.add(interaction.user.id)  # nessun await tra controllo e inserimento
        await interaction.response.send_message(await testo_per(interaction, "rif_dentro", n=len(self.iscritti)), ephemeral=True)

    async def estrai(self) -> tuple[int | None, str]:
        """Sceglie il vincitore e paga dalla cassa. (vincitore, esito): «ok», «nessuno», «cassa» o «blacklist»."""
        if self.chiusa:
            return None, "chiusa"
        self.chiusa = True
        self.stop()
        candidati = sorted(self.iscritti)
        # chi è in blacklist non vince: si sceglie tra gli altri
        candidati = [u for u in candidati if not await blacklist_repo.is_user_blacklisted(u)]
        if not candidati:
            return None, "nessuno"
        vincitore = candidati[secrets.randbelow(len(candidati))]
        if not await guild_chest_repo.pay_members(self.guild_id, [vincitore], self.premio, reason=REASON_EVENT_WINNER_PRIZE):
            return None, "cassa"
        return vincitore, "ok"

    async def on_timeout(self) -> None:
        vincitore, esito = await self.estrai()
        if self.messaggio is None or esito == "chiusa":
            return
        chiave = {"ok": "rif_vinta", "nessuno": "rif_nessuno", "cassa": "rif_cassa"}[esito]
        try:
            await self.messaggio.edit_original_response(
                content=await testo_per(self.messaggio, chiave, vincitore=f"<@{vincitore}>" if vincitore else "", premio=self.premio, moneta=self.moneta, pubblica=True),
                view=None, allowed_mentions=discord.AllowedMentions(users=[discord.Object(vincitore)] if vincitore else []),
            )
        except discord.HTTPException:
            pass


class RiffaCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._aperte: set[int] = set()

    def cog_unload(self) -> None:
        togli_comandi_del_cog(self)

    @comando_di_gruppo("admin-giochi", nome="riffa", descrizione="Una riffa pagata dalla cassa del server: chi clicca può vincere il premio.", sottogruppo=_SG)
    @app_commands.describe(premio="Monete di premio (dalla cassa del server)", minuti="Quanto dura (1-60 minuti)")
    async def riffa(
        self, interaction: discord.Interaction, premio: app_commands.Range[int, 1, 100_000], minuti: app_commands.Range[int, 1, 60] = 5
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        g = interaction.guild.id
        if g in self._aperte:
            await interaction.response.send_message(await testo_per(interaction, "rif_aperta"), ephemeral=True)
            return
        if await guild_chest_repo.get_balance(g) < premio:
            await interaction.response.send_message(await testo_per(interaction, "rif_cassa_poca", premio=premio), ephemeral=True)
            return
        moneta = (await leveling_settings_repo.get_config(g)).impostazioni.currency_name
        view = RiffaView(g, premio, minuti, moneta, interaction.user.id)
        view.messaggio = interaction
        self._aperte.add(g)
        try:
            await interaction.response.send_message(
                await testo_per(interaction, "rif_avvio", premio=premio, moneta=moneta, minuti=minuti, pubblica=True), view=view, allowed_mentions=NESSUNA_MENZIONE
            )
            await view.wait()
        finally:
            self._aperte.discard(g)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RiffaCog(bot))
