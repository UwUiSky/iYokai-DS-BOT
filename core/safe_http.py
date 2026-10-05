"""
core/safe_http.py
====================
`safe_get(url)`: scarica un URL scelto da un utente (feed RSS/Atom
custom, e in futuro ogni altro fetch di un URL non fidato) senza
essere usato come proxy verso indirizzi interni — SSRF (SEC-8,
SEC-18). `url_e_sicuro(url)`: lo stesso controllo senza scaricare.
Funzioni coperte: SPEC §10.8 (SEC-8, SEC-18)
"""

# DA FARE (issue #67, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §11 (Feed e alert).

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from urllib.parse import urljoin

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult
from aiohttp.resolver import DefaultResolver
from yarl import URL

logger = logging.getLogger("iyokai.safe_http")

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443}
DEFAULT_MAX_BYTES = 2_000_000
MAX_REDIRECTS = 3
REQUEST_TIMEOUT_SECONDS = 15
_REDIRECT_STATUS = {301, 302, 303, 307, 308}

# <?xml version="1.0" encoding="ISO-8859-1"?> in testa a un feed.
_ENCODING_PROLOGO_XML = re.compile(rb"""\s*<\?xml[^>]*encoding=["']([A-Za-z0-9._-]+)["']""")

# Intervalli che Python 3.11 considera ancora "globali" ma che non
# sono Internet pubblica: relay 6to4 e site-local IPv6 (deprecati).
_RETI_BLOCCATE_IN_PIU = (
    ipaddress.ip_network("192.88.99.0/24"),
    ipaddress.ip_network("fec0::/10"),
)


def _analizza(url: str) -> URL | None:
    """
    Analizza l'URL con yarl, lo stesso parser che usa aiohttp per
    connettersi: così l'host che controlliamo è proprio quello a cui
    aiohttp si collegherà. None se l'URL è malformato (BUG-20: porta
    fuori intervallo, IPv6 senza parentesi, ...).
    """
    try:
        return URL(url)
    except (ValueError, TypeError):
        return None


def _schema_e_porta_ammessi(url: str) -> bool:
    parsed = _analizza(url)
    if parsed is None or parsed.scheme not in ALLOWED_SCHEMES or not parsed.raw_host:
        return False
    return parsed.port in ALLOWED_PORTS


