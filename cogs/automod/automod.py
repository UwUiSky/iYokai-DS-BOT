"""
cogs/automod/automod.py
==========================
Ponte tra la configurazione salvata (core/repositories/automod_repo.py)
e le regole AutoMod native di Discord (core/automod_sync.py per la
logica di decisione). Modulo SEMPRE GRATUITO (MODULE_AUTOMOD), come
da schema — "Filtri base" è [Free].

Ogni comando che cambia la configurazione richiama subito
`_sync_guild()`: l'esperienza voluta è "plug and play" — l'admin
aggiunge una parola e la regola Discord viene aggiornata all'istante,
senza un comando /automod sync separato da ricordarsi di lanciare.

Questo file contiene ANCHE i filtri AutoMod avanzati lato bot
(SPEC.md §6.3-§6.14: anti-link, anti-spam, anti-caps, anti-zalgo,
anti-mass-mention, eccezioni per canale/ruolo, azioni configurabili,
log) — stesso modulo/stesso cog dei filtri base sopra, non uno
separato: sono entrambi "AutoMod", solo con motore diverso (native
Discord vs. `on_message` nel bot), e vivono sotto lo stesso comando
`/automod`.
"""

# DA FARE (issue #58, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §2 (AutoMod).
# DA FARE (issue #102, fase F13): NF-31, Blocco dei link di phishing.
#   Vedi revisione/02-piano/NUOVE_FUNZIONI.md.

from __future__ import annotations

import io
import logging
import re
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from core.automod_sync import DesiredRule, ExistingRule, SyncActionType, compute_sync_plan
from core.automod_advanced_logic import (
    AntiLinkConfig,
    AutomodAdvancedConfig,
    CapsFilterConfig,
    MessageSignals,
    RateFilterConfig,
    ThresholdFilterConfig,
    VIOLATION_ANTI_LINK,
    VIOLATION_ATTACHMENT_SPAM,
    VIOLATION_CAPS,
    VIOLATION_MASS_MENTION,
    VIOLATION_SPAM_EMOJI,
    VIOLATION_SPAM_MESSAGES,
    VIOLATION_SPAM_STICKER,
    VIOLATION_ZALGO,
    evaluate_message_violations,
    extract_domains,
)
from core.automod_rate_tracker import rate_tracker
from core.repositories.automod_repo import automod_repo
from core.repositories.automod_advanced_repo import (
    AutomodAdvancedSettings,
    VALID_ACTIONS,
    automod_advanced_repo,
)
from core.repositories.moderation_repo import moderation_repo
from core.database import db
from core.premium import PremiumModule, registry
from cogs.moderation._shared import ensure_module_enabled, post_to_mod_log, try_dm

logger = logging.getLogger("iyokai.automod")

MODULE_AUTOMOD = "automod"

# Oltre questa lunghezza /automod badword-list manda l'elenco come file
# (un messaggio Discord tiene 2000 caratteri).
MAX_ELENCO_IN_CHAT = 1900

# Discord accetta al massimo 60 caratteri per parola in una regola
# AutoMod: una parola più lunga farebbe fallire ogni sincronizzazione.
MAX_LUNGHEZZA_PAROLA = 60

# Regex di riconoscimento emoji per §6.5 (anti-spam emoji): emoji
# custom di Discord (`<a?:nome:id>`) + un intervallo unicode ampio
# che copre la stragrande maggioranza delle emoji standard. Non usa
# la libreria `emoji` (non una dipendenza del progetto): un
# sotto-conteggio occasionale su emoji unicode rare è accettabile,
# le custom (le più usate per lo spam vero, tipo emoji server-specific
# ripetute) sono coperte al 100%.
_CUSTOM_EMOJI_RE = re.compile(r"<a?:\w+:\d+>")
_UNICODE_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]"
)

_VIOLATION_LABELS = {
    VIOLATION_ANTI_LINK: "Anti-Link",
    VIOLATION_SPAM_MESSAGES: "Anti-Spam Messaggi",
    VIOLATION_SPAM_EMOJI: "Anti-Spam Emoji",
    VIOLATION_SPAM_STICKER: "Anti-Spam Sticker",
    VIOLATION_CAPS: "Anti-Caps",
    VIOLATION_ZALGO: "Anti-Zalgo",
    VIOLATION_MASS_MENTION: "Anti-Mass-Mention",
    VIOLATION_ATTACHMENT_SPAM: "Anti-Attachment-Spam",
}


def _count_emoji(content: str) -> int:
    return len(_CUSTOM_EMOJI_RE.findall(content)) + len(_UNICODE_EMOJI_RE.findall(content))


