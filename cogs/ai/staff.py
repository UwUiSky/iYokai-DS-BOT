"""
cogs/ai/staff.py
================
`/ai staff`: riassunto di un incidente (dagli eventi di sicurezza già salvati), assistente per le regole di AutoMod
(l'AI propone, una persona conferma con il bottone) e ricerca nei log con una domanda (l'AI propone i filtri, la
ricerca la fa il database). Funzionano anche con l'AI ferma. Risposte solo a chi ha lanciato il comando.
Funzioni coperte: SPEC §25.39, §25.40, §25.44 (AI-R-041, AI-R-042, AI-R-047)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from cogs.ai._comune import NESSUNA_MENZIONE, chiedi, registra_modulo_ai, richiesta_da, taglia
from core import ai_staff_logic as staff
from core import automod_assistente_logic as automod
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.repositories.ai_staff_repo import ai_staff_repo
from core.repositories.automod_advanced_repo import automod_advanced_repo
from core.repositories.lockdown_repo import lockdown_repo
from core.repositories.security_repo import security_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.ai_staff")

SOTTO_STAFF = ("staff", "Strumenti dello staff con l'AI")
MODULO_AUTOMOD = "automod"


# ---------------------------------------------------------------- incidente
async def eventi_recenti(guild_id: int, ore: int, adesso: datetime | None = None) -> list[staff.EventoSicurezza]:
    dal = (adesso or datetime.now(timezone.utc)) - timedelta(hours=ore)
    righe = await security_repo.get_recent_actions(guild_id, 200)
    return [
        staff.EventoSicurezza(r["created_at"], r["category"], r["actor_id"], r["detail"] or "")
        for r in righe if r["created_at"] >= dal
    ]


async def riassunto_incidente(interaction, eventi: list[staff.EventoSicurezza], blocco: str | None) -> str:
    """Il riassunto dell'AI; senza AI l'elenco in ordine di tempo."""
    if not eventi:
        return staff.testo_incidente_locale(eventi, blocco)
    testo = "\n".join(staff.righe_incidente(eventi)) + (f"\nBlocco del server: {blocco}" if blocco else "")
    risposta, _ = await chiedi(richiesta_da(
        interaction, "incidente_riassunto", "testo", testo, fascia="media", istruzioni=staff.ISTRUZIONI_INCIDENTE,
        messaggi_utenti=True, riusa=False, max_token=600,
    ))
    return taglia(risposta.testo, 3500) if risposta and risposta.testo.strip() else staff.testo_incidente_locale(eventi, blocco)


# ---------------------------------------------------------------- regola di AutoMod
class RegolaView(BaseView):
    """La proposta aspetta una persona: «Attiva» la applica, «Scarta» la butta."""

    def __init__(self, autore_id: int, proposta: automod.Proposta) -> None:
        super().__init__(timeout=600)
        self.autore_id = autore_id
        self.proposta = proposta

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.autore_id:
            await interaction.response.send_message("Questa proposta è di chi l'ha chiesta.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Attiva", style=discord.ButtonStyle.success)
    async def attiva(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from cogs.moderation._shared import ensure_module_enabled

        if not await ensure_module_enabled(interaction, MODULO_AUTOMOD):
            return
        await applica_proposta(interaction.guild_id, self.proposta)
        self.stop()
        await interaction.response.edit_message(content="Fatto: " + automod.descrizione(self.proposta), view=None)

    @discord.ui.button(label="Scarta", style=discord.ButtonStyle.secondary)
    async def scarta(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content="Proposta scartata. Non è cambiato nulla.", view=None)


async def applica_proposta(guild_id: int, proposta: automod.Proposta) -> None:
    from dataclasses import replace

    impostazioni = await automod_advanced_repo.get_settings(guild_id)
    await automod_advanced_repo.save_settings(replace(impostazioni, config=automod.applica(impostazioni.config, proposta)))


async def proponi_regola(interaction, richiesta: str) -> automod.Proposta | None:
    risposta, _ = await chiedi(richiesta_da(
        interaction, "automod_proponi", "giudizio", f"Richiesta dell'admin: «{richiesta}»", fascia="bassa",
        istruzioni=automod.ISTRUZIONI, messaggi_utenti=True, riusa=False, max_token=120,
    ))
    return (automod.leggi_proposta(risposta.testo) if risposta else None) or automod.proposta_locale(richiesta)


# ---------------------------------------------------------------- log
def trova_persone(guild: discord.Guild, nomi: tuple[str, ...]) -> tuple[list[int], list[str]]:
    """I nomi proposti dall'AI cercati tra i membri del server: (ID trovati, nomi non trovati)."""
    trovati: list[int] = []
    mancanti: list[str] = []
    for nome in nomi:
        m = guild.get_member_named(nome)
        if m is None:
            minuscolo = nome.lower()
            m = next((x for x in guild.members if x.display_name.lower() == minuscolo or x.name.lower() == minuscolo), None)
        (trovati if m else mancanti).append(m.id if m else nome)
    return trovati, mancanti


