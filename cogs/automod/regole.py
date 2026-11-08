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

from cogs.automod.automod import MODULE_AUTOMOD, _VIOLATION_LABELS
from core.ui_base import BaseView
from core.automod_liste_pannello import apri_liste
from core.automod_regole_pannello import apri_pannello
from cogs.moderation._shared import ensure_module_enabled
from core import account_rubato_opzioni, immagini_opzioni, automod_liste_service as liste_service, automod_regole_service as regole_service
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


class ConfermaAzzera(BaseView):
    """Un bottone per confermare l'azzeramento: lo vede e lo usa solo chi ha dato il comando."""

    def __init__(self, autore_id: int, guild_id: int, nome: str, dal: datetime | None, user_id: int | None, etichetta: str):
        super().__init__(timeout=TEMPO_CONFERMA_S)
        self.autore_id, self.guild_id, self.nome, self.dal, self.user_id = autore_id, guild_id, nome, dal, user_id
        self.conferma.label = etichetta[:45]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.autore_id and await super().interaction_check(interaction)

    @discord.ui.button(style=discord.ButtonStyle.danger, label="OK", custom_id="am:azzera:ok")
    async def conferma(self, interaction: discord.Interaction, bottone: discord.ui.Button) -> None:
        await interaction.response.defer()
        toccate = await automod_advanced_repo.azzera_a_lotti(self.guild_id, self.nome, self.dal, self.user_id)
        self.stop()
        await interaction.edit_original_response(
            content=await testo_per(interaction, "amregole_azzerato", righe=toccate, nome=self.nome), view=None)


AZIONI_IMMAGINI = [app_commands.Choice(name=n, value=n) for n in immagini_opzioni.AZIONI]


class RegoleCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @autocomplete_protetto(Livello.ADMIN)
    async def _completa_regola(self, interaction: discord.Interaction, scritto: str) -> list[app_commands.Choice[str]]:
        scelte = [(chiave, etichetta) for chiave, etichetta in _VIOLATION_LABELS.items()]
        scelte += [(r.chiave, r.nome) for r in await regole_service.regole_del_server(interaction.guild.id) if r.tipo == "personale"]
        return [app_commands.Choice(name=n[:100], value=k) for k, n in scelte if scritto.lower() in n.lower()][:25]

    @comando_di_gruppo(
        "admin-automod", nome="regole", descrizione="Apre il pannello delle regole AutoMod: condizioni e azioni."
    )
    @app_commands.describe(regola="Una regola da aprire subito (vuoto: l'elenco)")
    @app_commands.autocomplete(regola=_completa_regola)
    async def regole(self, interaction: discord.Interaction, regola: app_commands.Range[str, 1, 40] | None = None) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        if regola and regola not in _VIOLATION_LABELS and not regola.startswith("p:"):
            await interaction.response.send_message(await testo_per(interaction, "amregole_cmd_nessuna"), ephemeral=True)
            return
        await apri_pannello(interaction, dict(_VIOLATION_LABELS), regola)

    @autocomplete_protetto(Livello.ADMIN)
    async def _completa_lista(self, interaction: discord.Interaction, scritto: str) -> list[app_commands.Choice[str]]:
        nomi = [*liste_service.LISTE_DI_SISTEMA, *await liste_service.liste_del_server(interaction.guild.id)]
        return [app_commands.Choice(name=n[:100], value=n) for n in nomi if scritto.lower() in n.lower()][:25]

    @comando_di_gruppo(
        "admin-automod", nome="liste", descrizione="Apre il pannello delle liste con nome: parole e domini."
    )
    @app_commands.describe(lista="Una lista da aprire subito (vuoto: l'elenco)")
    @app_commands.autocomplete(lista=_completa_lista)
    async def liste(self, interaction: discord.Interaction, lista: app_commands.Range[str, 1, 32] | None = None) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        await apri_liste(interaction, lista)

    @comando_di_gruppo(
        "admin-automod", nome="gruppo", descrizione="Accende o spegne tutte le regole di un gruppo."
    )
    @app_commands.describe(nome="Il nome del gruppo", attivo="Sì: accese, no: spente")
    async def gruppo(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, 32], attivo: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        n = await regole_service.attiva_gruppo(interaction.guild.id, nome, attivo)
        stato = await testo_per(interaction, "amregole_gruppo_acceso" if attivo else "amregole_gruppo_spento")
        await interaction.response.send_message(
            await testo_per(interaction, "amregole_gruppo_fatto", nome=nome, n=n, stato=stato), ephemeral=True)

    @comando_di_gruppo(
        "admin-automod", nome="immagini", descrizione="Impostazioni del filtro per le immagini sospette."
    )
    @app_commands.describe(
        filtro="Accende o spegne il filtro", azione="Cosa fare di un'immagine sospetta",
        timeout_minuti="Minuti di timeout (se l'azione è timeout)", canale_log="Canale dove scrivere i casi",
        account_rubato="Difesa dagli account rubati (acceso di base): limita e avvisa lo staff",
    )
    @app_commands.choices(azione=AZIONI_IMMAGINI)
    async def immagini(
        self,
        interaction: discord.Interaction,
        filtro: bool | None = None,
        azione: app_commands.Choice[str] | None = None,
        timeout_minuti: app_commands.Range[int, 1, 40_320] | None = None,
        canale_log: discord.TextChannel | None = None,
        account_rubato: bool | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        gid = interaction.guild.id
        if any(v is not None for v in (filtro, azione, timeout_minuti, canale_log, account_rubato)):
            try:
                if account_rubato is not None:
                    await account_rubato_opzioni.imposta(gid, interaction.user.id, account_rubato)
                await immagini_opzioni.imposta(
                    gid, interaction.user.id, attivo=filtro, azione=azione.value if azione else None,
                    timeout_minuti=timeout_minuti, canale_log_id=canale_log.id if canale_log else None)
            except ValueError as errore:
                await interaction.response.send_message(await testo_per(interaction, "amregole_img_errore", errore=errore), ephemeral=True)
                return
            await interaction.response.send_message(await testo_per(interaction, "amregole_img_fatto"), ephemeral=True)
            return
        v = await immagini_opzioni.leggi(gid)
        await interaction.response.send_message(await testo_per(
            interaction, "amregole_img_stato",
            stato=await testo_per(interaction, "amregole_img_acceso" if v.attivo else "amregole_img_spento"),
            azione=v.azione, minuti=v.timeout_minuti,
            canale=f"<#{v.canale_log_id}>" if v.canale_log_id else await testo_per(interaction, "amregole_img_nessun_canale"))
            + "\n" + await testo_per(interaction, "arub_stato", stato=await testo_per(
                interaction, "amregole_img_acceso" if await account_rubato_opzioni.attivo(gid) else "amregole_img_spento")),
            ephemeral=True)

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
