"""
core/image_search_logic.py
================================
Interpretazione della risposta JSON di Pixabay per la ricerca di
immagini SFW (SPEC.md §16.9) — logica pura, testabile senza rete.

Pixabay applica il proprio filtro SFW lato server tramite il
parametro `safesearch=true` sulla richiesta (core/image_search_
fetcher.py lo imposta sempre) — non è questo modulo a dover
riconoscere contenuti espliciti, solo a interpretare risultati che
Pixabay ha già filtrato.
"""

from __future__ import annotations


def parse_pixabay_response(payload: dict) -> list[str]:
    """
    pixabay.com/api -> {"total": N, "totalHits": N, "hits": [
    {"webformatURL": "https://...", "tags": "..."}, ...]}

    Restituisce la lista degli URL trovati (può essere vuota se la
    ricerca non ha prodotto risultati, o se il payload non ha la
    forma aspettata) — mai un'eccezione.
    """
    if not isinstance(payload, dict):
        return []

    hits = payload.get("hits")
    if not isinstance(hits, list):
        return []

    urls = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        url = hit.get("webformatURL")
        if isinstance(url, str) and url:
            urls.append(url)
    return urls


def parse_pixabay_hits(payload: dict) -> list[tuple[str, str]]:
    """
    Come `parse_pixabay_response`, ma ogni risultato è la coppia
    (url dell'immagine, url della sua pagina su Pixabay). Se manca la
    pagina si usa la home di Pixabay: il credito c'è sempre.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("hits"), list):
        return []

    trovati = []
    for hit in payload["hits"]:
        if not isinstance(hit, dict):
            continue
        url = hit.get("webformatURL")
        if not (isinstance(url, str) and url):
            continue
        pagina = hit.get("pageURL")
        if not (isinstance(pagina, str) and pagina.startswith("https://")):
            pagina = "https://pixabay.com"
        trovati.append((url, pagina))
    return trovati
