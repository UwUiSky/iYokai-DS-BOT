"""
cogs/utility/activity_stats.py
==============================
Statistiche di attività (NF-25, #96): conta messaggi e minuti in vocale per
canale e per membro (solo somme per giorno, scritte a lotti ogni minuto),
dà e toglie i ruoli per attività. Comandi: /moduli statistiche …; la lettura
dei numeri sta in /utility serverstats (cogs/utility/server_stats.py).
Funzioni coperte: SPEC §23 (NF-25)
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.activity_stats_logic import (
    GIORNI_CONSERVAZIONE,
    MAX_REGOLE_PER_SERVER,
    ActivityBuffer,
    VoiceTracker,
    escluso,
    ruoli_da_aggiornare,
)
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.repositories.activity_stats_repo import ActivitySettings, activity_stats_repo

logger = logging.getLogger("iyokai.activity_stats")

MODULE_SERVER_STATS = "server_stats"
SECONDI_CACHE_IMPOSTAZIONI = 60
_SG = ("statistiche", "Statistiche di attività e ruoli per attività")
_NESSUNA_MENZIONE = discord.AllowedMentions.none()
_NOMI_METRICA = {"messages": "messaggi", "voice_minutes": "minuti in vocale"}


class ActivityStatsCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot, repo=activity_stats_repo) -> None:
        self.bot = bot
        self._repo = repo
        self._buffer = ActivityBuffer()
        self._voce = VoiceTracker()
        self._impostazioni: dict[int, tuple[float, ActivitySettings]] = {}
        self._ultimo_flush: datetime | None = None
        self._ultimo_errore: str | None = None
        self._giro_ruoli = 0

        @tasks.loop(seconds=60)
        async def _scrivi() -> None:
            await self.scrivi_lotto()

        @_scrivi.before_loop
        async def _prima_scrivi() -> None:
            await self.bot.wait_until_ready()
            await self._riprendi_vocali()

        @tasks.loop(minutes=30)
        async def _ruoli() -> None:
            try:
                await self.aggiorna_ruoli()
            except Exception:
                logger.exception("Errore nel giro dei ruoli per attività")

        @_ruoli.before_loop
        async def _prima_ruoli() -> None:
            await self.bot.wait_until_ready()

        self._scrivi, self._ruoli = _scrivi, _ruoli

    async def cog_load(self) -> None:
        await super().cog_load()
        self._scrivi.start()
        self._ruoli.start()

    async def cog_unload(self) -> None:
        self._scrivi.cancel()
        self._ruoli.cancel()
        await self.scrivi_lotto()
        await super().cog_unload()

    # ------------------------------------------------------------ raccolta
    async def _riprendi_vocali(self) -> None:
        ora = datetime.now(timezone.utc)
        for guild in self.bot.guilds:
            if not await self._conta(guild):
                continue
            imp = await self._impostazioni_di(guild.id)
            for canale in guild.voice_channels:
                if canale == guild.afk_channel:
                    continue
                for m in canale.members:
                    ruoli = {r.id for r in m.roles}
                    if not m.bot and not escluso(canale.id, ruoli, imp.ignored_channels, imp.ignored_roles):
                        self._voce.entra(guild.id, canale.id, m.id, ora)

    async def _impostazioni_di(self, guild_id: int) -> ActivitySettings:
        voce = self._impostazioni.get(guild_id)
        if voce is not None and time.monotonic() - voce[0] < SECONDI_CACHE_IMPOSTAZIONI:
            return voce[1]
        try:
            imp = await self._repo.get_settings(guild_id)
        except Exception:
            logger.exception("Impostazioni statistiche non lette")
            return voce[1] if voce else ActivitySettings()
        self._impostazioni[guild_id] = (time.monotonic(), imp)
        return imp

    async def _conta(self, guild: discord.Guild | None) -> bool:
        return guild is not None and await db.is_module_active_for_guild(guild.id, MODULE_SERVER_STATS)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot or message.webhook_id is not None:
            return
        if message.type not in (discord.MessageType.default, discord.MessageType.reply):
            return
        if not await self._conta(message.guild):
            return
        imp = await self._impostazioni_di(message.guild.id)
        ruoli = {r.id for r in getattr(message.author, "roles", ())}
        canale_id = getattr(message.channel, "parent_id", None) or message.channel.id
        if escluso(message.channel.id, ruoli, imp.ignored_channels, imp.ignored_roles) or (
            canale_id in imp.ignored_channels
        ):
            return
        self._buffer.add_message(message.guild.id, canale_id, message.author.id, datetime.now(timezone.utc))
        if self._buffer.pieno:
            await self.scrivi_lotto()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after) -> None:
        if member.bot or before.channel == after.channel:
            return
        ora = datetime.now(timezone.utc)
        guild = member.guild
        if before.channel is not None:
            self._accredita(self._voce.esce(guild.id, member.id, ora), ora)
        if after.channel is not None and after.channel != guild.afk_channel and await self._conta(guild):
            imp = await self._impostazioni_di(guild.id)
            ruoli = {r.id for r in member.roles}
            if not escluso(after.channel.id, ruoli, imp.ignored_channels, imp.ignored_roles):
                self._voce.entra(guild.id, after.channel.id, member.id, ora)

    def _accredita(self, crediti, ora: datetime) -> None:
        for guild_id, utente_id, canale_id, secondi in crediti:
            self._buffer.add_voice(guild_id, canale_id, utente_id, secondi, ora)

    async def scrivi_lotto(self) -> None:
        """Tempo in vocale maturato + somme in memoria → un solo lotto nel database."""
        ora = datetime.now(timezone.utc)
        self._accredita(self._voce.tick(ora), ora)
        lotto = self._buffer.drain()
        try:
            await self._repo.flush(*lotto)
            self._ultimo_flush, self._ultimo_errore = ora, None
        except Exception as exc:
            logger.exception("Lotto delle statistiche non scritto, riprovo al prossimo giro")
            self._ultimo_errore = type(exc).__name__
            self._buffer.restore(*lotto)

    # ------------------------------------------------------- ruoli per attività
    async def aggiorna_ruoli(self) -> None:
        self._giro_ruoli += 1
        for guild_id in await self._repo.guilds_with_rules():
            guild = self.bot.get_guild(guild_id)
            if guild is None or not await self._conta(guild):
                continue
            for regola in await self._repo.list_rules(guild_id):
                await self._applica_regola(guild, regola)

    async def _applica_regola(self, guild: discord.Guild, regola) -> None:
        ruolo = guild.get_role(regola.role_id)
        me = guild.me
        if ruolo is None or me is None or not me.guild_permissions.manage_roles or ruolo >= me.top_role:
            return
        da = datetime.now(timezone.utc).date() - timedelta(days=regola.period_days - 1)
        eleggibili = await self._repo.members_over(guild.id, da, regola.metric, regola.threshold)
        eleggibili = {u for u in eleggibili if (m := guild.get_member(u)) is not None and not m.bot}
        possessori = {m.id for m in ruolo.members}
        dare, togliere = ruoli_da_aggiornare(
            eleggibili, possessori, regola.remove_when_below, giro=self._giro_ruoli
        )
        motivo = f"Ruolo per attività ({_NOMI_METRICA[regola.metric]} >= {regola.threshold} in {regola.period_days} giorni)"
        for uid in dare | togliere:
            membro = guild.get_member(uid)
            if membro is None:
                continue
            try:
                if uid in dare:
                    await membro.add_roles(ruolo, reason=motivo)
                else:
                    await membro.remove_roles(ruolo, reason=motivo)
            except discord.HTTPException:
                logger.warning("Ruolo per attività non aggiornato (guild %s, ruolo %s)", guild.id, ruolo.id)
            await asyncio.sleep(0.5)

    # --------------------------------------------------------------- comandi
    async def _pronto(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_SERVER_STATS):
            await interaction.response.send_message(
                "Il modulo Server Stats non è attivo su questo server. "
                "Un amministratore può attivarlo con /admin setup attiva.",
                ephemeral=True,
            )
            return False
        return True

    @comando_di_gruppo("moduli", nome="impostazioni", descrizione="Escludi canali o ruoli dalle statistiche.", sottogruppo=_SG)
    @app_commands.describe(
        canale="Canale da escludere (o da rimettere se già escluso)",
        ruolo="Ruolo da escludere (o da rimettere se già escluso)",
    )
    async def impostazioni(
        self,
        interaction: discord.Interaction,
        canale: discord.abc.GuildChannel | None = None,
        ruolo: discord.Role | None = None,
    ) -> None:
        if not await self._pronto(interaction):
            return
        gid = interaction.guild.id
        righe = []
        if canale is not None:
            ora = await self._repo.toggle_ignored_channel(gid, canale.id)
            righe.append(f"{canale.mention}: {'escluso' if ora else 'di nuovo contato'}.")
        if ruolo is not None:
            ora = await self._repo.toggle_ignored_role(gid, ruolo.id)
            righe.append(f"{ruolo.mention}: {'escluso' if ora else 'di nuovo contato'}.")
        self._impostazioni.pop(gid, None)
        imp = await self._repo.get_settings(gid)
        righe.append(f"Canali esclusi: {', '.join(f'<#{c}>' for c in imp.ignored_channels[:20]) or 'nessuno'}")
        righe.append(f"Ruoli esclusi: {', '.join(f'<@&{r}>' for r in imp.ignored_roles[:20]) or 'nessuno'}")
        await interaction.response.send_message("\n".join(righe)[:2000], ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE)

    @comando_di_gruppo("moduli", nome="ruolo-aggiungi", descrizione="Dai un ruolo a chi è attivo e toglilo a chi smette.", sottogruppo=_SG)
    @app_commands.describe(
        ruolo="Il ruolo da dare", metrica="Cosa contare", soglia="Quanto serve nel periodo",
        giorni="Periodo in giorni (da 1 a 90)", togli="Togli il ruolo a chi scende sotto la soglia (sì)",
    )
    @app_commands.choices(
        metrica=[
            app_commands.Choice(name="Messaggi", value="messages"),
            app_commands.Choice(name="Minuti in vocale", value="voice_minutes"),
        ]
    )
    async def ruolo_aggiungi(
        self,
        interaction: discord.Interaction,
        ruolo: discord.Role,
        metrica: app_commands.Choice[str],
        soglia: app_commands.Range[int, 1, 1_000_000],
        giorni: app_commands.Range[int, 1, GIORNI_CONSERVAZIONE] = 7,
        togli: bool = True,
    ) -> None:
        if not await self._pronto(interaction):
            return
        guild = interaction.guild
        if ruolo.is_default() or ruolo.managed:
            await interaction.response.send_message("Questo ruolo non si può assegnare.", ephemeral=True)
            return
        if interaction.user.id != guild.owner_id and ruolo >= interaction.user.top_role:
            await interaction.response.send_message(
                "Non puoi scegliere un ruolo uguale o superiore al tuo.", ephemeral=True
            )
            return
        if guild.me is not None and ruolo >= guild.me.top_role:
            await interaction.response.send_message(
                "Il mio ruolo più alto è sotto quello scelto: spostami più in alto e riprova.", ephemeral=True
            )
            return
        if not await self._repo.add_rule(guild.id, ruolo.id, metrica.value, soglia, giorni, togli):
            await interaction.response.send_message(
                f"Hai già {MAX_REGOLE_PER_SERVER} regole: eliminane una prima.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"Regola salvata: {ruolo.mention} a chi ha almeno {soglia} {_NOMI_METRICA[metrica.value]} "
            f"negli ultimi {giorni} giorni. Controllo ogni 30 minuti.",
            ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
        )

    @comando_di_gruppo("moduli", nome="ruolo-elimina", descrizione="Elimina una regola dei ruoli per attività.", sottogruppo=_SG)
    @app_commands.describe(regola="Il numero della regola (lo trovi in /moduli statistiche elenco)")
    async def ruolo_elimina(self, interaction: discord.Interaction, regola: app_commands.Range[int, 1, 2_000_000_000]) -> None:
        if not await self._pronto(interaction):
            return
        ok = await self._repo.delete_rule(interaction.guild.id, regola)
        await interaction.response.send_message(
            "Regola eliminata." if ok else "Non trovo questa regola.", ephemeral=True
        )

    @comando_di_gruppo("moduli", nome="elenco", descrizione="Mostra regole ed esclusioni delle statistiche.", sottogruppo=_SG)
    async def elenco(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        gid = interaction.guild.id
        regole = await self._repo.list_rules(gid)
        imp = await self._repo.get_settings(gid)
        righe = [
            f"`{r.id}` · <@&{r.role_id}> · {r.threshold} {_NOMI_METRICA[r.metric]} in {r.period_days} giorni"
            f"{'' if r.remove_when_below else ' · non lo tolgo'}"
            for r in regole
        ] or ["Nessuna regola."]
        righe.append(f"\nCanali esclusi: {', '.join(f'<#{c}>' for c in imp.ignored_channels[:20]) or 'nessuno'}")
        righe.append(f"Ruoli esclusi: {', '.join(f'<@&{r}>' for r in imp.ignored_roles[:20]) or 'nessuno'}")
        embed = discord.Embed(title="Statistiche di attività", description="\n".join(righe)[:4000], color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE)

    @comando_di_gruppo("moduli", nome="diagnosi", descrizione="Perché le statistiche non si contano?", sottogruppo=_SG)
    async def diagnosi(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        guild = interaction.guild
        imp = await self._repo.get_settings(guild.id)
        ultimo, recenti = await self._repo.last_activity(guild.id)
        me = guild.me
        righe = [
            "✅ Modulo Server Stats attivo.",
            f"{'✅' if self._ultimo_errore is None else '❌'} Scrittura dei dati: "
            + ("ok" if self._ultimo_errore is None else f"ultimo errore {self._ultimo_errore}"),
            f"{'✅' if self._scrivi.is_running() else '❌'} Conteggio in funzione.",
            f"{'✅' if recenti else '⚠️'} Messaggi contati ieri e oggi: {recenti} (ultimo giorno con dati: {ultimo or 'mai'}).",
            f"Canali esclusi: {len(imp.ignored_channels)} · ruoli esclusi: {len(imp.ignored_roles)}.",
            f"{'✅' if me is not None and me.guild_permissions.manage_roles else '⚠️'} Permesso «Gestisci ruoli» (serve ai ruoli per attività).",
            f"Persone in vocale seguite adesso: {len(self._voce)} (in tutti i server).",
            "I dati si tengono 90 giorni. Bot, webhook e messaggi di sistema non si contano.",
        ]
        await interaction.response.send_message("\n".join(righe), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ActivityStatsCog(bot))
