"""
core/animal_api_logic.py
=============================
Interpretazione delle risposte JSON delle tre API pubbliche usate da
`/fun animal` (SPEC.md §16.4) — logica pura, testabile senza rete:
riceve il payload già deserializzato e restituisce l'URL
dell'immagine, o None se il payload non ha la forma aspettata (mai
un'eccezione che interromperebbe il comando).

Tutte e tre le API sono gratuite e non richiedono una chiave —
a differenza di §16.9 (ricerca immagini SFW), che usa Pixabay e
quindi una chiave opzionale (stesso principio già seguito per
Twitch/YouTube in core/config.py).
"""

from __future__ import annotations


def parse_dog_response(payload: dict) -> str | None:
    """dog.ceo/api/breeds/image/random -> {"status": "success", "message": "https://..."}"""
    if not isinstance(payload, dict):
        return None
    if payload.get("status") != "success":
        return None
    url = payload.get("message")
    if not isinstance(url, str) or not url:
        return None
    return url


def parse_cat_response(payload: list) -> str | None:
    """api.thecatapi.com/v1/images/search -> [{"url": "https://...", ...}]"""
    if not isinstance(payload, list) or not payload:
        return None
    primo = payload[0]
    if not isinstance(primo, dict):
        return None
    url = primo.get("url")
    if not isinstance(url, str) or not url:
        return None
    return url


def parse_fox_response(payload: dict) -> str | None:
    """randomfox.ca/floof/ -> {"image": "https://...", "link": "https://..."}"""
    if not isinstance(payload, dict):
        return None
    url = payload.get("image")
    if not isinstance(url, str) or not url:
        return None
    return url
