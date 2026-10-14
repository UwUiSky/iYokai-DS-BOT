"""
core/security_logic.py
==========================
Logica PURA (nessuna dipendenza da discord.py, nessun I/O) della
Security Suite (SPEC.md §7.1/§7.2/§7.5): Anti-Raid, Anti-Nuke,
Security Score. Stesso principio di core/automod_advanced_logic.py —
testabile con semplici input/output, il motore che legge Discord/DB
vive nei cog.

Anti-Nuke: soglia breve e soglia oraria per categoria, fiducia a livelli
(`TrustEntry`: fidato o extra owner, limitata a un'azione, a una categoria
di canali o a un webhook). La lista delle fiducie ha UNA fonte,
`trust_entries`: `aggiungi_fiducia` e `rimuovi_fiducia` (con le regole su
chi puo' toccare un extra owner) fondono nel nuovo formato anche i
`trusted_ids` vecchi; `voci_fiducia` li legge tutti insieme.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from datetime import datetime

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
    # SIC-003: chi non è fidato non può togliere la quarantena a mano (usa
    # /security antiraid rilascia) né dare altri ruoli a chi ci sta dentro.
    quarantine_hold: bool = False
    # SIC-023/024/026/027/028: filtri all'ingresso, ognuno con la sua azione
    # (core/security_join_logic.AZIONI_FILTRO). Lavorano anche fuori da un raid.
    azione_eta: str = "niente"
    azione_bot_non_verificato: str = "niente"
    azione_nome_pubblicitario: str = "niente"
    azione_nome_vietato: str = "niente"
    messaggio_eta: str = ""
    nomi_vietati: tuple[str, ...] = ()
    # SIC-029: la soglia di ingressi conta solo gli account sospetti.
    conta_solo_sospetti: bool = False
    # SIC-030/031: segnali di raid sugli ultimi ingressi (0 = spento).
    account_vicini_minimo: int = 0
    account_vicini_margine_secondi: int = 3600
    nomi_simili_minimo: int = 0
    # SIC-033: al raid, azione anche su chi è entrato nella finestra prima della soglia.
    retroattivo: bool = False
    # SIC-034: ruoli pingati nel primo allarme dell'episodio.
    ruoli_ping: tuple[int, ...] = ()


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
JOIN_VIOLATION_ACCOUNT_VICINI = "account_vicini"
JOIN_VIOLATION_NOMI_SIMILI = "nomi_simili"

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
    Il blocco del server scatta quando gli ingressi superano la soglia o
    quando gli ultimi ingressi si somigliano (account creati vicini, nomi
    simili: SIC-030/031). Gli altri segnali (account nuovo, nome sospetto,
    nessun avatar) da soli non bastano: descrivono chi entra durante un raid.
    """
    return bool({JOIN_VIOLATION_RATE, JOIN_VIOLATION_ACCOUNT_VICINI, JOIN_VIOLATION_NOMI_SIMILI} & set(violations))


# ================================================================
# Anti-Nuke (SPEC.md §7.2)
# ================================================================

NUKE_CATEGORY_CHANNEL = "channel"
NUKE_CATEGORY_ROLE = "role"
NUKE_CATEGORY_WEBHOOK = "webhook"
NUKE_CATEGORY_EMOJI = "emoji"
NUKE_CATEGORY_BAN_KICK = "ban_kick"
# SIC-007: cambi ai permessi dei canali (overwrite di ruoli e membri).
NUKE_CATEGORY_CHANNEL_PERMS = "channel_perms"
# SIC-005/006/008/009/025: non sono conteggi ma azioni singole; servono come
# "tipo di azione" nella fiducia limitata (SIC-019).
NUKE_ACTION_ROLE_PERMS = "role_perms"
NUKE_ACTION_MEMBER_ROLE = "member_role"
NUKE_ACTION_VANITY = "vanity"
NUKE_ACTION_BOT_ADD = "bot_add"
NUKE_ACTION_QUARANTINE_HOLD = "quarantine_hold"

