"""
tests/support/command_policy.py
===================================
Chi deve poter vedere ogni comando top-level del bot, e l'elenco
dei problemi noti ancora aperti ("cricchetto": l'elenco può solo
accorciarsi, vedi tests/test_command_policy.py).

Pubblici:
- PUBLIC: chiunque nel server.
- STAFF: solo chi ha un permesso Discord (o una delega del server in
  Integrazioni). Deve avere `default_permissions`.
- OWNER: solo il proprietario del bot. Deve avere `default_permissions`
  e, dopo la ristrutturazione (REVIEW.md R5), esistere solo nel server
  privato.
- MIXED: gruppi che oggi mescolano sotto-comandi pubblici e da staff.
  `default_permissions` vale per il gruppo intero, quindi vanno divisi
  (REVIEW.md §6, fase R5).
"""

from __future__ import annotations

PUBLIC = "public"
STAFF = "staff"
OWNER = "owner"
MIXED = "mixed"

AUDIENCE: dict[str, str] = {
    # AutoMod e sicurezza
    "automod": STAFF,
    "escalation": STAFF,
    "anti-nuke": STAFF,
    "anti-raid": STAFF,
    "global-ban": STAFF,
    "permission-heatmap": STAFF,
    "security-score": STAFF,
    "spamtrap-setup": STAFF,
    "verify": STAFF,
    # Moderazione
    "warn": STAFF,
    "kick": STAFF,
    "ban": STAFF,
    "tempban": STAFF,
    "unban": STAFF,
    "timeout": STAFF,
    "untimeout": STAFF,
    "softban": STAFF,
    "mute-role": STAFF,
    "unmute-role": STAFF,
    "modcase": STAFF,
    "modnote": STAFF,
    "lock": STAFF,
    "unlock": STAFF,
    "slowmode": STAFF,
    "clear": STAFF,
    "mod-log-setup": STAFF,
    "report-setup": STAFF,
    "report": PUBLIC,
    # Log
    "logs-setup": STAFF,
    "logs-status": STAFF,
    "logs": STAFF,
    # Fun
    "fun": PUBLIC,
    "ship": PUBLIC,
    "rate": PUBLIC,
    # Livelli, economia, clan
    "rank": PUBLIC,
    "balance": PUBLIC,
    "daily": PUBLIC,
    "work": PUBLIC,
    "pay": PUBLIC,
    "leaderboard": PUBLIC,
    "clan": PUBLIC,
    "shop": MIXED,
    "cassa": MIXED,
    "level-roles": STAFF,
    "monthly-winners": STAFF,
    "assegna-lobby": STAFF,
    "assegna-winner": STAFF,
    "giveaway": STAFF,
    # Musica
    "play": PUBLIC,
    "skip": PUBLIC,
    "stop": PUBLIC,
    "pause": PUBLIC,
    "resume": PUBLIC,
    "queue": PUBLIC,
    "clear-queue": PUBLIC,
    "shuffle": PUBLIC,
    "loop": PUBLIC,
    "nowplaying": PUBLIC,
    "volume": PUBLIC,
    "disconnect": PUBLIC,
    "nonstop": PUBLIC,
    "nonstop-main": OWNER,
    # Ticket
    "ticket": PUBLIC,
    "ticket-setup": STAFF,
    "ticket-panel": STAFF,
    "ticket-category": STAFF,
    "ticket-support-role": STAFF,
    "ticket-stats": STAFF,
    # Vocali temporanei
    "voice": PUBLIC,
    "voicetemp-setup": STAFF,
    "voicetemp-panel": STAFF,
    "voicetemp-cap": STAFF,
    "voicetemp-platform-setup": STAFF,
    # Utility
    "ping": PUBLIC,
    "poll": PUBLIC,
    "reminder": PUBLIC,
    "search": PUBLIC,
    "serverstats": PUBLIC,
    "reactionsnipe": PUBLIC,
    "suggest": PUBLIC,
    "request-custom-command": PUBLIC,
    "config": MIXED,
    "setup": STAFF,
    "setup-wizard": STAFF,
    "alerts": STAFF,
    "greetings": STAFF,
    "rolemenu": STAFF,
    "schedule-message": STAFF,
    "sticky": STAFF,
    "suggestion-setup": STAFF,
    "define-main": STAFF,
    "define-backup": STAFF,
    "promuovi-backup": STAFF,
    "configura-restore": STAFF,
    "restore-users": STAFF,
    # Owner
    "owner": OWNER,
    "custom-command-requests-setup": OWNER,
}

# Comandi staff/owner che oggi NON hanno default_permissions (tutti,
# REVIEW.md §6 / SEC-1). Ogni fix toglie il nome da qui.
KNOWN_MISSING_DEFAULT_PERMISSIONS: frozenset[str] = frozenset(
    name for name, audience in AUDIENCE.items() if audience in (STAFF, OWNER)
)

# Comandi che oggi non sono guild_only (tutti, REVIEW.md LC-2).
KNOWN_NOT_GUILD_ONLY: frozenset[str] = frozenset(AUDIENCE)
