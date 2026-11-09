"""
core/xkcd_fetcher.py
====================
Vignette di xkcd (#131, D70, FUN-035): l'ultima o una per numero, dall'indirizzo ufficiale `info.0.json`.
Download con `safe_get` (timeout e tetto di byte), immagine solo dal dominio imgs.xkcd.com, cache in memoria.
xkcd è CC BY-NC 2.5: credito sempre mostrato e mai dietro il Premium.
Funzioni coperte: SPEC §16 (FUN-035)
Dipende da: core/safe_http.py
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlparse

from core.safe_http import safe_get

URL_ULTIMA = "https://xkcd.com/info.0.json"
URL_NUMERO = "https://xkcd.com/{numero}/info.0.json"
DOMINIO_IMMAGINI = "imgs.xkcd.com"
MAX_BYTE = 100_000
SECONDI_CACHE_ULTIMA = 3600
SECONDI_CACHE_NUMERO = 24 * 3600
MAX_IN_CACHE = 200


@dataclass(frozen=True)
class Vignetta:
    numero: int
    titolo: str
    alt: str
    immagine: str

    @property
    def pagina(self) -> str:
        return f"https://xkcd.com/{self.numero}/"


def interpreta(testo: str | None) -> Vignetta | None:
    """None se il testo non è la risposta attesa o l'immagine non sta su imgs.xkcd.com."""
    try:
        dati = json.loads(testo or "")
    except ValueError:
        return None
    if not isinstance(dati, dict):
        return None
    numero, titolo, alt, img = dati.get("num"), dati.get("safe_title") or dati.get("title"), dati.get("alt"), dati.get("img")
    if not (isinstance(numero, int) and numero >= 1 and isinstance(titolo, str) and isinstance(img, str)):
        return None
    analizzato = urlparse(img)
    if analizzato.scheme != "https" or analizzato.hostname != DOMINIO_IMMAGINI:
        return None
    return Vignetta(numero, titolo[:200], alt[:1500] if isinstance(alt, str) else "", img)


class XkcdService:
    def __init__(
        self, scarica: Callable[..., Awaitable[str | None]] = safe_get, adesso: Callable[[], float] = time.monotonic
    ) -> None:
        self._scarica = scarica
        self._adesso = adesso
        self._cache: dict[int | None, tuple[float, Vignetta]] = {}

    async def vignetta(self, numero: int | None = None) -> Vignetta | None:
        """L'ultima (numero None) o la numero `numero`. None se non esiste o la rete non risponde."""
        durata = SECONDI_CACHE_ULTIMA if numero is None else SECONDI_CACHE_NUMERO
        in_cache = self._cache.get(numero)
        if in_cache is not None and self._adesso() - in_cache[0] < durata:
            return in_cache[1]
        url = URL_ULTIMA if numero is None else URL_NUMERO.format(numero=numero)
        trovata = interpreta(await self._scarica(url, max_bytes=MAX_BYTE))
        if trovata is None:
            return None
        if len(self._cache) >= MAX_IN_CACHE:
            self._cache.pop(next(iter(self._cache)))
        self._cache[numero] = (self._adesso(), trovata)
        return trovata


xkcd_service = XkcdService()
