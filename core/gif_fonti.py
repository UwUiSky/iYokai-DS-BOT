"""
core/gif_fonti.py
=================
Le fonti delle GIF di reazione e azione (D70): lettura di `config/gif_fornitori.env` (l'ambiente vince sul
file, un interruttore per fonte), richieste con `safe_get`, cache con tetto e giro tra le fonti accese con
ripiego. Solo categorie SFW: gli indirizzi sono costruiti qui, sempre nella parte SFW di ogni servizio, e
una categoria per adulti non parte mai. Le fonti per adulti stanno in un altro elenco (bot NSFW).
Funzioni coperte: SPEC §16 (FUN-081..135; D70, #131)
Dipende da: core/gif_catalogo.py, core/safe_http.py, core/bounded_cache.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, urlparse

from core.bounded_cache import BoundedCache
from core.gif_catalogo import Voce

logger = logging.getLogger("iyokai.gif_fonti")

FILE_FONTI = Path(__file__).resolve().parent.parent / "config" / "gif_fornitori.env"
TIMEOUT_SECONDI = 8
MAX_BYTES_RISPOSTA = 200_000
DURATA_CACHE_SECONDI = 6 * 3600
MAX_VOCI_IN_CACHE = 300
MAX_GIF_PER_VOCE = 20
SOGLIA_SENZA_RETE = 8  # con tante GIF già in cache non si chiama la fonte
PAUSA_FONTE_SECONDI = 60  # una fonte che non risponde riposa un minuto
GIPHY_CREDITO = "Powered by GIPHY"

# Fonti con adattatore: nome -> (indirizzo base, acceso di base, serve la chiave, domini ammessi per le GIF)
FONTI: dict[str, tuple[str, bool, bool, tuple[str, ...]]] = {
    "nekosbest": ("https://nekos.best/api/v2", True, False, ("nekos.best",)),
    "purrbot": ("https://api.purrbot.site/v2", True, False, ("purrbot.site",)),
    "waifupics": ("https://api.waifu.pics", True, False, ("waifu.pics",)),
    "otakugifs": ("https://api.otakugifs.xyz", True, False, ("otakugifs.xyz",)),
    "nekoslife": ("https://nekos.life/api/v2", False, False, ("nekos.life",)),
    "giphy": ("https://api.giphy.com/v1", False, True, ("giphy.com",)),
}
NOMI_VISIBILI = {
    "nekosbest": "nekos.best", "purrbot": "purrbot.site", "waifupics": "waifu.pics", "otakugifs": "otakugifs",
    "nekoslife": "nekos.life", "giphy": "GIPHY",
}
# Parole che indicano contenuti per adulti: se una categoria le contiene la richiesta non parte (SFW sempre).
PAROLE_VIETATE = (
    "nsfw", "lewd", "gasm", "spank", "ero", "hentai", "porn", "boob", "pussy", "anal", "blowjob", "cum", "trap",
    "kink", "nude", "sex", "fuck", "milf", "ass", "oppai", "bdsm", "futa", "yuri", "yaoi", "loli", "shota",
)
_SOLO_LETTERE = re.compile(r"[a-z]+")


def categoria_sfw(categoria: str) -> bool:
    """False se la categoria o la ricerca contiene una parola per adulti (confronto per parole e per prefisso)."""
    parole = _SOLO_LETTERE.findall((categoria or "").casefold())
    return bool(parole) and not any(p.startswith(v) or p == v for p in parole for v in PAROLE_VIETATE)


@dataclass(frozen=True)
class Fonte:
    nome: str
    url: str
    chiave: str = field(repr=False, default="")

    @property
    def visibile(self) -> str:
        return NOMI_VISIBILI.get(self.nome, self.nome)


@dataclass(frozen=True)
class Gif:
    url: str
    fonte: str
    dettaglio: str = ""
    link: str | None = None


def _si(valore: str | None, base: bool) -> bool:
    if valore is None or not valore.strip():
        return base
    return valore.strip().lower() in ("si", "sì", "yes", "true", "1", "on")


def env_con_file(env: Mapping[str, str] | None = None, percorso: Path | None = None) -> dict[str, str]:
    """L'ambiente più le variabili `GIF_*` del file (l'ambiente vince; un valore vuoto non copre il file)."""
    env = dict(os.environ if env is None else env)
    percorso = FILE_FONTI if percorso is None else percorso
    if not percorso.is_file():
        return env
    from dotenv import dotenv_values

    for chiave, valore in dotenv_values(percorso).items():
        if chiave.startswith("GIF_") and valore and not env.get(chiave):
            env[chiave] = valore
    return env


def leggi_fonti(env: Mapping[str, str] | None = None) -> list[Fonte]:
    """Le fonti accese, nell'ordine di `GIF_ORDINE` (poi le altre accese). Senza chiave, Giphy resta spenta."""
    env = os.environ if env is None else env
    ordine = [n.strip().lower() for n in (env.get("GIF_ORDINE") or "").split(",") if n.strip()]
    nomi = [n for n in ordine if n in FONTI] + [n for n in FONTI if n not in ordine]
    fonti: list[Fonte] = []
    for nome in nomi:
        base, acceso, serve_chiave, _ = FONTI[nome]
        su = nome.upper()
        if not _si(env.get(f"GIF_{su}_ATTIVO"), acceso):
            continue
        chiave = (env.get(f"GIF_{su}_KEY") or "").strip()
        if serve_chiave and not chiave:
            logger.warning("Fonte GIF %s accesa ma senza chiave: resta spenta.", nome)
            continue
        url = (env.get(f"GIF_{su}_URL") or base).strip().rstrip("/")
        if not url.startswith("https://"):
            logger.warning("Fonte GIF %s con indirizzo non https: resta spenta.", nome)
            continue
        fonti.append(Fonte(nome, url, chiave))
    return fonti


