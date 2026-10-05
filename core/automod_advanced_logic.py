"""
core/automod_advanced_logic.py
==================================
Logica PURA (nessuna dipendenza da discord.py, nessun I/O) dei
filtri AutoMod lato bot che l'AutoMod nativo di Discord non sa fare
da solo (SPEC.md §6.3-§6.10): anti-link generico, anti-spam
(messaggi/emoji/sticker/allegati), anti-caps, anti-zalgo,
anti-mass-mention.

Perché lato bot e non regole native: §6.1/§6.2 (parole vietate,
inviti) usano l'AutoMod nativo (core/automod_sync.py) perché Discord
lo supporta nativamente con trigger keyword/regex. I filtri qui sotto
non hanno un trigger nativo equivalente (soglie percentuali di
maiuscole, unicode zalgo, conteggi per-tipo-di-contenuto ripetuti nel
tempo) — vanno quindi calcolati leggendo il messaggio nel bot.

Tenuta separata da ogni chiamata a Discord/DB apposta: testabile con
semplici input/output, senza mock di discord.py o del database.
"""

# DA FARE (issue #58, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §2 (AutoMod).

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urlparse

# Soglia di segni diacritici combinanti (unicode categoria Mn/Me/Mc)
# oltre la quale un testo è considerato "zalgo". Valore scelto per
# inferenza (non specificato dall'utente): il testo normale (accenti
# italiani, emoji con modificatori) non supera mai qualche unità,
# mentre lo zalgo tipico ne accumula decine anche su poche lettere.
ZALGO_COMBINING_THRESHOLD = 8

_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def extract_domains(text: str) -> tuple[str, ...]:
    """
    Estrae i domini (senza sottodomini "www.") da ogni URL http/https
    trovato nel testo. Un testo senza link restituisce una tupla
    vuota.
    """
    domini = []
    for match in _URL_PATTERN.findall(text):
        try:
            host = urlparse(match).netloc.lower()
        except ValueError:
            continue
        if host.startswith("www."):
            host = host[4:]
        if host:
            domini.append(host)
    return tuple(domini)


def is_link_violation(
    domains: tuple[str, ...],
    mode: str,
    whitelist: tuple[str, ...],
    blacklist: tuple[str, ...],
) -> bool:
    """
    `mode` è "off" (mai in violazione), "whitelist" (in violazione
    se ALMENO UN dominio non è nella whitelist — modalità
    restrittiva: blocca tutto tranne quanto elencato) o "blacklist"
    (in violazione se ALMENO UN dominio è nella blacklist).
    """
    if not domains or mode == "off":
        return False
    if mode == "whitelist":
        insieme = {d.lower() for d in whitelist}
        return any(d.lower() not in insieme for d in domains)
    if mode == "blacklist":
        insieme = {d.lower() for d in blacklist}
        return any(d.lower() in insieme for d in domains)
    return False


def is_caps_violation(text: str, threshold_percent: int, min_length: int) -> bool:
    """
    Considera solo i caratteri ALFABETICI per il calcolo della
    percentuale (numeri, punteggiatura ed emoji non contano né a
    favore né contro) — altrimenti un messaggio come "!!!!!!!" o
    "123456" risulterebbe "100% maiuscolo" senza contenere una sola
    lettera vera.
    """
    lettere = [c for c in text if c.isalpha()]
    if len(lettere) < min_length:
        return False
    maiuscole = sum(1 for c in lettere if c.isupper())
    return (maiuscole / len(lettere)) * 100 >= threshold_percent


def is_zalgo_violation(text: str) -> bool:
    combinanti = sum(1 for c in text if unicodedata.combining(c) != 0)
    return combinanti >= ZALGO_COMBINING_THRESHOLD


def is_mass_mention_violation(mention_count: int, max_mentions: int) -> bool:
    return mention_count > max_mentions


def is_emoji_spam_violation(emoji_count: int, max_emoji: int) -> bool:
    return emoji_count > max_emoji


def is_rate_violation(count_in_window: int, max_count: int) -> bool:
    """
    Usata sia per anti-spam messaggi che per sticker/allegati: il
    chiamante ha già calcolato `count_in_window` (quanti eventi di
    quel tipo nella finestra temporale configurata, INCLUSO quello
    corrente) tramite core.automod_rate_tracker — questa funzione
    resta pura, la finestra mobile con lo stato nel tempo vive altrove.
    """
    return count_in_window > max_count


@dataclass(frozen=True)
class MessageSignals:
    """Tutto quello che serve valutare, già estratto dal messaggio reale."""

    content: str
    mention_count: int = 0
    emoji_count: int = 0
    attachment_count: int = 0
    sticker_count: int = 0
    recent_message_count: int = 1
    recent_attachment_count: int = 0
    recent_sticker_count: int = 0


