"""
core/verify_vpn_esterno.py
==========================
Servizio esterno facoltativo per riconoscere VPN e proxy (D64): proxycheck.io (livello gratuito con
chiave: 1.000 richieste al giorno; i termini li controlla l'owner). La chiave sta solo nel `.env`
(`VPN_PROXYCHECK_KEY`, globale); senza chiave il servizio non c'è. L'IP esce dal server solo se è
pubblico, nessuno strato locale ha già deciso e il tetto del giorno (`VPN_SERVIZIO_TETTO`, base 900)
non è finito. Risposte in cache con tetto, per impronta dell'IP; un errore o un timeout vuol dire
«non so»: la verifica prosegue. La chiave non va mai nei log.
Funzioni coperte: SPEC §4.2 (VPN e proxy, D64)
Dipende da: core/bounded_cache.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from urllib.parse import quote

from core.bounded_cache import BoundedCache

logger = logging.getLogger("iyokai.verify_vpn")

INDIRIZZO = "https://proxycheck.io/v2/{ip}"
TETTO_DI_BASE = 900
TTL_DI_BASE = 3600.0
TIMEOUT_DI_BASE = 3.0
PAUSA_DOPO_ERRORE = 60.0
TETTO_CACHE = 4096


def _oggi_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def leggi_risposta(dati) -> bool | None:
    """True/False dalla risposta del servizio, None se non è una risposta utile."""
    if not isinstance(dati, dict) or dati.get("status") != "ok":
        return None
    for valore in dati.values():  # la chiave è l'IP, in forma che può cambiare (IPv6): si prende la sezione dell'IP
        if isinstance(valore, dict) and "proxy" in valore:
            return {"yes": True, "no": False}.get(str(valore.get("proxy")).lower())
    return None


class ServizioEsterno:
    def __init__(self, chiave_api: str, *, tetto: int = TETTO_DI_BASE, richiedi=None, ttl: float = TTL_DI_BASE,
                 timeout: float = TIMEOUT_DI_BASE, oggi=_oggi_utc, adesso=time.monotonic) -> None:
        self._chiave = chiave_api
        self.tetto = tetto
        self._ttl = ttl
        self._timeout = timeout
        self._oggi = oggi
        self._adesso = adesso
        self._richiedi = richiedi or self._richiedi_http
        self._cache: BoundedCache[str, tuple[float, bool | None]] = BoundedCache(TETTO_CACHE)
        self._giorno = oggi()
        self._usate = 0

    @property
    def usate_oggi(self) -> int:
        self._rinnova_giorno()
        return self._usate

    def _rinnova_giorno(self) -> None:
        oggi = self._oggi()
        if oggi != self._giorno:
            self._giorno, self._usate = oggi, 0

    async def _richiedi_http(self, ip: str):
        import aiohttp

        durata = aiohttp.ClientTimeout(total=self._timeout)
        async with aiohttp.ClientSession(timeout=durata) as sessione:
            async with sessione.get(
                INDIRIZZO.format(ip=quote(ip, safe="")), params={"key": self._chiave, "vpn": "1"}
            ) as risposta:
                if risposta.status != 200:
                    return None
                return await risposta.json(content_type=None)

    async def controlla(self, ip: str, impronta: str) -> bool | None:
        """True = VPN/proxy, False = pulito, None = non so (spento, tetto finito, errore, timeout)."""
        adesso = self._adesso()
        voce = self._cache.get(impronta)
        if voce is not None and voce[0] > adesso:
            return voce[1]
        self._rinnova_giorno()
        if self._usate >= self.tetto:
            return None
        self._usate += 1
        try:
            risultato = leggi_risposta(await asyncio.wait_for(self._richiedi(ip), self._timeout))
        except Exception as errore:  # timeout, rete, JSON storto: il servizio non blocca mai nessuno
            logger.warning("Servizio VPN esterno non raggiungibile (%s).", type(errore).__name__)
            risultato = None
        durata = self._ttl if risultato is not None else PAUSA_DOPO_ERRORE
        self._cache.set(impronta, (adesso + durata, risultato))
        return risultato


_servizio: ServizioEsterno | None = None
_provato = False


def azzera() -> None:
    """Per i test: dimentica il servizio e rilegge il `.env` alla prossima richiesta."""
    global _servizio, _provato
    _servizio, _provato = None, False


def usa_servizio(servizio: ServizioEsterno | None) -> None:
    """Per i test: un servizio già pronto (o nessuno)."""
    global _servizio, _provato
    _servizio, _provato = servizio, True


def servizio() -> ServizioEsterno | None:
    """Il servizio, se l'owner ha messo la chiave nel `.env`. Altrimenti None."""
    global _servizio, _provato
    if _provato:
        return _servizio
    _provato = True
    chiave = os.environ.get("VPN_PROXYCHECK_KEY", "").strip()
    if not chiave:
        return None
    try:
        tetto = int(os.environ.get("VPN_SERVIZIO_TETTO", "").strip())
        if tetto < 0:
            raise ValueError
    except ValueError:
        tetto = TETTO_DI_BASE
    _servizio = ServizioEsterno(chiave, tetto=tetto)
    return _servizio
