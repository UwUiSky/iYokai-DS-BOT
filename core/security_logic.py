"""
core/security_logic.py
==========================
Logica PURA (nessuna dipendenza da discord.py, nessun I/O) della
Security Suite (SPEC.md §7.1/§7.2/§7.5): Anti-Raid, Anti-Nuke,
Security Score. Stesso principio di core/automod_advanced_logic.py —
testabile con semplici input/output, il motore che legge Discord/DB
vive nei cog.
"""

# DA FARE (issue #59, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §3 (Sicurezza (anti-raid,
#   anti-nuke, spam-trap, ban globale)).

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# ================================================================
# Anti-Raid (SPEC.md §7.1)
# ================================================================

# Pattern tipico di un account generato in massa da un raid-bot:
# parola/lettere seguite da 4+ cifre (es. "asjdk4821", "user93021").
# Un nome utente umano scelto a mano raramente termina con 4+ cifre
# consecutive — falsi positivi possibili ma rari. Soglia scelta per
# inferenza, nessun dettaglio più fine specificato dall'utente.
_SUSPICIOUS_USERNAME_RE = re.compile(r"^[A-Za-z]{2,}\d{4,}$")


def is_suspicious_username(username: str) -> bool:
    return bool(_SUSPICIOUS_USERNAME_RE.fullmatch(username))


def is_account_too_new(account_created_at: datetime, now: datetime, min_age_seconds: int) -> bool:
    return (now - account_created_at).total_seconds() < min_age_seconds


def is_rate_violation(count_in_window: int, max_count: int) -> bool:
    """Condivisa da anti-raid (join rate) e anti-nuke (azioni di massa)."""
    return count_in_window > max_count


@dataclass(frozen=True)
class AntiRaidConfig:
    enabled: bool = False
    join_rate_max: int = 10
    join_rate_window_seconds: int = 60
    min_account_age_seconds: int = 86400  # 1 giorno, per inferenza
    check_username_pattern: bool = True
    check_avatar_pattern: bool = True
    lockdown_action: str = "quarantine"  # "quarantine" | "verification" | "both"


@dataclass(frozen=True)
class JoinSignals:
    account_created_at: datetime
    has_avatar: bool
    username: str
    recent_join_count: int


JOIN_VIOLATION_RATE = "join_rate"
JOIN_VIOLATION_ACCOUNT_AGE = "account_age"
JOIN_VIOLATION_USERNAME = "username_pattern"
JOIN_VIOLATION_AVATAR = "avatar_pattern"

ALL_JOIN_VIOLATIONS = (
    JOIN_VIOLATION_RATE,
    JOIN_VIOLATION_ACCOUNT_AGE,
    JOIN_VIOLATION_USERNAME,
    JOIN_VIOLATION_AVATAR,
)


def evaluate_join(signals: JoinSignals, config: AntiRaidConfig, now: datetime) -> tuple[str, ...]:
    if not config.enabled:
        return ()

    violazioni = []
    if is_rate_violation(signals.recent_join_count, config.join_rate_max):
        violazioni.append(JOIN_VIOLATION_RATE)
    if is_account_too_new(signals.account_created_at, now, config.min_account_age_seconds):
        violazioni.append(JOIN_VIOLATION_ACCOUNT_AGE)
    if config.check_username_pattern and is_suspicious_username(signals.username):
        violazioni.append(JOIN_VIOLATION_USERNAME)
    if config.check_avatar_pattern and not signals.has_avatar:
        violazioni.append(JOIN_VIOLATION_AVATAR)
    return tuple(violazioni)


def is_raid(violations: tuple[str, ...]) -> bool:
    """
    Il blocco del server scatta solo quando gli ingressi superano la
    soglia. Gli altri segnali (account nuovo, nome sospetto, nessun
    avatar) da soli non bastano: descrivono chi entra durante un raid.
    """
    return JOIN_VIOLATION_RATE in violations


# ================================================================
# Anti-Nuke (SPEC.md §7.2)
# ================================================================

NUKE_CATEGORY_CHANNEL = "channel"
NUKE_CATEGORY_ROLE = "role"
NUKE_CATEGORY_WEBHOOK = "webhook"
NUKE_CATEGORY_EMOJI = "emoji"
NUKE_CATEGORY_BAN_KICK = "ban_kick"

ALL_NUKE_CATEGORIES = (
    NUKE_CATEGORY_CHANNEL,
    NUKE_CATEGORY_ROLE,
    NUKE_CATEGORY_WEBHOOK,
    NUKE_CATEGORY_EMOJI,
    NUKE_CATEGORY_BAN_KICK,
)


