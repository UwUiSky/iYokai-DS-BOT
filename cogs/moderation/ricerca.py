"""
cogs/moderation/ricerca.py
==========================
Ricerche dello staff: `/mod-ban cerca` (ban per nome, ID o motivo), `/mod-casi membri` (membri per filtri, con
CSV) e `/mod-casi invito` (cosa c'è dietro un codice invito), più il completamento di `/mod-ban unban`.
Funzioni coperte: SPEC §5.3 (MOD-107, MOD-108, MOD-110)
Dipende da: core/moderation_ricerca_logic.py
"""

from __future__ import annotations

import asyncio
import io
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from cogs.moderation._shared import MODULE_ACTIONS, MODULE_CASE_SYSTEM, ensure_module_enabled, truncate_text
from core import moderation_ricerca_logic as logica
from core.command_access import Livello, autocomplete_protetto
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.duration_logic import parse_duration
from core.i18n import testo_per

SECONDI_COMPLETAMENTO = 2.0
_NESSUNA_MENZIONE = discord.AllowedMentions.none()


async def completa_ban(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Fino a 25 ban per `/mod-ban unban`. Dalla cache; se è fredda, una pagina sola e in fretta."""
    guild = interaction.guild
    if guild is None:
        return []
    voci = logica.ban_in_cache(guild.id)
    if voci is None:
        try:
            voci = await asyncio.wait_for(_prima_pagina(guild), SECONDI_COMPLETAMENTO)
        except (asyncio.TimeoutError, discord.HTTPException):
            return []
    return [
        app_commands.Choice(name=truncate_text(f"{v.nome} ({v.user_id})", 100), value=str(v.user_id))
        for v in logica.suggerimenti_unban(voci, current)
    ]


async def _prima_pagina(guild: discord.Guild) -> list[logica.VoceBan]:
    return [logica.VoceBan(b.user.id, b.user.name, b.reason) async for b in guild.bans(limit=200)]


completa_ban = autocomplete_protetto(Livello.MODBAN)(completa_ban)


class RicercaModerazioneCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        await super().cog_load()

    async def cog_unload(self) -> None:
        await super().cog_unload()

    # ---------------------------------------------------------------- MOD-107
    @comando_di_gruppo("mod-ban", nome="cerca", descrizione="Cerca tra i ban del server per nome, ID o motivo.")
    @app_commands.describe(testo="Parte del nome, l'ID o una parola del motivo", aggiorna="Rilegge i ban da Discord (di base si usa l'elenco di 5 minuti fa)")
    async def cerca(self, interaction: discord.Interaction, testo: app_commands.Range[str, 1, 100], aggiorna: bool = False) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            voci, troncato = await logica.leggi_ban(interaction.guild.id, interaction.guild.bans(limit=None), forza=aggiorna)
        except discord.HTTPException:
            await interaction.followup.send(await testo_per(interaction, "ricercamod_ban_errore"), ephemeral=True)
            return
        trovate, totale = logica.cerca_ban(voci, testo)
        if not trovate:
            await interaction.followup.send(await testo_per(interaction, "ricercamod_ban_nessuno", testo=truncate_text(testo, 100)), ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE)
            return
        righe = [f"`{v.user_id}` {truncate_text(v.nome, 40)} - {truncate_text(v.motivo or '-', 120)}" for v in trovate]
        corpo = "\n".join(righe)
        if totale > len(trovate):
            corpo += "\n" + await testo_per(interaction, "ricercamod_altri", n=totale - len(trovate))
        if troncato:
            corpo += "\n" + await testo_per(interaction, "ricercamod_ban_troncati", n=logica.MAX_BAN_LETTI)
        embed = discord.Embed(title=await testo_per(interaction, "ricercamod_ban_titolo", n=totale), description=truncate_text(corpo, 4000), color=discord.Color.dark_red())
        await interaction.followup.send(embed=embed, ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE)

    # ---------------------------------------------------------------- MOD-108
    @comando_di_gruppo("mod-casi", nome="membri", descrizione="Cerca tra i membri del server con dei filtri.")
    @app_commands.describe(
        nome="Parte del nome, oppure re:espressione per un'espressione regolare",
        ruolo="Solo chi ha questo ruolo",
        in_vocale="Solo chi è (o non è) in un canale vocale",
        bot="Solo bot (sì) o solo persone (no)",
        entrato_dopo="Entrati dopo questa data (AAAA-MM-GG)",
        account_piu_giovane_di="Account creati da meno di questo tempo, es. 7d, 12h",
        esporta="Manda anche un file CSV con tutti i risultati",
    )
    async def membri(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, 105] | None = None,
        ruolo: discord.Role | None = None,
        in_vocale: bool | None = None,
        bot: bool | None = None,
        entrato_dopo: app_commands.Range[str, 8, 10] | None = None,
        account_piu_giovane_di: app_commands.Range[str, 2, 12] | None = None,
        esporta: bool = False,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        dopo = giovane = None
        try:
            if entrato_dopo:
                dopo = datetime.strptime(entrato_dopo, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if account_piu_giovane_di:
                giovane = timedelta(seconds=parse_duration(account_piu_giovane_di))
        except ValueError:
            await interaction.response.send_message(await testo_per(interaction, "ricercamod_filtro_errato"), ephemeral=True)
            return
        if nome:
            try:
                logica.compila_nome(nome)  # prima di rimandare: un'espressione sbagliata si dice subito
            except ValueError as exc:
                await interaction.response.send_message(str(exc), ephemeral=True)
                return
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        trovati = logica.filtra_membri(
            list(guild.members), nome=nome, ruolo_id=ruolo.id if ruolo else None, in_vocale=in_vocale, bot=bot,
            entrato_dopo=dopo, account_piu_giovane_di=giovane,
        )
        incompleta = guild.member_count is not None and len(guild.members) < guild.member_count
        if not trovati:
            await interaction.followup.send(await testo_per(interaction, "ricercamod_membri_nessuno"), ephemeral=True)
            return
        righe = [f"{m.mention} `{m.id}` {truncate_text(m.name, 32)}" for m in trovati[: logica.MAX_RISULTATI]]
        corpo = "\n".join(righe)
        if len(trovati) > logica.MAX_RISULTATI:
            corpo += "\n" + await testo_per(interaction, "ricercamod_altri", n=len(trovati) - logica.MAX_RISULTATI)
        if incompleta:
            corpo += "\n" + await testo_per(interaction, "ricercamod_membri_cache", n=len(guild.members), tot=guild.member_count)
        embed = discord.Embed(title=await testo_per(interaction, "ricercamod_membri_titolo", n=len(trovati)), description=truncate_text(corpo, 4000), color=discord.Color.blurple())
        file = None
        if esporta:
            dati, righe_csv = logica.csv_membri(trovati)
            file = discord.File(io.BytesIO(dati), filename="membri.csv")
            if righe_csv < len(trovati):
                embed.set_footer(text=await testo_per(interaction, "ricercamod_csv_tagliato", n=righe_csv))
        kw = {"file": file} if file else {}
        await interaction.followup.send(embed=embed, ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE, **kw)

    # ---------------------------------------------------------------- MOD-110
    @comando_di_gruppo("mod-casi", nome="invito", descrizione="Mostra cosa c'è dietro un invito: server, canale, chi l'ha creato.")
    @app_commands.describe(codice="Il codice o il link dell'invito")
    async def invito(self, interaction: discord.Interaction, codice: app_commands.Range[str, 2, 120]) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        pulito = logica.codice_invito(codice)
        if pulito is None:
            await interaction.response.send_message(await testo_per(interaction, "ricercamod_invito_non_valido"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            inv = await self.bot.fetch_invite(pulito, with_counts=True, with_expiration=True)
        except discord.NotFound:
            await interaction.followup.send(await testo_per(interaction, "ricercamod_invito_assente"), ephemeral=True)
            return
        except discord.HTTPException:
            await interaction.followup.send(await testo_per(interaction, "ricercamod_invito_errore"), ephemeral=True)
            return
        embed = discord.Embed(title=await testo_per(interaction, "ricercamod_invito_titolo", codice=inv.code), color=discord.Color.blurple())
        nd = await testo_per(interaction, "ricercamod_non_noto")
        guild = inv.guild
        embed.add_field(name=await testo_per(interaction, "ricercamod_invito_server"), value=truncate_text(f"{getattr(guild, 'name', nd)} ({getattr(guild, 'id', '?')})", 1024), inline=False)
        canale = inv.channel
        embed.add_field(name=await testo_per(interaction, "ricercamod_invito_canale"), value=truncate_text(f"#{getattr(canale, 'name', nd)}", 1024), inline=True)
        creatore = f"{inv.inviter} ({inv.inviter.id})" if inv.inviter else nd
        embed.add_field(name=await testo_per(interaction, "ricercamod_invito_creatore"), value=truncate_text(creatore, 1024), inline=True)
        membri = f"{inv.approximate_member_count} / {inv.approximate_presence_count}" if inv.approximate_member_count is not None else nd
        embed.add_field(name=await testo_per(interaction, "ricercamod_invito_membri"), value=membri, inline=True)
        scade = discord.utils.format_dt(inv.expires_at, "R") if inv.expires_at else await testo_per(interaction, "ricercamod_invito_mai")
        embed.add_field(name=await testo_per(interaction, "ricercamod_invito_scadenza"), value=scade, inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RicercaModerazioneCog(bot))
