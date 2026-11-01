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

from core.command_groups import nomi_gruppi

PUBLIC = "public"
STAFF = "staff"
OWNER = "owner"
MIXED = "mixed"

AUDIENCE: dict[str, str] = {
    # Staff, sotto il loro ruolo (D60)
    "admin-ai": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-antinuke": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-antiraid": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-automod": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-backup": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-benvenuto": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-bot": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-economia": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-filtri": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-giveaway": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-livelli": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-log": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-messaggi": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-moduli": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-musica": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-ruoli": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-sicurezza": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-ticket": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-ticket-opzioni": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-vocali": STAFF,  # gruppo condiviso per ruolo (D60)
    "mod-ban": STAFF,  # gruppo condiviso per ruolo (D60)
    "mod-canali": STAFF,  # gruppo condiviso per ruolo (D60)
    "mod-casi": STAFF,  # gruppo condiviso per ruolo (D60)
    "mod-sanzioni": STAFF,  # gruppo condiviso per ruolo (D60)
    "founder": STAFF,  # gruppo condiviso per ruolo (D60)
    "assistente": PUBLIC,  # gruppo condiviso per tutti (D56)
    "giochi": PUBLIC,  # gruppo condiviso per tutti (D56)
    "immagini": PUBLIC,  # gruppo condiviso per tutti (D56)
    "monete": PUBLIC,  # gruppo condiviso per tutti (D56)
    "sondaggi": PUBLIC,  # gruppo condiviso per tutti (D56)
    # Moderazione
    # Log
    # Fun
    "fun": PUBLIC,
    # Livelli, economia, clan
    "level": PUBLIC,  # gruppo condiviso (core/command_groups.py)
    "clan": PUBLIC,  # gruppo condiviso
    "music": PUBLIC,  # gruppo condiviso (core/command_groups.py)
    # Musica
    # Ticket
    "ticket": PUBLIC,
    # Vocali temporanei
    "voice": PUBLIC,
    # Utility
    "-cerca-comando": PUBLIC,  # primo livello, col trattino (D24, 06/10/2026)
    "-chiedi": PUBLIC,  # primo livello, mostra il pannello di -cerca-comando (#147)
    "utility": PUBLIC,  # gruppo condiviso (core/command_groups.py)
    # Owner: /owner è solo nel server dell'owner, non nell'albero globale
}

# I gruppi condivisi di F7 hanno già permessi e guild_only: fuori dai cricchetti.
_GRUPPI_YOKAI = frozenset(nomi_gruppi())

# Comandi staff/owner che oggi NON hanno default_permissions (tutti,
# REVIEW.md §6 / SEC-1). Ogni fix toglie il nome da qui.
KNOWN_MISSING_DEFAULT_PERMISSIONS: frozenset[str] = frozenset(
    name
    for name, audience in AUDIENCE.items()
    if audience in (STAFF, OWNER) and name not in _GRUPPI_YOKAI
)

# Comandi che oggi non sono guild_only (tutti, REVIEW.md LC-2).
# `-cerca-comando` è usabile anche in DM (D24): resta nel cricchetto.
KNOWN_NOT_GUILD_ONLY: frozenset[str] = frozenset(AUDIENCE) - _GRUPPI_YOKAI
