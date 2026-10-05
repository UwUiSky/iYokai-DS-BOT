"""
cogs/security/anti_raid.py
==============================
Anti-Raid (SPEC.md §7.1): rilevamento di un'ondata di join sospetti
(join rate limit, età account, pattern username/avatar) e risposta
automatica (quarantena e/o innalzamento del livello di verifica),
più alert allo staff. Modulo CANDIDATO PREMIUM (come Spam Trap,
§7.3): protezione avanzata del server.

Logica di valutazione PURA in core/security_logic.py — qui solo
l'estrazione dei segnali dal `discord.Member` reale e l'esecuzione
della risposta (assegnazione ruolo quarantena, innalzamento
verification_level, alert, log).

Il blocco scatta solo quando gli ingressi superano la soglia. Il
livello di verifica alzato torna quello di prima alla scadenza del
blocco (salvata nel database, controllata ogni minuto).

Funzioni coperte: SPEC §7.1
"""

# DA FARE (issue #59, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §3 (Sicurezza (anti-raid,
#   anti-nuke, spam-trap, ban globale)).

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.bot_ready import attendi_bot_pronto
from core.bounded_cache import BoundedCache
from core.database import db
from core.premium import PremiumModule, registry, requires_module
from core.repositories.security_repo import SecuritySettings, security_repo
from core.security_access import premium_sbloccato
from core.security_logic import AntiRaidConfig, JoinSignals, evaluate_join, is_raid
from core.security_raid_state import DURATA_RAID_SECONDI, azzera, segna_raid
from core.security_rate_tracker import GUILD_WIDE_KEY, security_rate_tracker
from cogs.moderation._shared import ensure_module_enabled, try_dm

logger = logging.getLogger("iyokai.anti_raid")

MODULE_ANTI_RAID = "anti_raid"

NOME_RUOLO_QUARANTENA = "Quarantined"

# Cosa non può fare chi è in quarantena. I thread ereditano dal canale
# che li contiene; la chat di un vocale è coperta da send_messages.
PERMESSI_QUARANTENA = {
    "send_messages": False,
    "send_messages_in_threads": False,
    "create_public_threads": False,
    "create_private_threads": False,
    "add_reactions": False,
    "speak": False,
    "connect": False,
}

# Dal 16/11/2026 un canale che il bot non può vedere arriva con questo
# nome finto (LIMITI.md, Parte 2): non va toccato.
NOME_CANALE_NASCOSTO = "___hidden___"

# Durata del blocco dopo l'ultimo ingresso del raid: passato questo
# tempo il livello di verifica torna quello di prima. Vale anche come
# durata di un "episodio": dentro un episodio il proprietario riceve un
# solo DM.
DURATA_BLOCCO_SECONDI = DURATA_RAID_SECONDI

# Quanti ultimi ingressi si elencano nell'avviso aggiornato, e quanto
# può essere lungo un nome (il testo di un embed arriva a 4096).
MAX_INGRESSI_ELENCATI = 15
MAX_NOME_ELENCATO = 80


@dataclass
class _Avviso:
    """L'avviso dell'episodio in corso: un solo messaggio, aggiornato."""

    messaggio: discord.Message | None
    ultimo_ingresso: datetime
    conteggio: int = 0
    recenti: deque = field(default_factory=lambda: deque(maxlen=MAX_INGRESSI_ELENCATI))


def _embed_avviso(avviso: _Avviso) -> discord.Embed:
    righe = "\n".join(f"• {voce}" for voce in avviso.recenti)
    return discord.Embed(
        title=f"🚨 Anti-Raid — {avviso.conteggio} join sospetti",
        description=f"Ultimi ingressi (dal più vecchio):\n{righe}"[:4096],
        color=discord.Color.red(),
    )


def _allinea_necessario(channel: discord.abc.GuildChannel, role: discord.Role) -> bool:
    """True se il canale non nega ancora al ruolo tutti i permessi di quarantena."""
    if channel.name == NOME_CANALE_NASCOSTO:
        return False
    permessi = channel.overwrites_for(role)
    return not all(getattr(permessi, nome) is False for nome in PERMESSI_QUARANTENA)