def _mention_count(message: discord.Message) -> int:
    # @everyone/@here contano come "molte menzioni insieme" per far
    # scattare comunque anti-mass-mention anche senza un numero
    # esplicito di utenti — scelta per inferenza, nessun dettaglio
    # più fine specificato.
    extra = 999 if message.mention_everyone else 0
    return len(message.mentions) + len(message.role_mentions) + extra


def build_message_signals(message: discord.Message) -> MessageSignals:
    """
    Estrae dal messaggio REALE tutto quello che serve alla logica
    pura (core/automod_advanced_logic.py) — i conteggi "nel tempo"
    (rate) passano dal tracker in memoria, mai persistiti (vedi
    core/automod_rate_tracker.py).
    """
    now = discord.utils.utcnow()
    guild_id = message.guild.id
    user_id = message.author.id

    recent_messages = rate_tracker.record_and_count(guild_id, user_id, "messages", now, window_seconds=10)
    recent_attachments = 0
    if message.attachments:
        recent_attachments = rate_tracker.record_and_count(
            guild_id, user_id, "attachments", now, window_seconds=30
        )
    recent_stickers = 0
    if message.stickers:
        recent_stickers = rate_tracker.record_and_count(
            guild_id, user_id, "stickers", now, window_seconds=30
        )

    return MessageSignals(
        content=message.content or "",
        mention_count=_mention_count(message),
        emoji_count=_count_emoji(message.content or ""),
        attachment_count=len(message.attachments),
        sticker_count=len(message.stickers),
        recent_message_count=recent_messages,
        recent_attachment_count=recent_attachments,
        recent_sticker_count=recent_stickers,
    )


def is_member_exempt(member: discord.Member, settings: AutomodAdvancedSettings, channel_id: int) -> bool:
    if channel_id in settings.exempt_channel_ids:
        return True
    ruoli_membro = {role.id for role in member.roles}
    return bool(ruoli_membro & set(settings.exempt_role_ids))


def _is_safe_from_automated_action(member: discord.Member) -> bool:
    """
    Rete di sicurezza per mute/ban automatici: mai su chi ha
    `manage_guild` o è il proprietario del server — un falso
    positivo che bannasse per errore un admin dello staff sarebbe un
    danno molto peggiore di un messaggio malevolo lasciato
    temporaneamente visibile. Non si applica a "delete"/"warn" (poco
    invasivi, reversibili). Scelta di sicurezza per inferenza, non
    richiesta esplicitamente.
    """
    if member.guild.owner_id == member.id:
        return True
    return member.guild_permissions.administrator or member.guild_permissions.manage_guild


async def _execute_actions(
    message: discord.Message,
    violation: str,
    actions: tuple[str, ...],
    settings: AutomodAdvancedSettings,
) -> tuple[str, ...]:
    """
    Esegue le azioni configurate per questa violazione, nell'ordine
    di VALID_ACTIONS (delete sempre prima). Restituisce quelle
    DAVVERO eseguite (per il log) — un'azione può non applicarsi
    (es. mute/ban su un admin protetto) senza bloccare le altre.
    """
    member = message.author
    eseguite = []
    protetto = _is_safe_from_automated_action(member)

    for azione in VALID_ACTIONS:
        if azione not in actions:
            continue

        if azione == "delete":
            try:
                await message.delete()
                eseguite.append("delete")
            except (discord.NotFound, discord.Forbidden):
                pass
            continue

        if protetto and azione in ("mute", "ban"):
            continue

        if azione == "warn":
            reason = f"AutoMod: {_VIOLATION_LABELS.get(violation, violation)}"
            case_number = await moderation_repo.create_case(
                guild_id=message.guild.id,
                user_id=member.id,
                moderator_id=message.guild.me.id if message.guild.me else member.id,
                action_type="warn",
                reason=reason,
            )
            embed = discord.Embed(
                title="⚠️ Warn automatico (AutoMod)",
                description=f"Caso #{case_number} — {reason}",
                color=discord.Color.yellow(),
            )
            await try_dm(member, embed)
            await post_to_mod_log(message.guild, embed)
            eseguite.append("warn")

        elif azione == "mute":
            try:
                await member.timeout(
                    timedelta(seconds=settings.mute_duration_seconds),
                    reason=f"AutoMod: {_VIOLATION_LABELS.get(violation, violation)}",
                )
                eseguite.append("mute")
            except (discord.Forbidden, discord.HTTPException):
                pass

        elif azione == "ban":
            try:
                await member.ban(
                    reason=f"AutoMod: {_VIOLATION_LABELS.get(violation, violation)}",
                    delete_message_seconds=0,
                )
                eseguite.append("ban")
            except (discord.Forbidden, discord.HTTPException):
                pass

    return tuple(eseguite)


