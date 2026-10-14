"""
core/channel_access.py
======================
Controlla che il bot possa fare ciò che serve in un canale prima di
promettere qualcosa all'utente (gioco del conteggio, giveaway programmati).
Funzioni coperte: SPEC §15.5, §23.6, §23.16
"""

from __future__ import annotations

PERMESSI_DI_SCRITTURA = ("view_channel", "send_messages", "embed_links")
PERMESSI_DI_REAZIONE = ("view_channel", "send_messages", "add_reactions", "read_message_history")

_NOMI = {
    "view_channel": "Vedere il canale",
    "send_messages": "Inviare messaggi",
    "embed_links": "Incorporare link",
    "add_reactions": "Aggiungere reazioni",
    "read_message_history": "Leggere la cronologia",
}


def permessi_mancanti(canale, me, richiesti: tuple[str, ...]) -> list[str]:
    """
    I nomi (in italiano) dei permessi che al bot mancano in `canale`. Vuoto se
    non si può controllare (canale o bot senza `permissions_for`): il controllo
    non deve mai bloccare ciò che Discord stesso permetterebbe.
    """
    if me is None or not hasattr(canale, "permissions_for"):
        return []
    permessi = canale.permissions_for(me)
    return [_NOMI[nome] for nome in richiesti if not getattr(permessi, nome, True)]


def motivo_se_il_bot_non_puo(canale, me, richiesti: tuple[str, ...]) -> str | None:
    """Una frase con i permessi mancanti, oppure None se va tutto bene."""
    mancano = permessi_mancanti(canale, me, richiesti)
    if not mancano:
        return None
    return "al bot mancano questi permessi nel canale: " + ", ".join(mancano)
