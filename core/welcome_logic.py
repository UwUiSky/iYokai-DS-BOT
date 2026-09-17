"""
core/welcome_logic.py
========================
Logica pura della catena di fallback per il messaggio di benvenuto
all'ingresso in un nuovo server (SPEC.md §1.8). Tre tentativi in
ordine, il primo che funziona vince:
1. il canale di sistema del server (`system_channel`), se il bot può
   scriverci
2. il primo canale testuale in cui il bot può scrivere, altrimenti
3. un DM al proprietario del server, come ultima risorsa

Qui c'è solo LA DECISIONE di quale via tentare, come stringa — non
l'invio vero (quello vive in main.py, con gli oggetti Discord reali
e la gestione degli errori HTTP).
"""

from __future__ import annotations

from typing import Literal

WelcomeTarget = Literal["system_channel", "first_writable_channel", "dm_owner"]


def choose_welcome_target(
    can_send_in_system_channel: bool,
    has_any_writable_channel: bool,
) -> WelcomeTarget:
    if can_send_in_system_channel:
        return "system_channel"
    if has_any_writable_channel:
        return "first_writable_channel"
    return "dm_owner"