ALL_NUKE_CATEGORIES = (
    NUKE_CATEGORY_CHANNEL,
    NUKE_CATEGORY_ROLE,
    NUKE_CATEGORY_WEBHOOK,
    NUKE_CATEGORY_EMOJI,
    NUKE_CATEGORY_BAN_KICK,
    NUKE_CATEGORY_CHANNEL_PERMS,
)

TRUST_LEVEL_TRUSTED = "trusted"
TRUST_LEVEL_EXTRA_OWNER = "extra_owner"
TRUST_KIND_USER = "user"
TRUST_KIND_WEBHOOK = "webhook"

# Finestra della seconda soglia (SIC-001): un'ora.
HOUR_WINDOW_SECONDS = 3600


@dataclass(frozen=True)
class TrustEntry:
    """
    Una fiducia piu' fine di un semplice ID in `trusted_ids`.

    - kind "user": utente o bot. kind "webhook": l'ID di un webhook
      (SIC-020), che esenta le azioni che lo riguardano.
    - level "extra_owner" (SIC-018): come l'owner, anche per cambiare
      le impostazioni dell'anti-nuke. "trusted": esente dai controlli,
      ma non tocca le impostazioni.
    - categories (SIC-019): vuoto = tutte le azioni; altrimenti solo
      quelle elencate.
    - channel_category_id (SIC-019): solo per le azioni sui canali, solo
      dentro questa categoria di Discord.
    """

    target_id: int
    kind: str = TRUST_KIND_USER
    level: str = TRUST_LEVEL_TRUSTED
    categories: tuple[str, ...] = ()
    channel_category_id: int | None = None


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
    channel_perms_max: int = 5
    channel_perms_window_seconds: int = 60
    # Seconda soglia (SIC-001): quante azioni in un'ora. 0 = spenta.
    channel_hour_max: int = 10
    role_hour_max: int = 10
    webhook_hour_max: int = 10
    emoji_hour_max: int = 20
    ban_kick_hour_max: int = 10
    channel_perms_hour_max: int = 20
    trusted_ids: tuple[int, ...] = ()
    punish_action: str = "quarantine"  # "quarantine" | "strip_roles" | "ban"
    recovery_enabled: bool = True
    trust_entries: tuple[TrustEntry, ...] = ()
    # Guardie su azioni singole (SIC-005/006, 008, 009, 025). Spente di default.
    role_perm_guard: str = "off"  # "off" | "public" | "all"
    member_role_guard: bool = False
    vanity_guard: bool = False
    bot_add_guard: bool = False


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
        NUKE_CATEGORY_CHANNEL_PERMS: config.channel_perms_window_seconds,
    }[category]


def category_max_count(category: str, config: AntiNukeConfig) -> int:
    return {
        NUKE_CATEGORY_CHANNEL: config.channel_max,
        NUKE_CATEGORY_ROLE: config.role_max,
        NUKE_CATEGORY_WEBHOOK: config.webhook_max,
        NUKE_CATEGORY_EMOJI: config.emoji_max,
        NUKE_CATEGORY_BAN_KICK: config.ban_kick_max,
        NUKE_CATEGORY_CHANNEL_PERMS: config.channel_perms_max,
    }[category]


def category_hour_max(category: str, config: AntiNukeConfig) -> int:
    """Seconda soglia (un'ora) della categoria; 0 = spenta."""
    return {
        NUKE_CATEGORY_CHANNEL: config.channel_hour_max,
        NUKE_CATEGORY_ROLE: config.role_hour_max,
        NUKE_CATEGORY_WEBHOOK: config.webhook_hour_max,
        NUKE_CATEGORY_EMOJI: config.emoji_hour_max,
        NUKE_CATEGORY_BAN_KICK: config.ban_kick_hour_max,
        NUKE_CATEGORY_CHANNEL_PERMS: config.channel_perms_hour_max,
    }[category]


