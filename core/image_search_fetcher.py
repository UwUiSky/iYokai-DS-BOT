"""
core/image_search_fetcher.py
============================
Ricerca di un'immagine SFW su Pixabay (SPEC §16.9), con le condizioni
d'uso di Pixabay: risultati in cache per 24 ore, immagine scaricata e
restituita come byte (mai collegata), link alla pagina Pixabay per il
credito. `safesearch=true` è sempre impostato: il filtro SFW è di Pixabay.
Funzioni coperte: M 15.2 (LIM-48).
Dipende da: PIXABAY_API_KEY (core/config.py), core/image_search_logic.py.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse

import aiohttp

from core.image_search_logic import parse_pixabay_hits
from core.safe_image import MAX_IMAGE_BYTES

logger = logging.getLogger("iyokai.image_search_fetcher")

REQUEST_TIMEOUT_SECONDS = 10
MAX_BYTE_TOTALI = 8 * 1024 * 1024  # più foto nello stesso messaggio: restano sotto i 10 MiB di Discord
PIXABAY_SEARCH_URL = "https://pixabay.com/api/"
DURATA_CACHE_SECONDI = 24 * 60 * 60
MAX_RICERCHE_IN_CACHE = 200
DOMINI_IMMAGINE = ("pixabay.com",)


@dataclass(frozen=True)
class RisultatoImmagine:
    dati: bytes
    estensione: str
    pagina: str


class ImageSearchFetcherService:
    def __init__(
        self,
        search_url: str = PIXABAY_SEARCH_URL,
        domini_immagine: tuple[str, ...] = DOMINI_IMMAGINE,
        adesso: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http_session: aiohttp.ClientSession | None = None
        self._search_url = search_url
        self._domini = domini_immagine
        self._adesso = adesso
        self._cache: dict[str, tuple[float, list[tuple[str, str]]]] = {}

    def _get_session(self) -> aiohttp.ClientSession:
        if self._http_session is None:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    def _dominio_ammesso(self, url: str) -> bool:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        return parsed.scheme in ("http", "https") and any(
            host == d or host.endswith("." + d) for d in self._domini
        )

    async def _cerca(self, api_key: str, query: str) -> list[tuple[str, str]] | None:
        """Risultati (url, pagina) dalla cache o da Pixabay; None se la richiesta fallisce."""
        chiave = " ".join(query.lower().split())
        ora = self._adesso()
        in_cache = self._cache.get(chiave)
        if in_cache is not None and ora - in_cache[0] < DURATA_CACHE_SECONDI:
            return in_cache[1]

        try:
            async with self._get_session().get(
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
                    logger.warning("Pixabay ha risposto con status %d.", risposta.status)
                    return None
                payload = await risposta.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            # Niente testo dell'eccezione: aiohttp ci scrive l'indirizzo intero, con la chiave.
            logger.warning("Impossibile contattare Pixabay (%s).", type(exc).__name__)
            return None

        risultati = parse_pixabay_hits(payload)
        if len(self._cache) >= MAX_RICERCHE_IN_CACHE:
            self._cache.pop(next(iter(self._cache)))
        self._cache[chiave] = (ora, risultati)
        return risultati

    async def _scarica(self, url: str) -> tuple[bytes, str] | None:
        if not self._dominio_ammesso(url):
            logger.warning("Immagine fuori da Pixabay, scartata.")
            return None
        try:
            async with self._get_session().get(
                url, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
            ) as risposta:
                tipo = (risposta.content_type or "").lower()
                if risposta.status != 200 or not tipo.startswith("image/"):
                    return None
                corpo = bytearray()
                async for blocco in risposta.content.iter_chunked(8192):
                    corpo.extend(blocco)
                    if len(corpo) > MAX_IMAGE_BYTES:
                        return None
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.warning("Impossibile scaricare l'immagine: %s", exc)
            return None
        estensione = tipo.split("/", 1)[1].replace("jpeg", "jpg")
        return bytes(corpo), estensione if estensione.isalnum() else "png"

    async def fetch_image(
        self, api_key: str, query: str, rng: random.Random
    ) -> RisultatoImmagine | None:
        """
        Un risultato a caso per `query`, già scaricato. None se la chiave è
        vuota, la rete fallisce o non c'è nulla: mai un'eccezione.
        """
        if not api_key:
            return None
        risultati = await self._cerca(api_key, query)
        if not risultati:
            return None
        url, pagina = rng.choice(risultati)
        scaricata = await self._scarica(url)
        if scaricata is None:
            return None
        return RisultatoImmagine(dati=scaricata[0], estensione=scaricata[1], pagina=pagina)

    async def fetch_immagini(
        self, api_key: str, query: str, rng: random.Random, quante: int
    ) -> list[RisultatoImmagine]:
        """
        Fino a `quante` foto diverse per `query`, scaricate insieme, in tutto sotto MAX_BYTE_TOTALI.
        Lista vuota se la chiave manca, la rete fallisce o non c'è nulla: mai un'eccezione.
        """
        if not api_key:
            return []
        risultati = await self._cerca(api_key, query)
        if not risultati:
            return []
        scelti = rng.sample(risultati, min(max(1, quante), len(risultati)))
        scaricate = await asyncio.gather(*(self._scarica(url) for url, _ in scelti))
        trovate, totale = [], 0
        for (_, pagina), esito in zip(scelti, scaricate):
            if esito is None or totale + len(esito[0]) > MAX_BYTE_TOTALI:
                continue
            totale += len(esito[0])
            trovate.append(RisultatoImmagine(dati=esito[0], estensione=esito[1], pagina=pagina))
        return trovate

    async def close(self) -> None:
        if self._http_session is not None:
            await self._http_session.close()
            self._http_session = None


image_search_fetcher = ImageSearchFetcherService()