def _richiesta(fonte: Fonte, voce: Voce) -> str | None:
    """L'indirizzo da chiamare, solo nella parte SFW del servizio. None se la fonte non copre la voce."""
    categoria = voce.fonti.get(fonte.nome)
    if fonte.nome == "giphy":
        if not voce.ricerca or not categoria_sfw(voce.ricerca):
            return None
        q = quote(voce.ricerca[:50])
        return f"{fonte.url}/gifs/search?api_key={quote(fonte.chiave)}&q={q}&rating=g&limit=10&lang=en"
    if not categoria or not categoria_sfw(categoria) or not re.fullmatch(r"[a-z_]{2,20}", categoria):
        return None
    if fonte.nome == "nekosbest":
        return f"{fonte.url}/{categoria}?amount=10"
    if fonte.nome == "purrbot":
        return f"{fonte.url}/img/sfw/{categoria}/gif"
    if fonte.nome == "waifupics":
        return f"{fonte.url}/sfw/{categoria}"
    if fonte.nome == "otakugifs":
        return f"{fonte.url}/gif?reaction={categoria}&format=gif"
    if fonte.nome == "nekoslife":
        return f"{fonte.url}/img/{categoria}"
    return None


def _dominio_ammesso(fonte: str, url: object) -> bool:
    if not isinstance(url, str) or not url.startswith("https://"):
        return False
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in FONTI[fonte][3])


def _testo(valore: object, massimo: int = 80) -> str:
    return valore.strip()[:massimo] if isinstance(valore, str) else ""


def _link(valore: object) -> str | None:
    return valore if isinstance(valore, str) and valore.startswith("https://") and len(valore) <= 300 else None


def leggi_risposta(nome: str, testo: str) -> list[Gif]:
    """Le GIF di una risposta. Scarta ciò che non è https o non sta nei domini della fonte."""
    try:
        dati = json.loads(testo)
    except ValueError:
        return []
    if not isinstance(dati, dict):
        return []
    visibile = NOMI_VISIBILI[nome]
    trovate: list[Gif] = []
    if nome == "nekosbest":
        for r in dati.get("results") or []:
            if isinstance(r, dict) and _dominio_ammesso(nome, r.get("url")):
                dettaglio = _testo(r.get("anime_name")) or _testo(r.get("artist_name"))
                trovate.append(Gif(r["url"], visibile, dettaglio, _link(r.get("artist_href")) or _link(r.get("source_url"))))
    elif nome == "giphy":
        for r in dati.get("data") or []:
            if not isinstance(r, dict):
                continue
            immagini = r.get("images") if isinstance(r.get("images"), dict) else {}
            for tipo in ("downsized_medium", "downsized", "original"):
                url = (immagini.get(tipo) or {}).get("url") if isinstance(immagini.get(tipo), dict) else None
                if _dominio_ammesso(nome, url):
                    trovate.append(Gif(url, visibile, GIPHY_CREDITO, _link(r.get("url"))))
                    break
    else:
        url = dati.get("link") if nome == "purrbot" else dati.get("url")
        if _dominio_ammesso(nome, url):
            trovate.append(Gif(url, visibile))
    return trovate


