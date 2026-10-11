"""
core/youtube_api_logic.py
=============================
Logica pura di YouTube live (SPEC.md §10.4, D5). Nessuna rete qui
dentro: interpreta il feed RSS del canale (gli ID dei video recenti) e
le risposte di `videos.list` (YouTube Data API v3) scaricate da
core/youtube_watcher.py. Un video e' in diretta se `liveBroadcastContent`
vale "live". Costo: il feed RSS non consuma quota, `videos.list` ne
consuma 1 unita' per gruppo di 50 ID (search.list ne costava 100 per
canale, BUG-16).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class YoutubeLiveStatus:
    channel_id: str
    is_live: bool
    video_id: str | None = None
    title: str | None = None


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
