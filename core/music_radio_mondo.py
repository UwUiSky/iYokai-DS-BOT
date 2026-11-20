"""
core/music_radio_mondo.py
=========================
Radio dal mondo (MUS-010): ricerca di stazioni nell'elenco pubblico radio-browser.info (gratuito, senza
chiave). Ogni richiesta passa da core/safe_http (`safe_get` con tetto di byte) e ogni indirizzo di stream
da `url_e_sicuro`. Risultati a pagine, con un tetto di pagine e una piccola memoria per non pesare sul servizio.
Funzioni coperte: SPEC §9 (catalogo MUS-010)
Dipende da: core/safe_http.py
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse

from core.safe_http import safe_get, url_e_sicuro

# Server dell'elenco, provati in ordine (il servizio ne ha più di uno).
SERVER_API = ("de1.api.radio-browser.info", "de2.api.radio-browser.info", "fi1.api.radio-browser.info")
PER_PAGINA = 10  # un menu a tendina regge 25 voci: qui ne mostriamo meno
MAX_PAGINE = 10  # una ricerca arriva al massimo a 100 stazioni
NOME_MIN = 2
NOME_MAX = 60
URL_MAX = 300
MAX_BYTE_RISPOSTA = 400_000
CACHE_SECONDI = 300
CACHE_MAX = 64

_cache: dict[tuple[str, int], tuple[float, "PaginaStazioni"]] = {}


@dataclass(frozen=True)
class Stazione:
    nome: str
    url: str
    dettaglio: str


@dataclass(frozen=True)
class PaginaStazioni:
    stazioni: tuple[Stazione, ...]
    ha_altre: bool


def nome_ricerca_valido(testo: str) -> str | None:
    """Il testo pulito (spazi singoli), o None se troppo corto, troppo lungo o con a capo e tabulazioni."""
    if any(c in (testo or "") for c in "\n\r\t\x00"):
        return None
    pulito = " ".join((testo or "").split())
    if not (NOME_MIN <= len(pulito) <= NOME_MAX):
        return None
    return pulito


def indirizzo_ricerca(server: str, nome: str, pagina: int) -> str:
    parametri = urlencode({
        "name": nome, "limit": PER_PAGINA + 1, "offset": pagina * PER_PAGINA,
        "hidebroken": "true", "order": "clickcount", "reverse": "true",
    })
    return f"https://{server}/json/stations/search?{parametri}"


def _url_di_stream_valido(url) -> bool:
    if not isinstance(url, str) or not url or len(url) > URL_MAX or any(c.isspace() for c in url):
        return False
    try:
        analizzato = urlparse(url)
        porta = analizzato.port
    except ValueError:
        return False
    if analizzato.scheme not in ("http", "https") or not analizzato.hostname:
        return False
    return porta in (None, 80, 443)  # le sole porte che safe_http ammette


def stazione_da_json(riga) -> Stazione | None:
    """Una stazione pronta da mostrare, o None se non adatta (spenta, HLS, senza nome, indirizzo strano)."""
    if not isinstance(riga, dict) or riga.get("lastcheckok") != 1 or riga.get("hls") == 1:
        return None
    nome = " ".join(str(riga.get("name") or "").split())[:100]
    if not nome:
        return None
    url = riga.get("url_resolved") or riga.get("url")
    if not _url_di_stream_valido(url):
        return None
    pezzi = [str(riga.get("countrycode") or "").strip()[:3], str(riga.get("codec") or "").strip()[:12]]
    bitrate = riga.get("bitrate")
    if isinstance(bitrate, int) and 0 < bitrate < 10_000:
        pezzi.append(f"{bitrate} kbps")
    dettaglio = " · ".join(p for p in pezzi if p)[:100]
    return Stazione(nome=nome, url=url, dettaglio=dettaglio or "-")


def stazioni_da_testo(testo: str) -> list[Stazione]:
    """Le stazioni valide di una risposta JSON, senza indirizzi doppi."""
    try:
        righe = json.loads(testo)
    except (ValueError, TypeError):
        return []
    if not isinstance(righe, list):
        return []
    viste: set[str] = set()
    risultato = []
    for riga in righe:
        stazione = stazione_da_json(riga)
        if stazione is not None and stazione.url not in viste:
            viste.add(stazione.url)
            risultato.append(stazione)
    return risultato


def svuota_cache() -> None:
    _cache.clear()


def dimensione_cache() -> int:
    return len(_cache)


def _ricorda(chiave: tuple[str, int], pagina: PaginaStazioni) -> None:
    adesso = time.monotonic()
    for k in [k for k, (quando, _) in _cache.items() if adesso - quando > CACHE_SECONDI]:
        del _cache[k]
    while len(_cache) >= CACHE_MAX:
        del _cache[min(_cache, key=lambda k: _cache[k][0])]
    _cache[chiave] = (adesso, pagina)


async def cerca_stazioni(
    nome: str, pagina: int, *, scarica=safe_get, controlla=url_e_sicuro
) -> PaginaStazioni | None:
    """
    Una pagina di stazioni, o None se il nome non è valido, la pagina è fuori dal tetto o nessun server
    risponde. Gli indirizzi non sicuri (`controlla`) sono tolti dall'elenco.
    """
    pulito = nome_ricerca_valido(nome)
    if pulito is None or not (0 <= pagina < MAX_PAGINE):
        return None
    chiave = (pulito.lower(), pagina)
    nota = _cache.get(chiave)
    if nota is not None and time.monotonic() - nota[0] <= CACHE_SECONDI:
        return nota[1]
    for server in SERVER_API:
        testo = await scarica(indirizzo_ricerca(server, pulito, pagina), max_bytes=MAX_BYTE_RISPOSTA)
        if testo is None:
            continue
        try:
            json_valido = isinstance(json.loads(testo), list)
        except ValueError:
            json_valido = False
        if not json_valido:
            continue
        trovate = stazioni_da_testo(testo)
        ha_altre = len(trovate) > PER_PAGINA
        mostrate = trovate[:PER_PAGINA]
        esiti = await asyncio.gather(*(controlla(s.url) for s in mostrate))
        risultato = PaginaStazioni(tuple(s for s, ok in zip(mostrate, esiti) if ok), ha_altre)
        _ricorda(chiave, risultato)
        return risultato
    return None
