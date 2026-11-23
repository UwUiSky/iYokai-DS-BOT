"""
core/music_spotify_mercati.py
=============================
Paese delle ricerche per Spotify (MUS-015, D127, D131): LavaSrc non passa al bot i paesi in cui un brano si ascolta, ma la
Web API di Spotify sì (`available_markets`). Se nel `.env` del bot ci sono `SPOTIFY_CLIENT_ID` e `SPOTIFY_CLIENT_SECRET`
(facoltativi) e il server ha scelto un paese, i brani Spotify senza dato vengono arricchiti con quei paesi prima del
filtro di `core/music_paese_logic.py`. Senza chiavi, senza paese, con un errore o con la quota finita: nessun dato, e il
brano passa (come prima). Solo due indirizzi fissi (accounts.spotify.com, api.spotify.com), mai l'indirizzo di un utente;
le chiavi si leggono solo dall'ambiente, non si scrivono nei log. Una richiesta per al massimo 50 brani, cache di un
giorno, pausa al 429, tetto giornaliero di richieste.
Funzioni coperte: SPEC §9 (catalogo MUS-015)
Dipende da: core/music_paese_logic.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import time
from collections import OrderedDict

import aiohttp

from core.music_paese_logic import paese_valido, paesi_della_traccia

logger = logging.getLogger("iyokai.music_spotify")

URL_TOKEN = "https://accounts.spotify.com/api/token"
URL_BRANI = "https://api.spotify.com/v1/tracks"
MAX_PER_RICHIESTA = 50  # il limite di Spotify per `GET /tracks`
MAX_RICHIESTE_PER_COMANDO = 2
MAX_RICHIESTE_AL_GIORNO = 2000
DURATA_CACHE = 24 * 3600
MAX_IN_CACHE = 5000
TEMPO_MASSIMO = 5  # secondi: il comando non aspetta Spotify più di tanto
DIMENSIONE_MASSIMA = 512 * 1024
PAUSA_MASSIMA = 600

_URL_BRANO = re.compile(r"^https://open\.spotify\.com/(?:intl-[a-z]{2,5}/)?track/([A-Za-z0-9]{10,40})/?(?:\?.*)?$")
_URI_BRANO = re.compile(r"^spotify:track:([A-Za-z0-9]{10,40})$")

_cache: OrderedDict[str, tuple[float, frozenset[str]]] = OrderedDict()
_token: dict = {"valore": None, "scade": 0.0}
_pausa_fino = 0.0
_giorno: dict = {"data": "", "richieste": 0}
_blocco_token = asyncio.Lock()


def chiavi() -> tuple[str, str] | None:
    """(id, segreto) di Spotify se stanno nell'ambiente del bot; altrimenti None (la funzione resta spenta)."""
    ident, segreto = os.environ.get("SPOTIFY_CLIENT_ID", "").strip(), os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
    return (ident, segreto) if ident and segreto else None


def id_brano(traccia) -> str | None:
    """L'ID Spotify di un brano (dall'indirizzo del brano), o None se non è un brano Spotify."""
    uri = getattr(traccia, "uri", None)
    if not isinstance(uri, str):
        return None
    trovato = _URL_BRANO.match(uri) or _URI_BRANO.match(uri)
    return trovato.group(1) if trovato else None


async def _http(metodo: str, url: str, **kw) -> tuple[int, object, float]:
    """(stato, JSON o None, secondi di attesa chiesti da Spotify). Errore di rete o risposta troppo grande: (0, None, 0)."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TEMPO_MASSIMO)) as sessione:
            async with sessione.request(metodo, url, allow_redirects=False, **kw) as risposta:
                corpo = await risposta.content.read(DIMENSIONE_MASSIMA + 1)
                try:
                    attesa = float(risposta.headers.get("Retry-After", "0"))
                except ValueError:
                    attesa = 0.0
                if len(corpo) > DIMENSIONE_MASSIMA:
                    return 0, None, 0.0
                try:
                    return risposta.status, json.loads(corpo) if corpo else None, attesa
                except ValueError:
                    return risposta.status, None, attesa
    except (aiohttp.ClientError, TimeoutError):
        logger.info("Spotify: nessuna risposta da %s.", url.split("?")[0].split("/")[2])
        return 0, None, 0.0


async def _token_valido() -> str | None:
    async with _blocco_token:
        if _token["valore"] and _token["scade"] - 60 > time.monotonic():
            return _token["valore"]
        coppia = chiavi()
        if coppia is None:
            return None
        credenziali = base64.b64encode(f"{coppia[0]}:{coppia[1]}".encode()).decode()
        stato, payload, _ = await _http(
            "POST", URL_TOKEN, data={"grant_type": "client_credentials"}, headers={"Authorization": f"Basic {credenziali}"}
        )
        if stato != 200 or not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str):
            logger.warning("Spotify: token non ottenuto (stato %s): controlla le chiavi.", stato)
            return None
        try:
            durata = float(payload.get("expires_in", 3600))
        except (TypeError, ValueError):
            durata = 3600.0
        _token.update(valore=payload["access_token"], scade=time.monotonic() + durata)
        return _token["valore"]


def _conta_richiesta() -> bool:
    """Tetto giornaliero: vero se si può fare un'altra richiesta."""
    oggi = time.strftime("%Y-%m-%d", time.gmtime())
    if _giorno["data"] != oggi:
        _giorno.update(data=oggi, richieste=0)
    if _giorno["richieste"] >= MAX_RICHIESTE_AL_GIORNO:
        return False
    _giorno["richieste"] += 1
    return True


