"""
core/music_capitoli_fonti.py
============================
Video lunghi (MUS-017): da dove viene l'elenco dei brani di un video YouTube. Prima i capitoli che Lavalink mette
nella traccia (`pluginInfo`), poi la descrizione del video letta con la chiave `YOUTUBE_API_KEY` (la stessa degli
avvisi YouTube; la chiave viaggia in un'intestazione, mai nell'indirizzo). Senza capitoli e senza chiave non succede
niente. Descrizioni in memoria per un'ora e al massimo 1.500 richieste al giorno: la quota di YouTube e' di tutti.
Funzioni coperte: SPEC §9 (catalogo MUS-017)
Dipende da: core/safe_http.py (unico punto di rete), core/music_capitoli_logic.py
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone

from core.music_capitoli_logic import MAX_TESTO, MAX_VIDEO_MS, MIN_VIDEO_CAPITOLI_MS, Voce, analizza_elenco, voci_da_capitoli
from core.safe_http import safe_richiesta

logger = logging.getLogger("iyokai.music.capitoli")

YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
MAX_BYTE_RISPOSTA = 150_000
DURATA_CACHE = 3600.0
MAX_CACHE = 200
TETTO_GIORNALIERO = 1500
_ID_VIDEO = re.compile(r"^[A-Za-z0-9_-]{11}$")

_cache: dict[str, tuple[float, str | None]] = {}
_conteggio = {"giorno": "", "n": 0}


def id_video(traccia) -> str | None:
    """L'identificativo di un video YouTube (11 caratteri) da una traccia di Lavalink; None per ogni altra fonte."""
    if str(getattr(traccia, "source", "") or "").lower() != "youtube":
        return None
    identificativo = str(getattr(traccia, "identifier", "") or "")
    return identificativo if _ID_VIDEO.match(identificativo) else None


def candidato(traccia) -> bool:
    """Vale la pena cercare un elenco? Video YouTube tra 10 minuti e 8 ore, non una diretta."""
    lunghezza = getattr(traccia, "length", 0)
    return (
        id_video(traccia) is not None and not getattr(traccia, "is_stream", False)
        and isinstance(lunghezza, int) and MIN_VIDEO_CAPITOLI_MS <= lunghezza <= MAX_VIDEO_MS
    )


def descrizione_da_risposta(testo) -> str | None:
    """La descrizione dalla risposta JSON dell'API di YouTube; None se manca o la risposta e' storta."""
    try:
        dati = json.loads(testo)
        voci = dati["items"]
        descrizione = voci[0]["snippet"]["description"] if voci else None
    except (TypeError, ValueError, KeyError, IndexError):
        return None
    return descrizione[:MAX_TESTO] if isinstance(descrizione, str) else None


def _tetto_raggiunto(adesso: datetime | None = None) -> bool:
    giorno = (adesso or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    if _conteggio["giorno"] != giorno:
        _conteggio["giorno"], _conteggio["n"] = giorno, 0
    return _conteggio["n"] >= TETTO_GIORNALIERO


async def descrizione_video(video_id: str, chiave_api: str) -> str | None:
    """La descrizione di un video (con cache e tetto giornaliero), o None."""
    if not chiave_api or not _ID_VIDEO.match(video_id or ""):
        return None
    adesso = time.monotonic()
    trovata = _cache.get(video_id)
    if trovata is not None and adesso - trovata[0] < DURATA_CACHE:
        return trovata[1]
    if _tetto_raggiunto():
        logger.info("Tetto giornaliero delle descrizioni dei video raggiunto.")
        return None
    _conteggio["n"] += 1
    url = f"{YOUTUBE_VIDEOS_URL}?part=snippet&id={video_id}&fields=items(snippet(description))"
    corpo = await safe_richiesta(url, headers={"x-goog-api-key": chiave_api}, max_bytes=MAX_BYTE_RISPOSTA)
    descrizione = descrizione_da_risposta(corpo) if corpo else None
    if len(_cache) >= MAX_CACHE:
        _cache.pop(min(_cache, key=lambda k: _cache[k][0]), None)
    _cache[video_id] = (adesso, descrizione)
    return descrizione


def capitoli_dal_plugin(traccia) -> list[Voce]:
    """I capitoli che Lavalink dà nella traccia (`pluginInfo.chapters`), se ci sono."""
    dati = getattr(traccia, "raw_data", None)
    plugin = dati.get("pluginInfo") if isinstance(dati, dict) else None
    capitoli = plugin.get("chapters") if isinstance(plugin, dict) else None
    return voci_da_capitoli(capitoli, getattr(traccia, "length", None))


async def voci_del_video(traccia, chiave_api: str) -> list[Voce]:
    """L'elenco dei brani di un video lungo: capitoli di Lavalink, altrimenti la descrizione. Lista vuota se non c'e'."""
    if not candidato(traccia):
        return []
    voci = capitoli_dal_plugin(traccia)
    if voci:
        return voci
    descrizione = await descrizione_video(id_video(traccia), chiave_api)
    return analizza_elenco(descrizione, traccia.length) if descrizione else []
