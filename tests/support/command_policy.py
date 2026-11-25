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
from core.comandi_diretti import DIRETTI

PUBLIC = "public"
STAFF = "staff"
OWNER = "owner"
MIXED = "mixed"

AUDIENCE: dict[str, str] = {
    # Staff, sotto il loro ruolo (D60)
    "admin-ai": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-automod": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-backup": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-benvenuto": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-bot": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-economia": STAFF,  # gruppo condiviso per ruolo (D60)
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
    "admin-alert": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-vocali": STAFF,  # gruppo condiviso per ruolo (D60)
    "mod-ban": STAFF,  # gruppo condiviso per ruolo (D60)
    "mod-canali": STAFF,  # gruppo condiviso per ruolo (D60)
    "mod-casi": STAFF,  # gruppo condiviso per ruolo (D60)
    "mod-sanzioni": STAFF,  # gruppo condiviso per ruolo (D60)
    "founder": STAFF,  # gruppo condiviso per ruolo (D60)
    "admin-sicurezza-antinuke": STAFF,  # gruppo condiviso per ruolo (D137)
    "admin-sicurezza-antiraid": STAFF,  # gruppo condiviso per ruolo (D137)
    "admin-sicurezza-verifica": STAFF,  # gruppo condiviso per ruolo (D137)
    "admin-automod-filtri": STAFF,  # gruppo condiviso per ruolo (D137)
    "admin-ruoli-menu": STAFF,  # gruppo condiviso per ruolo (D137)
    "admin-economia-negozio": STAFF,  # gruppo condiviso per ruolo (D137)
    "admin-livelli-rep": STAFF,  # gruppo condiviso per ruolo (D137)
    "admin-livelli-guadagno": STAFF,  # gruppo condiviso per ruolo (D137)
    "admin-messaggi-tag": STAFF,  # gruppo condiviso per ruolo (D137)
    "admin-ticket-pannelli": STAFF,  # gruppo condiviso per ruolo (D137)
    "admin-bot-config": STAFF,  # gruppo condiviso per ruolo (D137)
    "ai": PUBLIC,  # gruppo condiviso per tutti (D137)
    "vocali": PUBLIC,  # gruppo condiviso per tutti (D137)
    "monete-clan": PUBLIC,  # gruppo condiviso per tutti (D137)
    "music-playlist": PUBLIC,  # gruppo condiviso per tutti (D137)
    "giochi-sala": PUBLIC,  # gruppo condiviso per tutti (D137)
    "giochi-mondo": PUBLIC,  # gruppo condiviso per tutti (D137)
    "giochi-animali": PUBLIC,  # gruppo condiviso per tutti (D137)
    "utility-web": PUBLIC,  # gruppo condiviso per tutti (D137)
    "utility-server": PUBLIC,  # gruppo condiviso per tutti (D137)
    "help": PUBLIC,  # primo livello, unisce chiedi e cerca-comando (D137)
    "play": PUBLIC,  # comando diretto (D137)
    "skip": PUBLIC,  # comando diretto (D137)
    "stop": PUBLIC,  # comando diretto (D137)
    "pause": PUBLIC,  # comando diretto (D137)
    "resume": PUBLIC,  # comando diretto (D137)
    "queue": PUBLIC,  # comando diretto (D137)
    "ban": STAFF,  # comando diretto (D137)
    "kick": STAFF,  # comando diretto (D137)
    "mute": STAFF,  # comando diretto (D137)
    "shadowban": STAFF,  # comando diretto (D137)
    "giochi": PUBLIC,  # gruppo condiviso per tutti (D56)
    "immagini": PUBLIC,  # gruppo condiviso per tutti (D56)
    "monete": PUBLIC,  # gruppo condiviso per tutti (D56)
    "admin-inviti": STAFF,  # gruppo condiviso per ruolo (D69)
    "admin-automazioni": STAFF,  # script, inneschi e comandi del server (D69)
    "admin-giochi": STAFF,  # gruppo condiviso per ruolo (D69)
    "Salva citazione": PUBLIC,  # menu del tasto destro (D69, B16)
    "Statistiche del membro": PUBLIC,  # menu del tasto destro, solo server (STA-011); il filtro per ruolo è nel codice (STA-013)
    "Statistiche del canale": PUBLIC,  # menu del tasto destro sul messaggio (STA-011)
    "Orari nel mio fuso": PUBLIC,  # menu del tasto destro (D69, B6)
    "Riestrai giveaway": STAFF,  # menu del tasto destro (D69, B10)
    "Richiedi copia sicura": STAFF,  # menu del tasto destro, solo «Gestisci messaggi» (D74, #160)
    "Apri ticket": PUBLIC,  # menu col tasto destro sul messaggio (TKT-009)
    "Segnala messaggio": PUBLIC,  # menu col tasto destro sul messaggio (MOD-105)
    "Scheda moderazione": STAFF,  # menu col tasto destro sull'utente (MOD-106)
    # Moderazione
    # Log
    # Fun
    "fun": PUBLIC,
    # Livelli, economia, clan
    "level": PUBLIC,  # gruppo condiviso (core/command_groups.py)
    "music": PUBLIC,  # gruppo condiviso (core/command_groups.py)
    # Musica
    # Ticket
    "ticket": PUBLIC,
    # Vocali temporanei
    # Utility
    "utility": PUBLIC,  # gruppo condiviso (core/command_groups.py)
    # Owner: /owner è solo nel server dell'owner, non nell'albero globale
}

# I gruppi condivisi di F7 hanno già permessi e guild_only: fuori dai cricchetti.
# I menu col tasto destro già solo-server (e con permessi, se staff) contano come i gruppi.
_MENU_CON_PERMESSI = frozenset({"Scheda moderazione", "Apri ticket", "Segnala messaggio", "Riestrai giveaway"})
_GRUPPI_YOKAI = frozenset(nomi_gruppi()) | _MENU_CON_PERMESSI | frozenset(DIRETTI)  # i diretti copiano i permessi del gruppo

# Comandi staff/owner che oggi NON hanno default_permissions (tutti,
# REVIEW.md §6 / SEC-1). Ogni fix toglie il nome da qui.
KNOWN_MISSING_DEFAULT_PERMISSIONS: frozenset[str] = frozenset(
    name
    for name, audience in AUDIENCE.items()
    if audience in (STAFF, OWNER) and name not in _GRUPPI_YOKAI
)

# Comandi che oggi non sono guild_only (tutti, REVIEW.md LC-2).
# `help` è usabile anche in DM (D24): resta nel cricchetto.
KNOWN_NOT_GUILD_ONLY: frozenset[str] = frozenset(AUDIENCE) - _GRUPPI_YOKAI
