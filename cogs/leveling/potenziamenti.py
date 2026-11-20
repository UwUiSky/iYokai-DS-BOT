"""
cogs/leveling/potenziamenti.py
==============================
Potenziamenti a livelli (/monete conto potenzia), scrigno a sorpresa (/monete rischio scrigno) e la
tabella di cosa si guadagna (/monete conto guadagni). Le monete di gioco non si comprano con soldi veri.
Funzioni coperte: ECO-077, ECO-079, ECO-081
Dipende da: core/repositories/potenziamenti_repo.py
"""

from __future__ import annotations

import random

import discord
from discord import app_commands
from discord.ext import commands

from cogs.leveling.leveling import _comando_rifiutato
from cogs.leveling.rischio import _SG_CONTO, _SG_RISCHIO
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.i18n import testo_per
from core.leveling_logic import BONUS_PER_LIVELLO, LIVELLI_POTENZIAMENTO, costo_potenziamento, tasso_del_giorno
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.potenziamenti_repo import potenziamenti_repo
from core.rischio_logic import LUOGHI, PREZZO_SCRIGNO, premio_scrigno
from datetime import datetime, timezone

RNG = random.SystemRandom()
_SCELTE = [app_commands.Choice(name="Lavoro", value="lavoro"), app_commands.Choice(name="Premio periodico", value="premio")]


class PotenziamentiCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def cog_unload(self) -> None:
        togli_comandi_del_cog(self)

    @comando_di_gruppo("monete", nome="potenzia", descrizione="Potenzia il lavoro o il premio periodico: più livelli, più monete.", sottogruppo=_SG_CONTO)
    @app_commands.describe(tipo="Cosa potenziare (senza scelta vedi i livelli)")
    @app_commands.choices(tipo=_SCELTE)
    async def potenzia(self, interaction: discord.Interaction, tipo: app_commands.Choice[str] | None = None) -> None:
        if await _comando_rifiutato(interaction):
            return
        g, u = interaction.guild.id, interaction.user.id
        moneta = (await leveling_settings_repo.get_config(g)).impostazioni.currency_name
        if tipo is not None:
            esito, valore = await potenziamenti_repo.compra(g, u, tipo.value)
            if esito != "ok":
                chiave = "pot_massimo" if esito == "massimo" else "pot_poche"
                await interaction.response.send_message(await testo_per(interaction, chiave, costo=valore, moneta=moneta), ephemeral=True)
                return
        livelli = await potenziamenti_repo.livelli(g, u)
        righe = [
            await testo_per(
                interaction, "pot_riga", tipo=t, livello=livelli[t], massimo=LIVELLI_POTENZIAMENTO,
                bonus=BONUS_PER_LIVELLO * livelli[t], costo=costo_potenziamento(livelli[t]) or "-", moneta=moneta,
            )
            for t in livelli
        ]
        await interaction.response.send_message("\n".join(righe), ephemeral=True)

    @comando_di_gruppo("monete", nome="scrigno", descrizione=f"Apri uno scrigno a sorpresa per {PREZZO_SCRIGNO} monete.", sottogruppo=_SG_RISCHIO)
    async def scrigno(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        premio = premio_scrigno(RNG)
        saldo = await potenziamenti_repo.scrigno(interaction.guild.id, interaction.user.id, PREZZO_SCRIGNO, premio)
        if saldo is None:
            await interaction.response.send_message(await testo_per(interaction, "pot_scrigno_no", prezzo=PREZZO_SCRIGNO), ephemeral=True)
            return
        moneta = (await leveling_settings_repo.get_config(interaction.guild.id)).impostazioni.currency_name
        chiave = "pot_scrigno_ok" if premio else "pot_scrigno_vuoto"
        await interaction.response.send_message(await testo_per(interaction, chiave, premio=premio, moneta=moneta, saldo=saldo, pubblica=True))

    @comando_di_gruppo("monete", nome="guadagni", descrizione="Come si guadagnano monete in questo server.", sottogruppo=_SG_CONTO)
    async def guadagni(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        i = (await leveling_settings_repo.get_config(interaction.guild.id)).impostazioni
        tasso = tasso_del_giorno(interaction.guild.id, datetime.now(timezone.utc).date())
        righe = [
            f"`/monete daily` {i.daily_coins} ogni {i.daily_ore} h" + (f" (+{i.daily_bonus_serie} per giorno di fila)" if i.daily_bonus_serie else ""),
            f"`/monete work` {i.work_min}-{i.work_max} ogni {i.work_attesa_min} min",
        ]
        if i.settimanale_coins:
            righe.append(f"`/monete settimanale` {i.settimanale_coins}")
        if i.mensile_coins:
            righe.append(f"`/monete mensile` {i.mensile_coins}")
        righe.append("`/monete rischio cerca`: " + ", ".join(f"{n} {v[1]}-{v[2]} ({v[0]}%)" for n, v in LUOGHI.items()))
        righe.append("`/monete rischio elemosina`: 1-10 · `colpo`, `avventura`: premio da un multiplo della paga del lavoro")
        if i.msg_coins:
            righe.append(f"Messaggi nei canali scelti: {i.msg_coins} ogni {i.msg_coins_pausa}s (massimo {i.msg_coins_tetto} al giorno)")
        righe.append(f"Rivendita di oggi: {tasso}% del prezzo")
        await interaction.response.send_message("\n".join(righe)[:3900], ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PotenziamentiCog(bot))