@dataclass(frozen=True)
class AntiLinkConfig:
    mode: str = "off"  # "off" | "whitelist" | "blacklist"
    whitelist: tuple[str, ...] = ()
    blacklist: tuple[str, ...] = ()


@dataclass(frozen=True)
class RateFilterConfig:
    enabled: bool = False
    max_count: int = 5
    window_seconds: int = 10


@dataclass(frozen=True)
class ThresholdFilterConfig:
    enabled: bool = False
    max_count: int = 5


@dataclass(frozen=True)
class CapsFilterConfig:
    enabled: bool = False
    threshold_percent: int = 70
    min_length: int = 10


@dataclass(frozen=True)
class AutomodAdvancedConfig:
    """Configurazione completa dei filtri §6.3-§6.10 per un server."""

    anti_link: AntiLinkConfig = field(default_factory=AntiLinkConfig)
    anti_spam_messages: RateFilterConfig = field(default_factory=RateFilterConfig)
    anti_spam_emoji: ThresholdFilterConfig = field(default_factory=ThresholdFilterConfig)
    anti_spam_sticker: RateFilterConfig = field(default_factory=RateFilterConfig)
    anti_caps: CapsFilterConfig = field(default_factory=CapsFilterConfig)
    anti_zalgo_enabled: bool = False
    anti_mass_mention: ThresholdFilterConfig = field(default_factory=ThresholdFilterConfig)
    anti_attachment_spam: RateFilterConfig = field(default_factory=RateFilterConfig)


# Nomi delle violazioni possibili — usati come chiave sia per
# `evaluate_message_violations` che per la configurazione delle
# azioni (SPEC.md §6.13, core.repositories.automod_advanced_repo).
VIOLATION_ANTI_LINK = "anti_link"
VIOLATION_SPAM_MESSAGES = "anti_spam_messages"
VIOLATION_SPAM_EMOJI = "anti_spam_emoji"
VIOLATION_SPAM_STICKER = "anti_spam_sticker"
VIOLATION_CAPS = "anti_caps"
VIOLATION_ZALGO = "anti_zalgo"
VIOLATION_MASS_MENTION = "anti_mass_mention"
VIOLATION_ATTACHMENT_SPAM = "anti_attachment_spam"

ALL_VIOLATIONS = (
    VIOLATION_ANTI_LINK,
    VIOLATION_SPAM_MESSAGES,
    VIOLATION_SPAM_EMOJI,
    VIOLATION_SPAM_STICKER,
    VIOLATION_CAPS,
    VIOLATION_ZALGO,
    VIOLATION_MASS_MENTION,
    VIOLATION_ATTACHMENT_SPAM,
)


def evaluate_message_violations(
    signals: MessageSignals, config: AutomodAdvancedConfig
) -> tuple[str, ...]:
    """
    Valuta TUTTI i filtri e restituisce le violazioni scattate, in
    ordine fisso (quello di ALL_VIOLATIONS) — un messaggio può
    violare più filtri insieme (es. tutto maiuscolo E con un link
    non in whitelist), il chiamante decide come combinare le azioni.
    """
    violazioni = []

    domini = extract_domains(signals.content)
    if is_link_violation(domini, config.anti_link.mode, config.anti_link.whitelist, config.anti_link.blacklist):
        violazioni.append(VIOLATION_ANTI_LINK)

    if config.anti_spam_messages.enabled and is_rate_violation(
        signals.recent_message_count, config.anti_spam_messages.max_count
    ):
        violazioni.append(VIOLATION_SPAM_MESSAGES)

    if config.anti_spam_emoji.enabled and is_emoji_spam_violation(
        signals.emoji_count, config.anti_spam_emoji.max_count
    ):
        violazioni.append(VIOLATION_SPAM_EMOJI)

    if config.anti_spam_sticker.enabled and signals.sticker_count > 0 and is_rate_violation(
        signals.recent_sticker_count, config.anti_spam_sticker.max_count
    ):
        violazioni.append(VIOLATION_SPAM_STICKER)

    if config.anti_caps.enabled and is_caps_violation(
        signals.content, config.anti_caps.threshold_percent, config.anti_caps.min_length
    ):
        violazioni.append(VIOLATION_CAPS)

    if config.anti_zalgo_enabled and is_zalgo_violation(signals.content):
        violazioni.append(VIOLATION_ZALGO)

    if config.anti_mass_mention.enabled and is_mass_mention_violation(
        signals.mention_count, config.anti_mass_mention.max_count
    ):
        violazioni.append(VIOLATION_MASS_MENTION)

    if config.anti_attachment_spam.enabled and signals.attachment_count > 0 and is_rate_violation(
        signals.recent_attachment_count, config.anti_attachment_spam.max_count
    ):
        violazioni.append(VIOLATION_ATTACHMENT_SPAM)

    return tuple(violazioni)
