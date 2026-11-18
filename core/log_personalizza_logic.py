"""
core/log_personalizza_logic.py
==============================
Logica pura per personalizzare i log: il testo scritto dal server per un evento (LOG-026) con i segnaposto
presi dall'embed già pronto, e il formato della data. Il testo passa da `core/template_renderer.py`
(mai `str.format`): un segnaposto sconosciuto resta com'è.
Funzioni coperte: SPEC §8.20 (LOG-016, LOG-026)
Dipende da: core/template_renderer.py
"""

from __future__ import annotations

import re
import unicodedata

import discord

from core.template_renderer import render_template
from core.testo_limiti import DESCRIZIONE_MAX, tronca

FORMATO_MAX = 300
# Stili di data di Discord: lettera -> etichetta (l'ordine è quello del comando).
FORMATI_DATA: dict[str, str] = {
    "f": "Data e ora breve",
    "F": "Data e ora lunga",
    "d": "Solo data breve",
    "D": "Solo data lunga",
    "t": "Solo ora breve",
    "T": "Solo ora lunga",
    "R": "Relativa (3 ore fa)",
}
FORMATO_DATA_BASE = "f"
RIFERIMENTO_ROTTA = "rotta_"  # prefisso del «tipo» con cui i log di una rotta avvisano il proprietario
MAX_SEGNAPOSTO = 30


def nome_segnaposto(nome_campo: str) -> str:
    """«ID messaggio» -> «id_messaggio»: solo lettere minuscole e trattini bassi, come chiede il renderer."""
    ascii_ = unicodedata.normalize("NFKD", nome_campo).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z]+", "_", ascii_).strip("_")


def segnaposto_da_embed(embed: discord.Embed, formato_data: str = FORMATO_DATA_BASE) -> dict[str, str]:
    """`{titolo}`, `{descrizione}`, `{data}` e un segnaposto per ogni riga dell'embed (il suo nome in minuscolo)."""
    stile = formato_data if formato_data in FORMATI_DATA else FORMATO_DATA_BASE
    valori = {
        "titolo": embed.title or "",
        "descrizione": embed.description or "",
        "data": discord.utils.format_dt(embed.timestamp, style=stile) if embed.timestamp else "",
    }
    for campo in embed.fields[:MAX_SEGNAPOSTO]:
        nome = nome_segnaposto(campo.name or "")
        if nome and nome not in ("titolo", "descrizione", "data"):
            valori[nome] = campo.value or ""
    return valori


def applica_formato(embed: discord.Embed, testo: str, formato_data: str = FORMATO_DATA_BASE) -> bool:
    """
    LOG-026: la descrizione dell'embed diventa il testo del server, senza le righe. Titolo, colore e
    miniatura restano. Un risultato vuoto lascia l'embed com'era (False).
    """
    scritto = render_template(testo[:FORMATO_MAX], segnaposto_da_embed(embed, formato_data)).strip()
    if not scritto:
        return False
    embed.description = tronca(scritto, DESCRIZIONE_MAX)
    embed.clear_fields()
    return True


def testo_segnaposto() -> str:
    """L'aiuto per chi scrive un formato."""
    return (
        "{titolo}, {descrizione}, {data}, più una parola per ogni riga dell'evento, in minuscolo "
        "(per esempio {autore}, {canale}, {prima}, {dopo}, {utente})."
    )
