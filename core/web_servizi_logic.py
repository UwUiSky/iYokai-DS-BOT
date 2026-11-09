"""
core/web_servizi_logic.py
=========================
Servizi esterni di /web: meteo (MET Norway + geocodifica Nominatim con cache su DB e coda a 1 al secondo),
film e serie (TVmaze, ripiego Wikipedia), giochi Steam, prezzi cripto (CoinGecko, chiave dell'owner) e
accorciatore is.gd. Tempo massimo 8 secondi, cache in memoria, nessuna chiave nei log.
Funzioni coperte: catalogo #128 UTL-213, 217, 218, 219, 208 (D69, B2)
"""

from __future__ import annotations

import asyncio
import functools
import html
import json
import re
import time
from urllib.parse import quote, urlparse

import aiohttp

from core import strumenti_rapidi_logic as rapidi
from core.bounded_cache import BoundedCache
from core.phishing_logic import ACCORCIATORI, carica_lista_locale, e_phishing
from core.safe_http import USER_AGENT, safe_get, url_e_sicuro

TIMEOUT_SECONDI = 8
MAX_CITTA = 100
MAX_TITOLO = 100
MAX_LINK = 2000
INTERVALLO_NOMINATIM = 1.1  # i loro termini: al massimo una richiesta al secondo
CACHE_METEO = 1800
CACHE_STEAM = 86400
CACHE_PREZZI = 60

_cache: BoundedCache[tuple, tuple[float, object]] = BoundedCache(1000)


def dalla_cache(chiave: tuple, durata: int):
    visto = _cache.get(chiave)
    if visto is not None and time.monotonic() - visto[0] < durata:
        return visto[1]
    return None


def in_cache(chiave: tuple, valore) -> None:
    _cache.set(chiave, (time.monotonic(), valore))


def normalizza_luogo(testo: str) -> str:
    return " ".join(testo.casefold().split())[:MAX_CITTA]


def _json(testo: str | None):
    try:
        return json.loads(testo or "")
    except ValueError:
        return None


# --- geocodifica ---

_coda_nominatim = asyncio.Lock()
_ultima_nominatim = 0.0


def leggi_luogo(testo: str | None) -> tuple[float, float, str] | None:
    d = _json(testo)
    try:
        return float(d[0]["lat"]), float(d[0]["lon"]), str(d[0]["display_name"])[:200]
    except (TypeError, KeyError, IndexError, ValueError):
        return None


async def trova_luogo(repo, citta: str) -> tuple[float, float, str] | None:
    """Prima la cache su DB; altrimenti Nominatim, una richiesta alla volta e una al secondo."""
    chiave = normalizza_luogo(citta)
    trovato = await repo.luogo(chiave)
    if trovato:
        return trovato
    global _ultima_nominatim
    async with _coda_nominatim:
        attesa = INTERVALLO_NOMINATIM - (time.monotonic() - _ultima_nominatim)
        if attesa > 0:
            await asyncio.sleep(attesa)
        url = f"https://nominatim.openstreetmap.org/search?q={quote(chiave)}&format=jsonv2&limit=1"
        testo = await asyncio.wait_for(safe_get(url, max_bytes=100_000), TIMEOUT_SECONDI)
        _ultima_nominatim = time.monotonic()
    luogo = leggi_luogo(testo)
    if luogo:
        await repo.salva_luogo(chiave, *luogo)
    return luogo


# --- meteo ---

_CIELO = (  # (pezzo del codice MET, chiave del testo): il primo che c'è vince
    ("thunder", "meteo_cielo_temporale"), ("sleet", "meteo_cielo_nevischio"), ("snow", "meteo_cielo_neve"),
    ("rain", "meteo_cielo_pioggia"), ("fog", "meteo_cielo_nebbia"), ("partlycloudy", "meteo_cielo_parziale"),
    ("cloudy", "meteo_cielo_nuvoloso"), ("fair", "meteo_cielo_poco_nuvoloso"), ("clearsky", "meteo_cielo_sereno"),
)


def chiave_cielo(codice: str) -> str:
    return next((k for pezzo, k in _CIELO if pezzo in codice), "meteo_cielo_nuvoloso")


def url_meteo(lat: float, lon: float) -> str:
    # MET chiede al massimo 4 decimali.
    return f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat:.4f}&lon={lon:.4f}"


