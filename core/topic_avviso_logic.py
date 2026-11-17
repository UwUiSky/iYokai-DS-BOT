"""
core/topic_avviso_logic.py
==========================
Avviso «è cambiato l'argomento di un canale» (catalogo #123: RUO-027). Il testo dell'argomento lo scrive
un utente: si pulisce prima di metterlo in un messaggio. Funzioni semplici, provabili senza Discord.
Funzioni coperte: SPEC §14.4 (RUO-027)
"""

from __future__ import annotations

import discord

MAX_ARGOMENTO = 500
PAUSA_PER_CANALE_SECONDI = 60


def pulisci_argomento(testo: str | None) -> str:
    """L'argomento senza menzioni, senza formattazione che apre link o blocchi e senza a-capo, tagliato."""
    if not testo:
        return ""
    pulito = discord.utils.escape_markdown(discord.utils.escape_mentions(testo))
    pulito = " ".join(pulito.split())  # a-capo e spazi doppi
    pulito = "".join(c for c in pulito if c.isprintable() or c == "\u200b")
    return pulito[:MAX_ARGOMENTO]


def messaggio_avviso(menzione_canale: str, prima: str | None, dopo: str | None) -> str:
    """Il messaggio dell'avviso: vecchio e nuovo argomento (puliti); None o vuoto = «nessuno»."""
    vecchio = pulisci_argomento(prima) or "nessuno"
    nuovo = pulisci_argomento(dopo) or "nessuno"
    return f"L'argomento di {menzione_canale} è cambiato.\nPrima: {vecchio}\nOra: {nuovo}"[:2000]


def va_annunciato(prima: str | None, dopo: str | None) -> bool:
    """Solo se l'argomento è davvero cambiato (None e vuoto sono la stessa cosa)."""
    return (prima or "") != (dopo or "")
