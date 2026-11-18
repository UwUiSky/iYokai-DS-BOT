"""
cogs/leveling/drop.py
=====================
Monete lasciate in un canale (/monete lascia), drop regolabili (/admin-economia drop) e forzieri
fatti comparire dallo staff (/admin-economia forziere). Le monete lasciate stanno nel database:
se nessuno le prende tornano a chi le ha lasciate, anche dopo un riavvio.
Funzioni coperte: ECO-052, ECO-053, ECO-055
Dipende da: core/repositories/lasciti_repo.py
"""

from __future__ import annotations

import asyncio
import logging
import random

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.leveling.leveling import LevelingCog, _comando_rifiutato
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.i18n import testo_per
from core.repositories.lasciti_repo import DURATA_SECONDI, MAX_LASCITO, lasciti_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.leveling.drop")
NESSUNA_MENZIONE = discord.AllowedMentions.none()
MAX_FORZIERI = 5
PAUSA_TRA_FORZIERI = 1.0


class LascitoView(BaseView):
    """Bottone «Prendi»: vince il primo; la scrittura condizionata sta nel database."""

    def __init__(self, lascito_id: int, guild_id: int, moneta: str) -> None:
        super().__init__(timeout=DURATA_SECONDI)
        self.lascito_id = lascito_id
        self.guild_id = guild_id
        self.moneta = moneta
        self._chiuso = False

    @discord.ui.button(label="Prendi", emoji="💰", style=discord.ButtonStyle.success)
    async def prendi(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._chiuso:  # nessun await tra controllo e segno
            await interaction.response.send_message(await testo_per(interaction, "drop_gia_preso"), ephemeral=True)
            return
        importo = await lasciti_repo.prendi(self.lascito_id, self.guild_id, interaction.user.id)
        if importo is None:
            await interaction.response.send_message(await testo_per(interaction, "drop_non_puoi"), ephemeral=True)
            return
        self._chiuso = True
        self.stop()
        button.disabled = True
        button.label = f"{interaction.user.display_name[:40]}"
        await interaction.response.edit_message(
            content=await testo_per(interaction, "drop_preso", importo=importo, moneta=self.moneta, pubblica=True),
            view=self,
            allowed_mentions=NESSUNA_MENZIONE,
        )

    async def on_timeout(self) -> None:
        try:
            await lasciti_repo.rimborsa_scaduti()
        except Exception:
            logger.warning("Rimborso dei lasciti non riuscito", exc_info=True)


class DropCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._rimborsi.start()

    def cog_unload(self) -> None:
        self._rimborsi.cancel()
        togli_comandi_del_cog(self)

    @tasks.loop(minutes=2)
    async def _rimborsi(self) -> None:
        try:
            await lasciti_repo.rimborsa_scaduti()
        except Exception:
            logger.exception("Giro dei rimborsi dei lasciti")

    @_rimborsi.before_loop
    async def _prima(self) -> None:
        await self.bot.wait_until_ready()

    @comando_di_gruppo("monete", nome="lascia", descrizione="Lascia delle monete in questo canale: le prende chi arriva prima.")
    @app_commands.describe(importo="Quante monete lasciare")
    async def lascia(self, interaction: discord.Interaction, importo: app_commands.Range[int, 1, MAX_LASCITO]) -> None:
        if await _comando_rifiutato(interaction):
            return
        guild, canale = interaction.guild, interaction.channel
        if canale is None or not canale.permissions_for(guild.me).send_messages:
            await interaction.response.send_message(await testo_per(interaction, "drop_canale_no"), ephemeral=True)
            return
        lascito = await lasciti_repo.lascia(guild.id, interaction.user.id, importo)
        if lascito is None:
            await interaction.response.send_message(
                await testo_per(interaction, "leveling_non_hai_abbastanza_per_questo", moneta=""), ephemeral=True
            )
            return
        moneta = (await leveling_settings_repo.get_config(guild.id)).impostazioni.currency_name
        view = LascitoView(lascito, guild.id, moneta)
        await interaction.response.send_message(
            await testo_per(interaction, "drop_lasciato", chi=interaction.user.mention, importo=importo, moneta=moneta, pubblica=True),
            view=view,
            allowed_mentions=NESSUNA_MENZIONE,
        )

    @comando_di_gruppo("admin-economia", nome="drop", descrizione="Drop casuali: probabilità, importi, pausa e canale.")
    @app_commands.describe(
        per_mille="Probabilità per messaggio in millesimi (5 = 0,5%; 0 = spenti)",
        minimo="Monete minime", massimo="Monete massime", pausa="Secondi minimi tra due drop",
        canale="Solo in questo canale", ovunque="Sì = in tutti i canali",
    )
    async def drop(
        self,
        interaction: discord.Interaction,
        per_mille: app_commands.Range[int, 0, 100] | None = None,
        minimo: app_commands.Range[int, 1, 100_000] | None = None,
        massimo: app_commands.Range[int, 1, 100_000] | None = None,
        pausa: app_commands.Range[int, 0, 3600] | None = None,
        canale: discord.TextChannel | None = None,
        ovunque: bool | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        campi = {
            "drop_per_mille": per_mille, "drop_min": minimo, "drop_max": massimo, "drop_pausa": pausa,
        }
        campi = {k: v for k, v in campi.items() if v is not None}
        if ovunque:
            campi["drop_canale_id"] = None
        elif canale is not None:
            campi["drop_canale_id"] = canale.id
        if not campi:
            await interaction.response.send_message(await testo_per(interaction, "eco_scegli_un_valore"), ephemeral=True)
            return
        try:
            await leveling_settings_repo.set_options(interaction.guild.id, **campi)
        except ValueError as errore:
            await interaction.response.send_message(f"❌ {errore}", ephemeral=True)
            return
        await interaction.response.send_message(await testo_per(interaction, "eco_salvato"), ephemeral=True)

    @comando_di_gruppo("admin-economia", nome="forziere", descrizione="Fai comparire dei forzieri di monete in un canale.")
    @app_commands.describe(quanti=f"Quanti forzieri (1-{MAX_FORZIERI})", canale="Dove farli comparire")
    async def forziere(
        self,
        interaction: discord.Interaction,
        quanti: app_commands.Range[int, 1, MAX_FORZIERI],
        canale: discord.TextChannel,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        if not canale.permissions_for(interaction.guild.me).send_messages:
            await interaction.response.send_message(await testo_per(interaction, "drop_canale_no"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        i = (await leveling_settings_repo.get_config(interaction.guild.id)).impostazioni
        fatti = 0
        for _ in range(quanti):
            importo = random.SystemRandom().randint(i.drop_min, max(i.drop_min, i.drop_max))
            try:
                await canale.send(
                    f"🎁 Un forziere da **{importo}** {i.currency_name}! Clicca per aprirlo.",
                    view=LevelingCog.DropClaimView(interaction.guild.id, importo),
                    allowed_mentions=NESSUNA_MENZIONE,
                )
            except discord.HTTPException:
                break
            fatti += 1
            await asyncio.sleep(PAUSA_TRA_FORZIERI)
        logger.info("Forzieri: server %s, staff %s, %s nel canale %s.", interaction.guild.id, interaction.user.id, fatti, canale.id)
        await interaction.followup.send(await testo_per(interaction, "drop_forzieri", n=fatti), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DropCog(bot))
