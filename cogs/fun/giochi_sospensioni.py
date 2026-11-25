"""
cogs/fun/giochi_sospensioni.py
==============================
`/admin-giochi sospensione`: lo staff del server sospende una persona dai comandi di gioco (`/monete`, `/giochi`,
`/monete-clan`), la riabilita, vede l'elenco e decide sulle richieste di revisione (ECO-160). Il bottone per chiedere la
revisione lo vede la persona sospesa (core/economia_sospensioni_view.py). Non si sospendono bot, se stessi né chi
può gestire il server.
Funzioni coperte: ECO-160
Dipende da: core/economia_sospensioni.py
"""

from __future__ import annotations

from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from core import economia_sospensioni as es
from core.command_access import Livello, richiedi
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.duration_logic import parse_duration
from core.i18n import testo_per

NESSUNA_MENZIONE = discord.AllowedMentions.none()
AZIONI = ("sospendi", "riabilita", "accogli", "respingi", "elenco")


class GiochiSospensioniCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "admin-giochi",
        nome="sospensione",
        descrizione="Sospendi una persona dal gioco, riabilitala o decidi sulla sua richiesta di revisione.",
    )
    @app_commands.describe(
        azione="Che cosa fare",
        utente="La persona (non serve per l'elenco)",
        motivo="Perché (massimo 200 caratteri), per «sospendi»",
        durata="Per quanto tempo: 12h, 7d, 4w (al massimo 365 giorni); vuoto = finché non la togli",
    )
    @app_commands.choices(azione=[app_commands.Choice(name=a, value=a) for a in AZIONI])
    @richiedi(Livello.ADMIN)
    async def sospensione(
        self,
        interaction: discord.Interaction,
        azione: app_commands.Choice[str],
        utente: discord.User | None = None,
        motivo: app_commands.Range[str, 1, es.MAX_MOTIVO] | None = None,
        durata: app_commands.Range[str, 2, 6] | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        if azione.value == "elenco":
            righe = await es.elenco(guild.id)
            if not righe:
                await interaction.response.send_message(await testo_per(interaction, "sospensione_elenco_vuoto"), ephemeral=True)
                return
            testo = "\n".join(
                f"<@{r['user_id']}> · {discord.utils.escape_markdown(r['motivo'])[:80]}"
                + (f" · fino a {discord.utils.format_dt(r['fino_a'], 'd')}" if r["fino_a"] else "")
                + (" · **revisione aperta**" if r["appello_stato"] == "aperto" else "")
                for r in righe
            )
            await interaction.response.send_message(testo[:1900], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)
            return
        if utente is None:
            await interaction.response.send_message(await testo_per(interaction, "sospensione_serve_utente"), ephemeral=True)
            return
        nome = utente.mention
        if azione.value == "sospendi":
            membro = guild.get_member(utente.id)
            if utente.bot or utente.id == interaction.user.id or (
                membro is not None and (membro.guild_permissions.manage_guild or membro.guild_permissions.administrator)
            ):
                await interaction.response.send_message(await testo_per(interaction, "sospensione_non_staff"), ephemeral=True)
                return
            tempo = None
            if durata:
                try:
                    tempo = timedelta(seconds=parse_duration(durata))
                except ValueError as errore:
                    await interaction.response.send_message(str(errore), ephemeral=True)
                    return
            await es.sospendi(guild.id, utente.id, motivo or "-", tempo, interaction.user.id)
            scade = f" fino a {discord.utils.format_dt(discord.utils.utcnow() + min(tempo, es.MAX_DURATA), 'f')}" if tempo else ""
            await interaction.response.send_message(
                await testo_per(interaction, "sospensione_messa", utente=nome, scade=scade), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE
            )
            return
        if azione.value == "riabilita":
            chiave = "sospensione_tolta" if await es.riabilita(guild.id, utente.id) else "sospensione_non_c_e"
            await interaction.response.send_message(
                await testo_per(interaction, chiave, utente=nome), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE
            )
            return
        accogli = azione.value == "accogli"
        if not await es.decidi(guild.id, utente.id, accogli=accogli, da=interaction.user.id):
            await interaction.response.send_message(
                await testo_per(interaction, "sospensione_nessuna_richiesta", utente=nome), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE
            )
            return
        await interaction.response.send_message(
            await testo_per(interaction, "sospensione_decisa_accolta" if accogli else "sospensione_decisa_respinta", utente=nome),
            ephemeral=True, allowed_mentions=NESSUNA_MENZIONE,
        )
        try:  # la persona lo sa: messaggio privato, se può riceverlo
            await utente.send(
                await testo_per(interaction, "sospensione_esito_dm_accolta" if accogli else "sospensione_esito_dm_respinta", server=discord.utils.escape_markdown(guild.name), pubblica=True)
            )
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GiochiSospensioniCog(bot))
