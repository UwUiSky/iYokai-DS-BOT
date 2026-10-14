"""
cogs/utility/server_stats.py
================================
Server Stats (SPEC.md §14.18): un comando che mostra i numeri del
server (membri, canali, ruoli, boost) più un grafico di crescita
giornaliera basato sul log eventi unificato (core/repositories/
event_log_repo.py) — join/leave degli ultimi N giorni.
"""

from __future__ import annotations

import asyncio
import io
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.ui_base import BaseView
from core.premium import PremiumModule, registry
from core.repositories.activity_stats_repo import activity_stats_repo
from core.repositories.event_log_repo import event_log_repo
from core.server_stats_image import render_bar_chart, render_growth_chart
from core.activity_stats_logic import per_giorno_settimana
from core.server_stats_logic import compute_daily_net_change, fill_missing_days

MODULE_SERVER_STATS = "server_stats"
DEFAULT_DAYS = 14


VISTE = {
    "crescita": "Crescita netta dei membri",
    "ingressi": "Ingressi per giorno",
    "uscite": "Uscite per giorno",
    "canali": "Canali più attivi",
    "membri": "Membri più attivi",
    "ore": "Attività per ora del giorno",
    "giorni-settimana": "Attività per giorno della settimana",
    "membro": "Attività di un membro",
}
_NOMI_GIORNI = ("Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom")
_UNITA = {"messages": "messaggi", "voice_minutes": "minuti in vocale"}
RIGHE_CLASSIFICA = 10
PERIODI_BOTTONI = (7, 30, 90)
_NESSUNA_MENZIONE = discord.AllowedMentions.none()


def _canale_visibile(guild: discord.Guild, canale_id: int, membro: discord.Member) -> bool:
    canale = guild.get_channel(canale_id)
    return canale is None or canale.permissions_for(membro).view_channel


async def _eventi_giornalieri(guild_id: int, since: datetime, tipo: str) -> dict:
    eventi = await event_log_repo.get_events_by_type_since(guild_id, tipo, since)
    conteggi: dict = {}
    for e in eventi:
        conteggi[e.created_at.date()] = conteggi.get(e.created_at.date(), 0) + 1
    return conteggi


