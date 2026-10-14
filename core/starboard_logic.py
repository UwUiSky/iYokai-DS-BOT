"""
core/starboard_logic.py
=======================
Logica pura della bacheca (starboard, NF-08, SPEC §22.4): conteggio delle
stelle e embed entro i limiti di Discord.
Funzioni coperte: SPEC §22 (NF-08)
"""

from __future__ import annotations

from typing import Iterable

import discord

SOGLIA_MIN = 1
SOGLIA_MAX = 25
SOGLIA_PREDEFINITA = 3
EMOJI_PREDEFINITA = "⭐"

_MAX_AUTORE = 256
_MAX_DESCRIZIONE = 4096
_MAX_CAMPO = 1024
_MAX_RIGA_ALLEGATO = 200


def conta_stelle(utenti: Iterable, autore_id: int, voto_autore: bool) -> int:
    """Utenti diversi che hanno messo l'emoji: niente bot, e (di norma) niente voto dell'autore."""
    visti: set[int] = set()
    for utente in utenti:
        if getattr(utente, "bot", False):
            continue
        if not voto_autore and utente.id == autore_id:
            continue
        visti.add(utente.id)
    return len(visti)


def contenuto_bacheca(emoji: str, stelle: int, canale_id: int) -> str:
    return f"{emoji} **{stelle}** | <#{canale_id}>"


def _taglia(testo: str, massimo: int) -> str:
    return testo if len(testo) <= massimo else testo[: massimo - 1] + "…"


def costruisci_embed(
    *,
    testo: str,
    nome_autore: str,
    avatar_url: str | None,
    link: str,
    immagine_url: str | None,
    allegati: list[str],
) -> discord.Embed:
    """L'embed della bacheca: testo, autore, immagine, allegati non immagine, link all'originale."""
    embed = discord.Embed(description=_taglia(testo, _MAX_DESCRIZIONE) if testo else None, color=0xFFAC33)
    embed.set_author(name=_taglia(nome_autore, _MAX_AUTORE), icon_url=avatar_url)
    if immagine_url:
        embed.set_image(url=immagine_url)
    if allegati:
        righe: list[str] = []
        totale = 0
        for url in allegati:
            riga = _taglia(url, _MAX_RIGA_ALLEGATO)
            if totale + len(riga) + 1 > _MAX_CAMPO:
                break
            righe.append(riga)
            totale += len(riga) + 1
        if righe:
            embed.add_field(name="Allegati", value="\n".join(righe), inline=False)
    embed.add_field(name="Originale", value=f"[Vai al messaggio]({link})", inline=False)
    return embed
