"""
core/animal_fetcher.py
============================
Recupero on-demand di un'immagine casuale di animale (SPEC.md
§16.4) da tre API pubbliche GRATUITE, nessuna chiave richiesta:
dog.ceo (cane), thecatapi.com (gatto), randomfox.ca (volpe).

A differenza di core/twitch_watcher.py e core/youtube_watcher.py,
questo servizio non ha un `tasks.loop` periodico: la richiesta
avviene una sola volta, sincronamente con l'esecuzione del comando
`/fun animal`, perché non c'è nulla da monitorare nel tempo — è solo
"dammi un'immagine adesso". Stesso principio di gestione errori
(mai un'eccezione che risale al chiamante, log + None se la
richiesta fallisce) e stessa sessione aiohttp riusata tra chiamate.
"""

from __future__ import annotations

import logging

import aiohttp

from core.animal_api_logic import parse_cat_response, parse_dog_response, parse_fox_response

logger = logging.getLogger("iyokai.animal_fetcher")

REQUEST_TIMEOUT_SECONDS = 10

DOG_URL = "https://dog.ceo/api/breeds/image/random"
CAT_URL = "https://api.thecatapi.com/v1/images/search"
FOX_URL = "https://randomfox.ca/floof/"


class AnimalFetcherService:
    def __init__(
        self,
        dog_url: str = DOG_URL,
        cat_url: str = CAT_URL,
        fox_url: str = FOX_URL,
    ) -> None:
        self._http_session: aiohttp.ClientSession | None = None
        self._species = {
            "dog": (dog_url, parse_dog_response),
            "cat": (cat_url, parse_cat_response),
            "fox": (fox_url, parse_fox_response),
        }

    def _get_session(self) -> aiohttp.ClientSession:
        if self._http_session is None:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    async def fetch_image_url(self, species: str) -> str | None:
        """
        Restituisce l'URL di un'immagine casuale della specie
        richiesta, o None se la specie non è supportata, la richiesta
        fallisce (rete, timeout, status non-200) o la risposta non ha
        la forma aspettata — mai un'eccezione.
        """
        voce = self._species.get(species)
        if voce is None:
            return None
        url, parser = voce

        sessione = self._get_session()
        try:
            async with sessione.get(
                url, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
            ) as risposta:
                if risposta.status != 200:
                    logger.warning(
                        "Richiesta a %s fallita con status %d.", url, risposta.status
                    )
                    return None
                payload = await risposta.json()
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.warning("Impossibile contattare %s: %s", url, exc)
            return None

        return parser(payload)

    async def close(self) -> None:
        if self._http_session is not None:
            await self._http_session.close()
            self._http_session = None


animal_fetcher = AnimalFetcherService()