async def costruisci_statistiche(
    guild: discord.Guild,
    vista: str,
    giorni: int,
    metrica: str = "messages",
    ruolo: discord.Role | None = None,
    utente: discord.Member | None = None,
    visti_da: discord.Member | None = None,
) -> tuple[discord.Embed, discord.File | None]:
    """Embed (e grafico) di /utility serverstats per la vista scelta."""
    adesso = datetime.now(timezone.utc)
    since = adesso - timedelta(days=giorni)
    dal = (adesso - timedelta(days=giorni - 1)).date()
    titolo = f"📊 {VISTE[vista]} — {guild.name}"
    embed = discord.Embed(title=titolo, color=discord.Color.blurple())
    png: bytes | None = None
    unita = _UNITA[metrica]

    if vista in ("crescita", "ingressi", "uscite"):
        if vista == "crescita":
            ev = await event_log_repo.get_events_by_type_since(guild.id, "member_join", since)
            ev2 = await event_log_repo.get_events_by_type_since(guild.id, "member_remove", since)
            grezze = compute_daily_net_change(
                [(e.created_at, "member_join") for e in ev] + [(e.created_at, "member_remove") for e in ev2]
            )
        else:
            tipo = "member_join" if vista == "ingressi" else "member_remove"
            segno = 1 if vista == "ingressi" else -1
            grezze = {g: segno * n for g, n in (await _eventi_giornalieri(guild.id, since, tipo)).items()}
        serie = fill_missing_days(grezze, start=since.date(), end=adesso.date())
        png = await asyncio.to_thread(render_growth_chart, serie, f"{VISTE[vista]} — ultimi {giorni} giorni")
        embed.add_field(name="Membri", value=str(guild.member_count), inline=True)
        embed.add_field(
            name="Canali",
            value=(
                f"{len(guild.text_channels)} testo\n{len(guild.voice_channels)} vocali\n"
                f"{len(guild.forums)} forum\n{len(guild.stage_channels)} stage\n{len(guild.categories)} categorie"
            ),
            inline=True,
        )
        embed.add_field(name="Ruoli", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Emoji", value=f"{len(guild.emojis)} su {guild.emoji_limit}", inline=True)
        embed.add_field(name="Boost", value=f"Livello {guild.premium_tier} ({guild.premium_subscription_count} boost)", inline=True)
        embed.add_field(name="Creato il", value=discord.utils.format_dt(guild.created_at, style="D"), inline=True)
        if ruolo is not None:
            con = len(ruolo.members)
            embed.add_field(name=f"Con il ruolo {ruolo.name[:60]}", value=f"{con} con · {max(0, guild.member_count - con)} senza", inline=False)
        if guild.icon is not None:
            embed.set_thumbnail(url=guild.icon.url)
    elif vista == "canali":
        top = await activity_stats_repo.top_channels(guild.id, dal, metrica, RIGHE_CLASSIFICA * 5)
        if visti_da is not None:  # chi guarda non vede nomi e numeri dei canali che non può aprire
            top = [(c, n) for c, n in top if _canale_visibile(guild, c, visti_da)]
        top = top[:RIGHE_CLASSIFICA]
        embed.description = "\n".join(f"{i}. <#{c}> — **{n}** {unita}" for i, (c, n) in enumerate(top, 1)) or "Ancora nessun dato."
    elif vista == "membri":
        solo = {m.id for m in ruolo.members} if ruolo is not None else None
        top = await activity_stats_repo.top_members(guild.id, dal, metrica, RIGHE_CLASSIFICA, solo_utenti=solo)
        embed.description = "\n".join(f"{i}. <@{u}> — **{n}** {unita}" for i, (u, n) in enumerate(top, 1)) or "Ancora nessun dato."
        if ruolo is not None:
            embed.set_footer(text=f"Solo chi ha il ruolo {ruolo.name[:60]}")
    elif vista == "ore":
        ore = await activity_stats_repo.by_hour(guild.id, dal, metrica)
        png = await asyncio.to_thread(render_bar_chart, [str(h) for h in range(24)], ore, f"{unita} per ora (UTC)")
    elif vista == "giorni-settimana":
        per_giorno = await activity_stats_repo.by_day(guild.id, dal, metrica)
        png = await asyncio.to_thread(render_bar_chart, list(_NOMI_GIORNI), per_giorno_settimana(per_giorno), f"{unita} per giorno della settimana")
    else:  # membro
        bersaglio = utente
        if bersaglio is None:
            embed.description = "Scegli un membro nel campo `utente`."
        else:
            mess = await activity_stats_repo.member_total(guild.id, bersaglio.id, dal, "messages")
            voce = await activity_stats_repo.member_total(guild.id, bersaglio.id, dal, "voice_minutes")
            embed.description = f"{bersaglio.mention}: **{mess}** messaggi e **{voce}** minuti in vocale."
    if png is not None:
        embed.set_image(url="attachment://statistiche.png")
        embed.set_footer(text=f"Ultimi {giorni} giorni" + (" · orari in UTC" if vista == "ore" else ""))
    else:
        embed.set_footer(text=embed.footer.text or f"Ultimi {giorni} giorni")
    return embed, (discord.File(io.BytesIO(png), filename="statistiche.png") if png else None)


class _PeriodoView(BaseView):
    """Bottoni sotto la risposta: cambia periodo o aggiorna. Li usa solo chi ha lanciato il comando."""

    def __init__(self, autore_id: int, guild, vista, giorni, metrica, ruolo, utente, visti_da=None) -> None:
        super().__init__(timeout=300)
        self._autore_id = autore_id
        self._visti_da = visti_da
        self._args = [guild, vista, metrica, ruolo, utente]
        self.giorni = giorni
        for periodo in PERIODI_BOTTONI:
            b = discord.ui.Button(
                label=f"{periodo} giorni",
                style=discord.ButtonStyle.primary if periodo == giorni else discord.ButtonStyle.secondary,
            )
            b.callback = self._cambia(periodo)
            self.add_item(b)
        agg = discord.ui.Button(label="Aggiorna", emoji="🔄", style=discord.ButtonStyle.secondary)
        agg.callback = self._cambia(None)
        self.add_item(agg)

    def _cambia(self, periodo):
        async def _callback(interaction: discord.Interaction) -> None:
            if interaction.user.id != self._autore_id:
                await interaction.response.send_message("Questi bottoni sono di chi ha lanciato il comando.", ephemeral=True)
                return
            await interaction.response.defer()
            giorni = periodo or self.giorni
            guild, vista, metrica, ruolo, utente = self._args
            embed, file = await costruisci_statistiche(guild, vista, giorni, metrica, ruolo, utente, self._visti_da)
            nuova = _PeriodoView(self._autore_id, guild, vista, giorni, metrica, ruolo, utente, self._visti_da)
            await interaction.edit_original_response(
                embed=embed, attachments=[file] if file else [], view=nuova, allowed_mentions=_NESSUNA_MENZIONE
            )

        return _callback


class ServerStatsCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "utility",
        nome="serverstats",
        descrizione="Statistiche del server: crescita, attività dei canali e dei membri.",
    )
    @app_commands.describe(
        days="Quanti giorni indietro (default 14, massimo 90)",
        vista="Cosa mostrare (default: crescita)",
        metrica="Messaggi o minuti in vocale (per le viste di attività)",
        ruolo="Limita la classifica ai membri con questo ruolo, o conta chi lo ha",
        utente="Il membro, per la vista «Attività di un membro»",
    )
    @app_commands.choices(
        vista=[app_commands.Choice(name=nome, value=chiave) for chiave, nome in VISTE.items()],
        metrica=[
            app_commands.Choice(name="Messaggi", value="messages"),
            app_commands.Choice(name="Minuti in vocale", value="voice_minutes"),
        ],
    )
    async def server_stats(
        self,
        interaction: discord.Interaction,
        days: app_commands.Range[int, 1, 90] = DEFAULT_DAYS,
        vista: app_commands.Choice[str] | None = None,
        metrica: app_commands.Choice[str] | None = None,
        ruolo: discord.Role | None = None,
        utente: discord.Member | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        if not await db.is_module_active_for_guild(guild.id, MODULE_SERVER_STATS):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /admin setup attiva.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        chiave = vista.value if vista is not None else "crescita"
        misura = metrica.value if metrica is not None else "messages"
        embed, file = await costruisci_statistiche(guild, chiave, days, misura, ruolo, utente, interaction.user)
        view = _PeriodoView(interaction.user.id, guild, chiave, days, misura, ruolo, utente, interaction.user)
        kwargs = {"embed": embed, "view": view, "allowed_mentions": _NESSUNA_MENZIONE}
        if file is not None:
            kwargs["file"] = file
        await interaction.followup.send(**kwargs)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_SERVER_STATS,
            display_name="Server Stats",
            category="utility",
            description="Statistiche del server: crescita, attività di canali e membri, ruoli per attività.",
            premium_capable=False,
        )
    )
    await bot.add_cog(ServerStatsCog(bot))
