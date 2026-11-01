"""
cogs/leveling/progressi.py
==========================
/level progressi: missioni del giorno, serie di giorni, traguardi, stagione del mese e
profilo globale (solo numeri positivi). /economia progressi: lo staff li accende o spegne.
Le monete dei premi le accredita core/progressi_service.py in modo atomico.
Funzioni coperte: SPEC §23.17 (NF-41, D49)
Dipende da: core/progressi_service.py, core/progressi_logic.py
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from cogs.leveling.leveling import _comando_rifiutato
from core import progressi_service as servizio
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.leveling_logic import period_key
from core.progressi_logic import (
    MISSIONI,
    SERIE_BONUS_OGNI,
    TRAGUARDO_PER_CHIAVE,
    ProfiloGlobale,
    gradini_raggiunti,
    serie_attuale,
    stato_missione,
    testo_profilo_globale,
    testo_stagione,
    testo_traguardi,
)
from core.ui_base import BaseView

_SCELTE_SEZIONE = [
    app_commands.Choice(name="Missioni di oggi", value="missioni"),
    app_commands.Choice(name="Traguardi", value="traguardi"),
    app_commands.Choice(name="Serie di giorni", value="serie"),
    app_commands.Choice(name="Stagione del mese", value="stagione"),
    app_commands.Choice(name="Il mio profilo globale", value="globale"),
]
SPENTO = (
    "Missioni, serie, traguardi e stagione sono spenti su questo server. "
    "Un amministratore li accende con `/economia progressi`."
)


def _testo_nuovi(nuovi: tuple[str, ...]) -> str:
    if not nuovi:
        return ""
    return "\nNuovi traguardi: " + ", ".join(
        f"{TRAGUARDO_PER_CHIAVE[c].emoji} {TRAGUARDO_PER_CHIAVE[c].testo}" for c in nuovi if c in TRAGUARDO_PER_CHIAVE
    )


class VistaRiscatto(BaseView):
    """Un bottone «Riscuoti» per le missioni o per la stagione. Lo preme solo chi ha aperto la scheda."""

    def __init__(self, autore_id: int, sezione: str) -> None:
        super().__init__(timeout=300)
        self.autore_id = autore_id
        self.sezione = sezione

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        return interaction.user.id == self.autore_id

    @discord.ui.button(label="Riscuoti", style=discord.ButtonStyle.success)
    async def riscuoti(self, interaction: discord.Interaction, _bottone: discord.ui.Button) -> None:
        guild = interaction.guild
        if guild is None or not await servizio.attivo(guild.id):
            await interaction.response.send_message(SPENTO, ephemeral=True)
            return
        if self.sezione == "missioni":
            esito = await servizio.riscatta_missioni(guild.id, interaction.user.id)
        else:
            esito = await servizio.riscatta_stagione(guild.id, interaction.user.id)
        if esito.quanti == 0:
            await interaction.response.send_message("Non c'è niente da riscuotere adesso.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"🎁 Riscossi **{esito.monete}** coin ({esito.quanti} {'missioni' if self.sezione == 'missioni' else 'gradini'})."
            + _testo_nuovi(esito.traguardi_nuovi),
            ephemeral=True,
        )


class ProgressiCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        await super().cog_load()
        servizio.avvia(self.bot)

    async def cog_unload(self) -> None:
        await servizio.ferma()
        await super().cog_unload()

    @comando_di_gruppo(
        "level",
        nome="progressi",
        descrizione="Missioni di oggi, serie di giorni, traguardi, stagione del mese.",
    )
    @app_commands.describe(sezione="Cosa vedere (di base: le missioni di oggi)")
    @app_commands.choices(sezione=_SCELTE_SEZIONE)
    async def progressi(
        self, interaction: discord.Interaction, sezione: app_commands.Choice[str] | None = None
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        guild, utente = interaction.guild, interaction.user
        scelta = sezione.value if sezione is not None else "missioni"
        if scelta == "globale":
            await self._globale(interaction)
            return
        if not await servizio.attivo(guild.id):
            await interaction.response.send_message(SPENTO, ephemeral=True)
            return
        repo = servizio.progressi_repo
        vista = None
        if scelta == "missioni":
            await servizio.svuota(guild.id, utente.id)
            stato = await repo.missioni_di(guild.id, utente.id, servizio._oggi())
            righe = [stato_missione(m, *stato.get(m.chiave, (0, False))) for m in MISSIONI]
            testo = "\n".join(righe) + "\n\nSi azzerano a mezzanotte (UTC)."
            titolo = "Missioni di oggi"
            vista = VistaRiscatto(utente.id, "missioni")
        elif scelta == "traguardi":
            await servizio.valuta_traguardi(guild.id, utente.id)
            testo = testo_traguardi(await repo.traguardi_di(guild.id, utente.id))
            titolo = "Traguardi"
        elif scelta == "serie":
            serie, record, ultimo = await repo.serie_di(guild.id, utente.id)
            oggi = serie_attuale(serie, ultimo, servizio._oggi())
            testo = (
                f"Serie attuale: **{oggi}** giorni di fila con `/level daily`.\nRecord: **{record}**.\n"
                f"Ogni {SERIE_BONUS_OGNI} giorni di fila arriva un bonus di monete."
            )
            titolo = "Serie di giorni"
        else:
            mese = period_key()
            xp = await repo.xp_del_mese(guild.id, utente.id, mese)
            riscattati = await repo.gradini_riscattati(guild.id, utente.id, mese)
            testo = testo_stagione(xp, riscattati, mese)
            titolo = "Stagione del mese"
            if gradini_raggiunti(xp) > riscattati:
                vista = VistaRiscatto(utente.id, "stagione")
        embed = discord.Embed(title=titolo, description=testo[:4000], color=discord.Color.gold())
        if vista is not None:
            await interaction.response.send_message(embed=embed, view=vista, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _globale(self, interaction: discord.Interaction) -> None:
        """Il profilo globale lo vede solo chi lo chiede, e conta solo cose belle (nessun nome di server)."""
        server, massimo, record, traguardi = await servizio.progressi_repo.profilo_globale(interaction.user.id)
        embed = discord.Embed(
            title="Il tuo profilo globale",
            description=testo_profilo_globale(ProfiloGlobale(server, massimo, record, traguardi)),
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @comando_di_gruppo(
        "economia",
        nome="progressi",
        descrizione="Accende o spegne missioni, serie, traguardi e stagione.",
    )
    @app_commands.describe(attivo="Sì per accenderli (i premi sono monete), no per spegnerli")
    async def progressi_staff(self, interaction: discord.Interaction, attivo: bool) -> None:
        if await _comando_rifiutato(interaction):
            return
        await servizio.imposta_attivo(interaction.guild.id, attivo, interaction.user.id)
        await interaction.response.send_message(
            "Missioni, serie, traguardi e stagione sono **accesi**: i premi sono monete e si riscuotono con `/level progressi`."
            if attivo
            else "Missioni, serie, traguardi e stagione sono **spenti**. I dati già raccolti restano.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ProgressiCog(bot))
