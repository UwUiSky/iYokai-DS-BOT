"""
cogs/fun/immagini_comunita.py
=============================
`/immagini post`: un'immagine da una comunità Lemmy dell'elenco chiuso (con il bottone «Segnala») e
`/admin-giochi servizi`: gli interruttori dei servizi esterni del Divertimento (spenti di base).
Funzioni coperte: SPEC §16 (FUN-053, FUN-055, FUN-056, FUN-065; B10 di #131)
Dipende da: core/lemmy_logic.py, core/fun_servizi_logic.py, core/repositories/immagini_segnalazioni_repo.py
"""

from __future__ import annotations

import time

import discord
from discord import app_commands
from discord.ext import commands

from cogs.fun.entertainment import MODULE_FUN
from core import fun_servizi_logic as servizi
from core import lemmy_logic as lemmy
from core.command_access import Livello, richiedi
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.config_impostazioni import imposta_impostazione
from core.database import db
from core.i18n import testo_per
from core.repositories.immagini_segnalazioni_repo import SOGLIA_BLOCCO, immagini_segnalazioni_repo
from core.ui_base import BaseView

PAUSA_SECONDI = 5
MAX_UTENTI_NELLA_PAUSA = 500
SCADENZA_BOTTONE_SECONDI = 3600
NESSUNA_MENZIONE = discord.AllowedMentions.none()


async def _completa(interaction: discord.Interaction, digitato: str) -> list[app_commands.Choice[str]]:
    return [app_commands.Choice(name=n, value=v) for n, v in lemmy.suggerimenti(digitato)]


class SegnalaView(BaseView):
    """Il bottone «Segnala»: chiunque può segnalare, una volta sola per post; con 3 persone il post si nasconde."""

    def __init__(self, post_key: str, etichetta: str) -> None:
        super().__init__(timeout=SCADENZA_BOTTONE_SECONDI)
        self._post_key = post_key
        self.bottone = discord.ui.Button(label=etichetta[:80], style=discord.ButtonStyle.secondary, emoji="🚩")
        self.bottone.callback = self._premuto
        self.add_item(self.bottone)

    async def _premuto(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild.id if interaction.guild else 0
        totale = await immagini_segnalazioni_repo.segnala(self._post_key, interaction.user.id, guild_id)
        if totale >= SOGLIA_BLOCCO:
            embed = discord.Embed(description=await testo_per(interaction, "immagini_post_nascosto", pubblica=True))
            await interaction.response.edit_message(embed=embed, view=None, attachments=[])
            return
        await interaction.response.send_message(await testo_per(interaction, "immagini_post_segnalato"), ephemeral=True)


class ImmaginiComunitaCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot, servizio: lemmy.ServizioLemmy | None = None) -> None:
        self.bot = bot
        self._servizio = servizio
        self._ultima: dict[int, float] = {}

    def _lemmy(self) -> lemmy.ServizioLemmy:
        return self._servizio or lemmy.servizio_lemmy

    def _pausa(self, utente_id: int) -> int:
        ora = time.monotonic()
        resta = PAUSA_SECONDI - (ora - self._ultima.get(utente_id, -1e9))
        if resta > 0:
            return int(resta) + 1
        if len(self._ultima) >= MAX_UTENTI_NELLA_PAUSA:
            self._ultima = {u: t for u, t in self._ultima.items() if ora - t < PAUSA_SECONDI}
        self._ultima[utente_id] = ora
        return 0

    @comando_di_gruppo("immagini", nome="post", descrizione="Un'immagine da una comunità Lemmy (spento di base: lo accende l'admin).")
    @app_commands.describe(comunita="Da quale comunità")
    @app_commands.autocomplete(comunita=_completa)
    async def post(self, interaction: discord.Interaction, comunita: app_commands.Range[str, 1, 100]) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_FUN):
            await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
            return
        if not await servizi.acceso(interaction.guild.id, servizi.SETTING_IMMAGINI_POST):
            await interaction.response.send_message(await testo_per(interaction, "immagini_post_spento"), ephemeral=True)
            return
        com = lemmy.trova(comunita)
        if com is None:
            await interaction.response.send_message(await testo_per(interaction, "immagini_post_comunita_sconosciuta"), ephemeral=True)
            return
        resta = self._pausa(interaction.user.id)
        if resta:
            await interaction.response.send_message(await testo_per(interaction, "immagini_post_aspetta", secondi=resta), ephemeral=True)
            return
        await interaction.response.defer()
        elenco = await self._lemmy().elenco(com)
        bloccati = await immagini_segnalazioni_repo.bloccati([p.chiave for p in elenco]) if elenco else set()
        scelto = await self._lemmy().post(com, bloccati)
        if scelto is None:
            await interaction.delete_original_response()
            await interaction.followup.send(await testo_per(interaction, "immagini_post_nessuno"), ephemeral=True)
            return
        embed = discord.Embed(title=scelto.titolo[:256] or None, url=scelto.pagina, color=discord.Color.blurple())
        embed.set_image(url=scelto.immagine)
        embed.set_footer(text=(await testo_per(interaction, "immagini_post_credito", pubblica=True, autore=scelto.autore or "?", comunita=com.nome))[:2000])
        vista = SegnalaView(scelto.chiave, await testo_per(interaction, "immagini_post_segnala", pubblica=True))
        await interaction.followup.send(embed=embed, view=vista, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("admin-giochi", nome="servizi", descrizione="Accende o spegne i servizi esterni: immagini Lemmy e ricerca di GIF.")
    @app_commands.describe(immagini_post="Il comando /immagini post (spento di base)", gif_cerca="Il comando /gif cerca (spento di base, serve una chiave del bot)")
    @richiedi(Livello.ADMIN)
    async def servizi_esterni(
        self, interaction: discord.Interaction, immagini_post: bool | None = None, gif_cerca: bool | None = None
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        for chiave, valore in ((servizi.SETTING_IMMAGINI_POST, immagini_post), (servizi.SETTING_GIF_CERCA, gif_cerca)):
            if valore is not None:
                await imposta_impostazione(interaction.guild, servizi.SCHEDA_FUN, chiave, "1" if valore else "0", interaction.user.id)
        acceso_post = await servizi.acceso(interaction.guild.id, servizi.SETTING_IMMAGINI_POST)
        acceso_gif = await servizi.acceso(interaction.guild.id, servizi.SETTING_GIF_CERCA)
        si, no = await testo_per(interaction, "fun_servizi_acceso"), await testo_per(interaction, "fun_servizi_spento")
        testo = await testo_per(interaction, "fun_servizi_stato", immagini_post=si if acceso_post else no, gif_cerca=si if acceso_gif else no)
        await interaction.response.send_message(testo, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ImmaginiComunitaCog(bot))