Scarica = Callable[[str], Awaitable[str | None]]


async def _scarica_vero(url: str) -> str | None:
    from core.safe_http import safe_get

    try:
        return await asyncio.wait_for(safe_get(url, max_bytes=MAX_BYTES_RISPOSTA), TIMEOUT_SECONDI)
    except (asyncio.TimeoutError, OSError):
        return None


class ServizioGif:
    """Una GIF per ogni voce: cache con tetto, giro tra le fonti accese e ripiego sulle altre."""

    def __init__(
        self,
        fonti: list[Fonte] | None = None,
        scarica: Scarica | None = None,
        rng: random.Random | None = None,
        adesso: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fonti = fonti
        self._scarica = scarica or _scarica_vero
        self._rng = rng or random.Random()
        self._adesso = adesso
        self._cache: BoundedCache[tuple[str, str], tuple[float, list[Gif]]] = BoundedCache(MAX_VOCI_IN_CACHE)
        self._riposo: dict[str, float] = {}
        self._giro = 0

    def fonti(self) -> list[Fonte]:
        if self._fonti is None:
            self._fonti = leggi_fonti(env_con_file())
        return self._fonti

    def ricarica(self) -> None:
        self._fonti = None
        self._cache.clear()

    def _in_cache(self, fonte: str, voce: Voce) -> list[Gif]:
        visto = self._cache.get((fonte, voce.id))
        if visto is None or self._adesso() - visto[0] > DURATA_CACHE_SECONDI:
            return []
        return visto[1]

    def _salva(self, fonte: str, voce: Voce, nuove: list[Gif]) -> list[Gif]:
        pool = list(self._in_cache(fonte, voce))
        conosciute = {g.url for g in pool}
        pool += [g for g in nuove if g.url not in conosciute]
        pool = pool[-MAX_GIF_PER_VOCE:]
        self._cache.set((fonte, voce.id), (self._adesso(), pool))
        return pool

    async def _da_fonte(self, fonte: Fonte, voce: Voce) -> Gif | None:
        pool = self._in_cache(fonte.nome, voce)
        if len(pool) >= SOGLIA_SENZA_RETE:
            return self._rng.choice(pool)
        url = _richiesta(fonte, voce)
        if url is None:
            return None
        if self._riposo.get(fonte.nome, 0) > self._adesso():
            return self._rng.choice(pool) if pool else None
        testo = await self._scarica(url)
        nuove = leggi_risposta(fonte.nome, testo) if testo else []
        if not nuove:
            if not testo:
                self._riposo[fonte.nome] = self._adesso() + PAUSA_FONTE_SECONDI
            return self._rng.choice(pool) if pool else None
        return self._rng.choice(self._salva(fonte.nome, voce, nuove))

    async def prendi(self, voce: Voce) -> Gif | None:
        """Una GIF per `voce`, o None. La prima fonte cambia a ogni richiesta; se non risponde si prova la prossima."""
        copre = [f for f in self.fonti() if _richiesta(f, voce) is not None]
        if not copre:
            return None
        partenza = self._giro % len(copre)
        self._giro += 1
        for fonte in copre[partenza:] + copre[:partenza]:
            try:
                gif = await self._da_fonte(fonte, voce)
            except Exception:
                logger.exception("Fonte GIF %s fallita", fonte.nome)
                gif = None
            if gif is not None:
                return gif
        return None


servizio_gif = ServizioGif()