async def _blocca_canale(channel: discord.abc.GuildChannel, role: discord.Role) -> None:
    """
    Nega al ruolo di quarantena scrittura, thread, reazioni e voce su
    un canale. Gli stessi permessi valgono per ogni tipo di canale
    (testo, forum, vocale con la sua chat, palco, categoria): quelli
    che non c'entrano con quel tipo non hanno effetto. Un canale che
    rifiuta la modifica non ferma gli altri.
    """
    if channel.name == NOME_CANALE_NASCOSTO:
        return
    try:
        await channel.set_permissions(
            role, reason="Anti-Raid: blocco del ruolo di quarantena", **PERMESSI_QUARANTENA
        )
    except discord.HTTPException:
        logger.warning(
            "Impossibile impostare l'overwrite quarantena sul canale %s (server %s).",
            channel.id, channel.guild.id,
        )


async def _get_or_create_quarantine_role(
    guild: discord.Guild, settings: SecuritySettings
) -> tuple[discord.Role | None, bool]:
    """
    Stesso schema di `_get_or_create_mute_role` in
    cogs/moderation/softban_mute.py (ruolo dedicato + overwrite su
    ogni canale), ma un ruolo SEPARATO: la quarantena è per un
    sospetto raider appena entrato, il mute è per un membro esistente
    sanzionato — mescolarli renderebbe impossibile distinguere i due
    casi nell'audit trail del server.

    Restituisce (ruolo, creato_adesso): un ruolo appena creato ha già
    i permessi su ogni canale, uno trovato no.

    Va chiamata dentro il blocco per server del cog
    (AntiRaidCog._ruolo_quarantena): senza, più ingressi insieme
    creerebbero più ruoli.
    """
    if settings.quarantine_role_id is not None:
        role = guild.get_role(settings.quarantine_role_id)
        if role is not None:
            return role, False

    # Un ruolo "Quarantined" già nel server (fatto a mano o da una
    # versione precedente) si usa, invece di crearne un secondo.
    esistente = discord.utils.get(guild.roles, name=NOME_RUOLO_QUARANTENA)
    if esistente is not None and not esistente.managed:
        await security_repo.save_settings(_replace(settings, quarantine_role_id=esistente.id))
        return esistente, False

    try:
        role = await guild.create_role(
            name=NOME_RUOLO_QUARANTENA,
            reason="Ruolo di quarantena creato automaticamente da iYokai (Anti-Raid)",
        )
    except discord.HTTPException as errore:
        logger.warning(
            "Impossibile creare il ruolo di quarantena nel server %s: %s", guild.id, errore
        )
        return None, False

    for channel in guild.channels:
        await _blocca_canale(channel, role)

    nuova = _replace(settings, quarantine_role_id=role.id)
    await security_repo.save_settings(nuova)
    return role, True


def _replace(settings: SecuritySettings, **overrides) -> SecuritySettings:
    dati = {
        "guild_id": settings.guild_id,
        "anti_raid": settings.anti_raid,
        "anti_nuke": settings.anti_nuke,
        "quarantine_role_id": settings.quarantine_role_id,
        "alert_channel_id": settings.alert_channel_id,
    }
    anti_raid_fields = set(AntiRaidConfig.__dataclass_fields__.keys())
    anti_raid_overrides = {k: v for k, v in overrides.items() if k in anti_raid_fields}
    altri_overrides = {k: v for k, v in overrides.items() if k not in anti_raid_fields}

    if anti_raid_overrides:
        dati["anti_raid"] = AntiRaidConfig(
            **{**{f: getattr(settings.anti_raid, f) for f in anti_raid_fields}, **anti_raid_overrides}
        )
    dati.update(altri_overrides)
    return SecuritySettings(**dati)


async def _alert_staff(
    guild: discord.Guild,
    settings: SecuritySettings,
    embed: discord.Embed,
) -> None:
    if guild.owner is not None:
        await try_dm(guild.owner, embed)
    if settings.alert_channel_id is not None:
        canale = guild.get_channel(settings.alert_channel_id)
        if isinstance(canale, discord.TextChannel):
            try:
                await canale.send(embed=embed)
            except discord.HTTPException:
                pass


class AntiRaidCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Un blocco per server sulla creazione del ruolo di quarantena.
        self._blocchi_ruolo: dict[int, asyncio.Lock] = {}
        # Un blocco per server sull'invio/modifica dell'avviso.
        self._blocchi_avviso: dict[int, asyncio.Lock] = {}
        # Server -> ora dell'ultimo ingresso di raid segnalato.
        self._avvisi: BoundedCache[int, _Avviso] = BoundedCache(max_size=500)
        # Server in cui il ruolo di quarantena è già allineato ai canali.
        self._ruoli_allineati: BoundedCache[int, bool] = BoundedCache(max_size=500)

    async def cog_load(self) -> None:
        self._controlla_scadenze.start()

    async def _modulo_utilizzabile(self, guild_id: int) -> bool:
        """Modulo attivo nel server e, se è premium, sbloccato."""
        if not await db.is_module_active_for_guild(guild_id, MODULE_ANTI_RAID):
            return False
        return await premium_sbloccato(guild_id, MODULE_ANTI_RAID, self.bot)

    async def cog_unload(self) -> None:
        self._controlla_scadenze.cancel()

    anti_raid_group = app_commands.Group(
        name="anti-raid", description="Configura la protezione anti-raid del server."
    )

    @anti_raid_group.command(name="enable", description="Attiva o disattiva l'Anti-Raid.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @requires_module(MODULE_ANTI_RAID)
    async def enable(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, enabled=enabled))
        await interaction.response.send_message(f"Anti-Raid {'attivato' if enabled else 'disattivato'}.", ephemeral=True)

    @anti_raid_group.command(name="join-rate", description="Configura il limite di join in un intervallo di tempo.")
    @app_commands.describe(max_joins="Numero massimo di join consentiti nella finestra", seconds="Finestra in secondi")
    @app_commands.checks.has_permissions(manage_guild=True)
    @requires_module(MODULE_ANTI_RAID)
    async def join_rate(self, interaction: discord.Interaction, max_joins: int, seconds: int) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(
            _replace(settings, join_rate_max=max_joins, join_rate_window_seconds=seconds)
        )
        await interaction.response.send_message(f"Join rate limit impostato a {max_joins} ogni {seconds}s.", ephemeral=True)

    @anti_raid_group.command(name="account-age", description="Età minima dell'account per non essere considerato sospetto.")
    @app_commands.describe(seconds="Età minima in secondi (es. 86400 = 1 giorno)")
    @app_commands.checks.has_permissions(manage_guild=True)
    @requires_module(MODULE_ANTI_RAID)
    async def account_age(self, interaction: discord.Interaction, seconds: int) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, min_account_age_seconds=seconds))
        await interaction.response.send_message(f"Età minima account impostata a {seconds} secondi.", ephemeral=True)

    @anti_raid_group.command(name="username-check", description="Attiva/disattiva il rilevamento pattern username sospetti.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @requires_module(MODULE_ANTI_RAID)
    async def username_check(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, check_username_pattern=enabled))
        await interaction.response.send_message(f"Rilevamento pattern username {'attivato' if enabled else 'disattivato'}.", ephemeral=True)

    @anti_raid_group.command(name="avatar-check", description="Attiva/disattiva il rilevamento avatar assente.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @requires_module(MODULE_ANTI_RAID)
    async def avatar_check(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, check_avatar_pattern=enabled))
        await interaction.response.send_message(f"Rilevamento avatar assente {'attivato' if enabled else 'disattivato'}.", ephemeral=True)

    @anti_raid_group.command(name="lockdown-action", description="Cosa fare quando un raid viene rilevato.")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Quarantena (ruolo dedicato)", value="quarantine"),
            app_commands.Choice(name="Innalza il livello di verifica del server", value="verification"),
            app_commands.Choice(name="Entrambe", value="both"),
        ]
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @requires_module(MODULE_ANTI_RAID)
    async def lockdown_action(self, interaction: discord.Interaction, action: app_commands.Choice[str]) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, lockdown_action=action.value))
        await interaction.response.send_message(f"Azione di lockdown impostata su **{action.name}**.", ephemeral=True)

    @anti_raid_group.command(name="alert-channel", description="Canale dove ricevere gli alert di sicurezza (Anti-Raid + Anti-Nuke).")
    @app_commands.checks.has_permissions(manage_guild=True)
    @requires_module(MODULE_ANTI_RAID)
    async def alert_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, alert_channel_id=channel.id))
        await interaction.response.send_message(f"Canale di alert impostato su {channel.mention}.", ephemeral=True)

    @anti_raid_group.command(name="status", description="Mostra la configurazione attuale dell'Anti-Raid.")
    @requires_module(MODULE_ANTI_RAID)
    async def status(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        r = settings.anti_raid
        righe = [
            f"**Attivo**: {'sì' if r.enabled else 'no'}",
            f"**Join rate**: max {r.join_rate_max} ogni {r.join_rate_window_seconds}s",
            f"**Età minima account**: {r.min_account_age_seconds}s",
            f"**Controllo username**: {'sì' if r.check_username_pattern else 'no'}",
            f"**Controllo avatar**: {'sì' if r.check_avatar_pattern else 'no'}",
            f"**Azione di lockdown**: {r.lockdown_action}",
        ]
        await interaction.response.send_message("\n".join(righe), ephemeral=True)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        """Un canale creato dopo il ruolo di quarantena riceve lo stesso blocco."""
        guild = channel.guild
        if not await self._modulo_utilizzabile(guild.id):
            return
        settings = await security_repo.get_settings(guild.id)
        if settings.quarantine_role_id is None:
            return
        ruolo = guild.get_role(settings.quarantine_role_id)
        if ruolo is not None:
            await _blocca_canale(channel, ruolo)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        # Un bot entra solo se un amministratore lo invita: non è un
        # ingresso da contare né da mettere in quarantena.
        if member.bot:
            return
        guild = member.guild
        if not await self._modulo_utilizzabile(guild.id):
            return

        settings = await security_repo.get_settings(guild.id)
        if not settings.anti_raid.enabled:
            return

        now = discord.utils.utcnow()
        conteggio = security_rate_tracker.record_and_count(
            guild.id, GUILD_WIDE_KEY, "joins", now, settings.anti_raid.join_rate_window_seconds
        )

        segnali = JoinSignals(
            account_created_at=member.created_at,
            has_avatar=member.avatar is not None,
            username=member.name,
            recent_join_count=conteggio,
        )
        violazioni = evaluate_join(segnali, settings.anti_raid, now)
        # Il blocco scatta solo sulla soglia di ingressi: un singolo
        # ingresso "sospetto" (senza avatar, account nuovo) è normale.
        if not is_raid(violazioni):
            return

        # Chi manda messaggi ai nuovi arrivati (benvenuto privato) sta
        # zitto finché dura il raid.
        segna_raid(guild.id, now)

        azione = settings.anti_raid.lockdown_action
        if azione in ("quarantine", "both"):
            ruolo = await self._ruolo_quarantena(guild)
            if ruolo is not None:
                try:
                    await member.add_roles(ruolo, reason="Anti-Raid: join sospetto")
                except discord.HTTPException:
                    pass

        if azione in ("verification", "both"):
            await self._alza_verifica(guild, now)

        dettaglio = f"{member} — violazioni: {', '.join(violazioni)}"
        await security_repo.log_action(guild.id, "raid_join", member.id, dettaglio)

        await self._avvisa(guild, settings, f"{member.name} ({member.id})"[:MAX_NOME_ELENCATO], now)

    async def _ruolo_quarantena(self, guild: discord.Guild) -> discord.Role | None:
        """
        Il ruolo di quarantena del server, creato se manca. Un blocco
        per server: con più ingressi insieme il primo crea il ruolo,
        gli altri aspettano e lo trovano già salvato.
        """
        blocco = self._blocchi_ruolo.setdefault(guild.id, asyncio.Lock())
        async with blocco:
            settings = await security_repo.get_settings(guild.id)
            ruolo, creato = await _get_or_create_quarantine_role(guild, settings)
            if ruolo is not None and not creato and guild.id not in self._ruoli_allineati:
                # Una volta per server (finché il bot resta acceso): un
                # ruolo che esisteva già può avere canali senza i
                # permessi di quarantena.
                for canale in guild.channels:
                    if _allinea_necessario(canale, ruolo):
                        await _blocca_canale(canale, ruolo)
            if ruolo is not None:
                self._ruoli_allineati.set(guild.id, True)
            return ruolo

    async def _alza_verifica(self, guild: discord.Guild, now: datetime) -> None:
        """
        Porta il livello di verifica al massimo per la durata del
        blocco. Il livello di prima viene salvato PRIMA di cambiarlo,
        così un riavvio a metà non lo fa perdere. Se il raid continua
        si sposta solo la scadenza.
        """
        scadenza = now + timedelta(seconds=DURATA_BLOCCO_SECONDI)
        await security_repo.start_or_extend_lockdown(
            guild.id, guild.verification_level.name, scadenza
        )
        if guild.verification_level == discord.VerificationLevel.highest:
            return
        try:
            await guild.edit(
                verification_level=discord.VerificationLevel.highest,
                reason="Anti-Raid: ondata di join sospetti rilevata",
            )
        except discord.HTTPException:
            await security_repo.end_lockdown(guild.id)

    async def _avvisa(
        self, guild: discord.Guild, settings: SecuritySettings, voce: str, now: datetime
    ) -> None:
        """
        Avviso allo staff. Nel canale degli allarmi c'è UN messaggio
        per episodio, aggiornato a ogni ingresso (conteggio e ultimi
        nomi); il proprietario riceve un solo DM per episodio.
        """
        # Un blocco per server: ingressi simultanei non devono mandare
        # un messaggio ciascuno prima che il primo sia stato salvato.
        blocco = self._blocchi_avviso.setdefault(guild.id, asyncio.Lock())
        async with blocco:
            avviso = self._avvisi.get(guild.id)
            episodio_in_corso = (
                avviso is not None
                and (now - avviso.ultimo_ingresso).total_seconds() <= DURATA_BLOCCO_SECONDI
            )
            if not episodio_in_corso:
                avviso = _Avviso(messaggio=None, ultimo_ingresso=now)
            avviso.ultimo_ingresso = now
            avviso.conteggio += 1
            avviso.recenti.append(voce)
            self._avvisi.set(guild.id, avviso)
            embed = _embed_avviso(avviso)

            if not episodio_in_corso and guild.owner is not None:
                await try_dm(guild.owner, embed)

            canale = (
                guild.get_channel(settings.alert_channel_id)
                if settings.alert_channel_id is not None
                else None
            )
            if not isinstance(canale, discord.TextChannel):
                return
            if avviso.messaggio is not None:
                try:
                    await avviso.messaggio.edit(embed=embed)
                    return
                except discord.HTTPException:
                    avviso.messaggio = None  # cancellato: se ne manda uno nuovo
            try:
                avviso.messaggio = await canale.send(embed=embed)
            except discord.HTTPException:
                pass

    # ================================================================
    # Fine del blocco: il livello di verifica torna quello di prima
    # ================================================================
    @tasks.loop(seconds=60)
    async def _controlla_scadenze(self) -> None:
        try:
            await self.ripristina_blocchi_scaduti(discord.utils.utcnow())
        except Exception:
            # Un'eccezione che esce da qui spegnerebbe il controllo fino
            # al riavvio: si riprova al prossimo minuto.
            logger.exception("Errore nel controllo delle scadenze dei blocchi anti-raid")

    @_controlla_scadenze.before_loop
    async def _prima_del_controllo(self) -> None:
        await attendi_bot_pronto(self.bot)

    async def ripristina_blocchi_scaduti(self, now: datetime) -> None:
        for guild_id, livello_prima in await security_repo.get_expired_lockdowns(now):
            try:
                await self._chiudi_blocco(guild_id, livello_prima)
            except Exception:
                # Un server che dà errore non ferma il giro per gli altri.
                logger.exception("Errore nel chiudere il blocco anti-raid del server %s", guild_id)

    async def _chiudi_blocco(self, guild_id: int, livello_prima: str) -> None:
        # La riga si toglie subito: un ripristino che fallisce non
        # deve essere ritentato ogni minuto per sempre.
        await security_repo.end_lockdown(guild_id)
        azzera(guild_id)
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        # Se lo staff ha già cambiato il livello a mano, vale la sua scelta.
        if guild.verification_level != discord.VerificationLevel.highest:
            return
        if livello_prima == discord.VerificationLevel.highest.name:
            return
        try:
            await guild.edit(
                verification_level=discord.VerificationLevel[livello_prima],
                reason="Anti-Raid: blocco scaduto, livello di verifica ripristinato",
            )
        except (discord.HTTPException, KeyError) as errore:
            logger.warning(
                "Ripristino del livello di verifica fallito nel server %s: %s", guild_id, errore
            )
            settings = await security_repo.get_settings(guild_id)
            embed = discord.Embed(
                title="⚠️ Anti-Raid — livello di verifica da ripristinare a mano",
                description=(
                    "Il blocco anti-raid è scaduto ma non sono riuscito a riportare il "
                    f"livello di verifica del server a **{livello_prima}**. "
                    "Puoi farlo da Impostazioni server → Configurazione di sicurezza."
                ),
                color=discord.Color.orange(),
            )
            await _alert_staff(guild, settings, embed)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_ANTI_RAID,
            display_name="Anti-Raid",
            category="security",
            description="Rilevamento e risposta automatica a ondate di join sospetti.",
            premium_capable=True,
        )
    )
    await bot.add_cog(AntiRaidCog(bot))
