"""
core/nsfw_fonti.py
==================
Ricerca sulle fonti ammesse dell'istanza NSFW (oggi RedGifs) e scarico
dell'anteprima, per calcolarne l'impronta. Cache dei risultati per tag:
poche richieste alla fonte. Mai un'eccezione verso il chiamante.
Funzioni coperte: SPEC §16.10 (NF-23)
Dipende da: core/nsfw_filter_logic.py
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

import aiohttp

from core.nsfw_filter_logic import FONTI, ElementoFonte, dominio_della_fonte, leggi_redgifs
from core.safe_image import MAX_IMAGE_BYTES

logger = logging.getLogger("iyokai.nsfw_fonti")

TIMEOUT_SECONDI = 10
REDGIFS_API = "https://api.redgifs.com"
DURATA_CACHE_SECONDI = 10 * 60
DURATA_GETTONE_SECONDI = 12 * 3600
MAX_TAG_IN_CACHE = 200
RISULTATI_PER_RICERCA = 40


class FontiNsfw:
    def __init__(self, api: str = REDGIFS_API, adesso: Callable[[], float] = time.monotonic) -> None:
        self._api = api.rstrip("/")
        self._adesso = adesso
        self._sessione: aiohttp.ClientSession | None = None
        self._gettone: tuple[float, str] | None = None
        self._cache: dict[str, tuple[float, list[ElementoFonte]]] = {}

    def _http(self) -> aiohttp.ClientSession:
        if self._sessione is None or self._sessione.closed:
            self._sessione = aiohttp.ClientSession(headers={"User-Agent": "iYokai-NSFW/1.0"})
        return self._sessione

    async def _json(self, url: str, **kw) -> object | None:
        try:
            async with self._http().get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDI), **kw) as r:
                if r.status != 200:
                    logger.warning("La fonte NSFW ha risposto %d.", r.status)
                    return None
                return await r.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            logger.warning("Fonte NSFW non raggiungibile: %s", type(exc).__name__)
            return None

    async def _gettone_redgifs(self) -> str | None:
        ora = self._adesso()
        if self._gettone is not None and ora - self._gettone[0] < DURATA_GETTONE_SECONDI:
            return self._gettone[1]
        dati = await self._json(f"{self._api}/v2/auth/temporary")
        gettone = dati.get("token") if isinstance(dati, dict) else None
        if not isinstance(gettone, str) or not gettone:
            return None
        self._gettone = (ora, gettone)
        return gettone

    async def cerca(self, tag: str) -> list[ElementoFonte] | None:
        """Elementi per `tag` (non ancora filtrati). None se la fonte non risponde."""
        chiave = " ".join(tag.lower().split())
        ora = self._adesso()
        in_cache = self._cache.get(chiave)
        if in_cache is not None and ora - in_cache[0] < DURATA_CACHE_SECONDI:
            return in_cache[1]
        gettone = await self._gettone_redgifs()
        if gettone is None:
            return None
        dati = await self._json(
            f"{self._api}/v2/gifs/search",
            params={"search_text": chiave, "order": "top", "count": RISULTATI_PER_RICERCA, "page": 1},
            headers={"Authorization": f"Bearer {gettone}"},
        )
        if dati is None:
            self._gettone = None  # un gettone scaduto si rinnova al prossimo giro
            return None
        elementi = leggi_redgifs(dati)
        if len(self._cache) >= MAX_TAG_IN_CACHE:
            self._cache.pop(next(iter(self._cache)))
        self._cache[chiave] = (ora, elementi)
        return elementi

    async def scarica_anteprima(self, elemento: ElementoFonte) -> bytes | None:
        """Byte dell'anteprima (solo dai domini della fonte, solo immagini, entro 8 MB)."""
        fonte = FONTI.get(elemento.fonte)
        if fonte is None or not dominio_della_fonte(elemento.url_anteprima, fonte):
            return None
        try:
            async with self._http().get(
                elemento.url_anteprima, allow_redirects=False, timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDI)
            ) as r:
                if r.status != 200 or not (r.content_type or "").lower().startswith("image/"):
                    return None
                corpo = bytearray()
                async for blocco in r.content.iter_chunked(8192):
                    corpo.extend(blocco)
                    if len(corpo) > MAX_IMAGE_BYTES:
                        return None
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.warning("Anteprima NSFW non scaricata: %s", type(exc).__name__)
            return None
        return bytes(corpo)

    async def close(self) -> None:
        if self._sessione is not None:
            await self._sessione.close()
            self._sessione = None


fonti_nsfw = FontiNsfw()
