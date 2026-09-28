"""
core/safe_http.py
====================
`safe_get(url)`: scarica un URL scelto da un utente (feed RSS/Atom
custom, e in futuro ogni altro fetch di un URL non fidato) senza
essere usato come proxy verso indirizzi interni — SSRF (SEC-8).
Funzioni coperte: SPEC §10.8 (SEC-8)
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
from urllib.parse import urljoin, urlparse

import aiohttp

logger = logging.getLogger("iyokai.safe_http")

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443}
DEFAULT_MAX_BYTES = 2_000_000
MAX_REDIRECTS = 3
REQUEST_TIMEOUT_SECONDS = 15
_REDIRECT_STATUS = {301, 302, 303, 307, 308}


def _porta_effettiva(parsed) -> int | None:
    """Porta esplicita nell'URL, oppure quella di default dello schema."""
    if parsed.port is not None:
        return parsed.port
    if parsed.scheme == "http":
        return 80
    if parsed.scheme == "https":
        return 443
    return None


def _schema_e_porta_ammessi(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        return False
    if not parsed.hostname:
        return False
    porta = _porta_effettiva(parsed)
    return porta in ALLOWED_PORTS


def _ip_e_bloccato(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """
    Vero se l'IP non deve mai essere raggiunto da un fetch scelto da
    un utente esterno: privato, loopback, link-local (include
    169.254.169.254, i metadati cloud), multicast, riservato o non
    specificato. Copre sia IPv4 che IPv6.
    """
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def _risolvi_ip(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """
    Risolve il nome host in tutti gli IP (IPv4 e IPv6) a cui potrebbe
    connettersi davvero. Un nome con anche un solo IP bloccato viene
    trattato come pericoloso nel suo insieme: un dominio potrebbe
    rispondere con un elenco misto per provare a passare solo con
    l'IP "buono".
    """
    loop = asyncio.get_event_loop()
    try:
        infos = await loop.getaddrinfo(hostname, None)
    except OSError:
        return []

    ip_trovati = []
    for info in infos:
        indirizzo = info[4][0]
        try:
            ip_trovati.append(ipaddress.ip_address(indirizzo))
        except ValueError:
            continue
    return ip_trovati


async def _url_e_sicuro(url: str) -> bool:
    """
    Controllo completo su un URL prima di scaricarlo: schema/porta
    ammessi, e nessuno degli IP a cui il nome host risolve è in un
    intervallo bloccato. Va richiamato ad OGNI passo di un redirect,
    non solo sull'URL di partenza.
    """
    if not _schema_e_porta_ammessi(url):
        return False

    hostname = urlparse(url).hostname
    ip_risolti = await _risolvi_ip(hostname)
    if not ip_risolti:
        return False
    return not any(_ip_e_bloccato(ip) for ip in ip_risolti)


async def safe_get(url: str, *, max_bytes: int = DEFAULT_MAX_BYTES) -> str | None:
    """
    Scarica il testo di `url` con protezioni SSRF: redirect Discord-
    style disattivati e seguiti a mano (al massimo MAX_REDIRECTS,
    ricontrollando ogni nuova destinazione da zero), lettura a blocchi
    con un tetto di `max_bytes` (una risposta più grande interrompe
    subito il download, non lo tronca), timeout totale sulla singola
    richiesta. Restituisce None per qualunque motivo di rifiuto o
    errore di rete — il chiamante tratta "None" come "salta questo
    giro", mai come "server risponde vuoto".
    """
    url_corrente = url

    async with aiohttp.ClientSession() as session:
        for _ in range(MAX_REDIRECTS + 1):
            if not await _url_e_sicuro(url_corrente):
                logger.warning("URL rifiutato (SSRF/schema/porta non ammessi): %s", url_corrente)
                return None

            try:
                async with session.get(
                    url_corrente,
                    allow_redirects=False,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
                ) as risposta:
                    if risposta.status in _REDIRECT_STATUS:
                        location = risposta.headers.get("Location")
                        if not location:
                            return None
                        url_corrente = urljoin(url_corrente, location)
                        continue

                    if risposta.status != 200:
                        logger.warning(
                            "%s ha risposto con status %d.", url_corrente, risposta.status
                        )
                        return None

                    corpo = bytearray()
                    async for blocco in risposta.content.iter_chunked(8192):
                        corpo.extend(blocco)
                        if len(corpo) > max_bytes:
                            logger.warning(
                                "%s ha superato il limite di %d byte, scarico interrotto.",
                                url_corrente,
                                max_bytes,
                            )
                            return None
                    return corpo.decode(errors="replace")
            except (aiohttp.ClientError, TimeoutError) as exc:
                logger.warning("Impossibile scaricare %s: %s", url_corrente, exc)
                return None

        logger.warning("Troppi redirect (oltre %d) per %s.", MAX_REDIRECTS, url)
        return None
