"""
core/moderation_nomi.py
=======================
Storico dei nomi (MOD-103) e soprannome / mute vocale ridati a chi rientra (MOD-104): le due scelte del server
(spente di base, sono dati personali con scadenza), le righe da mostrare e cosa si può ridare. Senza Discord.
Funzioni coperte: MOD-103, MOD-104
"""

from __future__ import annotations

import discord

SETTING_STORICO_NOMI = "mod_storico_nomi"
SETTING_PERSISTENZA = "mod_persistenza"
MAX_NICK = 32
TIPI = {"soprannome": "Soprannome", "nome": "Nome utente", "visualizzato": "Nome visualizzato"}


def pulisci(testo: str | None) -> str:
    """Un nome pronto da mostrare: senza markdown né menzioni."""
    return discord.utils.escape_mentions(discord.utils.escape_markdown(testo or "-"))[:100]


def riga(voce: dict) -> str:
    quando = int(voce["quando"].timestamp())
    return f"<t:{quando}:d> **{TIPI.get(voce['tipo'], voce['tipo'])}**: {pulisci(voce['prima'])} → {pulisci(voce['dopo'])}"


def nick_da_ridare(nick: str | None, ruolo_piu_alto_membro_sopra_bot: bool) -> str | None:
    """Il soprannome salvato, se si può ridare: non vuoto, entro 32 caratteri e il membro non sta sopra il bot."""
    if not nick or len(nick) > MAX_NICK or ruolo_piu_alto_membro_sopra_bot:
        return None
    return nick
