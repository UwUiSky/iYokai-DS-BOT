"""
core/greetings_embed_logic.py
=============================
Benvenuto, DM e addio dentro un embed salvato (catalogo #123: RUO-001, RUO-014, RUO-015). Dai dati di un
embed salvato (core/embed_builder_logic) si fa l'embed vero, con i segnaposto sostituiti e tutti i testi
tagliati ai limiti di Discord. Funzioni semplici, provabili senza Discord.
Funzioni coperte: SPEC §14.4 (RUO-001, 014, 015)
"""

from __future__ import annotations

from typing import Callable

import discord

from core import embed_builder_logic as eb

DOVE = ("benvenuto", "dm", "addio")  # dove può stare l'embed
TOGLI = "togli"


def embed_con_segnaposto(dati: dict, rende: Callable[[str], str]) -> discord.Embed | None:
    """
    L'embed salvato con `rende` applicato a titolo, testo, piede e campi (i segnaposto). I testi si
    tagliano ai limiti; se l'embed resta non valido (vuoto, oltre 6000 in tutto) torna None: il
    messaggio parte lo stesso, solo con il testo.
    """
    try:
        salvato = eb.da_json(dati)
    except (TypeError, ValueError, KeyError):
        return None

    def cura(testo: str | None, massimo: int) -> str | None:
        return rende(testo)[:massimo] if testo else testo

    campi = tuple(
        (cura(n, eb.MAX_NOME_CAMPO) or "", cura(v, eb.MAX_VALORE_CAMPO) or "", i)
        for n, v, i in salvato.fields[: eb.MAX_CAMPI]
    )
    dati_finali = eb.DatiEmbed(
        title=cura(salvato.title, eb.MAX_TITOLO),
        description=cura(salvato.description, eb.MAX_DESCRIZIONE),
        color=salvato.color,
        image_url=salvato.image_url,
        thumbnail_url=salvato.thumbnail_url,
        footer=cura(salvato.footer, eb.MAX_PIEDE),
        fields=campi,
    )
    if eb.valida(dati_finali):
        return None
    return eb.costruisci(dati_finali)