def is_actor_trusted(actor_id: int, trusted_ids: tuple[int, ...]) -> bool:
    return actor_id in trusted_ids


def actor_is_trusted(
    actor_id: int,
    action: str,
    config: AntiNukeConfig,
    *,
    channel_category_id: int | None = None,
    target_id: int | None = None,
) -> bool:
    """
    True se l'autore e' esente per questa azione: fidato senza limiti,
    oppure con una fiducia (SIC-018/019/020) che copre questo tipo di
    azione, questa categoria di canali o questo webhook.
    `target_id` e' l'oggetto dell'azione (per i webhook: l'ID del webhook).
    """
    if is_actor_trusted(actor_id, config.trusted_ids):
        return True
    for voce in config.trust_entries:
        if voce.categories and action not in voce.categories:
            continue
        if voce.kind == TRUST_KIND_WEBHOOK:
            if target_id is not None and voce.target_id == target_id:
                return True
            continue
        if voce.target_id != actor_id:
            continue
        if voce.channel_category_id is not None and voce.channel_category_id != channel_category_id:
            continue
        return True
    return False


def is_extra_owner(user_id: int, config: AntiNukeConfig) -> bool:
    return any(
        voce.kind == TRUST_KIND_USER
        and voce.level == TRUST_LEVEL_EXTRA_OWNER
        and voce.target_id == user_id
        for voce in config.trust_entries
    )


def voci_fiducia(config: AntiNukeConfig) -> tuple[TrustEntry, ...]:
    """
    Tutte le fiducie del server, in un solo elenco. `trusted_ids` e'
    il formato di prima (un ID e basta): chi lo ha ancora salvato conta
    come una fiducia semplice, finche' la prima modifica non lo fonde
    nell'elenco (da li' in poi la fonte e' una sola: `trust_entries`).
    """
    presenti = {(v.target_id, v.kind) for v in config.trust_entries}
    vecchie = tuple(
        TrustEntry(target_id=i) for i in config.trusted_ids if (i, TRUST_KIND_USER) not in presenti
    )
    return config.trust_entries + vecchie


def aggiungi_fiducia(
    config: AntiNukeConfig,
    *,
    chi_id: int,
    owner_id: int,
    target_id: int,
    kind: str = TRUST_KIND_USER,
    level: str = TRUST_LEVEL_TRUSTED,
    categories: tuple[str, ...] = (),
    channel_category_id: int | None = None,
    max_voci: int = 100,
) -> tuple[AntiNukeConfig | None, str | None]:
    """
    Aggiunge (o sostituisce) una fiducia. Restituisce (nuova config, None)
    oppure (None, motivo del rifiuto). Le regole stanno qui, non nel comando:
    - un extra owner lo nomina solo il proprietario, ed e' sempre un
      utente valido per tutte le azioni (niente tipo, azione o categoria);
    - un extra owner esistente lo cambia (declassa o sostituisce) solo
      il proprietario: altrimenti un extra owner ne toglierebbe un altro
      dalla porta di servizio;
    - la lista ha un tetto.
    """
    e_owner = chi_id == owner_id
    if level == TRUST_LEVEL_EXTRA_OWNER:
        if not e_owner:
            return None, "Solo il proprietario del server può nominare un extra owner."
        if kind != TRUST_KIND_USER or categories or channel_category_id is not None:
            return None, "Un extra owner è un utente e vale per tutte le azioni: niente tipo, azione o categoria."
    if kind == TRUST_KIND_USER and not e_owner and is_extra_owner(target_id, config):
        return None, "Solo il proprietario del server può cambiare un extra owner."
    voci = voci_fiducia(config)
    altre = tuple(v for v in voci if not (v.target_id == target_id and v.kind == kind))
    if len(altre) >= max_voci:
        return None, f"La lista dei fidati è piena ({max_voci}): toglierne qualcuno con /antinuke trusted-remove."
    nuova = TrustEntry(
        target_id=target_id,
        kind=kind,
        level=level,
        categories=tuple(categories),
        channel_category_id=channel_category_id,
    )
    return dataclasses.replace(config, trusted_ids=(), trust_entries=altre + (nuova,)), None