def _paesi_della_risposta(payload) -> dict[str, frozenset[str]]:
    trovati: dict[str, frozenset[str]] = {}
    elenco = payload.get("tracks") if isinstance(payload, dict) else None
    for voce in elenco if isinstance(elenco, list) else []:
        if not isinstance(voce, dict) or not isinstance(voce.get("id"), str):
            continue
        mercati = voce.get("available_markets")
        codici = {c for c in (paese_valido(m) for m in mercati) if c} if isinstance(mercati, list) else set()
        if codici:  # elenco vuoto = Spotify non lo dice: il brano passa
            trovati[voce["id"]] = frozenset(codici)
    return trovati


def _dalla_cache(identificativo: str) -> frozenset[str] | None:
    voce = _cache.get(identificativo)
    if voce is None or voce[0] <= time.monotonic():
        _cache.pop(identificativo, None)
        return None
    _cache.move_to_end(identificativo)
    return voce[1]


async def paesi_dei_brani(ids: list[str]) -> dict[str, frozenset[str]]:
    """I paesi di questi brani (solo quelli che Spotify dichiara). Non solleva mai."""
    global _pausa_fino
    trovati: dict[str, frozenset[str]] = {}
    mancanti = []
    for i in dict.fromkeys(ids):
        noto = _dalla_cache(i)
        if noto is not None:
            trovati[i] = noto
        else:
            mancanti.append(i)
    if not mancanti or chiavi() is None or time.monotonic() < _pausa_fino:
        return trovati
    try:
        token = await _token_valido()
        if token is None:
            return trovati
        for inizio in range(0, min(len(mancanti), MAX_PER_RICHIESTA * MAX_RICHIESTE_PER_COMANDO), MAX_PER_RICHIESTA):
            if not _conta_richiesta():
                logger.warning("Spotify: tetto giornaliero di richieste raggiunto.")
                break
            lotto = mancanti[inizio:inizio + MAX_PER_RICHIESTA]
            stato, payload, attesa = await _http(
                "GET", URL_BRANI, params={"ids": ",".join(lotto)}, headers={"Authorization": f"Bearer {token}"}
            )
            if stato == 429:
                _pausa_fino = time.monotonic() + min(max(attesa, 30.0), PAUSA_MASSIMA)
                logger.warning("Spotify: troppe richieste, pausa.")
                break
            if stato == 401:  # il token non vale più: se ne chiede uno nuovo la volta dopo
                _token.update(valore=None, scade=0.0)
                break
            if stato != 200:
                break
            nuovi = _paesi_della_risposta(payload)
            scadenza = time.monotonic() + DURATA_CACHE
            for i, paesi in nuovi.items():
                _cache[i] = (scadenza, paesi)
                if len(_cache) > MAX_IN_CACHE:
                    _cache.popitem(last=False)
            trovati.update(nuovi)
    except Exception:  # noqa: BLE001 - il filtro per paese è un di più: se non va, il brano passa
        logger.warning("Spotify: lettura dei paesi non riuscita.", exc_info=True)
    return trovati


async def arricchisci(tracce, paese: str | None) -> int:
    """
    Mette `available_markets` nei dati dei brani Spotify che non dichiarano i paesi, ma solo se c'è un paese da
    rispettare. Ritorna quanti brani ha arricchito. Non solleva mai.
    """
    if not paese or chiavi() is None:
        return 0
    per_id: dict[str, list] = {}
    for t in tracce:
        if paesi_della_traccia(t):
            continue
        identificativo = id_brano(t)
        if identificativo is not None:
            per_id.setdefault(identificativo, []).append(t)
    if not per_id:
        return 0
    paesi = await paesi_dei_brani(list(per_id))
    fatti = 0
    for identificativo, elenco in per_id.items():
        if identificativo not in paesi:
            continue
        for t in elenco:
            dati = getattr(t, "raw_data", None)
            if not isinstance(dati, dict):
                continue
            info = dati.get("pluginInfo")
            if not isinstance(info, dict):
                info = dati["pluginInfo"] = {}
            info["available_markets"] = sorted(paesi[identificativo])
            fatti += 1
    return fatti
