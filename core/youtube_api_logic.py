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


# D5 / M 11.1: il feed RSS del canale dice QUALI video esistono (zero
# quota); una sola `videos.list` per gruppo di 50 ID dice quali sono live.
VIDEOS_LIST_MAX_ID = 50
VIDEO_PER_CANALE = 5  # i piu' recenti del feed: una diretta in corso e' tra questi


def video_id_da_voce(entry_id: str, link: str = "") -> str | None:
    """ID del video da una voce del feed YouTube ("yt:video:<id>", oppure ?v=<id> nel link)."""
    if entry_id.startswith("yt:video:"):
        return entry_id.removeprefix("yt:video:") or None
    if "v=" in link:
        return link.split("v=", 1)[1].split("&", 1)[0] or None
    return None


@dataclass(frozen=True)
class YoutubeVideoInfo:
    video_id: str
    title: str
    is_live: bool


def parse_videos_list_response(payload: dict) -> dict[str, YoutubeVideoInfo]:
    """`videos.list` (part=snippet): video_id -> info, con is_live da liveBroadcastContent."""
    risultato = {}
    for item in payload.get("items", []):
        video_id = item.get("id")
        if not isinstance(video_id, str) or not video_id:
            continue
        snippet = item.get("snippet", {})
        risultato[video_id] = YoutubeVideoInfo(
            video_id=video_id,
            title=snippet.get("title") or "",
            is_live=snippet.get("liveBroadcastContent") == "live",
        )
    return risultato


def stato_live_del_canale(
    channel_id: str, video_ids: list[str], info: dict[str, YoutubeVideoInfo]
) -> YoutubeLiveStatus:
    """Il canale e' live se almeno uno dei suoi video recenti lo e'."""
    for video_id in video_ids:
        voce = info.get(video_id)
        if voce is not None and voce.is_live:
            return YoutubeLiveStatus(
                channel_id=channel_id, is_live=True, video_id=voce.video_id, title=voce.title
            )
    return YoutubeLiveStatus(channel_id=channel_id, is_live=False)