async def _log_violation(
    message: discord.Message,
    violation: str,
    actions_taken: tuple[str, ...],
    settings: AutomodAdvancedSettings,
) -> None:
    contenuto = (message.content or "")[:200]
    await automod_advanced_repo.log_action(
        message.guild.id, message.author.id, message.channel.id, violation, actions_taken, contenuto
    )

    if settings.log_channel_id is None:
        return
    canale = message.guild.get_channel(settings.log_channel_id)
    if not isinstance(canale, discord.TextChannel):
        return

    embed = discord.Embed(
        title=f"🛡️ AutoMod — {_VIOLATION_LABELS.get(violation, violation)}",
        color=discord.Color.orange(),
    )
    embed.add_field(name="Utente", value=f"{message.author.mention} ({message.author.id})", inline=False)
    embed.add_field(name="Canale", value=message.channel.mention, inline=True)
    embed.add_field(name="Azioni eseguite", value=", ".join(actions_taken) or "nessuna", inline=True)
    if contenuto:
        embed.add_field(name="Contenuto", value=contenuto, inline=False)
    try:
        await canale.send(embed=embed)
    except discord.HTTPException:
        pass

# Nomi delle regole che iYokai gestisce, sempre con il prefisso
# convenzionale (vedi core/automod_sync.py) così non vengono mai
# confuse con regole create a mano dall'admin.
RULE_NAME_BADWORDS = "iYokai — Parole Vietate"
RULE_NAME_INVITES = "iYokai — Anti-Invite"

# Pattern regex per riconoscere inviti Discord in ogni loro forma
# comune. Discord AutoMod applica i regex ai messaggi in arrivo.
INVITE_REGEX_PATTERNS = (
    r"discord\.gg/\S+",
    r"discord\.com/invite/\S+",
    r"discordapp\.com/invite/\S+",
)


def _build_desired_rules(
    custom_badwords: tuple[str, ...],
    block_invites: bool,
    last_synced_badwords: tuple[str, ...],
    last_synced_invite_regex: tuple[str, ...],
) -> list[DesiredRule]:
    """
    Costruisce le regole desiderate SEMPRE, anche quando il
    contenuto è vuoto (es. l'admin ha rimosso l'ultima parola): il
    merge a tre vie in core/automod_sync.py deve comunque poter
    valutare se restano parole "dell'admin" da preservare o se la
    regola va eliminata — vedi compute_sync_plan().
    """
    return [
        DesiredRule(
            name=RULE_NAME_BADWORDS,
            keywords=custom_badwords,
            previously_synced_keywords=last_synced_badwords,
        ),
        DesiredRule(
            name=RULE_NAME_INVITES,
            regex_patterns=INVITE_REGEX_PATTERNS if block_invites else (),
            previously_synced_regex=last_synced_invite_regex,
        ),
    ]


