"""
core/phishing_list_fetcher.py
=============================
Tiene in memoria la lista dei domini di phishing: parte dal file locale
(`data/phishing_domains.txt`) e, se e' impostata la variabile
`PHISHING_LIST_URL`, la integra con una lista scaricata.
Funzioni coperte: SPEC §23 (NF-31)

Regole del download: al massimo uno ogni 6 ore, attesa massima 10 secondi,
risposta fino a 2 MB, testo con un dominio per riga o JSON con un elenco di
domini. Se il download fallisce resta la lista che c'era. Condizioni d'uso
della fonte: le sceglie chi imposta l'indirizzo (vedi LIMITI.md, parte 5).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import aiohttp

from core.phishing_logic import MAX_DOMINI_LISTA, carica_domini, carica_lista_locale

logger = logging.getLogger("iyokai.phishing")

VARIABILE_URL = "PHISHING_LIST_URL"
INTERVALLO_SECONDI = 6 * 3600
ATTESA_SECONDI = 10
MAX_BYTE = 2 * 1024 * 1024


def interpreta_lista(corpo: str) -> frozenset[str]:
    """Testo con un dominio per riga, oppure un JSON con un elenco di stringhe."""
    corpo = corpo.strip()
    if corpo.startswith("["):
        try:
            voci = json.loads(corpo)
        except ValueError:
            return frozenset()
        return carica_domini("\n".join(v for v in voci if isinstance(v, str)))
    return carica_domini(corpo)


class ListaPhishing:
    def __init__(self) -> None:
        self._locale = carica_lista_locale()
        self._scaricata: frozenset[str] = frozenset()
        self._ultimo_tentativo = 0.0
        self._compito: asyncio.Task | None = None

    @property
    def domini(self) -> frozenset[str]:
        return self._locale | self._scaricata

    def url(self) -> str | None:
        valore = os.environ.get(VARIABILE_URL, "").strip()
        return valore if valore.startswith("https://") else None

    async def scarica(self, url: str) -> bool:
        """True se la lista scaricata e' valida e sostituisce la precedente."""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=ATTESA_SECONDI)) as sessione:
                async with sessione.get(url) as risposta:
                    if risposta.status != 200:
                        logger.warning("Lista phishing: risposta %s.", risposta.status)
                        return False
                    corpo = await risposta.content.read(MAX_BYTE + 1)
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as errore:
            logger.warning("Lista phishing non scaricata: %s", type(errore).__name__)
            return False
        if len(corpo) > MAX_BYTE:
            logger.warning("Lista phishing troppo grande: ignorata.")
            return False
        domini = interpreta_lista(corpo.decode("utf-8", errors="ignore"))
        if not domini or len(domini) >= MAX_DOMINI_LISTA:
            return False
        self._scaricata = domini
        return True

    def aggiorna_se_serve(self) -> None:
        """Lancia il download in sottofondo se e' passato l'intervallo; torna subito."""
        url = self.url()
        adesso = time.monotonic()
        if url is None or (self._compito is not None and not self._compito.done()):
            return
        if self._ultimo_tentativo and adesso - self._ultimo_tentativo < INTERVALLO_SECONDI:
            return
        self._ultimo_tentativo = adesso
        self._compito = asyncio.get_running_loop().create_task(self.scarica(url))


lista_phishing = ListaPhishing()