def leggi_meteo(testo: str | None) -> dict | None:
    """Adesso + fino a 3 giorni (la voce delle 12 UTC di ciascuno)."""
    d = _json(testo)
    try:
        serie = d["properties"]["timeseries"]
        ora = serie[0]["data"]["instant"]["details"]
        codice = (serie[0]["data"].get("next_1_hours") or serie[0]["data"].get("next_6_hours"))["summary"]["symbol_code"]
        giorni = []
        for v in serie[1:]:
            if v["time"][11:13] == "12" and len(giorni) < 3 and "next_6_hours" in v["data"]:
                giorni.append({
                    "data": v["time"][:10],
                    "temp": v["data"]["instant"]["details"]["air_temperature"],
                    "codice": v["data"]["next_6_hours"]["summary"]["symbol_code"],
                })
        return {
            "temp": ora["air_temperature"], "vento": ora.get("wind_speed"), "umidita": ora.get("relative_humidity"),
            "codice": codice, "giorni": giorni,
        }
    except (TypeError, KeyError, IndexError):
        return None


async def meteo_di(repo, citta: str) -> tuple[str, dict] | str | None:
    """(nome del luogo, meteo); "luogo" se la città non esiste; None se un servizio non risponde."""
    try:
        luogo = await trova_luogo(repo, citta)
    except (TimeoutError, asyncio.TimeoutError):
        return None
    if luogo is None:
        return "luogo"
    lat, lon, nome = luogo
    chiave = ("meteo", round(lat, 2), round(lon, 2))
    meteo = dalla_cache(chiave, CACHE_METEO)
    if meteo is None:
        try:
            meteo = leggi_meteo(await asyncio.wait_for(safe_get(url_meteo(lat, lon), max_bytes=2_000_000), TIMEOUT_SECONDI))
        except (TimeoutError, asyncio.TimeoutError):
            meteo = None
        if meteo is None:
            return None
        in_cache(chiave, meteo)
    return nome, meteo


# --- film e serie ---


