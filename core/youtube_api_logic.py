"""
core/youtube_api_logic.py
=============================
Logica pura di YouTube live (SPEC.md §10.4). Nessuna rete qui dentro
— solo interpretazione delle risposte JSON dell'endpoint
`search.list` della YouTube Data API v3, già scaricate dal chiamante
(core/youtube_watcher.py). Stesso principio di core/twitch_api_logic.py.

Perché search.list e non un endpoint più economico
-------------------------------------------------------
La YouTube Data API non ha un endpoint dedicato "questo canale è live
adesso?" — il modo documentato da Google per scoprirlo è interrogare
`search.list` con `channelId=<id>` ed `eventType=live`
`type=video`: se la ricerca restituisce un video, quel canale è live
in questo momento, con l'id del video in diretta. Questo endpoint
costa 100 unità di quota per chiamata (su una quota giornaliera
gratuita di 10.000), molto più caro del semplice feed RSS già usato
per "nuovo video" (SPEC.md §10.3, zero quota) — è esattamente il
motivo per cui SPEC.md segnava questa voce come rimandata: non è
affidabile via RSS (che non indica lo stato live) e richiede una
chiave API a consumo. Ora che l'infrastruttura di sblocco opzionale
via env var esiste già per Twitch, lo stesso principio si applica
qui: la funzione resta inattiva finché YOUTUBE_API_KEY non è
configurata, e col watcher a intervalli più lunghi di Twitch per non
esaurire la quota in fretta con molti canali sottoscritti.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class YoutubeLiveStatus:
    channel_id: str
    is_live: bool
    video_id: str | None = None
    title: str | None = None


def parse_search_live_response(payload: dict, channel_id: str) -> YoutubeLiveStatus:
    """
    Interpreta la risposta di UNA chiamata a search.list per UN
    canale (channelId/eventType=live/type=video già nei parametri
    della richiesta, non qui). Se `items` è vuoto, il canale non è
    live in questo momento — non è un errore, è lo stato normale
    nella stragrande maggioranza dei tick.
    """
    items = payload.get("items", [])
    if not items:
        return YoutubeLiveStatus(channel_id=channel_id, is_live=False)

    primo = items[0]
    video_id = primo.get("id", {}).get("videoId")
    titolo = primo.get("snippet", {}).get("title")
    if not video_id:
        # Risposta malformata/inattesa: trattato come non-live invece
        # di sollevare — un tick perso non deve mai far crashare il
        # watcher, ne riprova al giro successivo.
        return YoutubeLiveStatus(channel_id=channel_id, is_live=False)

    return YoutubeLiveStatus(
        channel_id=channel_id, is_live=True, video_id=video_id, title=titolo
    )
