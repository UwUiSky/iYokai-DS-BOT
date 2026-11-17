"""
core/podcast_logic.py
=====================
Cerca un podcast per nome e ne trova il feed (ALR-007). Fonte: l'elenco pubblico di Apple Podcasts
(nessuna chiave); la richiesta passa da `core/safe_http.py` e ogni feed trovato si ricontrolla prima
di salvarlo. Funzioni coperte: SPEC §10.8 (#129 ALR-007)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlencode

from core.alert_messaggio_logic import pulisci_esterno
from core.safe_http import safe_get

URL_RICERCA = "https://itunes.apple.com/search"
MAX_RISULTATI = 5
MAX_URL_FEED = 512


@dataclass(frozen=True)
class Podcast:
    nome: str
    autore: str
    feed_url: str


def url_ricerca(termine: str) -> str:
    return URL_RICERCA + "?" + urlencode({"media": "podcast", "limit": MAX_RISULTATI * 2, "term": termine.strip()[:100]})


def leggi_risultati(testo: str) -> list[Podcast]:
    """Al massimo 5 podcast con un feed http/https corto; il resto (dati strani) si scarta."""
    try:
        dati = json.loads(testo)
    except ValueError:
        return []
    voci = dati.get("results") if isinstance(dati, dict) else None
    trovati: list[Podcast] = []
    for v in voci if isinstance(voci, list) else []:
        if not isinstance(v, dict):
            continue
        feed = v.get("feedUrl")
        if not isinstance(feed, str) or not feed.startswith(("https://", "http://")) or len(feed) > MAX_URL_FEED:
            continue
        nome = pulisci_esterno(v.get("collectionName") or v.get("trackName"), 80)
        if nome and all(p.feed_url != feed for p in trovati):
            trovati.append(Podcast(nome, pulisci_esterno(v.get("artistName"), 60), feed))
        if len(trovati) >= MAX_RISULTATI:
            break
    return trovati


async def cerca_podcast(termine: str) -> list[Podcast]:
    testo = await safe_get(url_ricerca(termine), max_bytes=500_000)
    return leggi_risultati(testo) if testo else []