@dataclass(frozen=True)
class AntiNukeConfig:
    enabled: bool = False
    channel_max: int = 3
    channel_window_seconds: int = 60
    role_max: int = 3
    role_window_seconds: int = 60
    webhook_max: int = 3
    webhook_window_seconds: int = 60
    emoji_max: int = 5
    emoji_window_seconds: int = 60
    ban_kick_max: int = 3
    ban_kick_window_seconds: int = 60
    trusted_ids: tuple[int, ...] = ()
    punish_action: str = "strip_roles"  # "strip_roles" | "ban"
    recovery_enabled: bool = True


# Finestra per categoria: usata dal cog per sapere quale
# window_seconds passare al rate tracker senza un grosso if/elif
# ripetuto in ogni singolo handler di evento.
def category_window_seconds(category: str, config: AntiNukeConfig) -> int:
    return {
        NUKE_CATEGORY_CHANNEL: config.channel_window_seconds,
        NUKE_CATEGORY_ROLE: config.role_window_seconds,
        NUKE_CATEGORY_WEBHOOK: config.webhook_window_seconds,
        NUKE_CATEGORY_EMOJI: config.emoji_window_seconds,
        NUKE_CATEGORY_BAN_KICK: config.ban_kick_window_seconds,
    }[category]


def category_max_count(category: str, config: AntiNukeConfig) -> int:
    return {
        NUKE_CATEGORY_CHANNEL: config.channel_max,
        NUKE_CATEGORY_ROLE: config.role_max,
        NUKE_CATEGORY_WEBHOOK: config.webhook_max,
        NUKE_CATEGORY_EMOJI: config.emoji_max,
        NUKE_CATEGORY_BAN_KICK: config.ban_kick_max,
    }[category]


def is_actor_trusted(actor_id: int, trusted_ids: tuple[int, ...]) -> bool:
    return actor_id in trusted_ids


def is_nuke_violation(
    actor_id: int, category: str, count_in_window: int, config: AntiNukeConfig
) -> bool:
    if not config.enabled:
        return False
    if is_actor_trusted(actor_id, config.trusted_ids):
        return False
    return is_rate_violation(count_in_window, category_max_count(category, config))


# ================================================================
# Security Score (SPEC.md §7.5)
# ================================================================

@dataclass(frozen=True)
class ServerSecuritySignals:
    mfa_level: int  # guild.mfa_level: 0 = nessun requisito, 1 = 2FA richiesto per lo staff
    verification_level: str  # "none" | "low" | "medium" | "high" | "highest"
    admin_member_count: int
    total_member_count: int
    anti_raid_enabled: bool
    anti_nuke_enabled: bool
    automod_badwords_active: bool


_LOW_VERIFICATION_LEVELS = ("none", "low")


def compute_security_score(signals: ServerSecuritySignals) -> tuple[int, tuple[str, ...]]:
    """
    Restituisce (punteggio 0-100, consigli). Ogni controllo pesa un
    valore fisso, scelto per inferenza (nessuna formula "ufficiale"
    esiste per un security score di un server Discord) — l'obiettivo
    è dare un segnale utile e azionabile, non un numero preciso al
    punto percentuale.
    """
    punteggio = 100
    consigli = []

    if signals.mfa_level == 0:
        punteggio -= 15
        consigli.append("Attiva l'autenticazione a due fattori obbligatoria per lo staff (impostazioni del server).")

    if signals.verification_level in _LOW_VERIFICATION_LEVELS:
        punteggio -= 10
        consigli.append("Alza il livello di verifica del server (Impostazioni → Moderazione).")

    if signals.total_member_count > 0:
        quota_admin = signals.admin_member_count / signals.total_member_count
        if quota_admin > 0.05:
            punteggio -= 15
            consigli.append(
                "Troppi membri hanno permessi di amministratore: valuta ruoli più mirati."
            )

    if not signals.anti_raid_enabled:
        punteggio -= 15
        consigli.append("Attiva l'Anti-Raid con /anti-raid enable.")

    if not signals.anti_nuke_enabled:
        punteggio -= 15
        consigli.append("Attiva l'Anti-Nuke con /anti-nuke enable.")

    if not signals.automod_badwords_active:
        punteggio -= 10
        consigli.append("Attiva il modulo AutoMod per un filtro di base sui contenuti.")

    return max(0, punteggio), tuple(consigli)
