"""
cogs/ai/misteri.py
==================
Misteri: l'admin nasconde un codice e un indizio. Quando qualcuno trova il codice, tutto il server riceve
un premio: XP ai membri attivi, oppure un canale segreto aperto per qualche ora.
Funzioni coperte: SPEC §25.56 (AI-R-061)

I comandi dell'admin stanno in `/ai mistero`, quello per rispondere in `/utility ai mistero` (D43):
`/fun` ha già 25 figli. L'XP «per 24 ore» diventa un'unica ricompensa di XP (D18: non si tocca il calcolo dei livelli).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from cogs.ai._comune import NESSUNA_MENZIONE, SOTTO_AI, registra_modulo_ai, taglia
from core import misteri_logic as logica
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.repositories.activity_stats_repo import activity_stats_repo
from core.repositories.ai_gioco_repo import Mistero, ai_gioco_repo
from core.repositories.leveling_repo import leveling_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.scheduler import scheduler
from core.ui_base import BaseModal

logger = logging.getLogger("iyokai.ai_misteri")

SOTTO_MISTERO = ("mistero", "Misteri nascosti: codice, indizio e premio per il server")
AZIONE_CANALE = "ai_mistero_canale"
TENTATIVI = logica.LimiteTentativi()


async def premia_server(guild: discord.Guild, m: Mistero) -> str:
    """Il premio per tutti: XP ai membri attivi negli ultimi 7 giorni, o il canale segreto aperto a tutti per `durata_ore`."""
    if m.premio == "xp":
        oggi = datetime.now(timezone.utc).date()
        attivi = sorted(await activity_stats_repo.members_over(guild.id, oggi - timedelta(days=7), "messages", 1))
        tetto = (await leveling_settings_repo.get_config(guild.id)).impostazioni.max_level
        dati = 0
        for user_id in attivi[: logica.MAX_MEMBRI_PREMIATI]:
            try:
                await leveling_repo.modifica_xp(guild.id, user_id, "aggiungi", min(m.premio_valore, logica.MAX_XP_PREMIO), tetto)
                dati += 1
            except Exception:
                logger.warning("XP del mistero non dati a %s.", user_id, exc_info=True)
        return f"{min(m.premio_valore, logica.MAX_XP_PREMIO)} XP a {dati} membri attivi."
    canale = guild.get_channel(m.premio_valore)
    if canale is None:
        return "Il canale segreto non esiste più: nessun premio da aprire."
    precedente = canale.overwrites_for(guild.default_role).view_channel
    try:
        await canale.set_permissions(guild.default_role, view_channel=True, reason="Premio del mistero")
    except discord.HTTPException:
        return "Non ho il permesso di aprire il canale segreto."
    await scheduler.schedule(
        guild.id, 0, AZIONE_CANALE, datetime.now(timezone.utc) + timedelta(hours=m.durata_ore),
        {"channel_id": canale.id, "prima": precedente},
    )
    return f"Il canale {canale.mention} è aperto a tutti per {m.durata_ore} ore."


class _MisteroModal(BaseModal, title="Nuovo mistero"):
    titolo = discord.ui.TextInput(label="Titolo", max_length=80)
    indizio = discord.ui.TextInput(label="Indizio per i giocatori", style=discord.TextStyle.paragraph, max_length=800)
    codice = discord.ui.TextInput(label="Codice da trovare (segreto)", min_length=3, max_length=60)

    def __init__(self, premio: str, valore: int, ore: int) -> None:
        super().__init__()
        self.premio, self.valore, self.ore = premio, valore, ore

    async def on_submit(self, interaction: discord.Interaction) -> None:
        impronta = logica.impronta_codice(interaction.guild_id, self.codice.value)
        if impronta is None:
            await interaction.response.send_message("Il codice deve avere almeno 3 lettere o cifre.", ephemeral=True)
            return
        if len(await ai_gioco_repo.misteri(interaction.guild_id, solo_aperti=True)) >= 10:
            await interaction.response.send_message("Ci sono già 10 misteri aperti.", ephemeral=True)
            return
        mistero_id = await ai_gioco_repo.mistero_crea(
            interaction.guild_id, self.titolo.value.strip(), self.indizio.value.strip(), impronta, self.premio, self.valore, self.ore,
            interaction.user.id,
        )
        await interaction.response.send_message(
            f"Mistero n. {mistero_id} creato. Il codice non si può rileggere: l'indizio lo pubblichi tu dove vuoi.", ephemeral=True
        )


class AiMisteriCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def chiudi_canale(self, guild_id: int, user_id: int, payload: dict) -> None:
        guild = self.bot.get_guild(guild_id)
        canale = guild.get_channel(int(payload.get("channel_id", 0))) if guild else None
        if canale is not None:
            await canale.set_permissions(guild.default_role, view_channel=payload.get("prima"), reason="Fine del premio del mistero")

    @comando_di_gruppo("ai", nome="crea", descrizione="Nasconde un mistero con un codice e un premio per il server.", sottogruppo=SOTTO_MISTERO)
    @app_commands.describe(
        premio="Il premio: XP ai membri attivi o un canale segreto aperto a tutti", xp="Quanti XP (premio XP, al massimo 500)",
        canale="Il canale segreto (premio canale)", ore="Quante ore resta aperto il canale",
    )
    @app_commands.choices(premio=[app_commands.Choice(name="XP ai membri attivi", value="xp"), app_commands.Choice(name="Canale segreto", value="canale")])
    async def mistero_crea(
        self, interaction: discord.Interaction, premio: app_commands.Choice[str], xp: app_commands.Range[int, 1, 500] = 100,
        canale: discord.TextChannel | None = None, ore: app_commands.Range[int, 1, 168] = 24,
    ) -> None:
        if premio.value == "canale" and canale is None:
            await interaction.response.send_message("Per il canale segreto scegli quale canale aprire.", ephemeral=True)
            return
        await interaction.response.send_modal(_MisteroModal(premio.value, canale.id if premio.value == "canale" else xp, ore))

    @comando_di_gruppo("ai", nome="elenco", descrizione="I misteri del server (il codice resta segreto).", sottogruppo=SOTTO_MISTERO)
    async def mistero_elenco(self, interaction: discord.Interaction) -> None:
        misteri = await ai_gioco_repo.misteri(interaction.guild_id)
        if not misteri:
            await interaction.response.send_message("Nessun mistero.", ephemeral=True)
            return
        righe = [
            f"{m.id}. {m.titolo} — {'aperto' if m.stato == 'aperto' else 'risolto da <@%d>' % (m.risolto_da or 0)} — premio: "
            + (f"{m.premio_valore} XP" if m.premio == "xp" else f"canale <#{m.premio_valore}> per {m.durata_ore} ore")
            for m in misteri
        ]
        await interaction.response.send_message(taglia("\n".join(righe), 1900), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("ai", nome="togli", descrizione="Toglie un mistero.", sottogruppo=SOTTO_MISTERO)
    @app_commands.describe(numero="Il numero nell'elenco")
    async def mistero_togli(self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 2_000_000_000]) -> None:
        tolto = await ai_gioco_repo.mistero_togli(interaction.guild_id, numero)
        await interaction.response.send_message("Mistero tolto." if tolto else "Non trovo quel mistero.", ephemeral=True)

    @comando_di_gruppo("utility", nome="mistero", descrizione="Rispondi a un mistero del server con il codice.", sottogruppo=SOTTO_AI)
    @app_commands.describe(codice="Il codice che hai trovato")
    async def rispondi(self, interaction: discord.Interaction, codice: app_commands.Range[str, 3, 60]) -> None:
        motivo = TENTATIVI.consenti(interaction.guild_id, interaction.user.id)
        if motivo:
            await interaction.response.send_message(
                "Piano: un tentativo ogni pochi secondi." if motivo == "attesa" else "Troppi tentativi: riprova tra un po'.", ephemeral=True
            )
            return
        impronta = logica.impronta_codice(interaction.guild_id, codice)
        trovato = await ai_gioco_repo.mistero_risolvi(interaction.guild_id, impronta, interaction.user.id) if impronta else None
        if trovato is None:
            await interaction.response.send_message("Non è il codice giusto.", ephemeral=True)
            return
        await interaction.response.defer()
        premio = await premia_server(interaction.guild, trovato)
        await interaction.followup.send(
            f"{interaction.user.mention} ha risolto il mistero «{trovato.titolo}»! Premio per tutti: {premio}", allowed_mentions=NESSUNA_MENZIONE
        )


async def setup(bot: commands.Bot) -> None:
    registra_modulo_ai()
    cog = AiMisteriCog(bot)
    await bot.add_cog(cog)
    scheduler.register_handler(AZIONE_CANALE, cog.chiudi_canale)
