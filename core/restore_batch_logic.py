"""
core/restore_batch_logic.py
===============================
Logica pura (nessun I/O) di /restore-users (SPEC.md §11.11/§11.12):
per ogni utente nello snapshot, decide COSA fare — nessuna chiamata
a Discord o al database qui, solo la decisione; l'esecuzione vera
vive nel comando (cogs/utility/restore.py).
"""

from __future__ import annotations

from core.repositories.restore_oauth_repo import (
    STATUS_ACTIVE,
    STATUS_BANNED_BLACKLISTED,
    STATUS_KICKED_FLAGGED,
)

MODE_VERIFY_OAUTH = "verify_oauth"
MODE_ON_DEMAND_OAUTH = "on_demand_oauth"
MODE_CLASSIC_INVITE = "classic_invite"
DEFAULT_RESTORE_MODE = MODE_ON_DEMAND_OAUTH

ACTION_AUTO_JOIN = "auto_join"
ACTION_REQUEST_CONSENT = "request_consent"
ACTION_CLASSIC_INVITE = "classic_invite"
ACTION_SKIP_BLACKLISTED = "skip_blacklisted"

# Un token di chi è stato KICKATO resta comunque valido per un
# restore: kickare qualcuno da un server non è la stessa decisione
# di escluderlo per sempre da una migrazione dell'intero server
# (disaster recovery) — è la scelta esplicita dell'utente per il
# solo caso BAN (blacklist vera).
_STATI_TOKEN_RIUTILIZZABILI = frozenset({STATUS_ACTIVE, STATUS_KICKED_FLAGGED})


def plan_restore_action(mode: str, token_status: str | None, token_expired: bool) -> str:
    """
    mode: una delle costanti MODE_*.
    token_status: STATUS_ACTIVE/STATUS_KICKED_FLAGGED/
        STATUS_BANNED_BLACKLISTED, o None se non esiste alcun token
        salvato per questo utente.
    token_expired: irrilevante se token_status è None.
    """
    if token_status == STATUS_BANNED_BLACKLISTED:
        return ACTION_SKIP_BLACKLISTED

    if mode == MODE_CLASSIC_INVITE:
        return ACTION_CLASSIC_INVITE

    if token_status in _STATI_TOKEN_RIUTILIZZABILI and not token_expired:
        return ACTION_AUTO_JOIN

    return ACTION_REQUEST_CONSENT