def rimuovi_fiducia(
    config: AntiNukeConfig, *, chi_id: int, owner_id: int, target_id: int
) -> tuple[AntiNukeConfig | None, str | None]:
    """Toglie ogni fiducia di `target_id`. Togliere un extra owner spetta solo al proprietario."""
    if is_extra_owner(target_id, config) and chi_id != owner_id:
        return None, "Solo il proprietario del server può togliere un extra owner."
    voci = tuple(v for v in voci_fiducia(config) if v.target_id != target_id)
    return dataclasses.replace(config, trusted_ids=(), trust_entries=voci), None


def is_nuke_violation(
    actor_id: int,
    category: str,
    count_in_window: int,
    config: AntiNukeConfig,
    *,
    count_in_hour: int = 0,
    channel_category_id: int | None = None,
    target_id: int | None = None,
) -> bool:
    if not config.enabled:
        return False
    if actor_is_trusted(
        actor_id, category, config, channel_category_id=channel_category_id, target_id=target_id
    ):
        return False
    if is_rate_violation(count_in_window, category_max_count(category, config)):
        return True
    ora_max = category_hour_max(category, config)
    return ora_max > 0 and is_rate_violation(count_in_hour, ora_max)


# ================================================================
# Posizione del ruolo del bot (SIC-022)
# ================================================================

def bot_role_problems(
    *,
    has_manage_roles: bool,
    bot_top_position: int,
    quarantine_role_position: int | None,
    highest_staff_position: int,
) -> tuple[str, ...]:
    """
    Cosa impedisce al bot di fare il suo lavoro per colpa dei ruoli.
    `highest_staff_position` e' la posizione del ruolo piu' alto tra
    quelli con permessi pericolosi (non gestiti da bot): se sta sopra al
    ruolo del bot, il bot non puo' toglierlo a chi attacca.
    """
    problemi = []
    if not has_manage_roles:
        problemi.append(
            "Al mio ruolo manca il permesso Gestisci ruoli: non posso mettere in quarantena né togliere ruoli."
        )
    if quarantine_role_position is not None and quarantine_role_position >= bot_top_position:
        problemi.append(
            "Il ruolo di quarantena sta sopra al mio ruolo più alto: non posso assegnarlo. Sposta il mio ruolo più in alto."
        )
    if highest_staff_position >= bot_top_position:
        problemi.append(
            "C'è un ruolo con permessi pericolosi sopra al mio: chi lo ha non si può fermare. "
            "Metti il mio ruolo subito sotto quello del proprietario."
        )
    return tuple(problemi)


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
    # SIC-022: cosa, nei ruoli, impedisce al bot di lavorare (frasi pronte).
    role_problems: tuple[str, ...] = ()


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

    # Due amministratori (oltre al proprietario) non sono "troppi" nemmeno
    # in un server piccolo, dove sarebbero comunque piu' del 5%.
    if signals.total_member_count > 0 and signals.admin_member_count > 2:
        quota_admin = signals.admin_member_count / signals.total_member_count
        if quota_admin > 0.05:
            punteggio -= 15
            consigli.append(
                "Troppi membri hanno permessi di amministratore: valuta ruoli più mirati."
            )

    if not signals.anti_raid_enabled:
        punteggio -= 15
        consigli.append("Attiva l'Anti-Raid con /security antiraid enable.")

    if not signals.anti_nuke_enabled:
        punteggio -= 15
        consigli.append("Attiva l'Anti-Nuke con /antinuke enable.")

    if not signals.automod_badwords_active:
        punteggio -= 10
        consigli.append("Attiva il modulo AutoMod per un filtro di base sui contenuti.")

    if signals.role_problems:
        punteggio -= 10
        consigli.extend(signals.role_problems)

    return max(0, punteggio), tuple(consigli)