def pulisci_html(testo: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", testo or "")).strip()


def leggi_serie(testo: str | None) -> dict[str, str] | None:
    d = _json(testo)
    try:
        return {
            "titolo": str(d["name"])[:256],
            "testo": rapidi.tronca(pulisci_html(d.get("summary") or "") or "—"),
            "link": str(d.get("url") or ""),
            "immagine": str((d.get("image") or {}).get("medium") or ""),
            "dettagli": " · ".join(
                x for x in (str(d.get("premiered") or "")[:4], ", ".join(d.get("genres") or [])[:100],
                            f"{(d.get('rating') or {}).get('average')}/10" if (d.get("rating") or {}).get("average") else "") if x
            ),
        }
    except (TypeError, KeyError, AttributeError):
        return None


async def cerca_serie(titolo: str) -> dict[str, str] | None:
    titolo = titolo.strip()[:MAX_TITOLO]
    chiave = ("serie", titolo.casefold())
    if (c := dalla_cache(chiave, 3600)) is not None:
        return c
    r = leggi_serie(await asyncio.wait_for(safe_get(f"https://api.tvmaze.com/singlesearch/shows?q={quote(titolo)}", max_bytes=500_000), TIMEOUT_SECONDI))
    if r:
        in_cache(chiave, r)
    return r


async def cerca_film(lingua: str, titolo: str) -> dict[str, str] | None:
    """Il sommario di Wikipedia: cerca «titolo film» per non cadere su omonimi."""
    return await rapidi.cerca_wikipedia(lingua, f"{titolo.strip()[:MAX_TITOLO]} film")


# --- Steam ---

LINGUE_STEAM = {"it": "italian", "en": "english", "de": "german", "fr": "french", "es": "spanish", "ja": "japanese",
                "ko": "koreana", "ru": "russian", "uk": "ukrainian", "zh": "schinese"}


def leggi_gioco(testo: str | None, appid: int) -> dict[str, str] | None:
    d = _json(testo)
    try:
        dati = d[str(appid)]["data"]
        prezzo = (dati.get("price_overview") or {}).get("final_formatted") or ("Gratis" if dati.get("is_free") else "—")
        return {
            "titolo": str(dati["name"])[:256],
            "testo": rapidi.tronca(pulisci_html(dati.get("short_description") or "") or "—"),
            "link": f"https://store.steampowered.com/app/{appid}",
            "immagine": str(dati.get("header_image") or ""),
            "prezzo": str(prezzo)[:100],
            "uscita": str((dati.get("release_date") or {}).get("date") or "—")[:100],
            "generi": ", ".join(g.get("description", "") for g in (dati.get("genres") or [])[:5])[:300] or "—",
        }
    except (TypeError, KeyError, AttributeError):
        return None


def primo_appid(testo: str | None) -> int | None:
    d = _json(testo)
    try:
        return int(d["items"][0]["id"])
    except (TypeError, KeyError, IndexError, ValueError):
        return None


async def cerca_gioco(lingua: str, titolo: str) -> dict[str, str] | None:
    titolo = titolo.strip()[:MAX_TITOLO]
    chiave = ("steam", lingua, titolo.casefold())
    if (c := dalla_cache(chiave, CACHE_STEAM)) is not None:
        return c
    lg = LINGUE_STEAM.get(lingua, "english")
    appid = primo_appid(await asyncio.wait_for(safe_get(
        f"https://store.steampowered.com/api/storesearch/?term={quote(titolo)}&l={lg}&cc=it", max_bytes=300_000), TIMEOUT_SECONDI))
    if appid is None:
        return None
    r = leggi_gioco(await asyncio.wait_for(safe_get(
        f"https://store.steampowered.com/api/appdetails?appids={appid}&l={lg}&cc=it", max_bytes=1_000_000), TIMEOUT_SECONDI), appid)
    if r:
        in_cache(chiave, r)
    return r


# --- prezzi cripto ---

MONETE = {  # simbolo -> id CoinGecko: elenco locale, il completamento non chiama nessun servizio
    "btc": "bitcoin", "eth": "ethereum", "usdt": "tether", "bnb": "binancecoin", "sol": "solana", "xrp": "ripple",
    "usdc": "usd-coin", "ada": "cardano", "doge": "dogecoin", "trx": "tron", "ton": "the-open-network",
    "avax": "avalanche-2", "dot": "polkadot", "link": "chainlink", "matic": "matic-network", "ltc": "litecoin",
    "shib": "shiba-inu", "bch": "bitcoin-cash", "xlm": "stellar", "atom": "cosmos", "xmr": "monero",
    "etc": "ethereum-classic", "near": "near", "uni": "uniswap", "algo": "algorand", "dai": "dai",
}
VALUTE = ("eur", "usd")


def cerca_monete(testo: str, massimo: int = 25) -> list[str]:
    t = testo.strip().casefold()
    return [s for s, i in MONETE.items() if t in s or t in i][:massimo]


def leggi_prezzo(testo: str | None, id_moneta: str, valuta: str) -> tuple[float, float | None] | None:
    d = _json(testo)
    try:
        riga = d[id_moneta]
        return float(riga[valuta]), (float(riga[valuta + "_24h_change"]) if riga.get(valuta + "_24h_change") is not None else None)
    except (TypeError, KeyError, ValueError):
        return None


async def prezzo_di(chiave_api: str, simbolo: str, valuta: str) -> tuple[float, float | None] | None:
    """Chiave nell'intestazione (non nell'indirizzo), così non finisce in nessun log."""
    id_moneta = MONETE.get(simbolo.strip().casefold())
    if id_moneta is None or valuta not in VALUTE:
        return None
    chiave = ("prezzo", id_moneta, valuta)
    if (c := dalla_cache(chiave, CACHE_PREZZI)) is not None:
        return c
    url = (f"https://api.coingecko.com/api/v3/simple/price?ids={id_moneta}&vs_currencies={valuta}"
           "&include_24hr_change=true")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDI),
                                         headers={"x-cg-demo-api-key": chiave_api, "User-Agent": USER_AGENT}) as s:
            async with s.get(url) as r:
                if r.status != 200:
                    return None
                testo = (await r.content.read(100_000)).decode("utf-8", "replace")
    except (aiohttp.ClientError, TimeoutError, asyncio.TimeoutError):
        return None
    esito = leggi_prezzo(testo, id_moneta, valuta)
    if esito:
        in_cache(chiave, esito)
    return esito


# --- accorciatore ---


@functools.lru_cache(maxsize=1)
def _lista_phishing() -> frozenset[str]:
    return carica_lista_locale()


async def accorcia_link(link: str) -> str:
    """Il link corto, oppure un codice di rifiuto: "non_valido", "pericoloso", "gia_corto", "errore"."""
    link = link.strip()
    p = urlparse(link)
    if p.scheme not in ("http", "https") or not p.hostname or len(link) > MAX_LINK:
        return "non_valido"
    if p.hostname.casefold() in ACCORCIATORI:
        return "gia_corto"
    if e_phishing([p.hostname], _lista_phishing()) or not await url_e_sicuro(link):
        return "pericoloso"
    try:
        risposta = await asyncio.wait_for(safe_get(f"https://is.gd/create.php?format=simple&url={quote(link, safe='')}", max_bytes=2000), TIMEOUT_SECONDI)
    except (TimeoutError, asyncio.TimeoutError):
        return "errore"
    corto = (risposta or "").strip()
    return corto if corto.startswith("https://is.gd/") and " " not in corto else "errore"
