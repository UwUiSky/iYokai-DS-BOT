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

I filtri lato bot controllano anche i messaggi MODIFICATI (`on_message_edit`,
AMD-021): la modifica non conta come messaggio in più per l'anti-spam, e un
messaggio modificato più volte vale un solo warn per violazione.
Il blocco del phishing (NF-31, `/automod filtri phishing`) usa la lista di
core/phishing_list_fetcher.py: cancella il messaggio e mette in timeout.
Due categorie hanno un interruttore proprio (SIC-042): accorciatori di link
e inviti a server per adulti (il server dell'invito lo chiede a Discord).
Filtri in più: messaggi ripetuti, troppo corti, link e menzioni contati nel
tempo (AMD-001/004/006/007, `/automod filtri messaggi`), testo di embed (solo
per i filtri dei link, anche quando l'anteprima arriva con una modifica) e
inoltri (AMD-019/020) e tipi di file vietati (AMD-022, `/automod filtri
contenuto`), canali solo media o senza allegati (AMD-023/024, `/automod
filtri canale-media`; sticker e inoltri con immagine valgono come media), azione kick (AMD-041).
Funzioni coperte: SPEC §6 (M 2.1-2.7, AMD-001, 004, 006, 007, 019–024, 041), §23 (NF-31, SIC-042)
"""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core import channel_router as router
from core.phishing_list_fetcher import lista_phishing
from core.phishing_logic import codici_invito, server_per_adulti
from core.repositories.output_channel_repo import output_channel_repo

from core.automod_sync import (
    MAX_KEYWORD_LENGTH,
    MAX_KEYWORD_RULES,
    DesiredRule,
    ExistingRule,
    SyncAction,
    SyncActionType,
    compute_sync_plan,
)
from core.automod_advanced_logic import (
    AntiLinkConfig,
    AutomodAdvancedConfig,
    CapsFilterConfig,
    MAX_DOMINI_LISTA,
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
    VIOLATION_PHISHING,
    VIOLATION_A_CAPO,
    VIOLATION_LUNGHEZZA,
    VIOLATION_SPOILER,
    VIOLATION_ACCORCIATORI,
    VIOLATION_INVITI_ADULTI,
    VIOLATION_RIPETUTI,
    VIOLATION_CORTO,
    VIOLATION_LINK_TEMPO,
    VIOLATION_MENZIONI_TEMPO,
    VIOLATION_ESTENSIONI,
    VIOLATION_SOLO_MEDIA,
    VIOLATION_SENZA_ALLEGATI,
    MAX_ESTENSIONI,
    extract_domains,
    pulisci_estensioni,
    AZIONI_DI_PARTENZA,
    AZIONI_DI_PARTENZA_GENERALI,
    evaluate_message_violations,
    normalize_domain,
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
from core.invio_file import invia_file_su_interazione
from core.premium import PremiumModule, registry
from cogs.moderation._shared import ensure_module_enabled, post_to_mod_log, try_dm

logger = logging.getLogger("iyokai.automod")

MODULE_AUTOMOD = "automod"

# Oltre questa lunghezza /automod badword-list manda l'elenco come file
# (un messaggio Discord tiene 2000 caratteri).
MAX_ELENCO_IN_CHAT = 1900

# Discord accetta al massimo 60 caratteri per parola in una regola
# AutoMod: una parola più lunga farebbe fallire ogni sincronizzazione.
MAX_LUNGHEZZA_PAROLA = MAX_KEYWORD_LENGTH

# Un nome di dominio è lungo al massimo 253 caratteri.
MAX_LUNGHEZZA_DOMINIO = 253

# Finestra massima (in secondi) dei filtri anti-spam: il contatore in
# memoria tiene un valore per ogni evento dentro la finestra.
MAX_FINESTRA_SECONDI = 300

# AMD-006/007: link e menzioni contati al massimo per questo numero in un messaggio
# (la coda in memoria di ogni utente non cresce oltre il tetto per messaggio).
MAX_EVENTI_PER_MESSAGGIO = 50

# AMD-023/024: canali solo media e canali senza allegati, per tipo.
MAX_CANALI_MEDIA = 25

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
    VIOLATION_PHISHING: "Anti-Phishing",
    VIOLATION_A_CAPO: "Troppi a-capo",
    VIOLATION_LUNGHEZZA: "Messaggio troppo lungo",
    VIOLATION_SPOILER: "Troppi spoiler",
    VIOLATION_ACCORCIATORI: "Accorciatori di link",
    VIOLATION_INVITI_ADULTI: "Inviti a server per adulti",
    VIOLATION_RIPETUTI: "Messaggi ripetuti",
    VIOLATION_CORTO: "Messaggio troppo corto",
    VIOLATION_LINK_TEMPO: "Troppi link nel tempo",
    VIOLATION_MENZIONI_TEMPO: "Troppe menzioni nel tempo",
    VIOLATION_ESTENSIONI: "Tipo di file vietato",
    VIOLATION_SOLO_MEDIA: "Canale solo media",
    VIOLATION_SENZA_ALLEGATI: "Canale senza allegati",
}

# AMD-001: ultimo testo e quante volte di fila, per (server, utente). Tetto in memoria.
MAX_TESTI_IN_MEMORIA = 20_000
_ultimi_testi: "OrderedDict[tuple[int, int], tuple[str, int]]" = OrderedDict()


def _conta_ripetuti(guild_id: int, user_id: int, testo: str) -> int:
    """Quante volte di fila (questa compresa) l'utente ha mandato lo stesso testo."""
    chiave = (guild_id, user_id)
    pulito = " ".join(testo.lower().split())
    if not pulito:
        _ultimi_testi.pop(chiave, None)
        return 1
    prima, volte = _ultimi_testi.get(chiave, ("", 0))
    volte = volte + 1 if prima == pulito else 1
    _ultimi_testi[chiave] = (pulito, volte)
    _ultimi_testi.move_to_end(chiave)
    while len(_ultimi_testi) > MAX_TESTI_IN_MEMORIA:
        _ultimi_testi.popitem(last=False)
    return volte


def _testo_embed(embeds) -> str:
    """Titolo, descrizione e campi degli embed, uniti (AMD-019)."""
    pezzi = []
    for embed in embeds or []:
        pezzi += [embed.title or "", embed.description or ""]
        pezzi += [f"{campo.name} {campo.value}" for campo in embed.fields]
    return "\n".join(p for p in pezzi if p)


def _testo_da_controllare(message: discord.Message, config: AutomodAdvancedConfig) -> tuple[str, str]:
    """
    (testo, testo degli embed). Il testo comprende gli inoltri (AMD-020) se
    scelti; gli embed (AMD-019) restano a parte: valgono solo per i link.
    """
    pezzi = [message.content or ""]
    embed = [_testo_embed(message.embeds)] if config.controlla_embed else []
    if config.controlla_inoltrati:
        for snap in getattr(message, "message_snapshots", None) or []:
            pezzi.append(getattr(snap, "content", "") or "")
            if config.controlla_embed:
                embed.append(_testo_embed(getattr(snap, "embeds", None)))
    return "\n".join(p for p in pezzi if p), "\n".join(p for p in embed if p)


def _media_inoltrati(message: discord.Message) -> int:
    """Allegati ed embed dentro gli inoltri: un'immagine inoltrata conta come media (AMD-023)."""
    return sum(
        len(getattr(snap, "attachments", None) or []) + len(getattr(snap, "embeds", None) or [])
        for snap in getattr(message, "message_snapshots", None) or []
    )

# Le violazioni della famiglia phishing: canale di log suo e link non cliccabile.
_VIOLAZIONI_PHISHING = frozenset({VIOLATION_PHISHING, VIOLATION_ACCORCIATORI, VIOLATION_INVITI_ADULTI})
# AMD-019: le sole violazioni che il testo di un embed può far scattare.
_VIOLAZIONI_LINK = frozenset({VIOLATION_ANTI_LINK, VIOLATION_PHISHING, VIOLATION_ACCORCIATORI})

# SIC-042: esito degli inviti gia' chiesti a Discord (codice -> per adulti?). Tetto in memoria.
MAX_INVITI_IN_MEMORIA = 2000
_inviti_adulti: "OrderedDict[str, bool]" = OrderedDict()


async def _invito_per_adulti(bot, codice: str, guild_id: int) -> bool:
    """Chiede a Discord il server dell'invito (una volta per codice). Invito non valido o del server stesso: no."""
    if codice in _inviti_adulti:
        _inviti_adulti.move_to_end(codice)
        return _inviti_adulti[codice]
    try:
        invito = await bot.fetch_invite(codice, with_counts=False)
    except (discord.NotFound, discord.Forbidden):
        esito = False
    except discord.HTTPException:
        return False  # errore passeggero: non si ricorda
    else:
        server = getattr(invito, "guild", None)
        esito = (
            server is not None
            and getattr(server, "id", None) != guild_id
            and server_per_adulti(getattr(getattr(server, "nsfw_level", None), "name", ""), getattr(server, "name", ""))
        )
    _inviti_adulti[codice] = esito
    while len(_inviti_adulti) > MAX_INVITI_IN_MEMORIA:
        _inviti_adulti.popitem(last=False)
    return esito


def _count_emoji(content: str) -> int:
    return len(_CUSTOM_EMOJI_RE.findall(content)) + len(_UNICODE_EMOJI_RE.findall(content))


def _mention_count(message: discord.Message) -> int:
    # @everyone/@here contano come "molte menzioni insieme" per far
    # scattare comunque anti-mass-mention anche senza un numero
    # esplicito di utenti — scelta per inferenza, nessun dettaglio
    # più fine specificato.
    extra = 999 if message.mention_everyone else 0
    return len(message.mentions) + len(message.role_mentions) + extra


def _finestra(filtro: RateFilterConfig) -> int:
    """La finestra salvata per il filtro, tenuta tra 1 secondo e il massimo."""
    return max(1, min(filtro.window_seconds, MAX_FINESTRA_SECONDI))


def build_message_signals(
    message: discord.Message, config: AutomodAdvancedConfig, conta_nel_tempo: bool = True,
    solo_embed: bool = False,
) -> MessageSignals:
    """
    Estrae dal messaggio REALE tutto quello che serve alla logica
    pura (core/automod_advanced_logic.py) — i conteggi "nel tempo"
    (rate) passano dal tracker in memoria, mai persistiti (vedi
    core/automod_rate_tracker.py). Ogni conteggio usa la finestra in
    secondi salvata dall'admin per quel filtro.

    `solo_embed`: modifica che aggiunge solo embed (anteprima di un link
    arrivata dopo): si guarda solo il testo degli embed.
    """
    now = discord.utils.utcnow()
    guild_id = message.guild.id
    user_id = message.author.id
    testo, testo_embed = _testo_da_controllare(message, config)
    if solo_embed:
        return MessageSignals(content="", testo_embed=testo_embed, channel_id=message.channel.id)
    nomi_allegati = tuple(getattr(a, "filename", "") or "" for a in message.attachments)

    if not conta_nel_tempo:
        # Messaggio modificato (AMD-021): vale per il testo, non ai conteggi
        # nel tempo. Una modifica non è un messaggio in più.
        return MessageSignals(
            content=testo,
            testo_embed=testo_embed,
            media_inoltrati=_media_inoltrati(message),
            mention_count=_mention_count(message),
            emoji_count=_count_emoji(message.content or ""),
            attachment_count=len(message.attachments),
            sticker_count=len(message.stickers),
            recent_message_count=0,
            recent_attachment_count=0,
            recent_sticker_count=0,
            nomi_allegati=nomi_allegati,
            channel_id=message.channel.id,
        )

    recent_messages = rate_tracker.record_and_count(
        guild_id, user_id, "messages", now, window_seconds=_finestra(config.anti_spam_messages)
    )
    recent_attachments = 0
    if message.attachments:
        recent_attachments = rate_tracker.record_and_count(
            guild_id, user_id, "attachments", now,
            window_seconds=_finestra(config.anti_attachment_spam),
        )
    recent_stickers = 0
    if message.stickers:
        recent_stickers = rate_tracker.record_and_count(
            guild_id, user_id, "stickers", now,
            window_seconds=_finestra(config.anti_spam_sticker),
        )

    ripetuti = _conta_ripetuti(guild_id, user_id, message.content or "") if config.max_ripetuti else 1
    recent_links = 0
    if config.link_nel_tempo.enabled:
        for _ in extract_domains(f"{testo}\n{testo_embed}")[:MAX_EVENTI_PER_MESSAGGIO]:  # tetto come per le menzioni
            recent_links = rate_tracker.record_and_count(
                guild_id, user_id, "links", now, window_seconds=_finestra(config.link_nel_tempo)
            )
    menzioni = _mention_count(message)
    recent_mentions = 0
    if config.menzioni_nel_tempo.enabled:
        for _ in range(min(menzioni, MAX_EVENTI_PER_MESSAGGIO)):  # @everyone vale 999: tetto al conteggio
            recent_mentions = rate_tracker.record_and_count(
                guild_id, user_id, "mentions", now, window_seconds=_finestra(config.menzioni_nel_tempo)
            )

    return MessageSignals(
        content=testo,
        testo_embed=testo_embed,
        media_inoltrati=_media_inoltrati(message),
        mention_count=menzioni,
        emoji_count=_count_emoji(message.content or ""),
        attachment_count=len(message.attachments),
        sticker_count=len(message.stickers),
        recent_message_count=recent_messages,
        recent_attachment_count=recent_attachments,
        recent_sticker_count=recent_stickers,
        ripetuti=ripetuti,
        recent_link_count=recent_links,
        recent_mention_count=recent_mentions,
        nomi_allegati=nomi_allegati,
        channel_id=message.channel.id,
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


# Messaggi già avvisati, con tetto: (id messaggio, violazione). Serve a non
# dare un warn a ogni modifica dello stesso messaggio.
_AVVISATI_MAX = 2000
_avvisati: "OrderedDict[tuple[int, str], None]" = OrderedDict()


def _warn_da_dare(message_id: int, violazione: str, modificato: bool) -> bool:
    """
    Registra il warn. Per un messaggio modificato è False se lo stesso
    messaggio ha già avuto un warn per la stessa violazione.
    """
    chiave = (message_id, violazione)
    gia = chiave in _avvisati
    _avvisati[chiave] = None
    _avvisati.move_to_end(chiave)
    while len(_avvisati) > _AVVISATI_MAX:
        _avvisati.popitem(last=False)
    return not (modificato and gia)


async def _execute_actions(
    message: discord.Message,
    violation: str,
    actions: tuple[str, ...],
    settings: AutomodAdvancedSettings,
    modificato: bool = False,
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

        if protetto and azione in ("mute", "kick", "ban"):
            continue

        if azione == "warn":
            # Lo stesso messaggio, modificato più volte, vale un warn solo
            # per violazione (senza «delete» il testo resta al suo posto).
            if not _warn_da_dare(message.id, violation, modificato):
                continue
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

        elif azione == "kick":
            # AMD-041: il DM con il motivo parte prima (dopo il kick non arriverebbe).
            await try_dm(member, discord.Embed(
                title="Espulso dall'AutoMod",
                description=f"{message.guild.name}: {_VIOLATION_LABELS.get(violation, violation)}",
                color=discord.Color.orange(),
            ))
            try:
                await member.kick(reason=f"AutoMod: {_VIOLATION_LABELS.get(violation, violation)}")
                eseguite.append("kick")
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

    if violation in _VIOLAZIONI_PHISHING:
        # SIC-043: il phishing ha un canale suo (router, anche forum); senza scelta vale il log dell'AutoMod.
        canale = await router.destinazione(message.guild, router.TIPO_PHISHING, settings.log_channel_id)
    else:
        canale = message.guild.get_channel(settings.log_channel_id) if settings.log_channel_id else None
        if not isinstance(canale, discord.TextChannel):
            canale = None
    if canale is None:
        return

    embed = discord.Embed(
        title=f"🛡️ AutoMod — {_VIOLATION_LABELS.get(violation, violation)}",
        color=discord.Color.orange(),
    )
    embed.add_field(name="Utente", value=f"{message.author.mention} ({message.author.id})", inline=False)
    embed.add_field(name="Canale", value=message.channel.mention, inline=True)
    embed.add_field(name="Azioni eseguite", value=", ".join(actions_taken) or "nessuna", inline=True)
    if contenuto:
        # Nel log di phishing il link non deve restare cliccabile.
        valore = f"`{contenuto.replace('`', '')}`" if violation in _VIOLAZIONI_PHISHING else contenuto
        embed.add_field(name="Contenuto", value=valore, inline=False)
    if violation in _VIOLAZIONI_PHISHING:
        await router.invia_a(canale, message.guild, router.TIPO_PHISHING, embed=embed)
        return
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


AVVISO_TRONCATO = (
    "Attenzione: una o più regole hanno superato il limite di "
    "Discord (1000 parole o 10 pattern regex per regola) e "
    "sono state troncate. Le voci in eccesso non sono state "
    "applicate."
)
AVVISO_TROPPE_REGOLE = (
    f"Questo server ha già {MAX_KEYWORD_RULES} regole AutoMod a parole "
    f"chiave, il massimo di Discord: non posso crearne un'altra. "
    f"Elimina una regola dal pannello di Discord (Impostazioni server → "
    f"AutoMod) e poi usa `/automod sync`."
)


def _regola_esistente(rule: discord.AutoModRule) -> ExistingRule:
    return ExistingRule(
        name=rule.name,
        keywords=tuple(rule.trigger.keyword_filter or ()),
        regex_patterns=tuple(rule.trigger.regex_patterns or ()),
        allow_list=tuple(rule.trigger.allow_list or ()),
    )


def _trigger_completo(action: SyncAction) -> discord.AutoModTrigger:
    """
    Trigger con tutti i campi: Discord sostituisce il trigger intero,
    quindi un campo lasciato fuori (espressioni regolari, lista delle
    eccezioni) verrebbe cancellato.
    """
    return discord.AutoModTrigger(
        type=discord.AutoModRuleTriggerType.keyword,
        keyword_filter=list(action.final_keywords),
        regex_patterns=list(action.final_regex),
        allow_list=list(action.final_allow_list),
    )


async def _sync_guild(guild: discord.Guild) -> str | None:
    """
    Allinea le regole AutoMod di Discord alla configurazione salvata:
    legge le regole, calcola il piano (core/automod_sync.py) ed esegue
    creazioni, modifiche e cancellazioni. Dopo ogni scrittura riuscita
    salva in `automod_last_synced` la parte voluta da iYokai: serve al
    giro dopo per distinguere le nostre parole da quelle dell'admin.

    Restituisce un avviso per l'admin (limite di Discord raggiunto,
    errore di Discord), altrimenti None.
    """
    try:
        rules = await guild.fetch_automod_rules()
    except discord.Forbidden:
        return (
            "Non ho i permessi per leggere/gestire le regole AutoMod "
            "di questo server (serve Manage Server)."
        )
    except discord.HTTPException as errore:
        return f"Discord non mi ha fatto leggere le regole AutoMod: {str(errore)[:200]}"

    # Indicizzato per nome, serve per recuperare l'oggetto AutoModRule
    # vero su cui chiamare .edit()/.delete() quando il piano lo richiede.
    rules_by_name = {rule.name: rule for rule in rules}
    regole_a_parole = sum(
        1 for rule in rules if rule.trigger.type == discord.AutoModRuleTriggerType.keyword
    )

    config = await automod_repo.get_config(guild.id)
    last_synced_badwords, _ = await automod_repo.get_last_synced(guild.id, RULE_NAME_BADWORDS)
    _, last_synced_invite_regex = await automod_repo.get_last_synced(guild.id, RULE_NAME_INVITES)

    # Una parola oltre il limite farebbe rifiutare a Discord tutta la
    # regola: la si lascia fuori e lo si dice.
    parole_valide = tuple(w for w in config.custom_badwords if len(w) <= MAX_KEYWORD_LENGTH)
    parole_troppo_lunghe = len(config.custom_badwords) - len(parole_valide)

    desired = _build_desired_rules(
        parole_valide,
        config.block_invites,
        last_synced_badwords,
        last_synced_invite_regex,
    )
    plan = compute_sync_plan([_regola_esistente(rule) for rule in rules], desired)

    avvisi: list[str] = []
    if parole_troppo_lunghe:
        avvisi.append(
            f"{parole_troppo_lunghe} parole superano i {MAX_KEYWORD_LENGTH} caratteri "
            f"ammessi da Discord e non sono state applicate."
        )
    if any(action.truncated for action in plan):
        avvisi.append(AVVISO_TRONCATO)

    for action in plan:
        if action.action == SyncActionType.SKIP:
            continue

        try:
            if action.action == SyncActionType.DELETE:
                existing_rule = rules_by_name.get(action.name)
                if existing_rule is not None:
                    await existing_rule.delete(reason="Nessun contenuto residuo da mantenere")
                    regole_a_parole -= 1
                await automod_repo.clear_last_synced(guild.id, action.name)
                continue

            if action.action == SyncActionType.CREATE:
                if regole_a_parole >= MAX_KEYWORD_RULES:
                    avvisi.append(AVVISO_TROPPE_REGOLE)
                    continue
                await guild.create_automod_rule(
                    name=action.name,
                    event_type=discord.AutoModRuleEventType.message_send,
                    trigger=_trigger_completo(action),
                    actions=[
                        discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)
                    ],
                    enabled=True,
                    reason="Sincronizzazione automatica iYokai AutoMod",
                )
                regole_a_parole += 1
            else:
                await rules_by_name[action.name].edit(
                    trigger=_trigger_completo(action),
                    reason="Sincronizzazione automatica iYokai AutoMod",
                )
        except discord.HTTPException as errore:
            # last_synced resta quello vecchio: al prossimo giro si riprova.
            avvisi.append(
                f"Discord ha rifiutato la regola «{action.name}»: {str(errore)[:200]}"
            )
            continue

        await automod_repo.set_last_synced(
            guild.id, action.name, action.own_keywords, action.own_regex
        )

    return "\n".join(dict.fromkeys(avvisi)) or None


class AutomodCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "automod",
        nome="add",
        descrizione="Aggiunge una parola vietata.",
        sottogruppo=("parole", "Parole vietate."),
    )
    @app_commands.describe(word="La parola da vietare (massimo 60 caratteri)")
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

    @comando_di_gruppo(
        "automod",
        nome="remove",
        descrizione="Rimuove una parola vietata.",
        sottogruppo=("parole", "Parole vietate."),
    )
    @app_commands.describe(word="La parola da rimuovere (massimo 60 caratteri)")
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

    @comando_di_gruppo(
        "automod",
        nome="list",
        descrizione="Mostra le parole vietate configurate.",
        sottogruppo=("parole", "Parole vietate."),
    )
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
        await invia_file_su_interazione(
            interaction,
            contenuto,
            "parole_vietate.txt",
            contenuto=f"Parole vietate configurate ({totale}): l'elenco è lungo, lo trovi nel file allegato.",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "automod",
        nome="invites",
        descrizione="Attiva o disattiva il blocco automatico degli inviti Discord.",
        sottogruppo=("filtri", "Filtri automatici sui messaggi."),
    )
    @app_commands.describe(enabled="True per bloccare gli inviti, False per consentirli")
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

    @comando_di_gruppo(
        "automod",
        nome="sync",
        descrizione="Forza una sincronizzazione manuale delle regole AutoMod.",
    )
    async def sync(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return

        await interaction.response.defer(ephemeral=True)
        avviso = await _sync_guild(interaction.guild)
        await interaction.followup.send(avviso or "Sincronizzazione completata.", ephemeral=True)

    # ================================================================
    # Filtri avanzati lato bot (SPEC.md §6.3-§6.10)
    # ================================================================
    @comando_di_gruppo(
        "automod",
        nome="anti-link-mode",
        descrizione="Imposta la modalità del filtro link.",
        sottogruppo=("filtri", "Filtri automatici sui messaggi."),
    )
    @app_commands.describe(mode="off = spento, whitelist = solo i domini elencati, blacklist = blocca i domini elencati")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Disattivato", value="off"),
            app_commands.Choice(name="Whitelist", value="whitelist"),
            app_commands.Choice(name="Blacklist", value="blacklist"),
        ]
    )
    async def anti_link_mode(self, interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        nuova = _replace_settings(settings, anti_link=AntiLinkConfig(
            mode=mode.value, whitelist=settings.config.anti_link.whitelist, blacklist=settings.config.anti_link.blacklist,
        ))
        await automod_advanced_repo.save_settings(nuova)
        await interaction.response.send_message(f"Modalità anti-link impostata su **{mode.name}**.", ephemeral=True)

    @comando_di_gruppo(
        "automod",
        nome="anti-link-domain",
        descrizione="Aggiunge o rimuove un dominio dalla whitelist/blacklist link.",
        sottogruppo=("filtri", "Filtri automatici sui messaggi."),
    )
    @app_commands.describe(action="add o remove", lista="whitelist o blacklist", domain="Il dominio, es. esempio.com")
    @app_commands.choices(
        action=[app_commands.Choice(name="Aggiungi", value="add"), app_commands.Choice(name="Rimuovi", value="remove")],
        lista=[app_commands.Choice(name="Whitelist", value="whitelist"), app_commands.Choice(name="Blacklist", value="blacklist")],
    )
    async def anti_link_domain(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        lista: app_commands.Choice[str],
        domain: app_commands.Range[str, 1, MAX_LUNGHEZZA_DOMINIO],
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        # Si salva il solo nome host: "https://www.Evil.com:443/x" e
        # "evil.com" sono la stessa voce.
        dominio = normalize_domain(domain)
        if not dominio:
            await interaction.response.send_message(
                "Non riconosco un dominio in quello che hai scritto. Esempio: `esempio.com`.",
                ephemeral=True,
            )
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        attuale = settings.config.anti_link.whitelist if lista.value == "whitelist" else settings.config.anti_link.blacklist

        if action.value == "add":
            if dominio not in attuale and len(attuale) >= MAX_DOMINI_LISTA:
                await interaction.response.send_message(
                    f"La {lista.name.lower()} ha già {MAX_DOMINI_LISTA} domini, il massimo. "
                    "Rimuovi un dominio con `/automod filtri anti-link-domain` prima di aggiungerne altri.",
                    ephemeral=True,
                )
                return
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

    @comando_di_gruppo(
        "automod",
        nome="anti-spam-messages",
        descrizione="Configura l'anti-spam messaggi (troppi messaggi in poco tempo).",
        sottogruppo=("filtri", "Filtri automatici sui messaggi."),
    )
    @app_commands.describe(enabled="Attiva/disattiva", max_messages="Numero massimo consentito", seconds="Finestra in secondi (da 1 a 300)")
    async def anti_spam_messages(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        max_messages: int = 5,
        seconds: app_commands.Range[int, 1, MAX_FINESTRA_SECONDI] = 10,
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

    @comando_di_gruppo(
        "automod",
        nome="anti-spam-emoji",
        descrizione="Configura l'anti-spam emoji (troppe emoji in un messaggio).",
        sottogruppo=("filtri", "Filtri automatici sui messaggi."),
    )
    @app_commands.describe(enabled="Attiva/disattiva", max_emoji="Numero massimo di emoji per messaggio")
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

    @comando_di_gruppo(
        "automod",
        nome="anti-spam-sticker",
        descrizione="Configura l'anti-spam sticker (troppi sticker in poco tempo).",
        sottogruppo=("filtri", "Filtri automatici sui messaggi."),
    )
    @app_commands.describe(enabled="Attiva/disattiva", max_sticker="Numero massimo consentito", seconds="Finestra in secondi (da 1 a 300)")
    async def anti_spam_sticker(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        max_sticker: int = 3,
        seconds: app_commands.Range[int, 1, MAX_FINESTRA_SECONDI] = 30,
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

    @comando_di_gruppo(
        "automod",
        nome="anti-caps",
        descrizione="Configura l'anti-caps (troppo maiuscolo).",
        sottogruppo=("filtri", "Filtri automatici sui messaggi."),
    )
    @app_commands.describe(enabled="Attiva/disattiva", percent="Percentuale di lettere maiuscole per far scattare il filtro", min_length="Lunghezza minima del messaggio (in lettere) da valutare")
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

    @comando_di_gruppo(
        "automod",
        nome="anti-zalgo",
        descrizione="Attiva o disattiva l'anti-zalgo (testo con segni diacritici anomali).",
        sottogruppo=("filtri", "Filtri automatici sui messaggi."),
    )
    @app_commands.describe(enabled="Attiva/disattiva")
    async def anti_zalgo(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        nuova = _replace_settings(settings, anti_zalgo_enabled=enabled)
        await automod_advanced_repo.save_settings(nuova)
        await interaction.response.send_message(f"Anti-zalgo {'attivato' if enabled else 'disattivato'}.", ephemeral=True)

    @comando_di_gruppo(
        "automod",
        nome="phishing",
        descrizione="Attiva o disattiva il blocco dei link di phishing (finti regali, finti login).",
        sottogruppo=("filtri", "Filtri automatici sui messaggi."),
    )
    @app_commands.describe(
        enabled="Attiva/disattiva",
        canale_log="Canale o forum dove scrivere ogni link bloccato (vuoto: il log dell'AutoMod)",
        accorciatori="Blocca anche gli accorciatori di link (bit.ly, tinyurl...); vuoto: non cambia",
        inviti_adulti="Blocca anche gli inviti a server per adulti; vuoto: non cambia",
    )
    async def anti_phishing(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        canale_log: discord.TextChannel | discord.ForumChannel | None = None,
        accorciatori: bool | None = None,
        inviti_adulti: bool | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        if canale_log is not None:
            await output_channel_repo.imposta(interaction.guild.id, router.TIPO_PHISHING, canale_log.id)
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        cambi = {"anti_phishing_enabled": enabled}
        if accorciatori is not None:
            cambi["phishing_accorciatori"] = accorciatori
        if inviti_adulti is not None:
            cambi["phishing_inviti_adulti"] = inviti_adulti
        nuova = _replace_settings(settings, **cambi)
        await automod_advanced_repo.save_settings(nuova)
        if enabled:
            lista_phishing.aggiorna_se_serve()
        c = nuova.config
        await interaction.response.send_message(
            f"Blocco del phishing {'attivato: cancello il messaggio e metto in timeout chi lo ha scritto' if enabled else 'disattivato'}. "
            f"Accorciatori di link: {'bloccati' if c.phishing_accorciatori else 'permessi'}. "
            f"Inviti a server per adulti: {'bloccati' if c.phishing_inviti_adulti else 'permessi'}. "
            "Se blocco un dominio per sbaglio, mettilo nella whitelist con `/automod filtri anti-link-domain`."
            + (f" I link bloccati si scrivono in {canale_log.mention}." if canale_log is not None else ""),
            ephemeral=True,
        )

    @comando_di_gruppo(
        "automod",
        nome="forma-testo",
        descrizione="Limiti sulla forma del messaggio: a-capo, lunghezza, spoiler (0 = spento).",
        sottogruppo=("filtri", "Filtri automatici sui messaggi."),
    )
    @app_commands.describe(
        max_a_capo="Massimo di righe a capo (muri di testo); 0 = spento",
        max_lunghezza="Massimo di caratteri per messaggio; 0 = spento",
        max_spoiler="Massimo di pezzi ||nascosti||; 0 = spento",
    )
    async def forma_testo(
        self,
        interaction: discord.Interaction,
        max_a_capo: app_commands.Range[int, 0, 200] | None = None,
        max_lunghezza: app_commands.Range[int, 0, 4000] | None = None,
        max_spoiler: app_commands.Range[int, 0, 100] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        c = settings.config
        nuovi = {
            "max_a_capo": c.max_a_capo if max_a_capo is None else max_a_capo,
            "max_lunghezza": c.max_lunghezza if max_lunghezza is None else max_lunghezza,
            "max_spoiler": c.max_spoiler if max_spoiler is None else max_spoiler,
        }
        await automod_advanced_repo.save_settings(_replace_settings(settings, **nuovi))
        nomi = {"max_a_capo": "a-capo", "max_lunghezza": "caratteri", "max_spoiler": "spoiler"}
        righe = [f"{nomi[k]}: {v if v else 'spento'}" for k, v in nuovi.items()]
        await interaction.response.send_message("Limiti salvati. " + "; ".join(righe) + ".", ephemeral=True)

    @comando_di_gruppo(
        "automod",
        nome="messaggi",
        descrizione="Ripetuti, troppo corti, link e menzioni contati nel tempo (0 = spento).",
        sottogruppo=("filtri", "Filtri automatici sui messaggi."),
    )
    @app_commands.describe(
        max_ripetuti="Stesso testo mandato più di N volte di fila",
        min_caratteri="Messaggi di testo più corti di N caratteri",
        max_link="Più di N link nella finestra",
        finestra_link="Finestra dei link, in secondi",
        max_menzioni="Più di N menzioni nella finestra, su più messaggi",
        finestra_menzioni="Finestra delle menzioni, in secondi",
    )
    async def messaggi(
        self,
        interaction: discord.Interaction,
        max_ripetuti: app_commands.Range[int, 0, 20] | None = None,
        min_caratteri: app_commands.Range[int, 0, 2000] | None = None,
        max_link: app_commands.Range[int, 0, 50] | None = None,
        finestra_link: app_commands.Range[int, 1, MAX_FINESTRA_SECONDI] | None = None,
        max_menzioni: app_commands.Range[int, 0, 100] | None = None,
        finestra_menzioni: app_commands.Range[int, 1, MAX_FINESTRA_SECONDI] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        c = settings.config
        cambi = {}
        if max_ripetuti is not None:
            cambi["max_ripetuti"] = max_ripetuti
        if min_caratteri is not None:
            cambi["min_caratteri"] = min_caratteri
        if max_link is not None or finestra_link is not None:
            massimo = c.link_nel_tempo.max_count if max_link is None else max_link
            cambi["link_nel_tempo"] = RateFilterConfig(
                enabled=massimo > 0 if max_link is not None else c.link_nel_tempo.enabled,
                max_count=massimo or c.link_nel_tempo.max_count,
                window_seconds=finestra_link or c.link_nel_tempo.window_seconds,
            )
        if max_menzioni is not None or finestra_menzioni is not None:
            massimo = c.menzioni_nel_tempo.max_count if max_menzioni is None else max_menzioni
            cambi["menzioni_nel_tempo"] = RateFilterConfig(
                enabled=massimo > 0 if max_menzioni is not None else c.menzioni_nel_tempo.enabled,
                max_count=massimo or c.menzioni_nel_tempo.max_count,
                window_seconds=finestra_menzioni or c.menzioni_nel_tempo.window_seconds,
            )
        nuova = _replace_settings(settings, **cambi).config
        await automod_advanced_repo.save_settings(_replace_settings(settings, **cambi))
        link = nuova.link_nel_tempo
        menz = nuova.menzioni_nel_tempo
        await interaction.response.send_message(
            f"Ripetuti: {nuova.max_ripetuti or 'spento'}. Minimo caratteri: {nuova.min_caratteri or 'spento'}. "
            f"Link: {f'più di {link.max_count} in {link.window_seconds}s' if link.enabled else 'spento'}. "
            f"Menzioni: {f'più di {menz.max_count} in {menz.window_seconds}s' if menz.enabled else 'spento'}.",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "automod",
        nome="contenuto",
        descrizione="Embed e inoltri controllati dai filtri; tipi di file vietati.",
        sottogruppo=("filtri", "Filtri automatici sui messaggi."),
    )
    @app_commands.describe(
        embed="I filtri dei link leggono anche gli embed del messaggio",
        inoltrati="I filtri di testo leggono anche i messaggi inoltrati",
        estensioni_vietate="Estensioni separate da spazi (es. exe bat scr); «-» svuota la lista",
    )
    async def contenuto(
        self,
        interaction: discord.Interaction,
        embed: bool | None = None,
        inoltrati: bool | None = None,
        estensioni_vietate: app_commands.Range[str, 1, 400] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        cambi = {}
        if embed is not None:
            cambi["controlla_embed"] = embed
        if inoltrati is not None:
            cambi["controlla_inoltrati"] = inoltrati
        if estensioni_vietate is not None:
            cambi["estensioni_vietate"] = () if estensioni_vietate.strip() == "-" else pulisci_estensioni(estensioni_vietate)
        nuova = _replace_settings(settings, **cambi)
        await automod_advanced_repo.save_settings(nuova)
        c = nuova.config
        await interaction.response.send_message(
            f"Embed: {'controllati' if c.controlla_embed else 'ignorati'}. "
            f"Inoltri: {'controllati' if c.controlla_inoltrati else 'ignorati'}. "
            f"Estensioni vietate ({len(c.estensioni_vietate)}/{MAX_ESTENSIONI}): "
            f"{', '.join(c.estensioni_vietate) or 'nessuna'}.",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "automod",
        nome="canale-media",
        descrizione="Canale solo media, senza allegati o normale.",
        sottogruppo=("filtri", "Filtri automatici sui messaggi."),
    )
    @app_commands.describe(canale="Il canale", modo="Cosa vale nel canale")
    @app_commands.choices(
        modo=[
            app_commands.Choice(name="Solo media: senza immagine, file o link si cancella", value="solo_media"),
            app_commands.Choice(name="Senza allegati: solo testo", value="senza_allegati"),
            app_commands.Choice(name="Normale", value="normale"),
        ]
    )
    async def canale_media(
        self, interaction: discord.Interaction, canale: discord.TextChannel, modo: app_commands.Choice[str]
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        media = [i for i in settings.config.canali_solo_media if i != canale.id]
        testo = [i for i in settings.config.canali_senza_allegati if i != canale.id]
        if modo.value == "solo_media":
            media.append(canale.id)
        elif modo.value == "senza_allegati":
            testo.append(canale.id)
        if len(media) > MAX_CANALI_MEDIA or len(testo) > MAX_CANALI_MEDIA:
            await interaction.response.send_message(
                f"Al massimo {MAX_CANALI_MEDIA} canali per tipo.", ephemeral=True
            )
            return
        await automod_advanced_repo.save_settings(
            _replace_settings(settings, canali_solo_media=tuple(media), canali_senza_allegati=tuple(testo))
        )
        await interaction.response.send_message(f"{canale.mention}: {modo.name.lower()}.", ephemeral=True)

    @comando_di_gruppo(
        "automod",
        nome="anti-mention",
        descrizione="Configura l'anti-mass-mention (troppi utenti taggati in un messaggio).",
        sottogruppo=("filtri", "Filtri automatici sui messaggi."),
    )
    @app_commands.describe(enabled="Attiva/disattiva", max_mentions="Numero massimo di menzioni per messaggio")
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

    @comando_di_gruppo(
        "automod",
        nome="anti-attachment",
        descrizione="Configura l'anti-attachment-spam (troppi allegati in poco tempo).",
        sottogruppo=("filtri", "Filtri automatici sui messaggi."),
    )
    @app_commands.describe(enabled="Attiva/disattiva", max_attachments="Numero massimo consentito", seconds="Finestra in secondi (da 1 a 300)")
    async def anti_attachment(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        max_attachments: int = 5,
        seconds: app_commands.Range[int, 1, MAX_FINESTRA_SECONDI] = 30,
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
    @comando_di_gruppo(
        "automod",
        nome="channel-add",
        descrizione="Esenta un canale da tutti i filtri AutoMod avanzati.",
        sottogruppo=("esenzioni", "Canali e ruoli esentati dai filtri."),
    )
    async def exempt_channel_add(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        if channel.id not in settings.exempt_channel_ids:
            nuova = _replace_settings(settings, exempt_channel_ids=settings.exempt_channel_ids + (channel.id,))
            await automod_advanced_repo.save_settings(nuova)
        await interaction.response.send_message(f"Canale {channel.mention} esentato dai filtri avanzati.", ephemeral=True)

    @comando_di_gruppo(
        "automod",
        nome="channel-remove",
        descrizione="Rimuove l'esenzione di un canale.",
        sottogruppo=("esenzioni", "Canali e ruoli esentati dai filtri."),
    )
    async def exempt_channel_remove(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        nuova = _replace_settings(
            settings, exempt_channel_ids=tuple(c for c in settings.exempt_channel_ids if c != channel.id)
        )
        await automod_advanced_repo.save_settings(nuova)
        await interaction.response.send_message(f"Esenzione rimossa per {channel.mention}.", ephemeral=True)

    @comando_di_gruppo(
        "automod",
        nome="role-add",
        descrizione="Esenta un ruolo da tutti i filtri AutoMod avanzati.",
        sottogruppo=("esenzioni", "Canali e ruoli esentati dai filtri."),
    )
    async def exempt_role_add(self, interaction: discord.Interaction, role: discord.Role) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        if role.id not in settings.exempt_role_ids:
            nuova = _replace_settings(settings, exempt_role_ids=settings.exempt_role_ids + (role.id,))
            await automod_advanced_repo.save_settings(nuova)
        await interaction.response.send_message(f"Ruolo {role.mention} esentato dai filtri avanzati.", ephemeral=True)

    @comando_di_gruppo(
        "automod",
        nome="role-remove",
        descrizione="Rimuove l'esenzione di un ruolo.",
        sottogruppo=("esenzioni", "Canali e ruoli esentati dai filtri."),
    )
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
    @comando_di_gruppo(
        "automod",
        nome="actions-set",
        descrizione="Configura quali azioni eseguire quando un filtro avanzato scatta.",
        sottogruppo=("filtri", "Filtri automatici sui messaggi."),
    )
    @app_commands.describe(
        violation="Quale filtro", delete="Cancella il messaggio", warn="Assegna un warn",
        mute="Timeout temporaneo (durata: /automod mute-duration)", ban="Banna l'utente",
        kick="Espelle l'utente",
    )
    @app_commands.choices(
        violation=[app_commands.Choice(name=label, value=key) for key, label in _VIOLATION_LABELS.items()]
    )
    async def actions_set(
        self,
        interaction: discord.Interaction,
        violation: app_commands.Choice[str],
        delete: bool = True,
        warn: bool = False,
        mute: bool = False,
        ban: bool = False,
        kick: bool = False,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        scelte = tuple(
            nome
            for nome, attiva in (("delete", delete), ("warn", warn), ("mute", mute), ("kick", kick), ("ban", ban))
            if attiva
        )
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        nuove_azioni = dict(settings.actions)
        nuove_azioni[violation.value] = scelte
        await automod_advanced_repo.save_settings(_replace_settings(settings, actions=nuove_azioni))
        await interaction.response.send_message(
            f"Azioni per **{violation.name}** impostate: {', '.join(scelte) or 'nessuna'}.", ephemeral=True
        )

    @comando_di_gruppo(
        "automod",
        nome="mute-duration",
        descrizione="Imposta la durata del timeout usato dall'azione 'mute' dell'AutoMod.",
    )
    @app_commands.describe(seconds="Durata in secondi (max 28 giorni, limite di Discord)")
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

    @comando_di_gruppo(
        "automod",
        nome="log-channel",
        descrizione="Imposta il canale dove pubblicare il log delle azioni AutoMod avanzate.",
    )
    async def log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        settings = await automod_advanced_repo.get_settings(interaction.guild.id)
        await automod_advanced_repo.save_settings(_replace_settings(settings, log_channel_id=channel.id))
        await interaction.response.send_message(f"Canale di log AutoMod impostato su {channel.mention}.", ephemeral=True)

    @comando_di_gruppo(
        "automod",
        nome="status",
        descrizione="Mostra la configurazione attuale dei filtri AutoMod avanzati.",
    )
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
            f"**Anti-Phishing**: {'ON' if c.anti_phishing_enabled else 'OFF'} (accorciatori "
            f"{'ON' if c.phishing_accorciatori else 'OFF'}, inviti per adulti {'ON' if c.phishing_inviti_adulti else 'OFF'})",
            f"**Forma del testo**: a-capo {c.max_a_capo or 'spento'}, caratteri {c.max_lunghezza or 'spento'}, "
            f"spoiler {c.max_spoiler or 'spento'}",
            f"**Anti-Mass-Mention**: {'ON' if c.anti_mass_mention.enabled else 'OFF'} (max {c.anti_mass_mention.max_count})",
            f"**Anti-Attachment-Spam**: {'ON' if c.anti_attachment_spam.enabled else 'OFF'} (max {c.anti_attachment_spam.max_count}/{c.anti_attachment_spam.window_seconds}s)",
            f"**Ripetuti**: {c.max_ripetuti or 'spento'} · **Minimo caratteri**: {c.min_caratteri or 'spento'}",
            f"**Link nel tempo**: {'ON' if c.link_nel_tempo.enabled else 'OFF'} (max {c.link_nel_tempo.max_count}/{c.link_nel_tempo.window_seconds}s) · "
            f"**Menzioni nel tempo**: {'ON' if c.menzioni_nel_tempo.enabled else 'OFF'} (max {c.menzioni_nel_tempo.max_count}/{c.menzioni_nel_tempo.window_seconds}s)",
            f"**Embed**: {'sì' if c.controlla_embed else 'no'} · **Inoltrati**: {'sì' if c.controlla_inoltrati else 'no'} · "
            f"**Estensioni vietate**: {', '.join(c.estensioni_vietate) or 'nessuna'}",
            f"**Canali solo media**: {len(c.canali_solo_media)} · **Canali senza allegati**: {len(c.canali_senza_allegati)}",
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
        await self._controlla(message, modificato=False)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        """
        AMD-021: chi modifica un messaggio per far passare ciò che era
        bloccato viene controllato di nuovo. Se il testo è uguale ma sono
        arrivati embed nuovi (l'anteprima di un link arriva così), si
        controllano solo gli embed (AMD-019).
        """
        if before.content != after.content:
            await self._controlla(after, modificato=True)
        elif (nuovi := _testo_embed(getattr(after, "embeds", None))) and nuovi != _testo_embed(
            getattr(before, "embeds", None)
        ):
            await self._controlla(after, modificato=True, solo_embed=True)

    async def _controlla(self, message: discord.Message, modificato: bool, solo_embed: bool = False) -> None:
        if message.guild is None or message.author.bot:
            return
        if not isinstance(message.author, discord.Member):
            return

        if not await db.is_module_active_for_guild(message.guild.id, MODULE_AUTOMOD):
            return

        settings = await automod_advanced_repo.get_settings(message.guild.id)
        if is_member_exempt(message.author, settings, message.channel.id):
            return

        if solo_embed and not settings.config.controlla_embed:
            return
        segnali = build_message_signals(
            message, settings.config, conta_nel_tempo=not modificato, solo_embed=solo_embed
        )
        if settings.config.anti_phishing_enabled:
            lista_phishing.aggiorna_se_serve()
        violazioni = evaluate_message_violations(segnali, settings.config, lista_phishing.domini)
        if solo_embed:
            # Il testo è già stato controllato: dagli embed contano solo i link.
            violazioni = tuple(v for v in violazioni if v in _VIOLAZIONI_LINK)
        elif settings.config.phishing_inviti_adulti and self.bot is not None:
            for codice in codici_invito(message.content):
                if await _invito_per_adulti(self.bot, codice, message.guild.id):
                    violazioni = (*violazioni, VIOLATION_INVITI_ADULTI)
                    break
        if not violazioni:
            return

        for violazione in violazioni:
            azioni_configurate = settings.actions.get(
                violazione, AZIONI_DI_PARTENZA.get(violazione, AZIONI_DI_PARTENZA_GENERALI)
            )
            eseguite = await _execute_actions(
                message, violazione, azioni_configurate, settings, modificato=modificato
            )
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
