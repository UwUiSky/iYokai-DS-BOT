"""
cogs/utility/marchio.py
=======================
`/admin premium marchio` (NF-38, #109): un server premium collega un bot suo, con nome e avatar suoi.
Il token si scrive in una finestra (mai come opzione del comando), si prova con Discord e si salva cifrato.
Funzioni coperte: SPEC §23 (NF-38)
Dipende da: core/whitelabel_bot.py, cogs/utility/premium_server.py (stesso sotto-gruppo)
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.utility.premium_server import SOTTOGRUPPO_PREMIUM
from core.bot_ready import attendi_bot_pronto
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.config import config
from core.i18n import testo_per
from core.premium import guild_has_premium_access
from core.repositories.whitelabel_repo import whitelabel_repo
from core.whitelabel_bot import (
    MAX_TESTO_STATO,
    MODULO_MARCHIO,
    GestoreMarchio,
    TokenRifiutato,
    collega_marchio,
    link_invito,
)

logger = logging.getLogger("iyokai.whitelabel")
INTERVALLO_MINUTI = 30


class TokenModal(discord.ui.Modal):
    """La finestra dove si incolla il token del bot. Il testo non esce mai da qui."""

    def __init__(self, cog: "MarchioCog", titolo: str, etichetta: str) -> None:
        super().__init__(title=titolo[:45], timeout=300)
        self.cog = cog
        self.token = discord.ui.TextInput(label=etichetta[:45], min_length=20, max_length=120, required=True)
        self.add_item(self.token)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.collega(interaction, self.token.value)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        logger.warning("Finestra del marchio fallita (%s).", type(error).__name__)


class MarchioCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.gestore = GestoreMarchio(bot)

    async def cog_load(self) -> None:
        await super().cog_load()
        self._giro.start()

    async def cog_unload(self) -> None:
        self._giro.cancel()
        await self.gestore.ferma_tutti()
        await super().cog_unload()

    @tasks.loop(minutes=INTERVALLO_MINUTI)
    async def _giro(self) -> None:
        try:
            await self.gestore.riconcilia()
        except Exception:
            logger.warning("Allineamento dei bot con marchio fallito.", exc_info=True)

    @_giro.before_loop
    async def _prima_del_giro(self) -> None:
        await attendi_bot_pronto(self.bot)

    # ------------------------------------------------------------------
    async def collega(self, interaction: discord.Interaction, token: str) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        try:
            marchio = await collega_marchio(guild, token, interaction.user.id, config=config)
        except TokenRifiutato as exc:
            await interaction.followup.send(await testo_per(interaction, exc.motivo), ephemeral=True)
            return
        await self.gestore.ferma(guild.id)  # un token nuovo: il client col token vecchio non deve restare acceso
        await self.gestore.avvia(guild.id)
        invito = link_invito(marchio)
        testo = await testo_per(interaction, "mar_collegato", nome=marchio.bot_name)
        if invito:
            testo += "\n" + await testo_per(interaction, "mar_invita", url=invito)
        testo += "\n" + await testo_per(interaction, "mar_nota_comandi")
        await interaction.followup.send(testo, ephemeral=True)

    async def _descrizione(self, interaction: discord.Interaction, marchio) -> str:
        stato = await testo_per(interaction, f"mar_stato_{marchio.last_state}")
        corpo = await testo_per(
            interaction, "mar_riga_stato",
            nome=marchio.bot_name, stato=stato,
            testo=marchio.status_text or await testo_per(interaction, "pol_nessuno"),
            acceso=await testo_per(interaction, "mar_si" if marchio.enabled else "mar_no"),
        )
        if marchio.last_state == "non_nel_server":
            invito = link_invito(marchio)
            if invito:
                corpo += "\n" + await testo_per(interaction, "mar_invita", url=invito)
        return corpo + "\n" + await testo_per(interaction, "mar_nota_comandi")

    # ------------------------------------------------------------------
    @comando_di_gruppo(
        "admin", nome="marchio", descrizione="Usa un bot con il tuo nome e il tuo avatar (premium).",
        sottogruppo=SOTTOGRUPPO_PREMIUM,
    )
    @app_commands.describe(azione="Cosa fare", testo="Solo per «testo di stato»: la frase da mostrare (vuoto = nessuna)")
    @app_commands.choices(
        azione=[
            app_commands.Choice(name="stato", value="stato"),
            app_commands.Choice(name="collega bot (token)", value="imposta"),
            app_commands.Choice(name="testo di stato", value="testo"),
            app_commands.Choice(name="accendi", value="avvia"),
            app_commands.Choice(name="spegni", value="ferma"),
            app_commands.Choice(name="scollega", value="rimuovi"),
        ]
    )
    async def marchio(
        self,
        interaction: discord.Interaction,
        azione: app_commands.Choice[str],
        testo: app_commands.Range[str, 1, MAX_TESTO_STATO] | None = None,
    ) -> None:
        guild = interaction.guild
        attuale = await whitelabel_repo.get(guild.id)
        if azione.value in ("imposta", "avvia", "testo") and not await guild_has_premium_access(
            guild.id, MODULO_MARCHIO, bot=self.bot
        ):
            await interaction.response.send_message(await testo_per(interaction, "mar_richiede_premium"), ephemeral=True)
            return
        if azione.value == "imposta":
            modal = TokenModal(
                self, await testo_per(interaction, "mar_modal_titolo"), await testo_per(interaction, "mar_modal_token")
            )
            await interaction.response.send_modal(modal)
            return
        if attuale is None:
            chiave = "mar_nessuno" if azione.value == "stato" else "mar_nessun_marchio"
            await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)
            return
        if azione.value == "stato":
            embed = discord.Embed(
                title=await testo_per(interaction, "mar_titolo"),
                description=(await self._descrizione(interaction, attuale))[:3900],
                color=discord.Color.blurple(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        elif azione.value == "testo":
            await whitelabel_repo.imposta_testo_stato(guild.id, testo)
            await self.gestore.aggiorna_testo(guild.id, testo)
            chiave = "mar_testo_ok" if testo else "mar_testo_azzerato"
            await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)
        elif azione.value == "avvia":
            await whitelabel_repo.imposta_abilitato(guild.id, True)
            partito = await self.gestore.avvia(guild.id)
            chiave = "mar_avviato" if partito else "mar_non_avviato"
            await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)
        elif azione.value == "ferma":
            await whitelabel_repo.imposta_abilitato(guild.id, False)
            await self.gestore.ferma(guild.id)
            await interaction.response.send_message(await testo_per(interaction, "mar_fermato"), ephemeral=True)
        else:  # rimuovi
            await self.gestore.ferma(guild.id)
            await whitelabel_repo.elimina(guild.id)
            await interaction.response.send_message(await testo_per(interaction, "mar_rimosso"), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MarchioCog(bot))
