"""
cogs/user_app/desktop.py
========================
Il collegamento di iYokai Desktop dall'app (SPEC D.1, D.5): `/desktop collega` crea il token personale (si vede
una volta sola, in privato), `scollega` lo revoca, `avvisi` accende o spegne menzioni e risposte, `parole` sceglie
le parole chiave, `stato` riassume. Si carica solo sul client dell'app (core/user_app_bot.py).
Funzioni coperte: SPEC D.1, D.5 (#108)
Dipende da: core/desktop_logic.py, core/repositories/desktop_repo.py
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.desktop_logic import MAX_PAROLE, ErroreDesktop, impronta, normalizza_parole, nuovo_token
from core.i18n import lingua_interazione, t, testo_per
from core.repositories.desktop_repo import desktop_repo
from core.user_app_bot import e_istanza_app

INSTALLAZIONE = app_commands.AppInstallationType(guild=False, user=True)
OVUNQUE = app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True)


class DesktopCog(commands.Cog):
    desktop = app_commands.Group(
        name="desktop", description="Collega il programma iYokai Desktop e scegli gli avvisi.",
        allowed_installs=INSTALLAZIONE, allowed_contexts=OVUNQUE,
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @desktop.command(name="collega", description="Crea il codice personale per il programma iYokai Desktop.")
    async def collega(self, interaction: discord.Interaction) -> None:
        token = nuovo_token()
        await desktop_repo.imposta_token(interaction.user.id, impronta(token))
        await interaction.response.send_message(
            await testo_per(interaction, "app_desktop_collegato", token=token), ephemeral=True
        )

    @desktop.command(name="scollega", description="Revoca il codice: il programma non entra più.")
    async def scollega(self, interaction: discord.Interaction) -> None:
        chiave = "app_desktop_scollegato" if await desktop_repo.revoca_token(interaction.user.id) else "app_desktop_non_collegato"
        await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)

    @desktop.command(name="avvisi", description="Accendi o spegni gli avvisi per menzioni e risposte sul programma.")
    @app_commands.describe(acceso="Sì: ti avviso; no: non salvo più nulla")
    async def avvisi(self, interaction: discord.Interaction, acceso: bool) -> None:
        await desktop_repo.imposta_menzioni(interaction.user.id, acceso)
        await interaction.response.send_message(
            await testo_per(interaction, "app_desktop_avvisi_accesi" if acceso else "app_desktop_avvisi_spenti"), ephemeral=True
        )

    @desktop.command(name="parole", description="Le parole chiave che ti avvisano (separate da virgole; vuoto le toglie).")
    @app_commands.describe(parole=f"Fino a {MAX_PAROLE} parole, da 2 a 30 lettere")
    async def parole(self, interaction: discord.Interaction, parole: app_commands.Range[str, 0, 400] = "") -> None:
        try:
            elenco = normalizza_parole(parole)
        except ErroreDesktop as errore:
            await interaction.response.send_message(await testo_per(interaction, errore.chiave, massimo=MAX_PAROLE), ephemeral=True)
            return
        await desktop_repo.imposta_parole(interaction.user.id, elenco)
        chiave = "app_desktop_parole_salvate" if elenco else "app_desktop_parole_tolte"
        await interaction.response.send_message(
            await testo_per(interaction, chiave, parole=", ".join(elenco)), ephemeral=True
        )

    @desktop.command(name="stato", description="Come è collegato iYokai Desktop e quali avvisi hai.")
    async def stato(self, interaction: discord.Interaction) -> None:
        pref = await desktop_repo.preferenze(interaction.user.id)
        lingua = await lingua_interazione(interaction)
        righe = [
            t("app_desktop_stato_collegato" if await desktop_repo.collegato(interaction.user.id) else "app_desktop_stato_non_collegato", lingua),
            t("app_desktop_stato_avvisi_si" if pref.menzioni else "app_desktop_stato_avvisi_no", lingua),
            t("app_desktop_stato_parole", lingua, parole=", ".join(pref.parole) or "-"),
        ]
        await interaction.response.send_message("\n".join(righe), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Solo sul client dell'app: il bot principale non riceve questi comandi."""
    if e_istanza_app(bot):
        await bot.add_cog(DesktopCog(bot))
