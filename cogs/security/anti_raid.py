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
dargli altri ruoli (si usa /antiraid rilascia, che è la stessa
funzione dell'anti-nuke). Le impostazioni che indeboliscono la difesa
(blocco, rilascio col blocco attivo) le cambia solo chi gestisce:
proprietario ed extra owner.

Filtri all'ingresso (SIC-023…028): età dell'account, bot non verificati,
nomi pubblicitari, nomi vietati; ognuno con la sua azione (quarantena,
timeout, kick, ban) e attivi anche fuori da un raid. Il bio del profilo non è
leggibile dai bot: il filtro pubblicitario guarda nome utente e nome
visualizzato. Segnali di raid in più: account creati vicini e nomi simili
tra gli ultimi ingressi (SIC-030/031), soglia contata solo sui sospetti
(SIC-029). Al raid: kick o ban (SIC-032), anche di chi è entrato poco prima
(SIC-033), ping dei ruoli dello staff (SIC-034), elenco completo con
/antiraid elenco (SIC-035), segnale di rete tra server (SIC-037) e
segnalazione a chi gestisce il bot con /antiraid segnala (SIC-038).

Livelli di allerta con nome (`/antiraid livello`, SIC-036): normale, allerta, alto,
blocco stringono le regole attive, a mano (con una durata) o da soli all'inizio di un raid.
Funzioni coperte: SPEC §7.1 (SIC-023…038)
"""

from __future__ import annotations

import asyncio
import dataclasses
import io
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core import bot_roles
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.bot_ready import attendi_bot_pronto
from core.bounded_cache import BoundedCache
from core.database import db
from core.lockdown_service import panico_automatico
from core.premium import PremiumModule, registry, requires_module
from core.repositories.security_repo import SecuritySettings, security_repo
from core.security_access import premium_sbloccato, solo_chi_gestisce
from core.security_audit import resolve_voce
from core.invio_file import invia_file_su_interazione
from core.security_join_logic import (
    AZIONE_NIENTE,
    FILTRO_BOT_NON_VERIFICATO,
    FILTRO_ETA,
    FILTRO_NOME_PUBBLICITARIO,
    FILTRO_NOME_VIETATO,
    MAX_MESSAGGIO_DM,
    MAX_NOMI_VIETATI,
    MAX_SCHEMA,
    SERVER_RETE_MINIMI,
    Ingresso,
    account_vicini,
    azione_piu_forte,
    elenco_testo,
    ingresso_in_rete,
    nome_pubblicitario,
    nome_vietato,
    nomi_simili,
    pulisci_schema,
    registra_ingresso,
    riga_elenco,
    ultimi_ingressi,
)
from core.security_logic import (
    JOIN_VIOLATION_ACCOUNT_AGE,
    JOIN_VIOLATION_ACCOUNT_VICINI,
    JOIN_VIOLATION_AVATAR,
    JOIN_VIOLATION_NOMI_SIMILI,
    JOIN_VIOLATION_USERNAME,
    NUKE_ACTION_QUARANTINE_HOLD,
    AntiRaidConfig,
    LIVELLI_ALLERTA,
    JoinSignals,
    actor_is_trusted,
    config_con_livello,
    livello_attivo,
    evaluate_join,
    is_account_too_new,
    is_raid,
)
from core.security_quarantine import (
    blocca_canale,
    problemi_ruoli_del_bot,
    rilascia_utente,
    ruolo_quarantena,
)
from core.security_raid_state import DURATA_RAID_SECONDI, azzera, raid_in_corso, segna_raid
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

# Timeout dato da un filtro all'ingresso o dal raid.
DURATA_TIMEOUT_FILTRO = timedelta(days=1)
# Pausa tra un'azione e l'altra sugli ingressi già fatti (SIC-033).
PAUSA_AZIONI_SECONDI = 0.3
# Ban al raid: si cancellano i messaggi dell'ultima ora.
SECONDI_MESSAGGI_BAN = 3600
MAX_RUOLI_PING = 3
_SOSPETTI = frozenset({JOIN_VIOLATION_ACCOUNT_AGE, JOIN_VIOLATION_USERNAME, JOIN_VIOLATION_AVATAR})
_SCELTE_AZIONE_FILTRO = [
    app_commands.Choice(name="Niente (filtro spento)", value="niente"),
    app_commands.Choice(name="Quarantena", value="quarantena"),
    app_commands.Choice(name="Timeout di un giorno", value="timeout"),
    app_commands.Choice(name="Kick", value="kick"),
    app_commands.Choice(name="Ban", value="ban"),
]
_CAMPO_FILTRO = {
    FILTRO_ETA: "azione_eta",
    FILTRO_BOT_NON_VERIFICATO: "azione_bot_non_verificato",
    FILTRO_NOME_PUBBLICITARIO: "azione_nome_pubblicitario",
    FILTRO_NOME_VIETATO: "azione_nome_vietato",
}


@dataclass
class _Avviso:
    """L'avviso dell'episodio in corso: un solo messaggio, aggiornato."""

    messaggio: discord.Message | None
    ultimo_ingresso: datetime
    conteggio: int = 0
    recenti: deque = field(default_factory=lambda: deque(maxlen=MAX_INGRESSI_ELENCATI))


def _embed_avviso(avviso: _Avviso) -> discord.Embed:
    righe = "\n".join(f"• {voce}" for voce in avviso.recenti)
    embed = discord.Embed(
        title=f"🚨 Anti-Raid — {avviso.conteggio} join sospetti",
        description=f"Ultimi ingressi (dal più vecchio):\n{righe}"[:4096],
        color=discord.Color.red(),
    )
    embed.set_footer(text="Elenco completo: /antiraid elenco")
    return embed


def guild_nome(member: discord.Member) -> str:
    return getattr(member.guild, "name", "server")


def _nomi(member: discord.Member) -> tuple:
    return (member.name, getattr(member, "global_name", None), member.display_name)


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
                await bot_roles.scrivi(canale, embed=embed)
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
        "antiraid",
        nome="enable",
        descrizione="Attiva o disattiva l'Anti-Raid.",
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
        "antiraid",
        nome="join-rate",
        descrizione="Configura il limite di join in un intervallo di tempo.",
    )
    @app_commands.describe(
        max_joins="Numero massimo di join consentiti nella finestra (da 1 a 1000)",
        seconds="Finestra in secondi (da 1 a 3600)",
        conta="Quali ingressi contare (vuoto: non cambia)",
    )
    @app_commands.choices(
        conta=[
            app_commands.Choice(name="Tutti gli ingressi", value="tutti"),
            app_commands.Choice(name="Solo gli account sospetti", value="sospetti"),
        ]
    )
    @requires_module(MODULE_ANTI_RAID)
    async def join_rate(
        self,
        interaction: discord.Interaction,
        max_joins: app_commands.Range[int, 1, 1000],
        seconds: app_commands.Range[int, 1, 3600],
        conta: app_commands.Choice[str] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        cambi = {"join_rate_max": max_joins, "join_rate_window_seconds": seconds}
        if conta is not None:
            cambi["conta_solo_sospetti"] = conta.value == "sospetti"
        nuove = _replace(settings, **cambi)
        await security_repo.save_settings(nuove)
        chi = "account sospetti" if nuove.anti_raid.conta_solo_sospetti else "ingressi"
        await interaction.response.send_message(
            f"Raid se entrano più di {max_joins} {chi} ogni {seconds}s.", ephemeral=True
        )

    @comando_di_gruppo(
        "antiraid",
        nome="account-age",
        descrizione="Età minima dell'account per non essere considerato sospetto.",
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
        "antiraid",
        nome="username-check",
        descrizione="Attiva/disattiva il rilevamento pattern username sospetti.",
    )
    @requires_module(MODULE_ANTI_RAID)
    async def username_check(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, check_username_pattern=enabled))
        await interaction.response.send_message(f"Rilevamento pattern username {'attivato' if enabled else 'disattivato'}.", ephemeral=True)

    @comando_di_gruppo(
        "antiraid",
        nome="avatar-check",
        descrizione="Attiva/disattiva il rilevamento avatar assente.",
    )
    @requires_module(MODULE_ANTI_RAID)
    async def avatar_check(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, check_avatar_pattern=enabled))
        await interaction.response.send_message(f"Rilevamento avatar assente {'attivato' if enabled else 'disattivato'}.", ephemeral=True)

    @comando_di_gruppo(
        "antiraid",
        nome="lockdown-action",
        descrizione="Cosa fare quando un raid viene rilevato.",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Quarantena (ruolo dedicato)", value="quarantine"),
            app_commands.Choice(name="Innalza il livello di verifica del server", value="verification"),
            app_commands.Choice(name="Entrambe", value="both"),
            app_commands.Choice(name="Kick degli account del raid", value="kick"),
            app_commands.Choice(name="Ban degli account del raid", value="ban"),
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
        "antiraid",
        nome="alert-channel",
        descrizione="Canale dove ricevere gli alert di sicurezza (Anti-Raid + Anti-Nuke).",
    )
    @requires_module(MODULE_ANTI_RAID)
    async def alert_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, alert_channel_id=channel.id))
        await interaction.response.send_message(f"Canale di alert impostato su {channel.mention}.", ephemeral=True)

    @comando_di_gruppo(
        "antiraid",
        nome="status",
        descrizione="Mostra la configurazione attuale dell'Anti-Raid.",
    )
    @requires_module(MODULE_ANTI_RAID)
    async def status(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        r = settings.anti_raid
        righe = [
            f"**Attivo**: {'sì' if r.enabled else 'no'}",
            f"**Livello di allerta**: {livello_attivo(r, discord.utils.utcnow().timestamp())}",
            f"**Join rate**: max {r.join_rate_max} ogni {r.join_rate_window_seconds}s",
            f"**Età minima account**: {r.min_account_age_seconds}s",
            f"**Controllo username**: {'sì' if r.check_username_pattern else 'no'}",
            f"**Controllo avatar**: {'sì' if r.check_avatar_pattern else 'no'}",
            f"**Azione di lockdown**: {r.lockdown_action}",
            f"**Blocco della quarantena**: {'sì' if r.quarantine_hold else 'no'}",
            f"**Filtri all'ingresso**: età {r.azione_eta}, bot non verificati {r.azione_bot_non_verificato}, "
            f"nomi pubblicitari {r.azione_nome_pubblicitario}, nomi vietati {r.azione_nome_vietato} "
            f"({len(r.nomi_vietati)} schemi)",
            f"**Soglia contata su**: {'solo account sospetti' if r.conta_solo_sospetti else 'tutti gli ingressi'}",
            f"**Account creati vicini**: {r.account_vicini_minimo or 'spento'} "
            f"(margine {r.account_vicini_margine_secondi // 60} min) · **Nomi simili**: {r.nomi_simili_minimo or 'spento'}",
            f"**Azione anche su chi è entrato prima**: {'sì' if r.retroattivo else 'no'}",
            f"**Ruoli avvisati**: {' '.join(f'<@&{i}>' for i in r.ruoli_ping) or 'nessuno'}",
            f"**Canale degli allarmi**: {f'<#{settings.alert_channel_id}>' if settings.alert_channel_id else 'nessuno (solo DM al proprietario)'}",
            f"**Ruolo di quarantena**: {f'<@&{settings.quarantine_role_id}>' if settings.quarantine_role_id else 'non ancora creato'}",
        ]
        problemi = problemi_ruoli_del_bot(interaction.guild, settings.quarantine_role_id)
        righe += [f"⚠️ {p}" for p in problemi]
        await interaction.response.send_message("\n".join(righe), ephemeral=True)

    @staticmethod
    async def _livello_al_raid(settings: SecuritySettings, livello_in_corso: str, now: datetime) -> None:
        """SIC-036: all'inizio di un raid scatta il livello scelto dal server, se è più alto di quello in corso."""
        r = settings.anti_raid
        if r.livello_al_raid not in LIVELLI_ALLERTA[1:]:
            return
        if LIVELLI_ALLERTA.index(r.livello_al_raid) <= LIVELLI_ALLERTA.index(livello_in_corso):
            return
        fino = int(now.timestamp()) + r.livello_al_raid_ore * 3600
        await security_repo.save_settings(_replace(settings, livello=r.livello_al_raid, livello_fino=fino))

    @comando_di_gruppo(
        "antiraid",
        nome="livello",
        descrizione="Livelli di allerta: normale, allerta, alto, blocco.",
    )
    @app_commands.describe(
        nome="Livello da attivare adesso (vuoto: non cambia)",
        ore="Per quante ore (vuoto: fino al prossimo cambio)",
        al_raid="Livello che scatta da solo quando comincia un raid (vuoto: non cambia)",
    )
    @app_commands.choices(
        nome=[app_commands.Choice(name=n.capitalize(), value=n) for n in LIVELLI_ALLERTA],
        al_raid=[app_commands.Choice(name="Nessuno", value="niente")]
        + [app_commands.Choice(name=n.capitalize(), value=n) for n in LIVELLI_ALLERTA[1:]],
    )
    @requires_module(MODULE_ANTI_RAID)
    async def livello(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Choice[str] | None = None,
        ore: app_commands.Range[int, 1, 168] | None = None,
        al_raid: app_commands.Choice[str] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        if not await solo_chi_gestisce(interaction, settings.anti_nuke):
            return
        cambi: dict = {}
        if nome is not None:
            fino = 0
            if ore is not None and nome.value != "normale":
                fino = int(discord.utils.utcnow().timestamp()) + ore * 3600
            cambi.update(livello=nome.value, livello_fino=fino)
        if al_raid is not None:
            cambi["livello_al_raid"] = al_raid.value
            if ore is not None and nome is None:
                cambi["livello_al_raid_ore"] = ore
        if cambi:
            await security_repo.save_settings(_replace(settings, **cambi))
        r = (await security_repo.get_settings(interaction.guild.id)).anti_raid
        attivo = livello_attivo(r, discord.utils.utcnow().timestamp())
        durata = f" fino a <t:{r.livello_fino}:f>" if r.livello_fino and attivo != "normale" else ""
        automatico = (
            f"da solo a inizio raid: **{r.livello_al_raid}** per {r.livello_al_raid_ore} ore"
            if r.livello_al_raid != "niente"
            else "da solo a inizio raid: nessuno"
        )
        await interaction.response.send_message(f"Livello: **{attivo}**{durata}. {automatico.capitalize()}.", ephemeral=True)

    @comando_di_gruppo(
        "antiraid",
        nome="quarantine-hold",
        descrizione="Impedisce a chi non è fidato di togliere la quarantena a mano.",
    )
    @app_commands.describe(
        enabled="Se attivo, togliere la quarantena a mano viene annullato: usa /antiraid rilascia"
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
        "antiraid",
        nome="rilascia",
        descrizione="Toglie la quarantena a un membro (il modo giusto, col blocco attivo).",
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

    # ================================================================
    # Filtri all'ingresso e segnali di raid (SIC-023…035, 038)
    # ================================================================
    @comando_di_gruppo(
        "antiraid",
        nome="filtro-ingresso",
        descrizione="Azione per un filtro all'ingresso (vale anche fuori da un raid).",
    )
    @app_commands.describe(
        filtro="Il filtro da regolare",
        azione="Cosa fare a chi non lo passa",
        messaggio_dm="Solo età: messaggio privato che spiega il requisito, mandato prima dell'azione",
    )
    @app_commands.choices(
        filtro=[
            app_commands.Choice(name="Account troppo giovane", value=FILTRO_ETA),
            app_commands.Choice(name="Bot non verificato da Discord", value=FILTRO_BOT_NON_VERIFICATO),
            app_commands.Choice(name="Invito Discord nel nome", value=FILTRO_NOME_PUBBLICITARIO),
            app_commands.Choice(name="Nome nella lista dei vietati", value=FILTRO_NOME_VIETATO),
        ],
        azione=_SCELTE_AZIONE_FILTRO,
    )
    @requires_module(MODULE_ANTI_RAID)
    async def filtro_ingresso(
        self,
        interaction: discord.Interaction,
        filtro: app_commands.Choice[str],
        azione: app_commands.Choice[str],
        messaggio_dm: app_commands.Range[str, 0, MAX_MESSAGGIO_DM] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        cambi = {_CAMPO_FILTRO[filtro.value]: azione.value}
        if messaggio_dm is not None and filtro.value == FILTRO_ETA:
            cambi["messaggio_eta"] = messaggio_dm.strip()
        await security_repo.save_settings(_replace(settings, **cambi))
        testo = f"Filtro **{filtro.name}**: {azione.name.lower()}."
        if filtro.value == FILTRO_NOME_VIETATO and not settings.anti_raid.nomi_vietati:
            testo += " La lista è vuota: aggiungi gli schemi con /antiraid nomi-vietati."
        if filtro.value == FILTRO_ETA:
            testo += f" Età minima: {settings.anti_raid.min_account_age_seconds} secondi (/antiraid account-age)."
        await interaction.response.send_message(testo, ephemeral=True)

    @comando_di_gruppo(
        "antiraid",
        nome="nomi-vietati",
        descrizione="Lista di parole o schemi (con *) vietati nei nomi di chi entra.",
    )
    @app_commands.describe(operazione="Cosa fare sulla lista", schema="Parola o schema con * (es. *free*nitro*)")
    @app_commands.choices(
        operazione=[
            app_commands.Choice(name="Aggiungi", value="aggiungi"),
            app_commands.Choice(name="Togli", value="togli"),
            app_commands.Choice(name="Mostra", value="mostra"),
            app_commands.Choice(name="Svuota", value="svuota"),
        ]
    )
    @requires_module(MODULE_ANTI_RAID)
    async def nomi_vietati(
        self,
        interaction: discord.Interaction,
        operazione: app_commands.Choice[str],
        schema: app_commands.Range[str, 1, MAX_SCHEMA] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        lista = list(settings.anti_raid.nomi_vietati)
        voce = pulisci_schema(schema or "")
        if operazione.value == "mostra":
            testo = ", ".join(f"`{v}`" for v in lista) or "La lista è vuota."
            await interaction.response.send_message(testo[:1900], ephemeral=True)
            return
        if operazione.value == "svuota":
            lista = []
        elif not voce:
            await interaction.response.send_message("Scrivi lo schema.", ephemeral=True)
            return
        elif operazione.value == "aggiungi":
            if voce in lista:
                await interaction.response.send_message(f"`{voce}` è già nella lista.", ephemeral=True)
                return
            if len(lista) >= MAX_NOMI_VIETATI:
                await interaction.response.send_message(
                    f"La lista è piena ({MAX_NOMI_VIETATI} schemi): togline uno.", ephemeral=True
                )
                return
            lista.append(voce)
        elif voce in lista:
            lista.remove(voce)
        else:
            await interaction.response.send_message(f"`{voce}` non è nella lista.", ephemeral=True)
            return
        await security_repo.save_settings(_replace(settings, nomi_vietati=tuple(lista)))
        await interaction.response.send_message(f"Lista aggiornata: {len(lista)} schemi.", ephemeral=True)

    @comando_di_gruppo(
        "antiraid",
        nome="segnali",
        descrizione="Segnali di raid sugli ultimi ingressi e azione su chi è entrato prima.",
    )
    @app_commands.describe(
        account_vicini="Raid se tanti account nella finestra sono creati vicini (0 = spento)",
        margine_minuti="Quanto vicini, in minuti, devono essere creati gli account",
        nomi_simili="Raid se tanti ingressi nella finestra hanno nomi simili (0 = spento)",
        retroattivo="Al raid agisce anche su chi è entrato nella finestra prima della soglia",
    )
    @requires_module(MODULE_ANTI_RAID)
    async def segnali(
        self,
        interaction: discord.Interaction,
        account_vicini: app_commands.Range[int, 0, 50] | None = None,
        margine_minuti: app_commands.Range[int, 1, 1440] | None = None,
        nomi_simili: app_commands.Range[int, 0, 50] | None = None,
        retroattivo: bool | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        cambi = {}
        if account_vicini is not None:
            cambi["account_vicini_minimo"] = 0 if account_vicini == 1 else account_vicini
        if margine_minuti is not None:
            cambi["account_vicini_margine_secondi"] = margine_minuti * 60
        if nomi_simili is not None:
            cambi["nomi_simili_minimo"] = 0 if nomi_simili == 1 else nomi_simili
        if retroattivo is not None:
            cambi["retroattivo"] = retroattivo
        r = _replace(settings, **cambi).anti_raid
        await security_repo.save_settings(_replace(settings, **cambi))
        await interaction.response.send_message(
            f"Account creati vicini: {r.account_vicini_minimo or 'spento'} "
            f"(entro {r.account_vicini_margine_secondi // 60} minuti). "
            f"Nomi simili: {r.nomi_simili_minimo or 'spento'}. "
            f"Azione su chi è entrato prima: {'sì' if r.retroattivo else 'no'}.",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "antiraid",
        nome="ping-ruoli",
        descrizione="Ruoli dello staff pingati al primo allarme di un raid (vuoto: nessuno).",
    )
    @app_commands.describe(ruolo_1="Primo ruolo", ruolo_2="Secondo ruolo", ruolo_3="Terzo ruolo")
    @requires_module(MODULE_ANTI_RAID)
    async def ping_ruoli(
        self,
        interaction: discord.Interaction,
        ruolo_1: discord.Role | None = None,
        ruolo_2: discord.Role | None = None,
        ruolo_3: discord.Role | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        ruoli = tuple(dict.fromkeys(r.id for r in (ruolo_1, ruolo_2, ruolo_3) if r is not None))
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, ruoli_ping=ruoli[:MAX_RUOLI_PING]))
        testo = " ".join(f"<@&{i}>" for i in ruoli) or "nessuno"
        await interaction.response.send_message(
            f"Ruoli avvisati al raid: {testo}.", ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )

    @comando_di_gruppo(
        "antiraid",
        nome="elenco",
        descrizione="File con tutti gli account dei raid nelle ultime ore.",
    )
    @app_commands.describe(ore="Quante ore indietro guardare (da 1 a 168)")
    @requires_module(MODULE_ANTI_RAID)
    async def elenco(self, interaction: discord.Interaction, ore: app_commands.Range[int, 1, 168] = 24) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        dal = discord.utils.utcnow() - timedelta(hours=ore)
        righe = [
            f"{r['actor_id']}\t{r['created_at']:%Y-%m-%d %H:%M:%S} UTC\t{r['detail'] or ''}"
            for r in await security_repo.raid_joins(interaction.guild.id, dal)
        ]
        if not righe:
            await interaction.response.send_message(f"Nessun account di raid nelle ultime {ore} ore.", ephemeral=True)
            return
        await invia_file_su_interazione(
            interaction,
            elenco_testo(righe).encode(),
            f"raid-{interaction.guild.id}.txt",
            contenuto=f"{len(righe)} account di raid nelle ultime {ore} ore.",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "antiraid",
        nome="segnala",
        descrizione="Segnala a chi gestisce il bot un raid che non è stato riconosciuto.",
    )
    @app_commands.describe(nota="Cosa è successo (facoltativo)")
    @requires_module(MODULE_ANTI_RAID)
    async def segnala(
        self, interaction: discord.Interaction, nota: app_commands.Range[str, 0, 500] | None = None
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_RAID):
            return
        from core.config import config

        await interaction.response.defer(ephemeral=True)
        ingressi = ultimi_ingressi(interaction.guild.id)
        righe = [riga_elenco(i.member_id, i.nome, i.creato, i.entrato) for i in ingressi]
        testo = (
            f"Raid segnalato dal server {interaction.guild.name} ({interaction.guild.id}) "
            f"da {interaction.user} ({interaction.user.id}). {len(righe)} ingressi recenti in memoria."
            + (f"\nNota: {nota}" if nota else "")
        )
        try:
            gestore = await self.bot.fetch_user(config.OWNER_ID)
            await gestore.send(
                testo[:2000],
                file=discord.File(io.BytesIO(elenco_testo(righe).encode()), filename=f"segnalazione-{interaction.guild.id}.txt"),
            )
        except discord.HTTPException:
            await interaction.followup.send("Non sono riuscito a mandare la segnalazione: riprova più tardi.", ephemeral=True)
            return
        await security_repo.log_action(interaction.guild.id, "raid_segnalato", interaction.user.id, (nota or "")[:500])
        await interaction.followup.send(
            f"Segnalazione mandata con {len(righe)} ingressi recenti. Grazie!", ephemeral=True
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
        if bot_roles.e_un_nostro_bot(autore, self.bot) or autore == guild.owner_id:
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
        embed.set_footer(text="Per liberare un membro: /antiraid rilascia")
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
        guild = member.guild
        if not await self._modulo_utilizzabile(guild.id):
            return

        settings = await security_repo.get_settings(guild.id)
        r = settings.anti_raid
        if not r.enabled:
            return

        now = discord.utils.utcnow()
        # SIC-036: il livello di allerta in vigore stringe le regole di questo ingresso.
        settings_base = settings
        livello = livello_attivo(r, now.timestamp())
        if livello != "normale":
            r = config_con_livello(r, livello)
            settings = dataclasses.replace(settings, anti_raid=r)
        # SIC-023: i filtri all'ingresso valgono anche fuori da un raid (e per i bot, SIC-026).
        if await self._filtri_ingresso(member, settings, now):
            return
        # Un bot entra solo se un amministratore lo invita: non è un
        # ingresso da contare né da mettere in quarantena.
        if member.bot:
            return

        # SIC-037: lo stesso account entra in molti server in pochi minuti.
        if ingresso_in_rete(member.id, guild.id, now) == SERVER_RETE_MINIMI:
            await self._avviso_rete(guild, settings, member)

        base = JoinSignals(
            account_created_at=member.created_at,
            has_avatar=member.avatar is not None,
            username=member.name,
            recent_join_count=0,
        )
        sospetto = bool(_SOSPETTI & set(evaluate_join(base, r, now)))
        finestra = r.join_rate_window_seconds
        if r.conta_solo_sospetti and not sospetto:
            conteggio = 0  # SIC-029: un ingresso normale non conta per la soglia
        else:
            categoria = "joins_sospetti" if r.conta_solo_sospetti else "joins"
            conteggio = security_rate_tracker.record_and_count(guild.id, GUILD_WIDE_KEY, categoria, now, finestra)

        registra_ingresso(guild.id, Ingresso(member.id, member.name, member.created_at, now, sospetto))
        recenti = ultimi_ingressi(guild.id, dal=now - timedelta(seconds=finestra))
        violazioni = list(evaluate_join(
            JoinSignals(member.created_at, member.avatar is not None, member.name, conteggio), r, now
        ))
        if r.account_vicini_minimo >= 2 and account_vicini(
            recenti, member.created_at, r.account_vicini_margine_secondi
        ) >= r.account_vicini_minimo:
            violazioni.append(JOIN_VIOLATION_ACCOUNT_VICINI)
        if r.nomi_simili_minimo >= 2 and nomi_simili(recenti, member.name) >= r.nomi_simili_minimo:
            violazioni.append(JOIN_VIOLATION_NOMI_SIMILI)
        # Il blocco scatta solo sui segnali di gruppo: un singolo
        # ingresso "sospetto" (senza avatar, account nuovo) è normale.
        if not is_raid(tuple(violazioni)):
            return

        primo_del_raid = not raid_in_corso(guild.id, now)
        if primo_del_raid:
            await self._livello_al_raid(settings_base, livello, now)
        # Chi manda messaggi ai nuovi arrivati (benvenuto privato) sta
        # zitto finché dura il raid.
        segna_raid(guild.id, now)

        azione = r.lockdown_action
        riuscita = await self._azione_raid(guild, member, azione)

        if azione in ("verification", "both"):
            await self._alza_verifica(guild, now)

        dettaglio = f"{member} — violazioni: {', '.join(violazioni)}"
        await security_repo.log_action(guild.id, "raid_join", member.id, dettaglio)

        voce = f"{member.name} ({member.id})"[:MAX_NOME_ELENCATO - 20]
        if not riuscita:
            voce += " ⚠ senza quarantena" if azione in ("quarantine", "both") else f" ⚠ {azione} non riuscito"
        await self._avvisa(guild, settings, voce, now)

        # SIC-033: al primo ingresso del raid, la stessa azione su chi è entrato nella finestra.
        if primo_del_raid and r.retroattivo:
            for ingresso in recenti:
                if ingresso.member_id == member.id:
                    continue
                if r.conta_solo_sospetti and not ingresso.sospetto:
                    continue  # SIC-029: chi non è sospetto non è contato nel raid, e non si tocca
                prima = guild.get_member(ingresso.member_id)
                if prima is None and azione != "ban":
                    continue
                await asyncio.sleep(PAUSA_AZIONI_SECONDI)
                await self._azione_raid(guild, prima or discord.Object(id=ingresso.member_id), azione)
                await security_repo.log_action(
                    guild.id, "raid_join", ingresso.member_id, f"{ingresso.nome} — entrato prima della soglia"
                )
                await self._avvisa(guild, settings, f"{ingresso.nome} ({ingresso.member_id}) ↩", now)

    async def _azione_raid(self, guild: discord.Guild, bersaglio, azione: str) -> bool:
        """Azione del raid su un account (SIC-032). True se riuscita o se non c'è niente da fare."""
        if azione in ("quarantine", "both"):
            return await self._esegui(guild, bersaglio, "quarantena", "Anti-Raid: join sospetto")
        if azione in ("kick", "ban"):
            return await self._esegui(guild, bersaglio, azione, "Anti-Raid: account del raid")
        return True

    async def _esegui(self, guild: discord.Guild, bersaglio, azione: str, motivo: str) -> bool:
        """Quarantena, timeout, kick o ban su un account appena entrato. False se Discord rifiuta."""
        try:
            if azione == "quarantena":
                ruolo = await self._ruolo_quarantena(guild)
                if ruolo is None or not isinstance(bersaglio, discord.Member):
                    return False
                await bot_roles.aggiungi_ruolo(bersaglio, ruolo, reason=motivo)
            elif azione == "timeout" and isinstance(bersaglio, discord.Member):
                await bot_roles.isola(bersaglio, DURATA_TIMEOUT_FILTRO, reason=motivo)
            elif azione == "kick" and isinstance(bersaglio, discord.Member):
                await bot_roles.espelli(bersaglio, reason=motivo)
            elif azione == "ban":
                await bot_roles.banna(guild, bersaglio, reason=motivo, delete_message_seconds=SECONDI_MESSAGGI_BAN)
            else:
                return False
        except discord.HTTPException:
            logger.warning("Anti-Raid: %s non riuscito su %s (server %s).", azione, bersaglio.id, guild.id)
            return False
        return True

    async def _filtri_ingresso(self, member: discord.Member, settings: SecuritySettings, now: datetime) -> bool:
        """
        Filtri all'ingresso (SIC-023…028). Se ne scattano più, vale l'azione
        più forte. True se l'account è stato cacciato (kick o ban riusciti).
        """
        r = settings.anti_raid
        scattati: list[tuple[str, str]] = []
        if r.azione_eta != AZIONE_NIENTE and not member.bot and is_account_too_new(
            member.created_at, now, r.min_account_age_seconds
        ):
            scattati.append((FILTRO_ETA, r.azione_eta))
        if r.azione_bot_non_verificato != AZIONE_NIENTE and member.bot and not member.public_flags.verified_bot:
            scattati.append((FILTRO_BOT_NON_VERIFICATO, r.azione_bot_non_verificato))
        if r.azione_nome_pubblicitario != AZIONE_NIENTE and nome_pubblicitario(_nomi(member)):
            scattati.append((FILTRO_NOME_PUBBLICITARIO, r.azione_nome_pubblicitario))
        if r.azione_nome_vietato != AZIONE_NIENTE and nome_vietato(_nomi(member), r.nomi_vietati):
            scattati.append((FILTRO_NOME_VIETATO, r.azione_nome_vietato))
        if not scattati:
            return False

        azione = azione_piu_forte(a for _, a in scattati)
        filtri = ", ".join(f for f, _ in scattati)
        # SIC-024: il DM che spiega il requisito parte PRIMA dell'azione (dopo un kick non arriva più).
        if r.messaggio_eta and any(f == FILTRO_ETA for f, _ in scattati):
            embed = discord.Embed(
                title=f"Ingresso in {guild_nome(member)}", description=r.messaggio_eta[:MAX_MESSAGGIO_DM]
            )
            await try_dm(member, embed)
        riuscita = await self._esegui(member.guild, member, azione, f"Anti-Raid: filtro all'ingresso ({filtri})")
        await security_repo.log_action(
            member.guild.id, "filtro_ingresso", member.id, f"{member} — {filtri}: {azione}{'' if riuscita else ' (non riuscito)'}"
        )
        if not raid_in_corso(member.guild.id, now):
            embed = discord.Embed(
                title="🛂 Anti-Raid — filtro all'ingresso",
                description=f"{member.mention} ({member.id})\nFiltri: {filtri}\nAzione: {azione}"
                + ("" if riuscita else " ⚠ non riuscita"),
                color=discord.Color.orange(),
            )
            await self._al_canale(member.guild, settings, embed)
        return riuscita and azione in ("kick", "ban")

    async def _al_canale(self, guild: discord.Guild, settings: SecuritySettings, embed: discord.Embed) -> None:
        canale = guild.get_channel(settings.alert_channel_id) if settings.alert_channel_id is not None else None
        if isinstance(canale, discord.TextChannel):
            try:
                await bot_roles.scrivi(canale, embed=embed)
            except discord.HTTPException:
                pass

    async def _avviso_rete(self, guild: discord.Guild, settings: SecuritySettings, member: discord.Member) -> None:
        """SIC-037: solo un avviso allo staff, nessuna azione e nessun punteggio."""
        await security_repo.log_action(guild.id, "raid_rete", member.id, f"{member} in {SERVER_RETE_MINIMI}+ server")
        embed = discord.Embed(
            title="🌐 Anti-Raid — ingresso in molti server",
            description=(
                f"{member.mention} ({member.id}) è entrato in almeno {SERVER_RETE_MINIMI} server "
                "che usano iYokai negli ultimi minuti. Può essere un account da raid: controllalo."
            ),
            color=discord.Color.gold(),
        )
        await self._al_canale(guild, settings, embed)

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

            if not episodio_in_corso:
                # SIC-011: se il server l'ha scelto, il raid accende il panico (una volta per episodio).
                await panico_automatico(guild, "Anti-Raid: ondata di ingressi sospetti")

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
            # SIC-034: i ruoli dello staff si pingano solo nel primo messaggio dell'episodio.
            ping = " ".join(f"<@&{i}>" for i in settings.anti_raid.ruoli_ping) if not episodio_in_corso else ""
            try:
                avviso.messaggio = await canale.send(
                    content=ping or None,
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(roles=True, users=False, everyone=False),
                )
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
