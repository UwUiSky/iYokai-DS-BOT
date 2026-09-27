"""
core/premium_status_logic.py
================================
Logica pura di formattazione per SPEC.md §3.2: "elencare i server in
whitelist" e "visualizzare lo stato premium di tutti i server".
Nessuna chiamata al database o a Discord qui dentro — solo funzioni
che prendono dati già letti e restituiscono una riga di testo, così
sono testabili senza un bot vero o una connessione al database (stesso
principio già seguito da core/ticket_logic.py, core/snipe_logic.py).
"""

from __future__ import annotations

from datetime import datetime


def format_whitelist_entry(
    guild_id: int,
    added_by: int,
    reason: str | None,
    added_at: datetime,
) -> str:
    """Una riga per /owner whitelist-list."""
    riga = f"`{guild_id}` — aggiunto da `{added_by}` il `{added_at.date().isoformat()}`"
    if reason:
        riga += f" — motivo: {reason}"
    return riga


def format_guild_status_line(
    guild_id: int,
    guild_name: str,
    whitelisted: bool,
    boosts_main_guild: bool,
    cassa_active: bool,
    subscription_count: int,
) -> str:
    """
    Una riga per /owner premium-status-all: elenca OGNI meccanismo di
    sblocco davvero attivo per questo server, non solo un True/False
    complessivo — così si capisce SUBITO perché un server ha (o non
    ha) accesso, senza dover controllare ogni comando singolarmente.
    """
    meccanismi = []
    if whitelisted:
        meccanismi.append("whitelist")
    if boosts_main_guild:
        meccanismi.append("nitro boost")
    if cassa_active:
        meccanismi.append("premium via cassa")
    if subscription_count > 0:
        meccanismi.append(f"{subscription_count} abbonamento/i per modulo")

    if meccanismi:
        dettaglio = ", ".join(meccanismi)
    else:
        dettaglio = "nessuno sblocco proprio"

    return f"`{guild_id}` ({guild_name}) — {dettaglio}"
