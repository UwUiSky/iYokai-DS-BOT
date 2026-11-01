"""
core/user_app_risposte.py
=========================
Risposte salvate personali di iYokai App (SPEC §B.5): nome, colore e immagine si controllano qui, senza
Discord. Il testo si scrive come risposta dell'app, mai a nome della persona.
Funzioni coperte: SPEC §B.5 (NF-36, #107)
Dipende da: core/user_app_strumenti.py
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from core.user_app_strumenti import ErroreStrumento, leggi_colore

MAX_TESTO = 2000
MAX_TITOLO = 256
MAX_URL = 300
_NOME = re.compile(r"^[a-z0-9_-]{1,32}$")


def normalizza_nome(nome: str) -> str:
    """Il nome come si salva: minuscolo, senza spazi ai lati. Non valido = ErroreStrumento."""
    pulito = (nome or "").strip().lower()
    if not _NOME.match(pulito):
        raise ErroreStrumento("app_risposta_nome_non_valido")
    return pulito


def colore_intero(testo: str | None) -> int | None:
    """Il colore come numero RGB (per l'embed), o None se la persona non l'ha scelto."""
    if not testo or not testo.strip():
        return None
    c = leggi_colore(testo)
    return (c.r << 16) | (c.g << 8) | c.b


def immagine_valida(url: str | None) -> str | None:
    """L'indirizzo dell'immagine se è https e corto; vuoto = nessuna immagine. Altro = ErroreStrumento."""
    if not url or not url.strip():
        return None
    url = url.strip()
    parti = urlsplit(url)
    if parti.scheme != "https" or not parti.netloc or len(url) > MAX_URL:
        raise ErroreStrumento("app_risposta_immagine_non_valida")
    return url


def e_embed(titolo: str | None, colore: int | None, immagine_url: str | None) -> bool:
    """Una risposta con titolo, colore o immagine esce come embed; altrimenti come testo semplice."""
    return bool(titolo) or colore is not None or bool(immagine_url)