def _ip_e_bloccato(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """
    Vero se l'IP non deve mai essere raggiunto da un fetch scelto da
    un utente esterno: tutto ciò che non è instradabile su Internet
    (privato, loopback, link-local con 169.254.169.254 dei metadati
    cloud, CGNAT 100.64.0.0/10, documentazione, riservato, non
    specificato) più il multicast. Un IPv4 scritto dentro un IPv6
    (::ffff:a.b.c.d) viene giudicato come l'IPv4 che contiene.
    """
    ipv4_contenuto = getattr(ip, "ipv4_mapped", None)
    if ipv4_contenuto is not None:
        ip = ipv4_contenuto
    if any(ip in rete for rete in _RETI_BLOCCATE_IN_PIU):
        return True
    return not ip.is_global or ip.is_multicast


def _indirizzo_e_bloccato(indirizzo: str) -> bool:
    """Come _ip_e_bloccato, partendo dal testo; se non è un IP valido è bloccato."""
    try:
        ip = ipaddress.ip_address(indirizzo)
    except ValueError:
        return True
    return _ip_e_bloccato(ip)


def _sembra_un_ip(host: str) -> bool:
    """
    Stesso criterio con cui aiohttp decide che un host è un IP scritto
    per esteso e quindi NON passa dal resolver: contiene ":" (IPv6) o
    è fatto solo di cifre e punti (anche forme come "2130706433" o
    "127.1", che il sistema operativo leggerebbe come 127.0.0.1).
    """
    return ":" in host or host.replace(".", "").isdigit()


def _destinazione_ammessa(url: str) -> URL | None:
    """
    Controlli che non richiedono il DNS: schema, porta e — se l'host è
    un IP scritto per esteso — che non sia un indirizzo bloccato.
    Restituisce l'URL già analizzato, o None se va rifiutato. Per i
    nomi host il controllo sugli IP lo fa _ResolverSicuro, al momento
    della connessione.
    """
    if not _schema_e_porta_ammessi(url):
        return None
    parsed = _analizza(url)
    if parsed is None or not parsed.raw_host:
        return None
    if _sembra_un_ip(parsed.raw_host) and _indirizzo_e_bloccato(parsed.raw_host):
        return None
    return parsed


class _ResolverSicuro(AbstractResolver):
    """
    SEC-18 (DNS rebinding): il resolver che aiohttp usa per
    connettersi. Risolve il nome UNA volta, scarta gli IP bloccati e
    restituisce solo quelli ammessi: il controllo e la connessione
    usano la stessa risposta DNS, quindi un nome che "cambia IP" tra
    una risoluzione e l'altra non può portare a un indirizzo interno.
    """

    def __init__(self) -> None:
        self._di_sistema = DefaultResolver()

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        try:
            risultati = await self._di_sistema.resolve(host, port, family)
        except ValueError as exc:
            # BUG-20: UnicodeError (sottoclasse di ValueError) per un
            # nome con un'etichetta vuota o più lunga di 63 caratteri.
            raise OSError(f"nome host non valido: {host!r}") from exc

        ammessi = [r for r in risultati if not _indirizzo_e_bloccato(r["host"])]
        if not ammessi:
            raise OSError(f"{host!r} non risolve a nessun indirizzo pubblico")
        return ammessi

    async def close(self) -> None:
        await self._di_sistema.close()


async def url_e_sicuro(url: str) -> bool:
    """
    Lo stesso controllo che safe_get applica prima di connettersi,
    senza scaricare nulla: schema, porta e almeno un IP pubblico a cui
    il nome host risolve. Un URL malformato vale False, non solleva
    mai (BUG-20). Usato da /alerts add per rifiutare subito un URL che
    non verrebbe mai scaricato.
    """
    parsed = _destinazione_ammessa(url)
    if parsed is None:
        return False
    if _sembra_un_ip(parsed.raw_host):
        return True  # IP scritto per esteso: già controllato sopra

    resolver = _ResolverSicuro()
    try:
        await resolver.resolve(parsed.raw_host, parsed.port)
    except OSError:
        return False
    finally:
        await resolver.close()
    return True


def _decodifica(corpo: bytes, charset_header: str | None) -> str:
    """
    Decodifica il corpo con la codifica dichiarata dalla risposta:
    quella dell'header Content-Type, altrimenti quella del prologo XML,
    altrimenti UTF-8. Una codifica sconosciuta ripiega su UTF-8; i byte
    non validi vengono sostituiti, mai un'eccezione.
    """
    dichiarata = charset_header
    if dichiarata is None:
        prologo = _ENCODING_PROLOGO_XML.match(corpo[:200])
        dichiarata = prologo.group(1).decode("ascii") if prologo else "utf-8"
    try:
        return corpo.decode(dichiarata, errors="replace")
    except LookupError:
        return corpo.decode("utf-8", errors="replace")


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
    resolver = _ResolverSicuro()
    try:
        connettore = aiohttp.TCPConnector(resolver=resolver)
        async with aiohttp.ClientSession(connector=connettore) as session:
            return await _scarica(session, url, max_bytes)
    finally:
        await resolver.close()


async def _scarica(session: aiohttp.ClientSession, url: str, max_bytes: int) -> str | None:
    url_corrente = url

    for _ in range(MAX_REDIRECTS + 1):
        destinazione = _destinazione_ammessa(url_corrente)
        if destinazione is None:
            logger.warning("URL rifiutato (SSRF/schema/porta non ammessi): %s", url_corrente)
            return None

        try:
            async with session.get(
                destinazione,
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
                    logger.warning("%s ha risposto con status %d.", url_corrente, risposta.status)
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
                return _decodifica(bytes(corpo), risposta.charset)
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            # ClientError copre anche il rifiuto di _ResolverSicuro
            # (nessun IP pubblico). ValueError (BUG-20): un Location
            # malformato fa sollevare urljoin.
            logger.warning("Impossibile scaricare %s: %s", url_corrente, exc)
            return None

    logger.warning("Troppi redirect (oltre %d) per %s.", MAX_REDIRECTS, url)
    return None
