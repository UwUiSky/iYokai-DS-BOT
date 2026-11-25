"""
cogs/utility/activity_stats.py
==============================
Statistiche di attività (NF-25, #96): conta messaggi e minuti in vocale per
canale e per membro (solo somme per giorno, scritte a lotti ogni minuto),
dà e toglie i ruoli per attività. Comandi: /admin-moduli statistiche …; la lettura
dei numeri sta in /utility serverstats (cogs/utility/server_stats.py).
Funzioni coperte: SPEC §23 (NF-25); STA-006, 008, 013, 025..027, 029, 030..032, 057
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
import zipfile
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.moderation_shadowban import add_roles_se_libero
from core.activity_stats_logic import (
    GIORNI_CONSERVAZIONE,
    MAX_REGOLE_PER_SERVER,
    ActivityBuffer,
    VoiceTracker,
    canali_del_messaggio,
    conta_secondo_i_filtri,
    regola_con_due_condizioni,
    ruoli_da_aggiornare,
)
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.invio_file import FileTroppoGrande, invia_file
from core.repositories.counter_repo import counter_repo
from core.server_stats_logic import tabella_in_csv
from core.i18n import testo_per
from core.repositories.activity_stats_repo import ActivitySettings, activity_stats_repo

logger = logging.getLogger("iyokai.activity_stats")

MODULE_SERVER_STATS = "server_stats"
SECONDI_CACHE_IMPOSTAZIONI = 60
_SG = ("statistiche", "Statistiche di attività e ruoli per attività")
_SG_PRIVACY = ("privacy", "I tuoi dati personali: copia e cancellazione")  # lo stesso sotto-gruppo di cogs/utility/privacy.py
_NESSUNA_MENZIONE = discord.AllowedMentions.none()
_NOMI_METRICA = {"messages": "messaggi", "voice_minutes": "minuti in vocale"}
_SCELTE_METRICA = [
    app_commands.Choice(name="Messaggi", value="messages"),
    app_commands.Choice(name="Minuti in vocale", value="voice_minutes"),
]


def _zip_di_tabelle(tabelle: dict[str, list[dict]]) -> bytes:
    """Uno ZIP con un CSV per tabella (STA-057). Le colonne sono quelle della prima riga."""
    uscita = io.BytesIO()
    with zipfile.ZipFile(uscita, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, righe in tabelle.items():
            intestazione = list(righe[0]) if righe else ["(vuota)"]
            z.writestr(f"{nome}.csv", tabella_in_csv(intestazione, [[r.get(c, "") for c in intestazione] for r in righe]))
    return uscita.getvalue()


def _seconda(r) -> str:
    if not r.metric2:
        return ""
    return f" {'e' if r.combine == 'e' else 'oppure'} {r.threshold2} {_NOMI_METRICA[r.metric2]}"


def _righe_filtri(imp: ActivitySettings) -> list[str]:
    """Il riepilogo dei filtri (STA-025..027, 013, 008), per i comandi e per «elenco»."""
    def elenco(prefisso: str, ids) -> str:
        return ", ".join(f"<{prefisso}{i}>" for i in ids[:20]) or "nessuno"

    return [
        f"Canali ({imp.channel_mode}): {elenco('#', imp.ignored_channels)}",
        f"Ruoli ({imp.role_mode}): {elenco('@&', imp.ignored_roles)}",
        f"Membri esclusi: {elenco('@', imp.ignored_members)}",
        f"Possono guardare le statistiche: {elenco('@&', imp.view_roles) if imp.view_roles else 'tutti'}",
        f"Campioni dei membri online: {'sì' if imp.track_online else 'no'}",
    ]


def _muto_sordo(stato) -> tuple[bool, bool]:
    """STA-006: muto/sordo per scelta del membro o del server."""
    if stato is None:
        return False, False
    muto = getattr(stato, "self_mute", False) is True or getattr(stato, "mute", False) is True
    sordo = getattr(stato, "self_deaf", False) is True or getattr(stato, "deaf", False) is True
    return muto, sordo


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

        @tasks.loop(hours=1)
        async def _campioni() -> None:
            try:
                await self.campiona_online()
            except Exception:
                logger.exception("Errore nei campioni dei membri online")

        @_campioni.before_loop
        async def _prima_campioni() -> None:
            await self.bot.wait_until_ready()

        self._scrivi, self._ruoli, self._campioni = _scrivi, _ruoli, _campioni

    async def cog_load(self) -> None:
        await super().cog_load()
        self._scrivi.start()
        self._ruoli.start()
        self._campioni.start()

    async def cog_unload(self) -> None:
        self._scrivi.cancel()
        self._ruoli.cancel()
        self._campioni.cancel()
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
                for m in canale.members:
                    ruoli = {r.id for r in m.roles}
                    if not m.bot and conta_secondo_i_filtri(imp, m.id, ruoli, canali_del_messaggio(canale)):
                        stato = m.voice
                        self._voce.entra(
                            guild.id, canale.id, m.id, ora, *_muto_sordo(stato), afk=canale == guild.afk_channel
                        )

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
        if not conta_secondo_i_filtri(imp, message.author.id, ruoli, canali_del_messaggio(message.channel)):
            return
        self._buffer.add_message(message.guild.id, canale_id, message.author.id, datetime.now(timezone.utc))
        if self._buffer.pieno:
            await self.scrivi_lotto()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after) -> None:
        if member.bot:
            return
        ora = datetime.now(timezone.utc)
        guild = member.guild
        muto, sordo = _muto_sordo(after)
        if before.channel == after.channel:  # STA-006: stesso canale, cambia solo muto o sordo
            if after.channel is not None:
                self._accredita(self._voce.cambia_stato(guild.id, member.id, ora, muto, sordo), ora)
            return
        if before.channel is not None:
            self._accredita(self._voce.esce(guild.id, member.id, ora), ora)
        if after.channel is not None and await self._conta(guild):
            imp = await self._impostazioni_di(guild.id)
            ruoli = {r.id for r in member.roles}
            if conta_secondo_i_filtri(imp, member.id, ruoli, canali_del_messaggio(after.channel)):
                self._voce.entra(guild.id, after.channel.id, member.id, ora, muto, sordo, afk=after.channel == guild.afk_channel)

    def _accredita(self, crediti, ora: datetime) -> None:
        for guild_id, utente_id, canale_id, secondi in crediti:
            self._buffer.add_voice(guild_id, canale_id, utente_id, secondi, ora)
        for guild_id, utente_id, secondi, muto, sordo, afk in self._voce.preleva_stati():
            self._buffer.add_voice_state(guild_id, utente_id, secondi, ora, muto, sordo, afk)

    async def scrivi_lotto(self) -> None:
        """Tempo in vocale maturato + somme in memoria → un solo lotto nel database."""
        ora = datetime.now(timezone.utc)
        self._accredita(self._voce.tick(ora), ora)
        lotto = self._buffer.drain()
        stati = self._buffer.drain_stati()
        try:
            await self._repo.flush(*lotto)
            await self._repo.flush_stati(stati)
            self._ultimo_flush, self._ultimo_errore = ora, None
        except Exception as exc:
            logger.exception("Lotto delle statistiche non scritto, riprovo al prossimo giro")
            self._ultimo_errore = type(exc).__name__
            self._buffer.restore(*lotto)
            self._buffer.restore_stati(stati)

    async def campiona_online(self) -> None:
        """STA-008: ogni ora, per i server che l'hanno acceso, i membri online stimati (una chiamata a server).

        Non serve l'intent delle presenze: Discord dà `approximate_presence_count` con i conteggi del server.
        """
        ora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        for guild_id in await self._repo.guilds_tracking_online():
            if self.bot.get_guild(guild_id) is None or not await db.is_module_active_for_guild(guild_id, MODULE_SERVER_STATS):
                continue
            try:
                guild = await self.bot.fetch_guild(guild_id, with_counts=True)
            except discord.HTTPException:
                logger.warning("Campione dei membri online non letto (guild %s)", guild_id)
                continue
            if guild.approximate_presence_count is not None:
                await self._repo.add_online_sample(guild_id, ora, guild.approximate_presence_count)
            await asyncio.sleep(1)

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
        if regola.metric2 and regola.threshold2:  # STA-032: seconda condizione
            seconda = await self._repo.members_over(guild.id, da, regola.metric2, regola.threshold2)
            eleggibili = regola_con_due_condizioni(eleggibili, seconda, regola.combine)
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
                    await add_roles_se_libero(membro, ruolo, reason=motivo)
                else:
                    await membro.remove_roles(ruolo, reason=motivo)
            except discord.HTTPException:
                logger.warning("Ruolo per attività non aggiornato (guild %s, ruolo %s)", guild.id, ruolo.id)
            await asyncio.sleep(0.5)

    # --------------------------------------------------------------- comandi
    async def _pronto(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_SERVER_STATS):
            await interaction.response.send_message(
                await testo_per(interaction, "activitystat_il_modulo_server_stats_non"),
                ephemeral=True,
            )
            return False
        return True

    @comando_di_gruppo("admin-moduli", nome="impostazioni", descrizione="Filtri delle statistiche: canali, membri, ruoli, chi le vede.", sottogruppo=_SG)
    @app_commands.describe(
        canale="Canale o categoria da escludere (o da rimettere se già nell'elenco)",
        ruolo="Ruolo da escludere (o da rimettere se già nell'elenco)",
        membro="Membro da escludere dalle statistiche (o da rimettere)",
        modo_canali="Elenco dei canali: «escludi» li toglie, «solo» conta soltanto quelli",
        modo_ruoli="Elenco dei ruoli: «escludi» li toglie, «solo» conta soltanto chi li ha",
        ruolo_vista="Ruolo che può guardare le statistiche (o da togliere); vuoto = tutti",
        online="Salva ogni ora quanti membri sono online (stima, per il grafico)",
    )
    @app_commands.choices(
        modo_canali=[app_commands.Choice(name="Escludi questi", value="escludi"), app_commands.Choice(name="Conta solo questi", value="solo")],
        modo_ruoli=[app_commands.Choice(name="Escludi questi", value="escludi"), app_commands.Choice(name="Conta solo questi", value="solo")],
    )
    async def impostazioni(
        self,
        interaction: discord.Interaction,
        canale: discord.abc.GuildChannel | None = None,
        ruolo: discord.Role | None = None,
        membro: discord.Member | None = None,
        modo_canali: app_commands.Choice[str] | None = None,
        modo_ruoli: app_commands.Choice[str] | None = None,
        ruolo_vista: discord.Role | None = None,
        online: bool | None = None,
    ) -> None:
        # STA-025 (canali e categorie, anche «solo»), STA-026 (membri), STA-027 (ruoli), STA-013 (chi vede), STA-008 (online)
        if not await self._pronto(interaction):
            return
        gid = interaction.guild.id
        righe = []
        if canale is not None:
            ora = await self._repo.toggle_ignored_channel(gid, canale.id)
            righe.append(f"{canale.mention}: {'nella lista' if ora else 'tolto dalla lista'}.")
        if ruolo is not None:
            ora = await self._repo.toggle_ignored_role(gid, ruolo.id)
            righe.append(f"{ruolo.mention}: {'nella lista' if ora else 'tolto dalla lista'}.")
        if membro is not None:
            ora = await self._repo.toggle_ignored_member(gid, membro.id)
            righe.append(f"{membro.mention}: {'escluso' if ora else 'di nuovo contato'}.")
        if modo_canali is not None:
            await self._repo.set_mode(gid, "canali", modo_canali.value)
        if modo_ruoli is not None:
            await self._repo.set_mode(gid, "ruoli", modo_ruoli.value)
        if ruolo_vista is not None:
            if ruolo_vista.is_default():
                await interaction.response.send_message(await testo_per(interaction, "statistiche_ruolo_vista_everyone"), ephemeral=True)
                return
            ora = await self._repo.toggle_view_role(gid, ruolo_vista.id)
            righe.append(f"{ruolo_vista.mention}: {'può vedere' if ora else 'tolto da chi può vedere'}.")
        if online is not None:
            await self._repo.set_track_online(gid, online)
        self._impostazioni.pop(gid, None)
        imp = await self._repo.get_settings(gid)
        righe += _righe_filtri(imp)
        await interaction.response.send_message("\n".join(righe)[:2000], ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE)

    @comando_di_gruppo("admin-moduli", nome="ruolo-aggiungi", descrizione="Dai un ruolo a chi è attivo e toglilo a chi smette.", sottogruppo=_SG)
    @app_commands.describe(
        ruolo="Il ruolo da dare", metrica="Cosa contare", soglia="Quanto serve nel periodo",
        giorni="Periodo in giorni (da 1 a 90)", togli="Togli il ruolo a chi scende sotto la soglia (sì)",
        metrica2="Seconda condizione: cosa contare (facoltativa)", soglia2="Quanto serve per la seconda condizione",
        unione="Servono tutte e due le condizioni, o basta una",
    )
    @app_commands.choices(
        metrica=_SCELTE_METRICA, metrica2=_SCELTE_METRICA,
        unione=[app_commands.Choice(name="Tutte e due", value="e"), app_commands.Choice(name="Basta una", value="o")],
    )
    async def ruolo_aggiungi(
        self,
        interaction: discord.Interaction,
        ruolo: discord.Role,
        metrica: app_commands.Choice[str],
        soglia: app_commands.Range[int, 1, 1_000_000],
        giorni: app_commands.Range[int, 1, GIORNI_CONSERVAZIONE] = 7,
        togli: bool = True,
        metrica2: app_commands.Choice[str] | None = None,
        soglia2: app_commands.Range[int, 1, 1_000_000] | None = None,
        unione: app_commands.Choice[str] | None = None,
    ) -> None:
        if not await self._pronto(interaction):
            return
        guild = interaction.guild
        if ruolo.is_default() or ruolo.managed:
            await interaction.response.send_message(await testo_per(interaction, "activitystat_questo_ruolo_non_si_puo"), ephemeral=True)
            return
        if (metrica2 is None) != (soglia2 is None):  # STA-032: la seconda condizione ha bisogno di tutte e due
            await interaction.response.send_message(await testo_per(interaction, "statistiche_seconda_condizione_incompleta"), ephemeral=True)
            return
        if interaction.user.id != guild.owner_id and ruolo >= interaction.user.top_role:
            await interaction.response.send_message(
                await testo_per(interaction, "activitystat_non_puoi_scegliere_un_ruolo"), ephemeral=True
            )
            return
        if guild.me is not None and ruolo >= guild.me.top_role:
            await interaction.response.send_message(
                await testo_per(interaction, "activitystat_il_mio_ruolo_piu_alto"), ephemeral=True
            )
            return
        if not await self._repo.add_rule(
            guild.id, ruolo.id, metrica.value, soglia, giorni, togli,
            metrica2.value if metrica2 else None, soglia2, unione.value if unione else "e",
        ):
            await interaction.response.send_message(
                await testo_per(interaction, "activitystat_hai_gia_regole_eliminane_una", v1=MAX_REGOLE_PER_SERVER), ephemeral=True
            )
            return
        condizione = f"{soglia} {_NOMI_METRICA[metrica.value]}"
        if metrica2 is not None:
            congiunzione = "e" if (unione is None or unione.value == "e") else "oppure"
            condizione += f" {congiunzione} {soglia2} {_NOMI_METRICA[metrica2.value]}"
        await interaction.response.send_message(
            f"Regola salvata: {ruolo.mention} a chi ha almeno {condizione} "
            f"negli ultimi {giorni} giorni. Controllo ogni 30 minuti.",
            ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
        )

    @comando_di_gruppo("admin-moduli", nome="ruolo-elimina", descrizione="Elimina una regola dei ruoli per attività.", sottogruppo=_SG)
    @app_commands.describe(regola="Il numero della regola (lo trovi in /admin-moduli statistiche elenco)")
    async def ruolo_elimina(self, interaction: discord.Interaction, regola: app_commands.Range[int, 1, 2_000_000_000]) -> None:
        if not await self._pronto(interaction):
            return
        ok = await self._repo.delete_rule(interaction.guild.id, regola)
        await interaction.response.send_message(
            await testo_per(interaction, "activitystat_regola_eliminata") if ok else await testo_per(interaction, "activitystat_non_trovo_questa_regola"), ephemeral=True
        )

    @comando_di_gruppo("admin-moduli", nome="elenco", descrizione="Mostra regole ed esclusioni delle statistiche.", sottogruppo=_SG)
    async def elenco(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        gid = interaction.guild.id
        regole = await self._repo.list_rules(gid)
        imp = await self._repo.get_settings(gid)
        righe = [
            f"`{r.id}` · <@&{r.role_id}> · {r.threshold} {_NOMI_METRICA[r.metric]} in {r.period_days} giorni"
            f"{_seconda(r)}{'' if r.remove_when_below else ' · non lo tolgo'}"
            for r in regole
        ] or ["Nessuna regola."]
        righe.append("")
        righe += _righe_filtri(imp)
        embed = discord.Embed(title=await testo_per(interaction, "activitystat_statistiche_di_attivita"), description="\n".join(righe)[:4000], color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE)

    @comando_di_gruppo("utility", nome="statistiche", descrizione="Mostra il tuo nome nelle classifiche delle statistiche, o resta anonimo.", sottogruppo=_SG_PRIVACY)
    @app_commands.describe(anonimo="Sì: compari come «utente anonimo» nelle classifiche di tutti i server (anche per il passato)")
    async def privacy_statistiche(self, interaction: discord.Interaction, anonimo: bool) -> None:
        # STA-028: vale per tutti i server e per i dati già raccolti, perché la maschera si applica quando si mostra
        await self._repo.set_anonymous(interaction.user.id, anonimo)
        chiave = "statistiche_anonimo_si" if anonimo else "statistiche_anonimo_no"
        await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)

    @comando_di_gruppo("admin-moduli", nome="esporta", descrizione="Esporta in un file ZIP le statistiche, i contatori e le regole del server.", sottogruppo=_SG)
    @app_commands.checks.cooldown(1, 300.0, key=lambda i: i.guild_id)
    async def esporta(self, interaction: discord.Interaction) -> None:
        # STA-057: tutti i dati statistici del server in un file (solo numeri e ID, mai il testo dei messaggi).
        # Il resto resta nei suoi comandi: /admin-bot-config export, /logs export, /admin-inviti esporta.
        if not await self._pronto(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild.id
        da = datetime.now(timezone.utc).date() - timedelta(days=GIORNI_CONSERVAZIONE)
        tabelle = await self._repo.righe_per_esportare(gid, da)
        tabelle["regole"] = [vars(r) for r in await self._repo.list_rules(gid)]
        tabelle["contatori"] = [vars(c) for c in await counter_repo.list_for_guild(gid)]
        imp = await self._repo.get_settings(gid)
        tabelle["impostazioni"] = [{k: ",".join(map(str, v)) if isinstance(v, list) else v for k, v in vars(imp).items()}]
        dati = await asyncio.to_thread(_zip_di_tabelle, tabelle)
        try:
            await invia_file(interaction.followup.send, dati, f"statistiche-{gid}.zip", dividi=False, ephemeral=True)
        except FileTroppoGrande:
            await interaction.followup.send(await testo_per(interaction, "statistiche_esporta_troppo_grande"), ephemeral=True)

    @comando_di_gruppo("admin-moduli", nome="diagnosi", descrizione="Perché le statistiche non si contano?", sottogruppo=_SG)
    async def diagnosi(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        guild = interaction.guild
        imp = await self._repo.get_settings(guild.id)
        ultimo, recenti = await self._repo.last_activity(guild.id)
        me = guild.me
        # STA-029: perché le statistiche non si contano: canali illeggibili, filtri, scrittura, permessi
        ciechi = [c for c in guild.text_channels if me is not None and not c.permissions_for(me).view_channel]
        righe = [
            "✅ Modulo Server Stats attivo.",
            f"{'✅' if self._ultimo_errore is None else '❌'} Scrittura dei dati: "
            + ("ok" if self._ultimo_errore is None else f"ultimo errore {self._ultimo_errore}"),
            f"{'✅' if self._scrivi.is_running() else '❌'} Conteggio in funzione.",
            f"{'✅' if recenti else '⚠️'} Messaggi contati ieri e oggi: {recenti} (ultimo giorno con dati: {ultimo or 'mai'}).",
            f"Canali nell'elenco: {len(imp.ignored_channels)} ({imp.channel_mode}) · ruoli: {len(imp.ignored_roles)} ({imp.role_mode}) · membri esclusi: {len(imp.ignored_members)}.",
            f"{'✅' if not ciechi else '⚠️'} Canali di testo che non posso leggere: {len(ciechi)}"
            + (f" ({', '.join(c.mention for c in ciechi[:8])})" if ciechi else "") + " (lì i messaggi non arrivano).",
            f"{'✅' if not imp.ignored_channels or imp.channel_mode == 'escludi' else '⚠️'} Filtro dei canali: modo «{imp.channel_mode}»"
            + (" (conto solo i canali dell'elenco)." if imp.channel_mode == "solo" and imp.ignored_channels else "."),
            f"{'✅' if me is not None and me.guild_permissions.manage_roles else '⚠️'} Permesso «Gestisci ruoli» (serve ai ruoli per attività).",
            f"Persone in vocale seguite adesso: {len(self._voce)} (in tutti i server).",
            "I dati si tengono 90 giorni. Bot, webhook e messaggi di sistema non si contano.",
        ]
        await interaction.response.send_message("\n".join(righe), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ActivityStatsCog(bot))
