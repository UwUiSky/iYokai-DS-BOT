"""
cogs/automod/regole.py
======================
Comandi di `/admin-automod` per le regole: riepilogo delle violazioni del server e azzeramento di un contatore.
La logica sta in core/automod_regole_*.py e core/automod_contatori.py; qui si legge l'interazione e si risponde.
Funzioni coperte: SPEC §6 (AMD-063, 064, 066), D63
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from cogs.automod.automod import MODULE_AUTOMOD
from cogs.moderation._shared import ensure_module_enabled
from core import automod_regole_service as regole_service
from core.command_access import Livello, autocomplete_protetto
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import testo_per
from core.repositories.automod_advanced_repo import automod_advanced_repo

RIGHE_PER_PAGINA = 10
TEMPO_CONFERMA_S = 60

VISTE = [
    app_commands.Choice(name="violazioni", value="violazioni"),
    app_commands.Choice(name="ultime", value="ultime"),
]


def _dal(giorni: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=giorni)


async def _nomi_contatori(guild_id: int) -> list[str]:
    nomi = {r.contatore.nome for r in await regole_service.regole_del_server(guild_id) if r.contatore}
    return sorted(nomi)


class ConfermaAzzera(discord.ui.View):
    """Un bottone per confermare l'azzeramento: lo vede e lo usa solo chi ha dato il comando."""

    def __init__(self, autore_id: int, guild_id: int, nome: str, dal: datetime | None, user_id: int | None, etichetta: str):
        super().__init__(timeout=TEMPO_CONFERMA_S)
        self.autore_id, self.guild_id, self.nome, self.dal, self.user_id = autore_id, guild_id, nome, dal, user_id
        self.conferma.label = etichetta[:45]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.autore_id

    @discord.ui.button(style=discord.ButtonStyle.danger, label="OK", custom_id="am:azzera:ok")
    async def conferma(self, interaction: discord.Interaction, bottone: discord.ui.Button) -> None:
        await interaction.response.defer()
        toccate = await automod_advanced_repo.azzera_a_lotti(self.guild_id, self.nome, self.dal, self.user_id)
        self.stop()
        await interaction.edit_original_response(
            content=await testo_per(interaction, "amregole_azzerato", righe=toccate, nome=self.nome), view=None)


class RegoleCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "admin-automod", nome="riepilogo", descrizione="Riepilogo delle violazioni AutoMod del server, a pagine."
    )
    @app_commands.describe(
        vista="Per tipo di violazione, oppure le più recenti",
        giorni="Quanti giorni guardare (solo per tipo)",
        pagina="Numero di pagina (10 righe)",
    )
    @app_commands.choices(vista=VISTE)
    async def riepilogo(
        self,
        interaction: discord.Interaction,
        vista: app_commands.Choice[str],
        giorni: app_commands.Range[int, 1, 365] = 7,
        pagina: app_commands.Range[int, 1, 1000] = 1,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        await interaction.response.defer(ephemeral=True)
        scarto = (pagina - 1) * RIGHE_PER_PAGINA
        if vista.value == "ultime":
            righe, totale = await automod_advanced_repo.recenti_pagina(interaction.guild.id, RIGHE_PER_PAGINA, scarto)
            testi = [
                f"{discord.utils.format_dt(r['created_at'], 'f')} · <@{r['user_id']}> · `{r['violation']}` · "
                f"{', '.join(r['actions_taken']) or '-'}" for r in righe
            ]
        else:
            righe, totale = await automod_advanced_repo.riepilogo_violazioni(
                interaction.guild.id, _dal(giorni), RIGHE_PER_PAGINA, scarto)
            testi = [
                await testo_per(interaction, "amregole_riga_riepilogo", tipo=r["violation"], totale=r["totale"], utenti=r["utenti"])
                for r in righe
            ]
        if not testi:
            await interaction.followup.send(await testo_per(interaction, "amregole_nulla_da_mostrare"), ephemeral=True)
            return
        pagine = -(-totale // RIGHE_PER_PAGINA)
        embed = discord.Embed(
            title=await testo_per(interaction, "amregole_titolo_riepilogo"),
            description="\n".join(testi)[:4000],
            color=discord.Color.orange(),
        )
        embed.set_footer(text=await testo_per(interaction, "amregole_pagina", pagina=pagina, pagine=pagine))
        await interaction.followup.send(embed=embed, ephemeral=True)

    @autocomplete_protetto(Livello.ADMIN)
    async def _completa_contatore(self, interaction: discord.Interaction, scritto: str) -> list[app_commands.Choice[str]]:
        nomi = await _nomi_contatori(interaction.guild.id)
        return [app_commands.Choice(name=n[:100], value=n) for n in nomi if scritto.lower() in n.lower()][:25]

    @comando_di_gruppo(
        "admin-automod", nome="azzera", descrizione="Azzera un contatore delle regole AutoMod."
    )
    @app_commands.describe(
        contatore="Il nome del contatore",
        giorni="Solo le violazioni degli ultimi giorni (vuoto: tutte)",
        utente="Solo le violazioni di questa persona",
    )
    @app_commands.autocomplete(contatore=_completa_contatore)
    async def azzera(
        self,
        interaction: discord.Interaction,
        contatore: app_commands.Range[str, 1, 32],
        giorni: app_commands.Range[int, 1, 365] | None = None,
        utente: discord.User | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        await interaction.response.defer(ephemeral=True)
        dal = _dal(giorni) if giorni else None
        quante = await automod_advanced_repo.conta_da_azzerare(
            interaction.guild.id, contatore, dal, utente.id if utente else None)
        if not quante:
            await interaction.followup.send(await testo_per(interaction, "amregole_nessuna_riga", nome=contatore), ephemeral=True)
            return
        vista = ConfermaAzzera(
            interaction.user.id, interaction.guild.id, contatore, dal, utente.id if utente else None,
            await testo_per(interaction, "amregole_conferma_azzera", righe=quante))
        await interaction.followup.send(
            await testo_per(interaction, "amregole_chiedi_azzera", righe=quante, nome=contatore), view=vista, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RegoleCog(bot))
