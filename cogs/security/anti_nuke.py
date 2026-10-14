"""
cogs/security/anti_nuke.py
==============================
Anti-Nuke (SPEC.md §7.2): rilevamento di azioni distruttive di massa
(cancellazione canali/ruoli, webhook, emoji/sticker, mass ban/kick)
ed intervento automatico sull'autore, più recovery best-effort e
alert allo staff. Modulo CANDIDATO PREMIUM, come Anti-Raid.

L'autore di un evento non è mai nel payload dell'evento gateway
stesso (Discord non lo include) — va sempre risolto via audit log
(`guild.audit_logs`), stesso approccio già usato in
`cogs/security/spam_trap.py` per il cleanup di webhook/inviti.
Il registro si legge solo dove l'anti-nuke è attivo, e si rilegge se
la voce non è ancora arrivata.

Recovery: `on_guild_channel_delete`/`on_guild_role_delete` ricevono
l'oggetto come l'ultima volta che era nella cache del client, PRIMA
della rimozione — permette di ricreare canale/ruolo con lo stesso
nome/permessi/posizione senza dover mantenere uno snapshot separato.
I canali vengono ricreati dello stesso tipo (testuale, annunci,
vocale, palco, categoria, forum).

Punizione (quarantena, ruoli tolti o ban): una sola per attacco. Un
attacco e' un caso numerato (/antinuke casi), un DM al
proprietario, un avviso; gli eventi che arrivano dopo la punizione non ne
creano altri finche' la punizione tiene. Impostazioni che cambiano chi e'
esente o quanto e' forte la difesa: solo il proprietario e gli extra owner
(core/security_access.solo_chi_gestisce).

Funzioni coperte: SPEC §7.2
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo

from core import channel_router as router
from core.bounded_cache import BoundedCache
from core.database import db
from core.lockdown_service import panico_automatico
from core.permission_risk_logic import critical_permissions_of
from core.premium import PremiumModule, registry, requires_module
from core.repositories.output_channel_repo import output_channel_repo
from core.repositories.security_repo import SecuritySettings, security_repo
from core.security_access import premium_sbloccato, solo_chi_gestisce
from core.security_audit import (
    ATTESE_REGISTRO,
    ATTESE_REGISTRO_USCITA,
    LOOKBACK_REGISTRO_SECONDI,
    resolve_voce,
)
from core.security_logic import (
    AntiNukeConfig,
    HOUR_WINDOW_SECONDS,
    NUKE_ACTION_BOT_ADD,
    NUKE_ACTION_MEMBER_ROLE,
    NUKE_ACTION_ROLE_PERMS,
    NUKE_ACTION_VANITY,
    NUKE_CATEGORY_BAN_KICK,
    NUKE_CATEGORY_CHANNEL,
    NUKE_CATEGORY_CHANNEL_PERMS,
    NUKE_CATEGORY_EMOJI,
    NUKE_CATEGORY_ROLE,
    NUKE_CATEGORY_WEBHOOK,
    TRUST_KIND_USER,
    TRUST_KIND_WEBHOOK,
    TRUST_LEVEL_EXTRA_OWNER,
    TRUST_LEVEL_TRUSTED,
    actor_is_trusted,
    category_hour_max,
    category_max_count,
    category_window_seconds,
    aggiungi_fiducia,
    is_nuke_violation,
    rimuovi_fiducia,
    voci_fiducia,
)
from core.security_quarantine import (
    azzera_contatori,
    metti_in_quarantena,
    problemi_ruoli_del_bot,
    rilascia_utente,
    ruolo_quarantena,
)
from core.security_rate_tracker import security_rate_tracker
from cogs.moderation._shared import ensure_module_enabled, try_dm

logger = logging.getLogger("iyokai.anti_nuke")

MODULE_ANTI_NUKE = "anti_nuke"

# Lunghezza massima di un motivo nel registro di controllo di Discord.
MAX_MOTIVO = 512

MOTIVO_RECOVERY = "Anti-Nuke: recovery automatico dopo cancellazione di massa"

# Quanti fidati si possono elencare in tutto (lista salvata nella riga del server).
MAX_FIDATI = 100
# Casi per pagina nell'elenco degli attacchi.
CASI_PER_PAGINA = 10

# Dopo un controllo del registro per i prune, per quanti secondi non se ne
# fa un altro per lo stesso server (una pulizia fa uscire molti membri
# insieme: la voce si legge una volta sola).
PAUSA_CONTROLLO_PRUNE = 5
# Quanti membri di un prune si contano al massimo (il motore è in memoria).
MAX_PRUNE_CONTATI = 1000

# Quanti membri si rimettono a un ruolo ricreato (Discord limita le
# richieste: oltre il tetto si lascia il resto allo staff) e quante
# cancellazioni si tengono da parte per autore.
MAX_MEMBRI_RIPRISTINO = 500
MAX_IN_ATTESA = 100

# Dal 16/11/2026 un canale che il bot non può vedere arriva con questo
# nome finto (LIMITI.md, Parte 2).
NOME_CANALE_NASCOSTO = "___hidden___"


def _replace(settings: SecuritySettings, **overrides) -> SecuritySettings:
    dati = {
        "guild_id": settings.guild_id,
        "anti_raid": settings.anti_raid,
        "anti_nuke": settings.anti_nuke,
        "quarantine_role_id": settings.quarantine_role_id,
        "alert_channel_id": settings.alert_channel_id,
    }
    anti_nuke_fields = set(AntiNukeConfig.__dataclass_fields__.keys())
    anti_nuke_overrides = {k: v for k, v in overrides.items() if k in anti_nuke_fields}
    altri_overrides = {k: v for k, v in overrides.items() if k not in anti_nuke_fields}

    if anti_nuke_overrides:
        dati["anti_nuke"] = AntiNukeConfig(
            **{**{f: getattr(settings.anti_nuke, f) for f in anti_nuke_fields}, **anti_nuke_overrides}
        )
    dati.update(altri_overrides)
    return SecuritySettings(**dati)


async def _punish_actor(
    guild: discord.Guild, actor_id: int, config: AntiNukeConfig, reason: str
) -> tuple[str, list[int]]:
    """
    Punisce l'autore. Restituisce (descrizione di cosa è stato fatto, per
    il log e l'avviso; ID dei ruoli tolti, per il caso e il rilascio).
    """
    if guild.owner_id == actor_id:
        return "nessuna azione: l'autore è il proprietario del server", []

    member = guild.get_member(actor_id)
    if member is None:
        return "nessuna azione: l'autore non è (più) un membro del server", []

    reason = reason[:MAX_MOTIVO]

    if config.punish_action == "ban":
        try:
            await member.ban(reason=reason, delete_message_seconds=0)
            return f"{member} bannato", []
        except discord.HTTPException:
            return f"tentativo di ban di {member} fallito (permessi insufficienti?)", []

    if member.bot:
        # Il ruolo di un bot è gestito da Discord e non si può
        # togliere: un bot che fa danni va tolto dal server.
        try:
            await member.kick(reason=reason)
            return f"bot {member} espulso", []
        except discord.HTTPException:
            return f"tentativo di espellere il bot {member} fallito (permessi insufficienti?)", []

    if config.punish_action == "quarantine":
        esito = await metti_in_quarantena(member, reason, togli_ruoli=True)
        if esito.completo:
            return f"{member} messo in quarantena (ruoli tolti: {len(esito.ruoli_tolti)})", esito.ruoli_tolti
        if esito.in_quarantena:
            # Il ruolo c'e' ma i poteri no: non e' una quarantena, e chi legge lo deve sapere.
            return (
                f"⚠️ {member} ha il ruolo di quarantena ma i suoi ruoli NON sono stati tolti: "
                "l'autore è ancora potente (il mio ruolo è sotto il suo?)"
            ), []
        # Senza ruolo di quarantena (permesso mancante) si toglie comunque il potere.

    # I ruoli gestiti da Discord (es. Server Booster) non si possono
    # togliere: chiederlo farebbe fallire tutta la modifica.
    ruoli_gestiti = [ruolo for ruolo in member.roles if ruolo.managed]
    tolti = [ruolo.id for ruolo in member.roles if not ruolo.managed and not ruolo.is_default()]
    try:
        await member.edit(roles=ruoli_gestiti, reason=reason)
        return f"tutti i ruoli rimossi da {member}", tolti
    except discord.HTTPException:
        return f"tentativo di rimuovere i ruoli di {member} fallito (permessi insufficienti?)", []


def _finestra_recupero(categoria: str, config: AntiNukeConfig) -> int:
    """
    Quanto indietro si recupera ciò che l'autore ha cancellato. Con la
    soglia oraria accesa un attacco lento si estende per un'ora: la
    finestra breve ne perderebbe quasi tutto.
    """
    breve = category_window_seconds(categoria, config)
    return max(breve, HOUR_WINDOW_SECONDS) if category_hour_max(categoria, config) > 0 else breve


def _categoria_del_canale(channel: discord.abc.GuildChannel) -> int | None:
    """La categoria di Discord a cui appartiene il canale (per una categoria, se stessa)."""
    if isinstance(channel, discord.CategoryChannel):
        return channel.id
    return getattr(channel, "category_id", None)


async def _alert_staff(guild: discord.Guild, settings: SecuritySettings, embed: discord.Embed) -> None:
    """DM al proprietario e avviso nel canale degli allarmi (#59 3.18).

    Il canale lo sceglie `/antinuke canale-allarmi` (router dei canali,
    puo' essere anche un forum); senza scelta vale quello dell'anti-raid.
    """
    if guild.owner is not None:
        await try_dm(guild.owner, embed)
    dest = await router.destinazione(guild, router.TIPO_ALLARMI, settings.alert_channel_id)
    if dest is not None:
        await router.invia_a(dest, guild, router.TIPO_ALLARMI, embed=embed)


def _campi_fiducia(config: AntiNukeConfig) -> dict:
    return {"trusted_ids": config.trusted_ids, "trust_entries": config.trust_entries}


class AntiNukeCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Categoria cancellata (ID vecchio) -> categoria ricreata.
        self._categorie_ricreate: BoundedCache[int, discord.CategoryChannel] = BoundedCache(
            max_size=500
        )
        # (server, autore) -> oggetti cancellati non ancora recuperati
        # perché l'autore era ancora sotto soglia.
        self._in_attesa: BoundedCache[tuple[int, int], list[tuple[datetime, str, object]]] = BoundedCache(max_size=500)
        # (server, autore) -> blocco: eventi simultanei dello stesso attacco
        # non puniscono due volte.
        self._blocchi_punizione: BoundedCache[tuple[int, int], asyncio.Lock] = BoundedCache(max_size=500)
        # Server -> (ora dell'ultimo controllo dei prune, ID dell'ultima voce contata).
        self._prune: BoundedCache[int, tuple[datetime, int | None]] = BoundedCache(max_size=500)

    async def _solo_chi_gestisce(
        self, interaction: discord.Interaction, settings: SecuritySettings
    ) -> bool:
        return await solo_chi_gestisce(interaction, settings.anti_nuke)

    @comando_di_gruppo(
        "antinuke",
        nome="enable",
        descrizione="Attiva o disattiva l'Anti-Nuke.",
    )
    @requires_module(MODULE_ANTI_NUKE)
    async def enable(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        # Spegnerlo è la prima mossa di chi vuole fare danni: solo chi gestisce.
        if not enabled and not await self._solo_chi_gestisce(interaction, settings):
            return
        await security_repo.save_settings(_replace(settings, enabled=enabled))
        await interaction.response.send_message(f"Anti-Nuke {'attivato' if enabled else 'disattivato'}.", ephemeral=True)
        if enabled and settings.anti_nuke.punish_action == "quarantine":
            await self._prepara_quarantena(interaction)

    async def _prepara_quarantena(self, interaction: discord.Interaction) -> None:
        """
        Il ruolo di quarantena (e i suoi permessi sui canali) si crea adesso,
        non durante l'attacco: con centinaia di canali ci vuole piu' del
        tempo che si ha. Un messaggio a parte dice se qualcosa non va.
        """
        guild = interaction.guild
        ruolo = await ruolo_quarantena(guild)
        if ruolo is None:
            avviso = (
                "⚠️ Non sono riuscito a creare il ruolo di quarantena (mi manca Gestire ruoli?): "
                "durante un attacco userei il ripiego, togliere i ruoli."
            )
        else:
            settings = await security_repo.get_settings(guild.id)
            problemi = problemi_ruoli_del_bot(guild, settings.quarantine_role_id)
            if not problemi:
                return
            avviso = "⚠️ " + "\n⚠️ ".join(problemi)
        await interaction.followup.send(avviso, ephemeral=True)

    @comando_di_gruppo(
        "antinuke",
        nome="limits",
        descrizione="Configura la soglia di rilevamento per una categoria.",
    )
    @app_commands.describe(
        category="Tipo di azione da controllare",
        max_actions="Azioni consentite nella finestra breve (poi scatta la punizione)",
        seconds="Durata della finestra breve in secondi (da 1 a 3600)",
        max_per_hour="Azioni consentite in un'ora, per l'attacco lento (0 = soglia oraria spenta)",
    )
    @app_commands.choices(
        category=[
            app_commands.Choice(name="Canali", value=NUKE_CATEGORY_CHANNEL),
            app_commands.Choice(name="Ruoli", value=NUKE_CATEGORY_ROLE),
            app_commands.Choice(name="Webhook", value=NUKE_CATEGORY_WEBHOOK),
            app_commands.Choice(name="Emoji/Sticker", value=NUKE_CATEGORY_EMOJI),
            app_commands.Choice(name="Ban/Kick", value=NUKE_CATEGORY_BAN_KICK),
            app_commands.Choice(name="Permessi dei canali", value=NUKE_CATEGORY_CHANNEL_PERMS),
        ]
    )
    @requires_module(MODULE_ANTI_NUKE)
    async def limits(
        self,
        interaction: discord.Interaction,
        category: app_commands.Choice[str],
        max_actions: app_commands.Range[int, 0, 1000],
        seconds: app_commands.Range[int, 1, 3600],
        max_per_hour: app_commands.Range[int, 0, 10000] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        if not await self._solo_chi_gestisce(interaction, settings):
            return
        prefisso = category.value
        campi = {f"{prefisso}_max": max_actions, f"{prefisso}_window_seconds": seconds}
        if max_per_hour is not None:
            campi[f"{prefisso}_hour_max"] = max_per_hour
        await security_repo.save_settings(_replace(settings, **campi))
        ora = category_hour_max(prefisso, _replace(settings, **campi).anti_nuke)
        testo_ora = f", {ora} in un'ora" if ora else ", soglia oraria spenta"
        await interaction.response.send_message(
            f"Soglia **{category.name}** impostata a {max_actions} ogni {seconds}s{testo_ora}.",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "antinuke",
        nome="trusted-add",
        descrizione="Esenta un utente, un bot o un webhook dai controlli Anti-Nuke.",
    )
    @app_commands.describe(
        user_id="ID dell'utente, del bot o del webhook da esentare",
        tipo="Che cos'è l'ID (predefinito: utente o bot)",
        livello="Fidato: esente. Extra owner: come il proprietario (lo assegna solo il proprietario)",
        azione="Esenta solo da questo tipo di azione (predefinito: tutte)",
        categoria_canali="Esenta solo per i canali di questa categoria di Discord",
    )
    @app_commands.choices(
        tipo=[
            app_commands.Choice(name="Utente o bot", value=TRUST_KIND_USER),
            app_commands.Choice(name="Webhook", value=TRUST_KIND_WEBHOOK),
        ],
        livello=[
            app_commands.Choice(name="Fidato (esente)", value=TRUST_LEVEL_TRUSTED),
            app_commands.Choice(name="Extra owner (come il proprietario)", value=TRUST_LEVEL_EXTRA_OWNER),
        ],
        azione=[
            app_commands.Choice(name="Canali", value=NUKE_CATEGORY_CHANNEL),
            app_commands.Choice(name="Ruoli", value=NUKE_CATEGORY_ROLE),
            app_commands.Choice(name="Webhook", value=NUKE_CATEGORY_WEBHOOK),
            app_commands.Choice(name="Emoji/Sticker", value=NUKE_CATEGORY_EMOJI),
            app_commands.Choice(name="Ban/Kick", value=NUKE_CATEGORY_BAN_KICK),
            app_commands.Choice(name="Permessi dei canali", value=NUKE_CATEGORY_CHANNEL_PERMS),
            app_commands.Choice(name="Permessi dei ruoli", value=NUKE_ACTION_ROLE_PERMS),
            app_commands.Choice(name="Ruoli dati ai membri", value=NUKE_ACTION_MEMBER_ROLE),
            app_commands.Choice(name="Aggiunta di bot", value=NUKE_ACTION_BOT_ADD),
        ],
    )
    @requires_module(MODULE_ANTI_NUKE)
    async def trusted_add(
        self,
        interaction: discord.Interaction,
        user_id: app_commands.Range[str, 1, 20],
        tipo: app_commands.Choice[str] | None = None,
        livello: app_commands.Choice[str] | None = None,
        azione: app_commands.Choice[str] | None = None,
        categoria_canali: discord.CategoryChannel | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        try:
            id_utente = int(user_id)
        except ValueError:
            await interaction.response.send_message("ID non valido.", ephemeral=True)
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        if not await self._solo_chi_gestisce(interaction, settings):
            return
        genere = tipo.value if tipo else TRUST_KIND_USER
        grado = livello.value if livello else TRUST_LEVEL_TRUSTED
        nuova, errore = aggiungi_fiducia(
            settings.anti_nuke,
            chi_id=interaction.user.id,
            owner_id=interaction.guild.owner_id,
            target_id=id_utente,
            kind=genere,
            level=grado,
            categories=(azione.value,) if azione else (),
            channel_category_id=categoria_canali.id if categoria_canali else None,
            max_voci=MAX_FIDATI,
        )
        if nuova is None:
            await interaction.response.send_message(errore, ephemeral=True)
            return
        await security_repo.save_settings(_replace(settings, **_campi_fiducia(nuova)))
        cosa = "Webhook" if genere == TRUST_KIND_WEBHOOK else "Utente"
        limite = ""
        if azione:
            limite += f" solo per: {azione.name}"
        if categoria_canali:
            limite += f" solo nella categoria {categoria_canali.name}"
        livello_testo = " come extra owner" if grado == TRUST_LEVEL_EXTRA_OWNER else ""
        await interaction.response.send_message(
            f"{cosa} `{id_utente}` esentato dai controlli Anti-Nuke{livello_testo}{limite}.", ephemeral=True
        )

    @comando_di_gruppo(
        "antinuke",
        nome="trusted-remove",
        descrizione="Rimuove un utente, un bot o un webhook dalla lista fidati Anti-Nuke.",
    )
    @app_commands.describe(user_id="ID da togliere dalla lista (utente, bot o webhook)")
    @requires_module(MODULE_ANTI_NUKE)
    async def trusted_remove(
        self, interaction: discord.Interaction, user_id: app_commands.Range[str, 1, 20]
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        try:
            id_utente = int(user_id)
        except ValueError:
            await interaction.response.send_message("ID non valido.", ephemeral=True)
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        if not await self._solo_chi_gestisce(interaction, settings):
            return
        nuova, errore = rimuovi_fiducia(
            settings.anti_nuke,
            chi_id=interaction.user.id,
            owner_id=interaction.guild.owner_id,
            target_id=id_utente,
        )
        if nuova is None:
            await interaction.response.send_message(errore, ephemeral=True)
            return
        await security_repo.save_settings(_replace(settings, **_campi_fiducia(nuova)))
        await interaction.response.send_message(f"`{id_utente}` rimosso dalla lista fidati.", ephemeral=True)

    @comando_di_gruppo(
        "antinuke",
        nome="trusted-list",
        descrizione="Elenca chi è esentato dai controlli Anti-Nuke e con quali limiti.",
    )
    @requires_module(MODULE_ANTI_NUKE)
    async def trusted_list(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        n = settings.anti_nuke
        righe = []
        for v in voci_fiducia(n):
            soggetto = f"webhook `{v.target_id}`" if v.kind == TRUST_KIND_WEBHOOK else f"<@{v.target_id}> (`{v.target_id}`)"
            grado = "extra owner" if v.level == TRUST_LEVEL_EXTRA_OWNER else "fidato"
            ambito = ", ".join(v.categories) if v.categories else "tutte le azioni"
            if v.channel_category_id:
                ambito += f", solo nella categoria <#{v.channel_category_id}>"
            righe.append(f"{soggetto} — {grado}, {ambito}")
        testo = "\n".join(righe) or "Nessuno: ogni amministratore è soggetto ai controlli."
        if len(testo) > 4000:
            testo = testo[:3990].rsplit("\n", 1)[0] + "\n…"
        await interaction.response.send_message(
            embed=discord.Embed(title="Esentati dall'Anti-Nuke", description=testo, color=discord.Color.blurple()),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @comando_di_gruppo(
        "antinuke",
        nome="punish-action",
        descrizione="Cosa fare all'autore di un'azione distruttiva di massa.",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Quarantena: ruoli tolti, resta nel server (un bot viene espulso)", value="quarantine"),
            app_commands.Choice(name="Rimuovi tutti i ruoli (un bot viene espulso)", value="strip_roles"),
            app_commands.Choice(name="Banna", value="ban"),
        ]
    )
    @requires_module(MODULE_ANTI_NUKE)
    async def punish_action(self, interaction: discord.Interaction, action: app_commands.Choice[str]) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        if not await self._solo_chi_gestisce(interaction, settings):
            return
        await security_repo.save_settings(_replace(settings, punish_action=action.value))
        await interaction.response.send_message(f"Azione punitiva impostata su **{action.name}**.", ephemeral=True)
        if action.value == "quarantine" and settings.anti_nuke.enabled:
            await self._prepara_quarantena(interaction)

    @comando_di_gruppo(
        "antinuke",
        nome="recovery",
        descrizione="Attiva/disattiva la ricreazione automatica di canali/ruoli cancellati durante un attacco.",
    )
    @requires_module(MODULE_ANTI_NUKE)
    async def recovery(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        if not await self._solo_chi_gestisce(interaction, settings):
            return
        await security_repo.save_settings(_replace(settings, recovery_enabled=enabled))
        await interaction.response.send_message(f"Recovery automatico {'attivato' if enabled else 'disattivato'}.", ephemeral=True)

    @comando_di_gruppo(
        "antinuke",
        nome="canale-allarmi",
        descrizione="Sceglie dove arrivano gli allarmi dell'Anti-Nuke (canale o forum).",
    )
    @app_commands.describe(channel="Canale di testo o forum degli allarmi")
    @requires_module(MODULE_ANTI_NUKE)
    async def canale_allarmi(
        self, interaction: discord.Interaction, channel: discord.TextChannel | discord.ForumChannel
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        if not await self._solo_chi_gestisce(interaction, settings):
            return
        await output_channel_repo.imposta(interaction.guild.id, router.TIPO_ALLARMI, channel.id)
        await interaction.response.send_message(
            f"Gli allarmi dell'Anti-Nuke arriveranno in {channel.mention}.", ephemeral=True
        )

    @comando_di_gruppo(
        "antinuke",
        nome="status",
        descrizione="Mostra la configurazione attuale dell'Anti-Nuke.",
    )
    @requires_module(MODULE_ANTI_NUKE)
    async def status(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        n = settings.anti_nuke
        scelta = await output_channel_repo.ottieni(interaction.guild.id, router.TIPO_ALLARMI)
        id_allarmi = scelta.channel_id if scelta and scelta.esplicito else settings.alert_channel_id

        def _riga(nome: str, categoria: str) -> str:
            ora = category_hour_max(categoria, n)
            testo_ora = f", {ora} all'ora" if ora else ", oraria spenta"
            return (
                f"**{nome}**: max {category_max_count(categoria, n)}/"
                f"{category_window_seconds(categoria, n)}s{testo_ora}"
            )

        righe = [
            f"**Attivo**: {'sì' if n.enabled else 'no'}",
            _riga("Canali", NUKE_CATEGORY_CHANNEL),
            _riga("Ruoli", NUKE_CATEGORY_ROLE),
            _riga("Webhook", NUKE_CATEGORY_WEBHOOK),
            _riga("Emoji/Sticker", NUKE_CATEGORY_EMOJI),
            _riga("Ban/Kick", NUKE_CATEGORY_BAN_KICK),
            _riga("Permessi dei canali", NUKE_CATEGORY_CHANNEL_PERMS),
            f"**Azione punitiva**: {n.punish_action}",
            f"**Canale degli allarmi**: {f'<#{id_allarmi}>' if id_allarmi else 'nessuno (solo DM al proprietario)'}",
            f"**Recovery automatico**: {'sì' if n.recovery_enabled else 'no'}",
            f"**Utenti fidati**: {sum(1 for v in voci_fiducia(n) if v.level != TRUST_LEVEL_EXTRA_OWNER)}",
            f"**Extra owner**: {sum(1 for v in voci_fiducia(n) if v.level == TRUST_LEVEL_EXTRA_OWNER)}",
            f"**Guardia permessi dei ruoli**: {n.role_perm_guard}",
            f"**Guardia ruoli pericolosi ai membri**: {'sì' if n.member_role_guard else 'no'}",
            f"**Guardia link personalizzato**: {'sì' if n.vanity_guard else 'no'}",
            f"**Guardia aggiunta di bot**: {'sì' if n.bot_add_guard else 'no'}",
        ]
        await interaction.response.send_message("\n".join(righe), ephemeral=True)

    @comando_di_gruppo(
        "antinuke",
        nome="guardie",
        descrizione="Protezioni su azioni singole: permessi dei ruoli, ruoli ai membri, link, bot.",
    )
    @app_commands.describe(
        permessi_ruoli="Annulla l'aggiunta di permessi pericolosi a un ruolo, se l'autore non è fidato",
        ruoli_ai_membri="Toglie un ruolo con permessi pericolosi dato a un membro da chi non è fidato",
        link_personalizzato="Avvisa (e prova a ripristinare) se cambia il link personalizzato del server",
        aggiunta_bot="Espelle un bot aggiunto da chi non è fidato",
    )
    @app_commands.choices(
        permessi_ruoli=[
            app_commands.Choice(name="Spenta", value="off"),
            app_commands.Choice(name="Solo @everyone e ruoli di quasi tutti", value="public"),
            app_commands.Choice(name="Ogni ruolo", value="all"),
        ]
    )
    @requires_module(MODULE_ANTI_NUKE)
    async def guardie(
        self,
        interaction: discord.Interaction,
        permessi_ruoli: app_commands.Choice[str] | None = None,
        ruoli_ai_membri: bool | None = None,
        link_personalizzato: bool | None = None,
        aggiunta_bot: bool | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        if not await self._solo_chi_gestisce(interaction, settings):
            return
        campi: dict = {}
        if permessi_ruoli is not None:
            campi["role_perm_guard"] = permessi_ruoli.value
        if ruoli_ai_membri is not None:
            campi["member_role_guard"] = ruoli_ai_membri
        if link_personalizzato is not None:
            campi["vanity_guard"] = link_personalizzato
        if aggiunta_bot is not None:
            campi["bot_add_guard"] = aggiunta_bot
        if campi:
            settings = _replace(settings, **campi)
            await security_repo.save_settings(settings)
        n = settings.anti_nuke
        await interaction.response.send_message(
            "Guardie: "
            f"permessi dei ruoli **{n.role_perm_guard}**, ruoli pericolosi ai membri **{'sì' if n.member_role_guard else 'no'}**, "
            f"link personalizzato **{'sì' if n.vanity_guard else 'no'}**, aggiunta di bot **{'sì' if n.bot_add_guard else 'no'}**.",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "antinuke",
        nome="casi",
        descrizione="Registro degli attacchi fermati: elenco o dettaglio di un caso.",
    )
    @app_commands.describe(
        numero="Numero del caso da vedere nel dettaglio (vuoto: l'elenco)",
        pagina="Pagina dell'elenco (10 casi per pagina)",
    )
    @requires_module(MODULE_ANTI_NUKE)
    async def casi(
        self,
        interaction: discord.Interaction,
        numero: app_commands.Range[int, 1, 1_000_000] | None = None,
        pagina: app_commands.Range[int, 1, 100] = 1,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        guild_id = interaction.guild.id
        if numero is not None:
            caso = await security_repo.get_nuke_case(guild_id, numero)
            if caso is None:
                await interaction.response.send_message(f"Il caso #{numero} non esiste.", ephemeral=True)
                return
            embed = discord.Embed(title=f"Anti-Nuke — caso #{caso.case_number}", color=discord.Color.red())
            embed.add_field(name="Autore", value=f"<@{caso.actor_id}> (`{caso.actor_id}`)" if caso.actor_id else "Sconosciuto", inline=False)
            embed.add_field(name="Categoria", value=caso.category, inline=True)
            embed.add_field(name="Quando", value=discord.utils.format_dt(caso.created_at, style="F"), inline=True)
            embed.add_field(name="Cosa è successo", value=(caso.detail or "—")[:1024], inline=False)
            embed.add_field(name="Punizione", value=(caso.punishment or "—")[:1024], inline=False)
            ruoli = " ".join(f"<@&{r}>" for r in caso.removed_role_ids)[:1000] or "Nessuno"
            embed.add_field(name="Ruoli tolti", value=ruoli, inline=False)
            embed.add_field(
                name="Stato",
                value=f"Rilasciato {discord.utils.format_dt(caso.released_at, style='R')}" if caso.released_at else "Non rilasciato",
                inline=False,
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
            )
            return
        elenco, totale = await security_repo.list_nuke_cases(guild_id, pagina, CASI_PER_PAGINA)
        if not elenco:
            testo = "Nessun attacco registrato." if totale == 0 else f"La pagina {pagina} è vuota."
            await interaction.response.send_message(testo, ephemeral=True)
            return
        righe = [
            f"**#{c.case_number}** · {discord.utils.format_dt(c.created_at, style='d')} · {c.category} · "
            f"<@{c.actor_id}>{' · rilasciato' if c.released_at else ''}"
            for c in elenco
        ]
        pagine = max(1, -(-totale // CASI_PER_PAGINA))
        embed = discord.Embed(
            title="Attacchi fermati dall'Anti-Nuke",
            description="\n".join(righe)[:4000],
            color=discord.Color.red(),
        )
        embed.set_footer(text=f"Pagina {pagina}/{pagine} · {totale} casi · /antinuke casi numero:N per il dettaglio")
        await interaction.response.send_message(
            embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )

    @comando_di_gruppo(
        "antinuke",
        nome="rilascia",
        descrizione="Toglie la quarantena all'autore di un caso e gli rimette i ruoli.",
    )
    @app_commands.describe(caso="Numero del caso (vedi /antinuke casi)")
    @requires_module(MODULE_ANTI_NUKE)
    async def rilascia(
        self, interaction: discord.Interaction, caso: app_commands.Range[int, 1, 1_000_000]
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        if not await self._solo_chi_gestisce(interaction, settings):
            return
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        registrato = await security_repo.get_nuke_case(guild.id, caso)
        if registrato is None:
            await interaction.followup.send(f"Il caso #{caso} non esiste.", ephemeral=True)
            return
        if registrato.released_at is not None:
            await interaction.followup.send(f"Il caso #{caso} è già stato rilasciato.", ephemeral=True)
            return
        membro = guild.get_member(registrato.actor_id) if registrato.actor_id else None
        if membro is None:
            await interaction.followup.send(
                "L'autore non è nel server (espulso, bannato o uscito): non c'è niente da rimettere. "
                "Se è bannato, toglilo dai ban.",
                ephemeral=True,
            )
            return
        esito = await rilascia_utente(
            membro, caso_numero=caso, reason=f"Anti-Nuke: caso #{caso} rilasciato da {interaction.user}"
        )
        if not esito.riuscito:
            await interaction.followup.send(
                "Discord non mi ha lasciato cambiare i ruoli di quel membro (il mio ruolo è più in basso del suo?).",
                ephemeral=True,
            )
            return
        azzera_contatori(guild.id, membro.id, security_rate_tracker)
        if esito.quarantena_tenuta:
            altri = ", ".join(f"#{n}" for n in esito.altri_casi)
            testo = (
                f"Caso #{caso} rilasciato: {membro.mention} ha di nuovo i ruoli di quel caso. "
                f"Resta in quarantena: ha altri casi attivi ({altri}), da rilasciare uno per uno."
            )
        else:
            testo = f"Caso #{caso} rilasciato: {membro.mention} è fuori dalla quarantena."
        if esito.saltati:
            testo += f" Non ho potuto rimettere {len(esito.saltati)} ruolo/i (cancellati, gestiti o sopra al mio)."
        await interaction.followup.send(testo, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    # ================================================================
    # Motore di rilevamento — un metodo condiviso per ogni categoria,
    # così la logica "conta -> valuta -> punisci -> logga -> alert" non
    # si ripete cinque volte quasi identica.
    # ================================================================
    async def _impostazioni_attive(self, guild: discord.Guild) -> SecuritySettings | None:
        """Le impostazioni del server se l'anti-nuke è attivo lì, altrimenti None."""
        if not await db.is_module_active_for_guild(guild.id, MODULE_ANTI_NUKE):
            return None
        if not await premium_sbloccato(guild.id, MODULE_ANTI_NUKE, self.bot):
            return None
        settings = await security_repo.get_settings(guild.id)
        return settings if settings.anti_nuke.enabled else None

    async def _evento(
        self,
        guild: discord.Guild,
        category: str,
        azioni: tuple[discord.AuditLogAction, ...],
        detail_suffix: str,
        target_id: int | None = None,
        attese: tuple[float, ...] = ATTESE_REGISTRO,
        cancellato: discord.abc.GuildChannel | discord.Role | None = None,
        categoria_canale_id: int | None = None,
    ) -> SecuritySettings | None:
        """
        Percorso comune dei listener. Prima si controlla se l'anti-nuke
        è attivo: dove è spento il registro di controllo non viene
        letto. Poi si cerca l'autore (nella prima delle `azioni` che ha
        una voce) e si passa al motore.

        Se è passato l'oggetto `cancellato`, lo si tiene da parte per
        quell'autore: sotto soglia non si ricrea nulla, ma appena
        l'autore la supera si recupera anche ciò che aveva già
        cancellato prima (e, se il recupero è attivo, ogni
        cancellazione successiva).

        `categoria_canale_id` è la categoria di Discord del canale
        coinvolto: serve alla fiducia limitata a una categoria (SIC-019).
        """
        settings = await self._impostazioni_attive(guild)
        if settings is None:
            return None
        actor_id = None
        oggetto_id = None
        for azione in azioni:
            voce = await resolve_voce(guild, azione, target_id, attese)
            if voce is not None:
                actor_id, oggetto_id = voce
                break
        if cancellato is not None and actor_id is not None and actor_id != self.bot.user.id:
            chiave = (guild.id, actor_id)
            in_attesa = self._in_attesa.get(chiave) or []
            adesso = discord.utils.utcnow()
            in_attesa = [v for v in in_attesa if (adesso - v[0]).total_seconds() <= HOUR_WINDOW_SECONDS]
            in_attesa.append((adesso, category, cancellato))
            self._in_attesa.set(chiave, in_attesa[-MAX_IN_ATTESA:])
        violazione = await self._handle_event(
            guild, category, actor_id, detail_suffix, settings,
            categoria_canale_id=categoria_canale_id, oggetto_id=oggetto_id,
        )
        if violazione is not None and cancellato is not None and violazione.anti_nuke.recovery_enabled:
            await self._recupera_in_attesa(guild.id, actor_id, violazione)
        return violazione

    async def _recupera_in_attesa(
        self, guild_id: int, actor_id: int, settings: SecuritySettings
    ) -> None:
        """
        Ricrea ciò che l'autore ha cancellato dentro la finestra della
        categoria (prima le categorie, poi il resto). Le cancellazioni
        più vecchie sono azioni di altri momenti, non di questo attacco:
        si scartano.
        """
        chiave = (guild_id, actor_id)
        voci = list(self._in_attesa.get(chiave) or [])
        self._in_attesa.delete(chiave)
        adesso = discord.utils.utcnow()
        in_attesa = [
            oggetto
            for ora, categoria, oggetto in voci
            if (adesso - ora).total_seconds() <= _finestra_recupero(categoria, settings.anti_nuke)
        ]
        in_attesa.sort(key=lambda oggetto: not isinstance(oggetto, discord.CategoryChannel))
        # Più cambi ai permessi dello stesso canale: vale il primo "prima" (SIC-007).
        gia_ripristinati: set[int] = set()
        for oggetto in in_attesa:
            try:
                if isinstance(oggetto, tuple):
                    _, canale, permessi_prima = oggetto
                    if canale.id in gia_ripristinati:
                        continue
                    gia_ripristinati.add(canale.id)
                    await canale.edit(overwrites=permessi_prima, reason=MOTIVO_RECOVERY)
                elif isinstance(oggetto, discord.Role):
                    await self._ricrea_ruolo(oggetto)
                else:
                    await self._ricrea_canale(oggetto)
            except discord.HTTPException as errore:
                logger.warning("Recovery di %s fallita: %s", getattr(oggetto, "name", "?"), errore)

    async def _handle_event(
        self,
        guild: discord.Guild,
        category: str,
        actor_id: int | None,
        detail_suffix: str,
        settings: SecuritySettings | None = None,
        *,
        categoria_canale_id: int | None = None,
        oggetto_id: int | None = None,
        conteggio_azioni: int = 1,
    ) -> SecuritySettings | None:
        # Le azioni del bot stesso (recovery, ticket, canali temporanei)
        # non si contano: il bot non deve mai punire se stesso.
        if actor_id is None or actor_id == self.bot.user.id:
            return None
        # Il proprietario non si ferma: non c'è nessuno sopra di lui.
        if actor_id == guild.owner_id:
            return None
        if settings is None:
            settings = await self._impostazioni_attive(guild)
            if settings is None:
                return None
        # Chi è esente per questa azione non si conta nemmeno.
        if actor_is_trusted(
            actor_id, category, settings.anti_nuke,
            channel_category_id=categoria_canale_id, target_id=oggetto_id,
        ):
            return None

        now = discord.utils.utcnow()
        finestra = category_window_seconds(category, settings.anti_nuke)
        for _ in range(max(conteggio_azioni - 1, 0)):
            security_rate_tracker.record_and_count(guild.id, actor_id, category, now, finestra)
            security_rate_tracker.record_and_count(
                guild.id, actor_id, f"{category}:ora", now, HOUR_WINDOW_SECONDS
            )
        conteggio = security_rate_tracker.record_and_count(guild.id, actor_id, category, now, finestra)
        # La seconda soglia (un'ora) prende l'attacco lento (SIC-001).
        conteggio_ora = security_rate_tracker.record_and_count(
            guild.id, actor_id, f"{category}:ora", now, HOUR_WINDOW_SECONDS
        )

        if not is_nuke_violation(
            actor_id, category, conteggio, settings.anti_nuke,
            count_in_hour=conteggio_ora,
            channel_category_id=categoria_canale_id, target_id=oggetto_id,
        ):
            return None

        sopra_ora = conteggio_ora > category_hour_max(category, settings.anti_nuke) > 0
        quanti = f"{conteggio_ora} azioni in un'ora" if sopra_ora and conteggio <= category_max_count(
            category, settings.anti_nuke
        ) else f"{conteggio} azioni in {finestra}s"

        # Una punizione per attacco: gli eventi che arrivano mentre il primo
        # sta ancora punendo, o dopo, aspettano e trovano il caso gia' aperto.
        chiave = (guild.id, actor_id)
        blocco = self._blocchi_punizione.get(chiave)
        if blocco is None:
            blocco = asyncio.Lock()
            self._blocchi_punizione.set(chiave, blocco)
        async with blocco:
            await self._punisci_una_volta(guild, settings, category, actor_id, detail_suffix, quanti)
        return settings

    async def _punisci_una_volta(
        self,
        guild: discord.Guild,
        settings: SecuritySettings,
        category: str,
        actor_id: int,
        detail_suffix: str,
        quanti: str,
    ) -> None:
        reason = f"Anti-Nuke: {category} — {detail_suffix}"
        aperti = await security_repo.active_cases_for_actor(guild.id, actor_id)
        episodio = next(
            (
                c for c in aperti
                if (discord.utils.utcnow() - c.created_at).total_seconds() <= HOUR_WINDOW_SECONDS
            ),
            None,
        )
        if episodio is not None:
            if await self._punizione_in_vigore(guild, actor_id, settings.anti_nuke):
                return  # stesso attacco, gia' fermato: niente caso, DM o avviso in piu'
            # La punizione non tiene (quarantena tolta a mano, ruoli tornati): si ripete,
            # sullo stesso caso. I ruoli tolti adesso si aggiungono a quelli gia' registrati.
            esito, tolti = await _punish_actor(guild, actor_id, settings.anti_nuke, reason=reason)
            await security_repo.extend_nuke_case(
                guild.id, episodio.case_number, esito, tuple(tolti)
            )
            await security_repo.log_action(
                guild.id, f"nuke_{category}", actor_id, f"{detail_suffix} — punizione ripetuta — {esito}"
            )
            return

        esito, tolti = await _punish_actor(guild, actor_id, settings.anti_nuke, reason=reason)
        dettaglio = f"{detail_suffix} — {quanti} — {esito}"
        await security_repo.log_action(guild.id, f"nuke_{category}", actor_id, dettaglio)
        numero = await security_repo.create_nuke_case(
            guild.id, actor_id, category, dettaglio, esito, tuple(tolti)
        )

        embed = discord.Embed(
            title=f"🚨 Anti-Nuke — {category} (caso #{numero})",
            description=dettaglio[:4096],
            color=discord.Color.red(),
        )
        if tolti:
            embed.set_footer(text=f"Per rilasciare e rimettere i ruoli: /antinuke rilascia caso:{numero}")
        await _alert_staff(guild, settings, embed)
        # SIC-011: se il server l'ha scelto, un attacco riconosciuto accende il panico.
        await panico_automatico(guild, f"Anti-Nuke: {category}")

    async def _punizione_in_vigore(
        self, guild: discord.Guild, actor_id: int, config: AntiNukeConfig
    ) -> bool:
        """True se l'autore non ha piu' potere: fuori dal server, o col ruolo di quarantena e nient'altro."""
        member = guild.get_member(actor_id)
        if member is None or config.punish_action == "ban":
            return member is None
        if member.bot:
            return False
        rimasti = [r for r in member.roles if not r.managed and not r.is_default()]
        if config.punish_action == "quarantine":
            qid = (await security_repo.get_settings(guild.id)).quarantine_role_id
            return qid is not None and any(r.id == qid for r in rimasti) and all(r.id == qid for r in rimasti)
        return not rimasti

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        await self._evento(
            channel.guild, NUKE_CATEGORY_CHANNEL, (discord.AuditLogAction.channel_create,),
            f"creato #{channel.name}", target_id=channel.id,
            categoria_canale_id=_categoria_del_canale(channel),
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        await self._evento(
            channel.guild, NUKE_CATEGORY_CHANNEL, (discord.AuditLogAction.channel_delete,),
            f"cancellato #{channel.name}", target_id=channel.id, cancellato=channel,
            categoria_canale_id=_categoria_del_canale(channel),
        )

    async def _ricrea_canale(self, channel: discord.abc.GuildChannel) -> None:
        """
        Ricrea un canale cancellato, dello stesso tipo, con nome,
        permessi, posizione e (dove esiste) argomento. I messaggi non
        si possono recuperare.
        """
        if channel.name == NOME_CANALE_NASCOSTO:
            # Canale che il bot non poteva vedere: Discord ne dà solo
            # un nome finto, ricrearlo sarebbe un danno.
            return

        guild = channel.guild
        opzioni: dict = {
            "name": channel.name,
            "position": channel.position,
            # I permessi di ruoli o membri spariti (Object) farebbero
            # rifiutare a Discord tutta la creazione.
            "overwrites": {
                bersaglio: permessi
                for bersaglio, permessi in channel.overwrites.items()
                if not isinstance(bersaglio, discord.Object)
            },
            "reason": MOTIVO_RECOVERY,
        }

        if isinstance(channel, discord.CategoryChannel):
            nuova = await guild.create_category(**opzioni)
            self._categorie_ricreate.set(channel.id, nuova)
            return

        # Se anche la categoria è stata cancellata e ricreata, il
        # canale torna in quella nuova.
        opzioni["category"] = channel.category or self._categorie_ricreate.get(channel.category_id)

        if isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
            if channel.topic:
                opzioni["topic"] = channel.topic
            opzioni["nsfw"] = channel.nsfw
            opzioni["slowmode_delay"] = channel.slowmode_delay
            if isinstance(channel, discord.TextChannel):
                await guild.create_text_channel(news=channel.is_news(), **opzioni)
            else:
                # I tag si ricreano nuovi (stesso nome, emoji, moderazione):
                # gli ID vecchi non esistono più.
                opzioni["available_tags"] = [
                    discord.ForumTag(name=tag.name, emoji=tag.emoji, moderated=tag.moderated)
                    for tag in channel.available_tags
                ]
                await guild.create_forum(media=channel.is_media(), **opzioni)
        elif isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            # La qualità audio non può superare quella che il server
            # ha adesso (dipende dai boost).
            opzioni["bitrate"] = min(channel.bitrate, int(guild.bitrate_limit))
            opzioni["user_limit"] = channel.user_limit
            if isinstance(channel, discord.StageChannel):
                await guild.create_stage_channel(**opzioni)
            else:
                await guild.create_voice_channel(nsfw=channel.nsfw, **opzioni)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        await self._evento(
            role.guild, NUKE_CATEGORY_ROLE, (discord.AuditLogAction.role_create,),
            f"creato ruolo {role.name}", target_id=role.id,
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        await self._evento(
            role.guild, NUKE_CATEGORY_ROLE, (discord.AuditLogAction.role_delete,),
            f"cancellato ruolo {role.name}", target_id=role.id, cancellato=role,
        )

    async def _ricrea_ruolo(self, role: discord.Role) -> None:
        """
        Ricrea un ruolo cancellato con le stesse impostazioni, nella
        posizione di prima (mai sopra il ruolo più alto del bot) e
        rimette il ruolo ai membri che lo avevano.
        """
        guild = role.guild
        nuovo = await guild.create_role(
            name=role.name,
            permissions=role.permissions,
            colour=role.colour,
            hoist=role.hoist,
            mentionable=role.mentionable,
            reason=MOTIVO_RECOVERY,
        )
        massima = guild.me.top_role.position - 1
        posizione = min(role.position, massima)
        if posizione >= 1:
            try:
                await nuovo.edit(position=posizione, reason=MOTIVO_RECOVERY)
            except discord.HTTPException as errore:
                logger.warning("Posizione del ruolo %s non ripristinata: %s", role.name, errore)

        membri = list(role.members)
        if len(membri) > MAX_MEMBRI_RIPRISTINO:
            logger.warning(
                "Ruolo %s: %d membri, ne rimetto solo %d.",
                role.name, len(membri), MAX_MEMBRI_RIPRISTINO,
            )
        for membro in membri[:MAX_MEMBRI_RIPRISTINO]:
            try:
                await membro.add_roles(nuovo, reason=MOTIVO_RECOVERY)
            except discord.HTTPException:
                continue

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel) -> None:
        await self._evento(
            channel.guild, NUKE_CATEGORY_WEBHOOK,
            (discord.AuditLogAction.webhook_create, discord.AuditLogAction.webhook_delete),
            f"webhook modificati in #{channel.name}",
        )

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before, after) -> None:
        # Le sound board non sono contate qui: emoji e sticker (sotto) sì.
        azione = discord.AuditLogAction.emoji_create if len(after) > len(before) else discord.AuditLogAction.emoji_delete
        await self._evento(guild, NUKE_CATEGORY_EMOJI, (azione,), "emoji del server modificate")

    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild: discord.Guild, before, after) -> None:
        azione = discord.AuditLogAction.sticker_create if len(after) > len(before) else discord.AuditLogAction.sticker_delete
        await self._evento(guild, NUKE_CATEGORY_EMOJI, (azione,), "sticker del server modificati")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.abc.User) -> None:
        await self._evento(
            guild, NUKE_CATEGORY_BAN_KICK, (discord.AuditLogAction.ban,),
            f"ban di {user}", target_id=user.id,
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        # Una pulizia dei membri inattivi (prune) non ha un kick per
        # ciascuno: la sua voce si legge una volta per gruppo (SIC-010).
        settings = await self._impostazioni_attive(member.guild)
        if settings is not None:
            await self._controlla_prune(member.guild, settings)
        # on_member_remove scatta anche per un'uscita volontaria: si
        # conta solo se nel registro c'è davvero un kick di questo
        # membro (senza voce il motore non conta niente).
        await self._evento(
            member.guild, NUKE_CATEGORY_BAN_KICK, (discord.AuditLogAction.kick,),
            f"kick di {member}", target_id=member.id, attese=ATTESE_REGISTRO_USCITA,
        )


    # ================================================================
    # Guardie su azioni singole (SIC-005…010, SIC-025)
    # ================================================================
    async def _autore_non_esente(
        self,
        guild: discord.Guild,
        settings: SecuritySettings,
        azione_registro: discord.AuditLogAction,
        azione_fiducia: str,
        target_id: int | None,
        attese: tuple[float, ...] = ATTESE_REGISTRO,
    ) -> int | None:
        """
        L'autore dell'azione se lo si trova nel registro e NON è esente
        (proprietario, bot stesso, fidato per questa azione); altrimenti
        None. Senza autore noto non si annulla niente: potrebbe essere il
        proprietario.
        """
        voce = await resolve_voce(guild, azione_registro, target_id, attese)
        if voce is None:
            return None
        autore = voce[0]
        if autore == self.bot.user.id or autore == guild.owner_id:
            return None
        if actor_is_trusted(autore, azione_fiducia, settings.anti_nuke):
            return None
        return autore

    async def _registra_intervento(
        self,
        guild: discord.Guild,
        settings: SecuritySettings,
        azione: str,
        autore: int | None,
        dettaglio: str,
        esito: str,
    ) -> int:
        """Log, caso numerato e avviso per un intervento che non è un conteggio."""
        completo = f"{dettaglio} — {esito}"
        await security_repo.log_action(guild.id, f"nuke_{azione}", autore, completo)
        numero = await security_repo.create_nuke_case(guild.id, autore, azione, completo, esito)
        embed = discord.Embed(
            title=f"🛡️ Anti-Nuke — {azione} (caso #{numero})",
            description=completo[:4096],
            color=discord.Color.orange(),
        )
        await _alert_staff(guild, settings, embed)
        return numero

    @staticmethod
    def _ruolo_pubblico(role: discord.Role) -> bool:
        """@everyone, o un ruolo che ha almeno metà dei membri del server (SIC-006)."""
        if role.is_default():
            return True
        totale = max(role.guild.member_count or 0, 1)
        return len(role.members) * 2 >= totale

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        """SIC-005/006: permessi pericolosi aggiunti a un ruolo da chi non è fidato."""
        guild = after.guild
        nuovi = [
            nome for nome in critical_permissions_of(dict(after.permissions))
            if nome not in critical_permissions_of(dict(before.permissions))
        ]
        if not nuovi:
            return
        settings = await self._impostazioni_attive(guild)
        if settings is None or settings.anti_nuke.role_perm_guard == "off":
            return
        if settings.anti_nuke.role_perm_guard == "public" and not self._ruolo_pubblico(after):
            return
        autore = await self._autore_non_esente(
            guild, settings, discord.AuditLogAction.role_update, NUKE_ACTION_ROLE_PERMS, after.id
        )
        if autore is None:
            return
        try:
            await after.edit(
                permissions=before.permissions,
                reason=f"Anti-Nuke: permessi pericolosi aggiunti da {autore}"[:MAX_MOTIVO],
            )
            esito = "permessi riportati a quelli di prima"
        except discord.HTTPException:
            esito = "tentativo di riportare i permessi fallito (il mio ruolo è sotto quel ruolo?)"
        await self._registra_intervento(
            guild, settings, NUKE_ACTION_ROLE_PERMS, autore,
            f"ruolo {after.name}: aggiunti {', '.join(nuovi)}", esito,
        )

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ) -> None:
        """SIC-007: cambi ai permessi dei canali, contati come le altre azioni di massa."""
        if before.overwrites == after.overwrites:
            return
        await self._evento(
            after.guild, NUKE_CATEGORY_CHANNEL_PERMS,
            (
                discord.AuditLogAction.overwrite_update,
                discord.AuditLogAction.overwrite_create,
                discord.AuditLogAction.overwrite_delete,
            ),
            f"permessi cambiati in #{after.name}", target_id=after.id,
            cancellato=("overwrites", after, before.overwrites),
            categoria_canale_id=_categoria_del_canale(after),
        )

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """SIC-008: ruolo con permessi pericolosi dato a un membro da chi non è fidato."""
        aggiunti = [r for r in after.roles if r not in before.roles]
        pericolosi = [
            r for r in aggiunti
            if not r.managed and not r.is_default() and critical_permissions_of(dict(r.permissions))
        ]
        if not pericolosi:
            return
        guild = after.guild
        settings = await self._impostazioni_attive(guild)
        if settings is None or not settings.anti_nuke.member_role_guard:
            return
        autore = await self._autore_non_esente(
            guild, settings, discord.AuditLogAction.member_role_update, NUKE_ACTION_MEMBER_ROLE, after.id
        )
        if autore is None:
            return
        try:
            await after.remove_roles(
                *pericolosi, reason=f"Anti-Nuke: ruolo pericoloso dato da {autore}"[:MAX_MOTIVO]
            )
            esito = "ruolo tolto"
        except discord.HTTPException:
            esito = "tentativo di togliere il ruolo fallito (il mio ruolo è più in basso?)"
        await self._registra_intervento(
            guild, settings, NUKE_ACTION_MEMBER_ROLE, autore,
            f"{after} ha ricevuto {', '.join(r.name for r in pericolosi)}", esito,
        )

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        """SIC-009: cambio del link personalizzato del server."""
        if before.vanity_url_code == after.vanity_url_code:
            return
        settings = await self._impostazioni_attive(after)
        if settings is None or not settings.anti_nuke.vanity_guard:
            return
        autore = await self._autore_non_esente(
            after, settings, discord.AuditLogAction.guild_update, NUKE_ACTION_VANITY, after.id
        )
        if autore is None:
            return
        prima, dopo = before.vanity_url_code, after.vanity_url_code
        esito = "link non ripristinato (non c'era un link prima)"
        if prima:
            try:
                # Discord non lo offre a discord.py: è la stessa chiamata che usa
                # il client. Richiede che il server abbia ancora il livello di boost.
                await self.bot.http.request(
                    discord.http.Route("PATCH", "/guilds/{guild_id}/vanity-url", guild_id=after.id),
                    json={"code": prima},
                    reason="Anti-Nuke: link personalizzato ripristinato",
                )
                esito = f"link ripristinato a /{prima}"
            except discord.HTTPException:
                esito = f"ripristino di /{prima} fallito (boost insufficienti o permesso mancante): rimettilo a mano"
        await self._registra_intervento(
            after, settings, NUKE_ACTION_VANITY, autore,
            f"link personalizzato cambiato da /{prima} a /{dopo}", esito,
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """SIC-025: un bot aggiunto da chi non è autorizzato viene espulso."""
        if not member.bot or member.id == self.bot.user.id:
            return
        guild = member.guild
        settings = await self._impostazioni_attive(guild)
        if settings is None or not settings.anti_nuke.bot_add_guard:
            return
        autore = await self._autore_non_esente(
            guild, settings, discord.AuditLogAction.bot_add, NUKE_ACTION_BOT_ADD, member.id
        )
        if autore is None:
            return
        try:
            await member.kick(reason=f"Anti-Nuke: bot aggiunto da {autore}, che non è autorizzato"[:MAX_MOTIVO])
            esito = "bot espulso"
        except discord.HTTPException:
            esito = "tentativo di espellere il bot fallito (il mio ruolo è più in basso?)"
        await self._registra_intervento(
            guild, settings, NUKE_ACTION_BOT_ADD, autore, f"bot {member} ({member.id}) aggiunto", esito
        )

    async def _controlla_prune(self, guild: discord.Guild, settings: SecuritySettings) -> None:
        """
        SIC-010: una pulizia dei membri inattivi (prune) fa uscire molti
        membri senza una voce "kick" ciascuno: c'è una sola voce
        "member_prune" col numero dei rimossi, contata come ban/kick di
        massa. Si legge una volta ogni pochi secondi per server.
        """
        adesso = discord.utils.utcnow()
        ultimo = self._prune.get(guild.id)
        if ultimo is not None and (adesso - ultimo[0]).total_seconds() < PAUSA_CONTROLLO_PRUNE:
            return
        self._prune.set(guild.id, (adesso, ultimo[1] if ultimo else None))
        try:
            async for voce in guild.audit_logs(action=discord.AuditLogAction.member_prune, limit=3):
                if (adesso - voce.created_at).total_seconds() > LOOKBACK_REGISTRO_SECONDI * 3:
                    break
                if ultimo is not None and ultimo[1] == voce.id:
                    return
                self._prune.set(guild.id, (adesso, voce.id))
                rimossi = int(getattr(voce.extra, "members_removed", 0) or 0)
                await self._handle_event(
                    guild, NUKE_CATEGORY_BAN_KICK, voce.user_id,
                    f"pulizia (prune) di {rimossi} membri", settings,
                    conteggio_azioni=min(max(rimossi, 1), MAX_PRUNE_CONTATI),
                )
                return
        except discord.HTTPException:
            return


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_ANTI_NUKE,
            display_name="Anti-Nuke",
            category="security",
            description="Rilevamento e risposta automatica ad azioni distruttive di massa sul server.",
            premium_capable=True,
        )
    )
    await bot.add_cog(AntiNukeCog(bot))
