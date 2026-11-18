"""
core/youtube_link_logic.py
==========================
Da un link YouTube qualsiasi (video, Short, @nome, playlist, canale) all'ID del canale (ALR-011).
Una sola richiesta, solo verso i siti di YouTube, sempre con `core/safe_http.py`.
Funzioni coperte: SPEC §10.4 (#129 ALR-011)
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from core.safe_http import safe_get

HOST_YOUTUBE = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
_ID = re.compile(r"^UC[\w-]{22}$")
_NEL_PERCORSO = re.compile(r"/channel/(UC[\w-]{22})(?:[/?#]|$)")
_NELLA_PAGINA = (
    re.compile(r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]{22})"'),
    re.compile(r'<meta itemprop="(?:channelId|identifier)" content="(UC[\w-]{22})"'),
    re.compile(r'"externalId":"(UC[\w-]{22})"'),
    re.compile(r'"channelId":"(UC[\w-]{22})"'),
)
MAX_PAGINA_BYTE = 1_500_000


def indirizzo_youtube(testo: str) -> str | None:
    """Il link ripulito se punta a un sito di YouTube (https), altrimenti None. Un @nome diventa il suo link."""
    testo = (testo or "").strip()
    if testo.startswith("@") and re.fullmatch(r"@[\w.-]{3,60}", testo):
        return f"https://www.youtube.com/{testo}"
    if "://" not in testo:
        testo = "https://" + testo
    parti = urlsplit(testo)
    if parti.scheme not in ("http", "https") or (parti.hostname or "").lower() not in HOST_YOUTUBE or parti.username:
        return None
    if parti.port not in (None, 80, 443) or len(testo) > 300:
        return None
    return testo


def id_canale_diretto(testo: str) -> str | None:
    """L'ID se il testo è già un ID o un link /channel/UC…; non fa richieste."""
    testo = (testo or "").strip()
    if _ID.match(testo):
        return testo
    trovato = _NEL_PERCORSO.search(urlsplit(testo if "://" in testo else "https://" + testo).path + "/")
    return trovato.group(1) if trovato else None


def id_nella_pagina(html: str) -> str | None:
    for modello in _NELLA_PAGINA:
        m = modello.search(html or "")
        if m:
            return m.group(1)
    return None


async def risolvi_canale(testo: str) -> str | None:
    """ID del canale (UC…) dal link, con al massimo una richiesta a YouTube; None se non si trova."""
    diretto = id_canale_diretto(testo)
    if diretto:
        return diretto
    indirizzo = indirizzo_youtube(testo)
    if indirizzo is None:
        return None
    pagina = await safe_get(indirizzo, max_bytes=MAX_PAGINA_BYTE)
    return id_nella_pagina(pagina) if pagina else None