async def filtri_dalla_domanda(interaction, domanda: str) -> staff.FiltriLog:
    risposta, _ = await chiedi(richiesta_da(
        interaction, "log_filtri", "giudizio", f"Domanda dello staff: «{domanda}»", fascia="bassa",
        istruzioni=staff.ISTRUZIONI_LOG, messaggi_utenti=True, riusa=False, max_token=150,
    ))
    return (staff.leggi_filtri(risposta.testo, domanda) if risposta else None) or staff.filtri_locali(domanda)


class AiStaffCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo("ai", nome="incidente", descrizione="Riassume gli ultimi eventi di sicurezza del server.", sottogruppo=SOTTO_STAFF)
    @app_commands.describe(ore="Quante ore indietro guardare (di base 24)")
    async def incidente(self, interaction: discord.Interaction, ore: app_commands.Range[int, 1, 168] = 24) -> None:
        await interaction.response.defer(ephemeral=True)
        eventi = await eventi_recenti(interaction.guild_id, ore)
        stato = await lockdown_repo.get_stato(interaction.guild_id)
        blocco = f"{stato.tipo} ({stato.stato}), avviato da <@{stato.avviato_da}>" if stato else None
        testo = await riassunto_incidente(interaction, eventi, blocco)
        embed = discord.Embed(title=f"Incidente: ultime {ore} ore", description=taglia(testo, 4000), color=discord.Color.orange())
        embed.set_footer(text="Solo gli eventi già salvati. Controlla prima di agire: decide una persona.")
        await interaction.followup.send(embed=embed, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("ai", nome="regola", descrizione="Scrivi cosa vuoi da AutoMod: ti propongo la regola, la attivi tu.", sottogruppo=SOTTO_STAFF)
    @app_commands.describe(richiesta="Per esempio: niente link dai nuovi, o troppi messaggi in fila")
    async def regola(self, interaction: discord.Interaction, richiesta: app_commands.Range[str, 3, 300]) -> None:
        await interaction.response.defer(ephemeral=True)
        proposta = await proponi_regola(interaction, richiesta)
        if proposta is None:
            await interaction.followup.send(
                "Non ho trovato un filtro adatto. AutoMod ha: link, spam di messaggi, emoji, maiuscole, menzioni di massa, zalgo, phishing.",
                ephemeral=True,
            )
            return
        embed = discord.Embed(title="Regola proposta", description=automod.descrizione(proposta), color=discord.Color.blurple())
        embed.set_footer(text="Scritta dall'AI: non è attiva finché non premi Attiva." if proposta.dall_ai else "Scelta con le tue parole: non è attiva finché non premi Attiva.")
        await interaction.followup.send(embed=embed, view=RegolaView(interaction.user.id, proposta), ephemeral=True)

    @comando_di_gruppo("ai", nome="cerca-log", descrizione="Cerca nei log con una domanda (chi, cosa, quando).", sottogruppo=SOTTO_STAFF)
    @app_commands.describe(domanda="Per esempio: cosa è successo a @Mario negli ultimi tre giorni?")
    async def cerca_log(self, interaction: discord.Interaction, domanda: app_commands.Range[str, 3, 300]) -> None:
        await interaction.response.defer(ephemeral=True)
        filtri = await filtri_dalla_domanda(interaction, domanda)
        trovati, mancanti = trova_persone(interaction.guild, filtri.nomi)
        utenti = tuple(dict.fromkeys([*filtri.utenti, *trovati]))[: staff.MAX_UTENTI]
        eventi = await ai_staff_repo.cerca_eventi(
            interaction.guild_id, list(utenti), filtri.prefissi(), staff.dal(filtri), staff.LIMITE_RIGHE
        )
        righe = [staff.riga_evento(e["created_at"], e["event_type"], e["actor_id"], e["target_user_id"], e["channel_id"]) for e in reversed(eventi)]
        usati = staff.FiltriLog(utenti=utenti, gruppi=filtri.gruppi, ore=filtri.ore)
        testo = "\n".join(righe) if righe else "Nessun evento con questi filtri."
        if mancanti:
            testo += "\nNon ho trovato nel server: " + ", ".join(mancanti) + ". Usa la menzione."
        embed = discord.Embed(title="Risultati dal log", description=taglia(testo, 4000), color=discord.Color.dark_teal())
        embed.set_footer(text=taglia("Filtri: " + usati.descrizione() + ". Il contenuto dei messaggi non si mostra qui.", 200))
        await interaction.followup.send(embed=embed, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)


async def setup(bot: commands.Bot) -> None:
    registra_modulo_ai()
    await bot.add_cog(AiStaffCog(bot))
