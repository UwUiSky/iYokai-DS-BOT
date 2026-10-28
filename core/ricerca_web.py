"""
core/ricerca_web.py
===================
Chiamata al servizio di ricerca sul web (indirizzo e chiave da `.env`). È la sola parte che parla in rete;
nei test si passa un trasporto finto.
Funzioni coperte: SPEC §25.45 (AI-R-048)
"""

from __future__ import annotations

import logging
import os

import aiohttp

from core.ricerca_web_logic import ConfigRicerca, QuotaGiornaliera, Risultato, leggi_config, leggi_risultati, risultati_sicuri

logger = logging.getLogger("iyokai.ricerca_web")
TIMEOUT_SECONDI = 10


class RicercaWeb:
    def __init__(self, config: ConfigRicerca | None, trasporto=None) -> None:
        self.config = config
        self.quota = QuotaGiornaliera(config.quota_giorno) if config else None
        self._trasporto = trasporto or self._http

    @property
    def attiva(self) -> bool:
        return self.config is not None

    async def _http(self, config: ConfigRicerca, domanda: str):
        timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDI)
        async with aiohttp.ClientSession(timeout=timeout) as sessione:
            async with sessione.get(
                config.url, params={"q": domanda}, headers={"Authorization": f"Bearer {config.chiave}", "Accept": "application/json"}
            ) as r:
                if r.status >= 400:
                    raise RuntimeError(f"ricerca web: stato {r.status}")
                return await r.json(content_type=None)

    async def cerca(self, domanda: str) -> list[Risultato] | None:
        """I risultati sicuri; None se la ricerca è spenta, ha finito la quota o il servizio non risponde."""
        if self.config is None or self.quota is None or not self.quota.consenti():
            return None
        try:
            return risultati_sicuri(leggi_risultati(await self._trasporto(self.config, domanda)))
        except Exception:
            logger.warning("Ricerca web non riuscita.", exc_info=True)
            return None


_ricerca: RicercaWeb | None = None


def ricerca_web() -> RicercaWeb:
    global _ricerca
    if _ricerca is None:
        _ricerca = RicercaWeb(leggi_config(os.environ))
    return _ricerca


def imposta_ricerca_web(r: RicercaWeb | None) -> None:
    """Per i test."""
    global _ricerca
    _ricerca = r
