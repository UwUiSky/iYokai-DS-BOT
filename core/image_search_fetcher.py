"""
core/image_search_fetcher.py
==================================
Recupero on-demand di un'immagine SFW a partire da un termine di
ricerca (SPEC.md §16.9), via Pixabay — stesso principio di sblocco
opzionale via variabile d'ambiente già usato per Twitch/YouTube
(core/config.py: PIXABAY_API_KEY vuota di default). A differenza di
core/animal_fetcher.py (nessuna chiave richiesta), questo comando
NON può funzionare affatto senza una chiave: Pixabay la richiede per
ogni richiesta, non è un extra opzionale.

`safesearch=true` è SEMPRE impostato in ogni richiesta — è Pixabay
stesso, lato server, a garantire che i risultati siano SFW; questo
codice si limita a interpretarli (core/image_search_logic.py).
"""

from __future__ import annotations

import logging
import random

import aiohttp

from core.image_search_logic import parse_pixabay_response

logger = logging.getLogger("iyokai.image_search_fetcher")

REQUEST_TIMEOUT_SECONDS = 10
PIXABAY_SEARCH_URL = "https://pixabay.com/api/"


class ImageSearchFetcherService:
    def __init__(self, search_url: str = PIXABAY_SEARCH_URL) -> None:
        self._http_session: aiohttp.ClientSession | None = None
        self._search_url = search_url

    def _get_session(self) -> aiohttp.ClientSession:
        if self._http_session is None:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    async def fetch_image_url(self, api_key: str, query: str, rng: random.Random) -> str | None:
        """
        Restituisce un URL casuale tra i risultati trovati per
        `query`, o None se la chiave è vuota, la richiesta fallisce
        (rete, timeout, status non-200) o non ci sono risultati —
        mai un'eccezione.
        """
        if not api_key:
            return None

        sessione = self._get_session()
        try:
            async with sessione.get(
                self._search_url,
                params={
                    "key": api_key,
                    "q": query,
                    "safesearch": "true",
                    "image_type": "photo",
                    "per_page": 20,
                },
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
            ) as risposta:
                if risposta.status != 200:
                    logger.warning(
                        "Richiesta a Pixabay fallita con status %d per la ricerca '%s'.",
                        risposta.status,
                        query,
                    )
                    return None
                payload = await risposta.json()
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.warning("Impossibile contattare Pixabay per la ricerca '%s': %s", query, exc)
            return None

        urls = parse_pixabay_response(payload)
        if not urls:
            return None
        return rng.choice(urls)

    async def close(self) -> None:
        if self._http_session is not None:
            await self._http_session.close()
            self._http_session = None


image_search_fetcher = ImageSearchFetcherService()
