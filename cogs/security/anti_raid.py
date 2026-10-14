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

Quarantena: il ruolo "Quarantined" (core/security_quarantine.py) si crea
quando si attiva il modulo, non durante il raid. Con il "blocco della
quarantena" attivo chi non è fidato non può liberare un membro a mano né
dargli altri ruoli (si usa /security antiraid rilascia, che è la stessa
funzione dell'anti-nuke). Le impostazioni che indeboliscono la difesa
(blocco, rilascio col blocco attivo) le cambia solo chi gestisce:
proprietario ed extra owner.

Funzioni coperte: SPEC §7.1
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.bot_ready import attendi_bot_pronto
from core.bounded_cache import BoundedCache
from core.database import db
from core.premium import PremiumModule, registry, requires_module
from core.repositories.security_repo import SecuritySettings, security_repo
from core.security_access import premium_sbloccato, solo_chi_gestisce
from core.security_audit import resolve_voce
from core.security_logic import (
    NUKE_ACTION_QUARANTINE_HOLD,
    AntiRaidConfig,
    JoinSignals,
    actor_is_trusted,
    evaluate_join,
    is_raid,
)
from core.security_quarantine import (
    blocca_canale,
    problemi_ruoli_del_bot,
    rilascia_utente,
    ruolo_quarantena,
)
from core.security_raid_state import DURATA_RAID_SECONDI, azzera, segna_raid
from core.security_rate_tracker import GUILD_WIDE_KEY, security_rate_tracker
from cogs.moderation._shared import ensure_module_enabled, try_dm

logger = logging.getLogger("iyokai.anti_raid")

MODULE_ANTI_RAID = "anti_raid"

# Il ruolo di quarantena e i suoi permessi stanno in
# core/security_quarantine.py (li usa anche l'anti-nuke, SIC-002).

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


class AntiRaidCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Un blocco per server sull'invio/modifica dell'avviso.
        self._blocchi_avviso: dict[int, asyncio.Lock] = {}
        # Server -> ora dell'ultimo ingresso di raid segnalato.
        self._avvisi: BoundedCache[int, _Avviso] = BoundedCache(max_size=500)
        # Server in cui il ruolo di quarantena è già allineato ai canali.
        self._ruoli_allineati: BoundedCache[int, bool] = BoundedCache(max_size=500)

    async def cog_load(self) -> None:
        self._controlla_scadenze.start()
        await super().cog_load()

    async def _modulo_utilizzabile(self, guild_id: int) -> bool:
        """Modulo attivo nel server e, se è premium, sbloccato."""
        if not await db.is_module_active_for_guild(guild_id, MODULE_ANTI_RAID):
            return False
        return await premium_sbloccato(guild_id, MODULE_ANTI_RAID, self.bot)

    async def cog_unload(self) -> None:
        self._controlla_scadenze.cancel()
        await super().cog_unload()

    @comando_di_gruppo(
        "security",
        nome="enable",
        descrizione="Attiva o disattiva l'Anti-Raid.",
        sottogruppo=("antiraid", "Protezione anti-raid del server."),
    )
    @requires_module(MODULE_ANTI_RAID)
    async def enable(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, enabled=enabled))
        await interaction.response.send_message(
            f"Anti-Raid {'attivato' if enabled else 'disattivato'}.", ephemeral=True
        )
        if not enabled:
            return
        avvisi = []
        if settings.anti_raid.lockdown_action in ("quarantine", "both"):
            # Il ruolo e i permessi sui canali si preparano adesso, non durante il raid.
            if await self._ruolo_quarantena(interaction.guild) is None:
                avvisi.append(
                    "Non sono riuscito a creare il ruolo di quarantena (mi manca Gestire ruoli?): "
                    "durante un raid i nuovi arrivati non verrebbero messi in quarantena."
                )
        # SIC-022: se i ruoli non mi lasciano lavorare, meglio saperlo adesso.
        aggiornate = await security_repo.get_settings(interaction.guild.id)
        avvisi += problemi_ruoli_del_bot(interaction.guild, aggiornate.quarantine_role_id)
        if avvisi:
            await interaction.followup.send("⚠️ " + "\n⚠️ ".join(avvisi), ephemeral=True)

    @comando_di_gruppo(
        "security",
        nome="join-rate",
        descrizione="Configura il limite di join in un intervallo di tempo.",
        sottogruppo=("antiraid", "Protezione anti-raid del server."),
    )
    @app_commands.describe(
        max_joins="Numero massimo di join consentiti nella finestra (da 1 a 1000)",
        seconds="Finestra in secondi (da 1 a 3600)",
    )
    @requires_module(MODULE_ANTI_RAID)
    async def join_rate(
        self,
        interaction: discord.Interaction,
        max_joins: app_commands.Range[int, 1, 1000],
        seconds: app_commands.Range[int, 1, 3600],
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(
            _replace(settings, join_rate_max=max_joins, join_rate_window_seconds=seconds)
        )
        await interaction.response.send_message(f"Join rate limit impostato a {max_joins} ogni {seconds}s.", ephemeral=True)

    @comando_di_gruppo(
        "security",
        nome="account-age",
        descrizione="Età minima dell'account per non essere considerato sospetto.",
        sottogruppo=("antiraid", "Protezione anti-raid del server."),
    )
    @app_commands.describe(seconds="Età minima in secondi (es. 86400 = 1 giorno; 0 = nessun minimo; massimo 1 anno)")
    @requires_module(MODULE_ANTI_RAID)
    async def account_age(
        self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 31_536_000]
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, min_account_age_seconds=seconds))
        await interaction.response.send_message(f"Età minima account impostata a {seconds} secondi.", ephemeral=True)

    @comando_di_gruppo(
        "security",
        nome="username-check",
        descrizione="Attiva/disattiva il rilevamento pattern username sospetti.",
        sottogruppo=("antiraid", "Protezione anti-raid del server."),
    )
    @requires_module(MODULE_ANTI_RAID)
    async def username_check(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, check_username_pattern=enabled))
        await interaction.response.send_message(f"Rilevamento pattern username {'attivato' if enabled else 'disattivato'}.", ephemeral=True)

    @comando_di_gruppo(
        "security",
        nome="avatar-check",
        descrizione="Attiva/disattiva il rilevamento avatar assente.",
        sottogruppo=("antiraid", "Protezione anti-raid del server."),
    )
    @requires_module(MODULE_ANTI_RAID)
    async def avatar_check(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, check_avatar_pattern=enabled))
        await interaction.response.send_message(f"Rilevamento avatar assente {'attivato' if enabled else 'disattivato'}.", ephemeral=True)

    @comando_di_gruppo(
        "security",
        nome="lockdown-action",
        descrizione="Cosa fare quando un raid viene rilevato.",
        sottogruppo=("antiraid", "Protezione anti-raid del server."),
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Quarantena (ruolo dedicato)", value="quarantine"),
            app_commands.Choice(name="Innalza il livello di verifica del server", value="verification"),
            app_commands.Choice(name="Entrambe", value="both"),
        ]
    )
    @requires_module(MODULE_ANTI_RAID)
    async def lockdown_action(self, interaction: discord.Interaction, action: app_commands.Choice[str]) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, lockdown_action=action.value))
        await interaction.response.send_message(f"Azione di lockdown impostata su **{action.name}**.", ephemeral=True)

    @comando_di_gruppo(
        "security",
        nome="alert-channel",
        descrizione="Canale dove ricevere gli alert di sicurezza (Anti-Raid + Anti-Nuke).",
        sottogruppo=("antiraid", "Protezione anti-raid del server."),
    )
    @requires_module(MODULE_ANTI_RAID)
    async def alert_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, alert_channel_id=channel.id))
        await interaction.response.send_message(f"Canale di alert impostato su {channel.mention}.", ephemeral=True)

    @comando_di_gruppo(
        "security",
        nome="status",
        descrizione="Mostra la configurazione attuale dell'Anti-Raid.",
        sottogruppo=("antiraid", "Protezione anti-raid del server."),
    )
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
            f"**Blocco della quarantena**: {'sì' if r.quarantine_hold else 'no'}",
            f"**Canale degli allarmi**: {f'<#{settings.alert_channel_id}>' if settings.alert_channel_id else 'nessuno (solo DM al proprietario)'}",
            f"**Ruolo di quarantena**: {f'<@&{settings.quarantine_role_id}>' if settings.quarantine_role_id else 'non ancora creato'}",
        ]
        problemi = problemi_ruoli_del_bot(interaction.guild, settings.quarantine_role_id)
        righe += [f"⚠️ {p}" for p in problemi]
        await interaction.response.send_message("\n".join(righe), ephemeral=True)

    @comando_di_gruppo(
        "security",
        nome="quarantine-hold",
        descrizione="Impedisce a chi non è fidato di togliere la quarantena a mano.",
        sottogruppo=("antiraid", "Protezione anti-raid del server."),
    )
    @app_commands.describe(
        enabled="Se attivo, togliere la quarantena a mano viene annullato: usa /security antiraid rilascia"
    )
    @requires_module(MODULE_ANTI_RAID)
    async def quarantine_hold(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        if not await solo_chi_gestisce(interaction, settings.anti_nuke):
            return
        await security_repo.save_settings(_replace(settings, quarantine_hold=enabled))
        await interaction.response.send_message(
            f"Blocco della quarantena {'attivato' if enabled else 'disattivato'}.", ephemeral=True
        )

    @comando_di_gruppo(
        "security",
        nome="rilascia",
        descrizione="Toglie la quarantena a un membro (il modo giusto, col blocco attivo).",
        sottogruppo=("antiraid", "Protezione anti-raid del server."),
    )
    @app_commands.describe(membro="Il membro da liberare dalla quarantena")
    @requires_module(MODULE_ANTI_RAID)
    async def rilascia(self, interaction: discord.Interaction, membro: discord.Member) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        # Col blocco attivo la quarantena si toglie solo da chi gestisce.
        if settings.anti_raid.quarantine_hold and not await solo_chi_gestisce(interaction, settings.anti_nuke):
            return
        ruolo = (
            interaction.guild.get_role(settings.quarantine_role_id)
            if settings.quarantine_role_id is not None else None
        )
        if ruolo is None or ruolo not in membro.roles:
            await interaction.response.send_message(
                f"{membro.mention} non è in quarantena.", ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        await interaction.response.defer(ephemeral=True)
        esito = await rilascia_utente(
            membro, caso_numero=None, reason=f"Anti-Raid: quarantena tolta da {interaction.user}"
        )
        if not esito.riuscito:
            await interaction.followup.send(
                "Discord non mi ha lasciato togliere il ruolo (il mio ruolo è più in basso?).", ephemeral=True
            )
            return
        await security_repo.log_action(
            interaction.guild.id, "raid_release", membro.id, f"rilasciato da {interaction.user.id}"
        )
        if esito.quarantena_tenuta:
            altri = ", ".join(f"#{n}" for n in esito.altri_casi)
            testo = (
                f"{membro.mention} resta in quarantena: ha casi anti-nuke attivi ({altri}). "
                "Si rilasciano con /antinuke rilascia."
            )
        else:
            testo = f"{membro.mention} è fuori dalla quarantena."
        await interaction.followup.send(
            testo, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        """
        SIC-004: il ruolo di quarantena resta senza permessi. Un permesso
        dato a mano (anche per sbaglio) ridarebbe poteri a chi è in quarantena.
        """
        if after.permissions.value == 0:
            return
        guild = after.guild
        if not await self._modulo_utilizzabile(guild.id):
            return
        settings = await security_repo.get_settings(guild.id)
        if settings.quarantine_role_id != after.id:
            return
        try:
            await after.edit(
                permissions=discord.Permissions.none(),
                reason="Anti-Raid: il ruolo di quarantena non può avere permessi",
            )
        except discord.HTTPException:
            logger.warning("Impossibile azzerare i permessi del ruolo di quarantena (server %s).", guild.id)
            return
        await security_repo.log_action(guild.id, "raid_quarantine_perms", None, f"permessi tolti a {after.name}")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """
        SIC-003: chi è in quarantena ci resta. Se qualcuno non fidato gli
        toglie il ruolo, o gli dà altri ruoli, il bot rimette le cose a
        posto e avvisa.
        """
        guild = after.guild
        prima = {r.id for r in before.roles}
        dopo = {r.id for r in after.roles}
        if prima == dopo:
            return
        if not await self._modulo_utilizzabile(guild.id):
            return
        settings = await security_repo.get_settings(guild.id)
        qid = settings.quarantine_role_id
        if not settings.anti_raid.quarantine_hold or qid is None:
            return
        tolta = qid in prima and qid not in dopo
        ruoli_dati = [r for r in after.roles if r.id not in prima and r.id != qid and not r.is_default()]
        if not tolta and not (qid in dopo and ruoli_dati):
            return
        voce = await resolve_voce(guild, discord.AuditLogAction.member_role_update, after.id)
        if voce is None:
            return
        autore = voce[0]
        if autore == self.bot.user.id or autore == guild.owner_id:
            return
        if actor_is_trusted(autore, NUKE_ACTION_QUARANTINE_HOLD, settings.anti_nuke):
            return
        ruolo = guild.get_role(qid)
        if ruolo is None:
            return
        try:
            if tolta:
                await after.add_roles(ruolo, reason=f"Anti-Raid: quarantena tolta a mano da {autore}"[:512])
                esito = "quarantena rimessa"
            else:
                await after.remove_roles(*ruoli_dati, reason=f"Anti-Raid: ruoli dati a un membro in quarantena da {autore}"[:512])
                esito = "ruoli tolti"
        except discord.HTTPException:
            esito = "annullamento fallito (il mio ruolo è più in basso?)"
        dettaglio = f"{after} ({after.id}) in quarantena: modificato da {autore} — {esito}"
        await security_repo.log_action(guild.id, "raid_quarantine_hold", autore, dettaglio)
        embed = discord.Embed(
            title="🛡️ Anti-Raid — quarantena", description=dettaglio[:4096], color=discord.Color.orange()
        )
        embed.set_footer(text="Per liberare un membro: /security antiraid rilascia")
        await _alert_staff(guild, settings, embed)

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
            await blocca_canale(channel, ruolo)

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
        non_in_quarantena = False
        if azione in ("quarantine", "both"):
            ruolo = await self._ruolo_quarantena(guild)
            if ruolo is None:
                non_in_quarantena = True
            else:
                try:
                    await member.add_roles(ruolo, reason="Anti-Raid: join sospetto")
                except discord.HTTPException:
                    # Il raid c'è comunque: si dice nell'avviso che la quarantena non è partita.
                    logger.warning("Quarantena non assegnata a %s (server %s).", member.id, guild.id)
                    non_in_quarantena = True

        if azione in ("verification", "both"):
            await self._alza_verifica(guild, now)

        dettaglio = f"{member} — violazioni: {', '.join(violazioni)}"
        await security_repo.log_action(guild.id, "raid_join", member.id, dettaglio)

        voce = f"{member.name} ({member.id})"[:MAX_NOME_ELENCATO - 20]
        if non_in_quarantena:
            voce += " ⚠ senza quarantena"
        await self._avvisa(guild, settings, voce, now)

    async def _ruolo_quarantena(self, guild: discord.Guild) -> discord.Role | None:
        """
        Il ruolo di quarantena del server, creato se manca (un blocco per
        server). L'allineamento dei canali a un ruolo trovato si fa una
        volta per server finché il bot resta acceso.
        """
        ruolo = await ruolo_quarantena(guild, allinea=guild.id not in self._ruoli_allineati)
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