async def _sync_guild(guild: discord.Guild) -> str | None:
    """
    Esegue davvero la sincronizzazione: legge le regole esistenti da
    Discord, calcola il piano (logica pura, testata separatamente in
    tests/test_automod_sync.py), ed esegue create/edit/delete per le
    azioni che lo richiedono. Dopo ogni azione riuscita, aggiorna
    anche `automod_last_synced` — è quello che permette al PROSSIMO
    sync di distinguere correttamente "parole nostre" da "parole
    dell'admin" (vedi core/automod_sync.py per il perché serve).

    Restituisce un messaggio di avviso se qualcosa è stato troncato
    per un limite di Discord, altrimenti None.
    """
    try:
        rules = await guild.fetch_automod_rules()
    except discord.Forbidden:
        return (
            "Non ho i permessi per leggere/gestire le regole AutoMod "
            "di questo server (serve Manage Server)."
        )

    existing = [
        ExistingRule(
            name=rule.name,
            keywords=tuple(rule.trigger.keyword_filter or ()),
            regex_patterns=tuple(rule.trigger.regex_patterns or ()),
        )
        for rule in rules
    ]
    # Indicizzato per nome, serve per recuperare l'oggetto AutoModRule
    # vero su cui chiamare .edit()/.delete() quando il piano lo richiede.
    rules_by_name = {rule.name: rule for rule in rules}

    config = await automod_repo.get_config(guild.id)
    last_synced_badwords, _ = await automod_repo.get_last_synced(guild.id, RULE_NAME_BADWORDS)
    _, last_synced_invite_regex = await automod_repo.get_last_synced(guild.id, RULE_NAME_INVITES)

    desired = _build_desired_rules(
        config.custom_badwords,
        config.block_invites,
        last_synced_badwords,
        last_synced_invite_regex,
    )

    plan = compute_sync_plan(existing, desired)

    truncated_any = False
    for action in plan:
        truncated_any = truncated_any or action.truncated

        if action.action == SyncActionType.SKIP:
            continue

        if action.action == SyncActionType.DELETE:
            existing_rule = rules_by_name.get(action.name)
            if existing_rule is not None:
                await existing_rule.delete(reason="Nessun contenuto residuo da mantenere")
            await automod_repo.clear_last_synced(guild.id, action.name)
            continue

        actions_payload = [
            discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)
        ]

        if action.name == RULE_NAME_BADWORDS:
            trigger = discord.AutoModTrigger(
                type=discord.AutoModRuleTriggerType.keyword,
                keyword_filter=list(action.final_keywords),
            )
        else:
            trigger = discord.AutoModTrigger(
                type=discord.AutoModRuleTriggerType.keyword,
                regex_patterns=list(action.final_regex),
            )

        if action.action == SyncActionType.CREATE:
            await guild.create_automod_rule(
                name=action.name,
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=trigger,
                actions=actions_payload,
                enabled=True,
                reason="Sincronizzazione automatica iYokai AutoMod",
            )
        elif action.action == SyncActionType.UPDATE:
            existing_rule = rules_by_name[action.name]
            await existing_rule.edit(
                trigger=trigger,
                reason="Sincronizzazione automatica iYokai AutoMod",
            )

        # Registra cosa abbiamo scritto DAVVERO, solo dopo che la
        # chiamata a Discord è andata a buon fine — se fosse fallita,
        # l'eccezione avrebbe già interrotto il ciclo prima di questa
        # riga, e last_synced resterebbe correttamente quello vecchio.
        await automod_repo.set_last_synced(
            guild.id, action.name, action.final_keywords, action.final_regex
        )

    if truncated_any:
        return (
            "Attenzione: una o più regole hanno superato il limite di "
            "Discord (1000 parole o 10 pattern regex per regola) e "
            "sono state troncate. Le voci in eccesso non sono state "
            "applicate."
        )
    return None


class AutomodCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    automod_group = app_commands.Group(
        name="automod", description="Configura il filtro automatico dei messaggi."
    )

    @automod_group.command(name="badword-add", description="Aggiunge una parola vietata.")
    @app_commands.describe(word="La parola da vietare (massimo 60 caratteri)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def badword_add(
        self,
        interaction: discord.Interaction,
        word: app_commands.Range[str, 1, MAX_LUNGHEZZA_PAROLA],
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return

        await interaction.response.defer(ephemeral=True)
        await automod_repo.add_badword(interaction.guild.id, word)
        avviso = await _sync_guild(interaction.guild)

        messaggio = f"Parola `{word}` aggiunta alla lista vietata."
        if avviso:
            messaggio += f"\n⚠️ {avviso}"
        await interaction.followup.send(messaggio, ephemeral=True)

    @automod_group.command(name="badword-remove", description="Rimuove una parola vietata.")
    @app_commands.describe(word="La parola da rimuovere (massimo 60 caratteri)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def badword_remove(
        self,
        interaction: discord.Interaction,
        word: app_commands.Range[str, 1, MAX_LUNGHEZZA_PAROLA],
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return

        await interaction.response.defer(ephemeral=True)
        await automod_repo.remove_badword(interaction.guild.id, word)
        avviso = await _sync_guild(interaction.guild)

        messaggio = (
            f"Parola `{word}` rimossa: la regola AutoMod su Discord è "
            f"stata aggiornata subito. Eventuali parole aggiunte a mano "
            f"dallo staff direttamente dal pannello Discord non vengono "
            f"toccate."
        )
        if avviso:
            messaggio += f"\n⚠️ {avviso}"
        await interaction.followup.send(messaggio, ephemeral=True)

    @automod_group.command(name="badword-list", description="Mostra le parole vietate configurate.")
    async def badword_list(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return

        config = await automod_repo.get_config(interaction.guild.id)
        if not config.custom_badwords:
            await interaction.response.send_message(
                "Nessuna parola vietata configurata.", ephemeral=True
            )
            return

        totale = len(config.custom_badwords)
        lista = ", ".join(f"`{w}`" for w in config.custom_badwords)
        testo = f"Parole vietate configurate ({totale}): {lista}"
        if len(testo) <= MAX_ELENCO_IN_CHAT:
            await interaction.response.send_message(testo, ephemeral=True)
            return

        # Un messaggio tiene 2000 caratteri: un elenco lungo va in un file.
        contenuto = "\n".join(config.custom_badwords).encode("utf-8")
        await interaction.response.send_message(
            f"Parole vietate configurate ({totale}): l'elenco è lungo, "
            f"lo trovi nel file allegato.",
            file=discord.File(io.BytesIO(contenuto), filename="parole_vietate.txt"),
            ephemeral=True,
        )

    @automod_group.command(
        name="invites", description="Attiva o disattiva il blocco automatico degli inviti Discord."
    )
    @app_commands.describe(enabled="True per bloccare gli inviti, False per consentirli")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def invites(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return

        await interaction.response.defer(ephemeral=True)
        await automod_repo.set_block_invites(interaction.guild.id, enabled)
        avviso = await _sync_guild(interaction.guild)

        stato = "attivato" if enabled else "disattivato"
        messaggio = f"Blocco automatico degli inviti Discord {stato}."
        if avviso:
            messaggio += f"\n⚠️ {avviso}"
        await interaction.followup.send(messaggio, ephemeral=True)

    @automod_group.command(
        name="sync", description="Forza una sincronizzazione manuale delle regole AutoMod."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sync(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return

        await interaction.response.defer(ephemeral=True)
        avviso = await _sync_guild(interaction.guild)
        await interaction.followup.send(avviso or "Sincronizzazione completata.", ephemeral=True)

    # ================================================================
    # Filtri avanzati lato bot (SPEC.md §6.3-§6.10)
    # ================================================================
    @automod_group.command(name="anti-link-mode", description="Imposta la modalità del filtro link.")
    @app_commands.describe(mode="off = disattivato, whitelist = blocca tutto tranne i domini elencati, blacklist = blocca solo i domini elencati")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Disattivato", value="off"),
            app_commands.Choice(name="Whitelist", value="whitelist"),
            app_commands.Choice(name="Blacklist", value="blacklist"),
        ]
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def anti_link_mode(self, interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        nuova = _replace_settings(settings, anti_link=AntiLinkConfig(
            mode=mode.value, whitelist=settings.config.anti_link.whitelist, blacklist=settings.config.anti_link.blacklist,
        ))
        await automod_advanced_repo.save_settings(nuova)
        await interaction.response.send_message(f"Modalità anti-link impostata su **{mode.name}**.", ephemeral=True)

    @automod_group.command(name="anti-link-domain", description="Aggiunge o rimuove un dominio dalla whitelist/blacklist link.")
    @app_commands.describe(action="add o remove", lista="whitelist o blacklist", domain="Il dominio, es. esempio.com")
    @app_commands.choices(
        action=[app_commands.Choice(name="Aggiungi", value="add"), app_commands.Choice(name="Rimuovi", value="remove")],
        lista=[app_commands.Choice(name="Whitelist", value="whitelist"), app_commands.Choice(name="Blacklist", value="blacklist")],
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def anti_link_domain(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        lista: app_commands.Choice[str],
        domain: str,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        dominio = domain.strip().lower()
        attuale = settings.config.anti_link.whitelist if lista.value == "whitelist" else settings.config.anti_link.blacklist

        if action.value == "add":
            aggiornata = tuple(attuale) if dominio in attuale else tuple(attuale) + (dominio,)
        else:
            aggiornata = tuple(d for d in attuale if d != dominio)

        nuovo_link_config = AntiLinkConfig(
            mode=settings.config.anti_link.mode,
            whitelist=aggiornata if lista.value == "whitelist" else settings.config.anti_link.whitelist,
            blacklist=aggiornata if lista.value == "blacklist" else settings.config.anti_link.blacklist,
        )
        await automod_advanced_repo.save_settings(_replace_settings(settings, anti_link=nuovo_link_config))
        await interaction.response.send_message(
            f"Dominio `{dominio}` {'aggiunto a' if action.value == 'add' else 'rimosso da'} {lista.name}.",
            ephemeral=True,
        )

    @automod_group.command(name="anti-spam-messages", description="Configura l'anti-spam messaggi (troppi messaggi in poco tempo).")
    @app_commands.describe(enabled="Attiva/disattiva", max_messages="Numero massimo consentito", seconds="Finestra in secondi")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def anti_spam_messages(
        self, interaction: discord.Interaction, enabled: bool, max_messages: int = 5, seconds: int = 10
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        nuova = _replace_settings(
            settings,
            anti_spam_messages=RateFilterConfig(enabled=enabled, max_count=max_messages, window_seconds=seconds),
        )
        await automod_advanced_repo.save_settings(nuova)
        await interaction.response.send_message(
            f"Anti-spam messaggi {'attivato' if enabled else 'disattivato'} (max {max_messages} ogni {seconds}s).",
            ephemeral=True,
        )

    @automod_group.command(name="anti-spam-emoji", description="Configura l'anti-spam emoji (troppe emoji in un messaggio).")
    @app_commands.describe(enabled="Attiva/disattiva", max_emoji="Numero massimo di emoji per messaggio")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def anti_spam_emoji(self, interaction: discord.Interaction, enabled: bool, max_emoji: int = 5) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        nuova = _replace_settings(settings, anti_spam_emoji=ThresholdFilterConfig(enabled=enabled, max_count=max_emoji))
        await automod_advanced_repo.save_settings(nuova)
        await interaction.response.send_message(
            f"Anti-spam emoji {'attivato' if enabled else 'disattivato'} (max {max_emoji} per messaggio).",
            ephemeral=True,
        )

    @automod_group.command(name="anti-spam-sticker", description="Configura l'anti-spam sticker (troppi sticker in poco tempo).")
    @app_commands.describe(enabled="Attiva/disattiva", max_sticker="Numero massimo consentito", seconds="Finestra in secondi")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def anti_spam_sticker(
        self, interaction: discord.Interaction, enabled: bool, max_sticker: int = 3, seconds: int = 30
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        nuova = _replace_settings(
            settings,
            anti_spam_sticker=RateFilterConfig(enabled=enabled, max_count=max_sticker, window_seconds=seconds),
        )
        await automod_advanced_repo.save_settings(nuova)
        await interaction.response.send_message(
            f"Anti-spam sticker {'attivato' if enabled else 'disattivato'} (max {max_sticker} ogni {seconds}s).",
            ephemeral=True,
        )

    @automod_group.command(name="anti-caps", description="Configura l'anti-caps (troppo maiuscolo).")
    @app_commands.describe(enabled="Attiva/disattiva", percent="Percentuale di lettere maiuscole per far scattare il filtro", min_length="Lunghezza minima del messaggio (in lettere) da valutare")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def anti_caps(
        self, interaction: discord.Interaction, enabled: bool, percent: int = 70, min_length: int = 10
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        nuova = _replace_settings(
            settings, anti_caps=CapsFilterConfig(enabled=enabled, threshold_percent=percent, min_length=min_length)
        )
        await automod_advanced_repo.save_settings(nuova)
        await interaction.response.send_message(
            f"Anti-caps {'attivato' if enabled else 'disattivato'} (soglia {percent}%, min {min_length} lettere).",
            ephemeral=True,
        )

    @automod_group.command(name="anti-zalgo", description="Attiva o disattiva l'anti-zalgo (testo con segni diacritici anomali).")
    @app_commands.describe(enabled="Attiva/disattiva")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def anti_zalgo(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        nuova = _replace_settings(settings, anti_zalgo_enabled=enabled)
        await automod_advanced_repo.save_settings(nuova)
        await interaction.response.send_message(f"Anti-zalgo {'attivato' if enabled else 'disattivato'}.", ephemeral=True)

    @automod_group.command(name="anti-mention", description="Configura l'anti-mass-mention (troppi utenti taggati in un messaggio).")
    @app_commands.describe(enabled="Attiva/disattiva", max_mentions="Numero massimo di menzioni per messaggio")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def anti_mention(self, interaction: discord.Interaction, enabled: bool, max_mentions: int = 5) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        nuova = _replace_settings(settings, anti_mass_mention=ThresholdFilterConfig(enabled=enabled, max_count=max_mentions))
        await automod_advanced_repo.save_settings(nuova)
        await interaction.response.send_message(
            f"Anti-mass-mention {'attivato' if enabled else 'disattivato'} (max {max_mentions} per messaggio).",
            ephemeral=True,
        )

    @automod_group.command(name="anti-attachment", description="Configura l'anti-attachment-spam (troppi allegati in poco tempo).")
    @app_commands.describe(enabled="Attiva/disattiva", max_attachments="Numero massimo consentito", seconds="Finestra in secondi")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def anti_attachment(
        self, interaction: discord.Interaction, enabled: bool, max_attachments: int = 5, seconds: int = 30
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        nuova = _replace_settings(
            settings,
            anti_attachment_spam=RateFilterConfig(enabled=enabled, max_count=max_attachments, window_seconds=seconds),
        )
        await automod_advanced_repo.save_settings(nuova)
        await interaction.response.send_message(
            f"Anti-attachment-spam {'attivato' if enabled else 'disattivato'} (max {max_attachments} ogni {seconds}s).",
            ephemeral=True,
        )

    # ================================================================
    # Eccezioni per canale/ruolo (SPEC.md §6.11/§6.12) — bypassano
    # TUTTI i filtri avanzati sopra, non uno specifico: un canale
    # #shitpost o il ruolo Staff pensati per essere fuori scope
    # dall'automod in generale, non filtro per filtro (altrimenti
    # servirebbero N eccezioni per N filtri, complessità non richiesta)
    # ================================================================
    @automod_group.command(name="exempt-channel-add", description="Esenta un canale da tutti i filtri AutoMod avanzati.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def exempt_channel_add(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        if channel.id not in settings.exempt_channel_ids:
            nuova = _replace_settings(settings, exempt_channel_ids=settings.exempt_channel_ids + (channel.id,))
            await automod_advanced_repo.save_settings(nuova)
        await interaction.response.send_message(f"Canale {channel.mention} esentato dai filtri avanzati.", ephemeral=True)

    @automod_group.command(name="exempt-channel-remove", description="Rimuove l'esenzione di un canale.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def exempt_channel_remove(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        nuova = _replace_settings(
            settings, exempt_channel_ids=tuple(c for c in settings.exempt_channel_ids if c != channel.id)
        )
        await automod_advanced_repo.save_settings(nuova)
        await interaction.response.send_message(f"Esenzione rimossa per {channel.mention}.", ephemeral=True)

    @automod_group.command(name="exempt-role-add", description="Esenta un ruolo da tutti i filtri AutoMod avanzati.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def exempt_role_add(self, interaction: discord.Interaction, role: discord.Role) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        if role.id not in settings.exempt_role_ids:
            nuova = _replace_settings(settings, exempt_role_ids=settings.exempt_role_ids + (role.id,))
            await automod_advanced_repo.save_settings(nuova)
        await interaction.response.send_message(f"Ruolo {role.mention} esentato dai filtri avanzati.", ephemeral=True)

    @automod_group.command(name="exempt-role-remove", description="Rimuove l'esenzione di un ruolo.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def exempt_role_remove(self, interaction: discord.Interaction, role: discord.Role) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        nuova = _replace_settings(
            settings, exempt_role_ids=tuple(r for r in settings.exempt_role_ids if r != role.id)
        )
        await automod_advanced_repo.save_settings(nuova)
        await interaction.response.send_message(f"Esenzione rimossa per {role.mention}.", ephemeral=True)

    # ================================================================
    # Azioni configurabili + log (SPEC.md §6.13/§6.14)
    # ================================================================
    @automod_group.command(name="actions-set", description="Configura quali azioni eseguire quando un filtro avanzato scatta.")
    @app_commands.describe(
        violation="Quale filtro", delete="Cancella il messaggio", warn="Assegna un warn",
        mute="Timeout temporaneo (durata: /automod mute-duration)", ban="Banna l'utente",
    )
    @app_commands.choices(
        violation=[app_commands.Choice(name=label, value=key) for key, label in _VIOLATION_LABELS.items()]
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def actions_set(
        self,
        interaction: discord.Interaction,
        violation: app_commands.Choice[str],
        delete: bool = True,
        warn: bool = False,
        mute: bool = False,
        ban: bool = False,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        scelte = tuple(
            nome for nome, attiva in (("delete", delete), ("warn", warn), ("mute", mute), ("ban", ban)) if attiva
        )
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        nuove_azioni = dict(settings.actions)
        nuove_azioni[violation.value] = scelte
        await automod_advanced_repo.save_settings(_replace_settings(settings, actions=nuove_azioni))
        await interaction.response.send_message(
            f"Azioni per **{violation.name}** impostate: {', '.join(scelte) or 'nessuna'}.", ephemeral=True
        )

    @automod_group.command(name="mute-duration", description="Imposta la durata del timeout usato dall'azione 'mute' dell'AutoMod.")
    @app_commands.describe(seconds="Durata in secondi (max 28 giorni, limite di Discord)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def mute_duration(self, interaction: discord.Interaction, seconds: int) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        limite = 28 * 24 * 3600
        if seconds <= 0 or seconds > limite:
            await interaction.response.send_message(
                f"La durata deve essere tra 1 secondo e {limite} secondi (28 giorni, limite di Discord).",
                ephemeral=True,
            )
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        await automod_advanced_repo.save_settings(_replace_settings(settings, mute_duration_seconds=seconds))
        await interaction.response.send_message(f"Durata del mute AutoMod impostata a {seconds} secondi.", ephemeral=True)

    @automod_group.command(name="log-channel", description="Imposta il canale dove pubblicare il log delle azioni AutoMod avanzate.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        await automod_advanced_repo.save_settings(_replace_settings(settings, log_channel_id=channel.id))
        await interaction.response.send_message(f"Canale di log AutoMod impostato su {channel.mention}.", ephemeral=True)

    @automod_group.command(name="status", description="Mostra la configurazione attuale dei filtri AutoMod avanzati.")
    async def status(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        c = settings.config
        righe = [
            f"**Anti-Link**: {c.anti_link.mode}",
            f"**Anti-Spam Messaggi**: {'ON' if c.anti_spam_messages.enabled else 'OFF'} (max {c.anti_spam_messages.max_count}/{c.anti_spam_messages.window_seconds}s)",
            f"**Anti-Spam Emoji**: {'ON' if c.anti_spam_emoji.enabled else 'OFF'} (max {c.anti_spam_emoji.max_count})",
            f"**Anti-Spam Sticker**: {'ON' if c.anti_spam_sticker.enabled else 'OFF'} (max {c.anti_spam_sticker.max_count}/{c.anti_spam_sticker.window_seconds}s)",
            f"**Anti-Caps**: {'ON' if c.anti_caps.enabled else 'OFF'} (soglia {c.anti_caps.threshold_percent}%)",
            f"**Anti-Zalgo**: {'ON' if c.anti_zalgo_enabled else 'OFF'}",
            f"**Anti-Mass-Mention**: {'ON' if c.anti_mass_mention.enabled else 'OFF'} (max {c.anti_mass_mention.max_count})",
            f"**Anti-Attachment-Spam**: {'ON' if c.anti_attachment_spam.enabled else 'OFF'} (max {c.anti_attachment_spam.max_count}/{c.anti_attachment_spam.window_seconds}s)",
            f"**Canali esenti**: {len(settings.exempt_channel_ids)}",
            f"**Ruoli esenti**: {len(settings.exempt_role_ids)}",
            f"**Canale di log**: {'<#' + str(settings.log_channel_id) + '>' if settings.log_channel_id else 'non impostato'}",
        ]
        await interaction.response.send_message("\n".join(righe), ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """
        Motore dei filtri avanzati (SPEC.md §6.3-§6.10): a differenza
        di §6.1/§6.2 (regole native, valutate da Discord stesso prima
        che il bot veda il messaggio), questi filtri esistono solo
        qui — un messaggio bloccato da una regola nativa non arriva
        comunque mai a on_message, quindi non c'è doppia valutazione.
        """
        if message.guild is None or message.author.bot:
            return
        if not isinstance(message.author, discord.Member):
            return

        if not await db.is_module_active_for_guild(message.guild.id, MODULE_AUTOMOD):
            return

        settings = await automod_advanced_repo.get_settings(message.guild.id)
        if is_member_exempt(message.author, settings, message.channel.id):
            return

        segnali = build_message_signals(message)
        violazioni = evaluate_message_violations(segnali, settings.config)
        if not violazioni:
            return

        for violazione in violazioni:
            azioni_configurate = settings.actions.get(violazione, ("delete",))
            eseguite = await _execute_actions(message, violazione, azioni_configurate, settings)
            await _log_violation(message, violazione, eseguite, settings)
            # Se il messaggio è stato cancellato dalla prima
            # violazione, le successive (stesso messaggio, altri
            # filtri scattati insieme) non hanno più nulla da
            # cancellare né senso di valutare per azioni aggiuntive
            # sullo stesso contenuto — esce dal ciclo.
            if "delete" in eseguite:
                break


def _replace_settings(settings: AutomodAdvancedSettings, **overrides) -> AutomodAdvancedSettings:
    dati = {
        "guild_id": settings.guild_id,
        "config": settings.config,
        "exempt_channel_ids": settings.exempt_channel_ids,
        "exempt_role_ids": settings.exempt_role_ids,
        "actions": settings.actions,
        "mute_duration_seconds": settings.mute_duration_seconds,
        "log_channel_id": settings.log_channel_id,
    }
    # Le sotto-chiavi di AutomodAdvancedConfig (anti_link, anti_caps...)
    # vanno sostituite DENTRO config, non a livello di settings —
    # separate le une dalle altre qui, per non dover ripetere la
    # stessa dance in ogni singolo comando sopra.
    config_overrides = {}
    settings_overrides = {}
    config_fields = set(AutomodAdvancedConfig.__dataclass_fields__.keys())
    for chiave, valore in overrides.items():
        if chiave in config_fields:
            config_overrides[chiave] = valore
        else:
            settings_overrides[chiave] = valore

    nuova_config = settings.config
    if config_overrides:
        nuova_config = AutomodAdvancedConfig(
            **{**{f: getattr(settings.config, f) for f in config_fields}, **config_overrides}
        )

    dati.update(settings_overrides)
    dati["config"] = nuova_config
    return AutomodAdvancedSettings(**dati)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_AUTOMOD,
            display_name="AutoMod",
            category="automod",
            description="Filtri base: parole vietate e blocco inviti, sincronizzati con l'AutoMod nativo di Discord.",
            premium_capable=False,
        )
    )
    await bot.add_cog(AutomodCog(bot))
