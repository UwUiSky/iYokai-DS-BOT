"""
cogs/leveling/mini_guadagni.py
==============================
Piccoli guadagni con pausa: /monete rischio scava, meme, coccole, gratta (biglietto a pagamento) e bersaglio
(clicca in tempo). Ogni pagamento passa da core/repositories/rischio_repo.py o potenziamenti_repo.py:
pausa e monete nella stessa transazione.
Funzioni coperte: ECO-042, ECO-043, ECO-044, ECO-046, ECO-047
Dipende da: core/rischio_logic.py
"""

from __future__ import annotations

import asyncio
import random

import discord
from discord import app_commands
from discord.ext import commands

from cogs.leveling.leveling import _comando_rifiutato, _format_seconds
from cogs.leveling.rischio import _SG_RISCHIO
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.i18n import testo_guild, testo_per

from core.anti_automazione import serve_controllo
from core.i18n import testo_per
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.potenziamenti_repo import potenziamenti_repo
from core.repositories.rischio_repo import rischio_repo
from core.rischio_logic import (
    MEME, PAUSA_BERSAGLIO, PAUSA_COCCOLE, PAUSA_MEME, PAUSA_SCAVA, PREZZO_GRATTA, TEMPO_BERSAGLIO,
    coccole, premio_bersaglio, premio_gratta, pubblica_meme, scava,
)
from core.ui_base import BaseView

RNG = random.SystemRandom()
_SCELTE_MEME = [app_commands.Choice(name=n.capitalize(), value=n) for n in MEME]
PAUSA_GRATTA = 60


class _SoloIlGiocatore(BaseView):
    def __init__(self, user_id: int, timeout: float) -> None:
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.usata = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(await testo_per(interaction, "bj_non_tua"), ephemeral=True)
            return False
        return True


class GrattaView(_SoloIlGiocatore):
    def __init__(self, user_id: int, guild_id: int, moneta: str) -> None:
        super().__init__(user_id, 60)
        self.guild_id, self.moneta = guild_id, moneta
        for n in range(5):
            b = discord.ui.Button(label="?", style=discord.ButtonStyle.secondary, row=0)
            b.callback = self._gratta
            self.add_item(b)

    async def _gratta(self, interaction: discord.Interaction) -> None:
        if self.usata:  # nessun await tra controllo e segno: un solo biglietto per comando
            await interaction.response.send_message(await testo_per(interaction, "leveling_gia_fatto"), ephemeral=True)
            return
        self.usata = True
        self.stop()
        premio = premio_gratta(RNG)
        saldo = await potenziamenti_repo.scrigno(self.guild_id, self.user_id, PREZZO_GRATTA, premio, "gratta", PAUSA_GRATTA)
        for b in self.children:
            b.disabled = True
        if saldo is None:
            testo = await testo_per(interaction, "mg_gratta_no", prezzo=PREZZO_GRATTA, moneta=self.moneta)
        else:
            chiave = "mg_gratta_ok" if premio else "mg_gratta_vuoto"
            testo = await testo_per(interaction, chiave, premio=premio, moneta=self.moneta, saldo=saldo, pubblica=True)
        await interaction.response.edit_message(content=testo, view=self)


class BersaglioView(_SoloIlGiocatore):
    def __init__(self, user_id: int, guild_id: int, moneta: str) -> None:
        super().__init__(user_id, TEMPO_BERSAGLIO + 1)
        self.guild_id, self.moneta = guild_id, moneta
        b = discord.ui.Button(label="🎯", style=discord.ButtonStyle.danger)
        b.callback = self._colpito
        self.add_item(b)

    async def _colpito(self, interaction: discord.Interaction) -> None:
        if self.usata:
            await interaction.response.send_message(await testo_per(interaction, "leveling_gia_fatto"), ephemeral=True)
            return
        self.usata = True
        self.stop()
        saldo = await rischio_repo.guadagna(self.guild_id, self.user_id, "bersaglio", PAUSA_BERSAGLIO, premio_bersaglio(RNG))
        if saldo is None:
            testo = await testo_per(interaction, "rsk_pausa", tempo=_format_seconds(PAUSA_BERSAGLIO))
        else:
            testo = await testo_per(interaction, "mg_bersaglio_ok", saldo=saldo, moneta=self.moneta, pubblica=True)
        await interaction.response.edit_message(content=testo, view=None)


class MiniGuadagniCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def cog_unload(self) -> None:
        togli_comandi_del_cog(self)

    async def _semplice(self, interaction: discord.Interaction, chiave: str, pausa_s: int, dato: int, ok: str, no: str) -> None:
        if await _comando_rifiutato(interaction):
            return
        if await serve_controllo(interaction, (await leveling_settings_repo.get_config(interaction.guild.id)).impostazioni.controllo_per_mille):  # ECO-158
            return
        saldo = await rischio_repo.guadagna(interaction.guild.id, interaction.user.id, chiave, pausa_s, dato)
        if saldo is None:
            resto = await rischio_repo.pausa_rimasta(interaction.guild.id, interaction.user.id, chiave, pausa_s)
            await interaction.response.send_message(await testo_per(interaction, "rsk_pausa", tempo=_format_seconds(max(1, resto))), ephemeral=True)
            return
        moneta = (await leveling_settings_repo.get_config(interaction.guild.id)).impostazioni.currency_name
        await interaction.response.send_message(await testo_per(interaction, ok if dato else no, importo=dato, moneta=moneta, pubblica=True))

    @comando_di_gruppo("monete", nome="scava", descrizione="Scava in cerca di monete (a volte un tesoro).", sottogruppo=_SG_RISCHIO)
    async def scava(self, interaction: discord.Interaction) -> None:
        await self._semplice(interaction, "scava", PAUSA_SCAVA, scava(RNG), "mg_scava_ok", "mg_scava_no")

    @comando_di_gruppo("monete", nome="meme", descrizione="Pubblica un meme: il tipo che scegli cambia rischio e premio.", sottogruppo=_SG_RISCHIO)
    @app_commands.describe(tipo="Che meme pubblichi")
    @app_commands.choices(tipo=_SCELTE_MEME)
    async def meme(self, interaction: discord.Interaction, tipo: app_commands.Choice[str]) -> None:
        await self._semplice(interaction, "meme", PAUSA_MEME, pubblica_meme(RNG, tipo.value), "mg_meme_ok", "mg_meme_no")

    @comando_di_gruppo("monete", nome="coccole", descrizione="Coccola il bot: ti lascia qualche moneta.", sottogruppo=_SG_RISCHIO)
    async def coccole(self, interaction: discord.Interaction) -> None:
        await self._semplice(interaction, "coccole", PAUSA_COCCOLE, coccole(RNG), "mg_coccole_ok", "mg_coccole_ok")

    @comando_di_gruppo("monete", nome="gratta", descrizione=f"Gratta e vinci: un biglietto da {PREZZO_GRATTA} monete, scegli una casella.", sottogruppo=_SG_RISCHIO)
    async def gratta(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        moneta = (await leveling_settings_repo.get_config(interaction.guild.id)).impostazioni.currency_name
        view = GrattaView(interaction.user.id, interaction.guild.id, moneta)
        await interaction.response.send_message(await testo_guild(interaction.guild, "mg_gratta", prezzo=PREZZO_GRATTA, moneta=moneta), view=view)

    @comando_di_gruppo("monete", nome="bersaglio", descrizione="Un bersaglio compare dopo qualche secondo: clicca in tempo.", sottogruppo=_SG_RISCHIO)
    async def bersaglio(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        g, u = interaction.guild.id, interaction.user.id
        resto = await rischio_repo.pausa_rimasta(g, u, "bersaglio", PAUSA_BERSAGLIO)
        if resto > 0:
            await interaction.response.send_message(await testo_per(interaction, "rsk_pausa", tempo=_format_seconds(resto)), ephemeral=True)
            return
        moneta = (await leveling_settings_repo.get_config(g)).impostazioni.currency_name
        await interaction.response.send_message(await testo_guild(interaction.guild, "mg_bersaglio_attesa"))
        await asyncio.sleep(RNG.uniform(2, 5))
        view = BersaglioView(u, g, moneta)
        try:
            await interaction.edit_original_response(content=await testo_per(interaction, "mg_bersaglio_ora"), view=view)
        except discord.HTTPException:
            return
        await view.wait()
        if not view.usata:
            try:
                await interaction.edit_original_response(content=await testo_per(interaction, "mg_bersaglio_perso"), view=None)
            except discord.HTTPException:
                pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MiniGuadagniCog(bot))
