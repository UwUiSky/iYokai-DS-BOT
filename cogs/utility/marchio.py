"""
cogs/utility/marchio.py
=======================
`/admin-bot premium marchio` (NF-38, #109): un server premium collega un bot suo, con nome e avatar suoi.
`/admin-bot premium aspetto` (CFG-030, #122): avatar, banner e descrizione dello stesso iYokai, solo in questo server.
Il token si scrive in una finestra (mai come opzione del comando), si prova con Discord e si salva cifrato.
Le azioni passano da `core/whitelabel_bot.py`, le stesse del pannello web (D16).
Funzioni coperte: SPEC §23 (NF-38), catalogo #122 (CFG-030), #128 (CFG-032: risincronizza i comandi e ultimi errori)
Dipende da: core/whitelabel_bot.py, core/bot_aspetto.py, cogs/utility/premium_server.py (stesso sotto-gruppo)
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.utility.premium_server import SOTTOGRUPPO_PREMIUM
from core.bot_aspetto import MAX_BIO, MAX_IMMAGINE, applica_aspetto
from core.bot_ready import attendi_bot_pronto
from core.command_groups import CogConGruppi, comando_di_gruppo
from core import marchio_errori as errori_marchio
from core.config import config
from core.i18n import testo_per
from core.ui_base import BaseModal
from core.repositories.whitelabel_repo import whitelabel_repo
from core.whitelabel_bot import (
    MAX_TESTO_STATO,
    GestoreMarchio,
    TokenRifiutato,
    applica_azione,
    collega_e_avvia,
    ha_premium,
    link_invito,
    puo_usare_strumenti,
)
from core.giro_periodico import giro_periodico

logger = logging.getLogger("iyokai.whitelabel")
INTERVALLO_MINUTI = 30


AZIONI_STRUMENTI = frozenset({"risincronizza", "errori"})


def riga_errore(e: errori_marchio.ErroreMarchio) -> str:
    """Una riga del registro: ora, origine e tipo di errore. Mai testi di errore, token o ID."""
    extra = f" ({e.dettaglio})" if e.dettaglio else ""
    return f"- <t:{int(e.quando.timestamp())}:R> `{e.origine}`: `{e.tipo}`{extra}"


class TokenModal(BaseModal):
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

    @giro_periodico(minutes=INTERVALLO_MINUTI)
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
            marchio = await collega_e_avvia(self.gestore, self.bot, guild, token, interaction.user.id, config=config)
        except TokenRifiutato as exc:
            await interaction.followup.send(await testo_per(interaction, exc.motivo), ephemeral=True)
            return
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
        "admin-bot", nome="marchio", descrizione="Usa un bot con il tuo nome e il tuo avatar (premium).",
        sottogruppo=SOTTOGRUPPO_PREMIUM,
    )
    @app_commands.describe(azione="Cosa fare", testo="Solo per «testo di stato»: la frase da mostrare (vuoto = nessuna)")
    @app_commands.choices(
        azione=[
            app_commands.Choice(name="stato", value="stato"),
            app_commands.Choice(name="risincronizza i comandi", value="risincronizza"),
            app_commands.Choice(name="ultimi errori", value="errori"),
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
        if azione.value == "imposta":
            if not await ha_premium(self.bot, guild.id):
                await interaction.response.send_message(
                    await testo_per(interaction, "mar_richiede_premium"), ephemeral=True
                )
                return
            modal = TokenModal(
                self, await testo_per(interaction, "mar_modal_titolo"), await testo_per(interaction, "mar_modal_token")
            )
            await interaction.response.send_modal(modal)
            return
        if azione.value in AZIONI_STRUMENTI:
            await self._strumenti(interaction, azione.value)
            return
        if azione.value != "stato":
            chiave = await applica_azione(self.gestore, self.bot, guild.id, azione.value, testo)
            await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)
            return
        attuale = await whitelabel_repo.get(guild.id)
        if attuale is None:
            await interaction.response.send_message(await testo_per(interaction, "mar_nessuno"), ephemeral=True)
            return
        embed = discord.Embed(
            title=await testo_per(interaction, "mar_titolo"),
            description=(await self._descrizione(interaction, attuale))[:3900],
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


    async def _strumenti(self, interaction: discord.Interaction, azione: str) -> None:
        """CFG-032: risincronizza i comandi e registro degli errori. Solo chi possiede il bot con marchio."""
        guild = interaction.guild
        marchio = await whitelabel_repo.get(guild.id)
        if marchio is None:
            await interaction.response.send_message(await testo_per(interaction, "mar_nessuno"), ephemeral=True)
            return
        if not puo_usare_strumenti(interaction.user.id, guild.owner_id, marchio):
            await interaction.response.send_message(await testo_per(interaction, "mar_strumenti_non_tuoi"), ephemeral=True)
            return
        if azione == "risincronizza":
            await interaction.response.defer(ephemeral=True)
            chiave, valori = await self.gestore.risincronizza(guild.id)
            await interaction.followup.send(await testo_per(interaction, chiave, **valori), ephemeral=True)
            return
        errori = errori_marchio.elenco(guild.id)
        if not errori:
            await interaction.response.send_message(await testo_per(interaction, "mar_errori_nessuno"), ephemeral=True)
            return
        righe = [riga_errore(e) for e in errori]
        testo = await testo_per(interaction, "mar_errori_titolo", n=len(righe)) + "\n" + "\n".join(righe)
        await interaction.response.send_message(testo[:1900], ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    # ------------------------------------------------------------------
    @comando_di_gruppo(
        "admin-bot", nome="aspetto", descrizione="Avatar, banner e descrizione del bot in questo server (premium).",
        sottogruppo=SOTTOGRUPPO_PREMIUM,
    )
    @app_commands.describe(
        avatar="Immagine PNG, JPEG, GIF o WEBP (massimo 8 MB)",
        banner="Immagine PNG, JPEG, GIF o WEBP (massimo 8 MB)",
        descrizione="La descrizione del profilo del bot in questo server",
        togli="Cosa togliere e riportare come nel resto di Discord",
    )
    @app_commands.choices(
        togli=[
            app_commands.Choice(name="avatar", value="avatar"),
            app_commands.Choice(name="banner", value="banner"),
            app_commands.Choice(name="descrizione", value="bio"),
            app_commands.Choice(name="tutto", value="tutto"),
        ]
    )
    async def aspetto(
        self,
        interaction: discord.Interaction,
        avatar: discord.Attachment | None = None,
        banner: discord.Attachment | None = None,
        descrizione: app_commands.Range[str, 1, MAX_BIO] | None = None,
        togli: app_commands.Choice[str] | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        campi: dict = {}
        if togli is not None:
            nomi = ("avatar", "banner", "bio") if togli.value == "tutto" else (togli.value,)
            campi = dict.fromkeys(nomi)
        if descrizione:
            campi["bio"] = descrizione
        for nome, allegato in (("avatar", avatar), ("banner", banner)):
            if allegato is None:
                continue
            if allegato.size > MAX_IMMAGINE:
                await interaction.followup.send(await testo_per(interaction, "asp_immagine_grande"), ephemeral=True)
                return
            try:
                campi[nome] = await allegato.read()
            except discord.HTTPException:  # allegato scaduto o Discord non risponde
                await interaction.followup.send(await testo_per(interaction, "asp_allegato_errore"), ephemeral=True)
                return
        chiave = await applica_aspetto(self.bot, interaction.guild, interaction.user.id, **campi)
        await interaction.followup.send(await testo_per(interaction, chiave), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MarchioCog(bot))
