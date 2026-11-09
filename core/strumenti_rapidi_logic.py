"""
core/strumenti_rapidi_logic.py
==============================
Logica senza Discord degli strumenti rapidi: caratteri Unicode, cronometro,
novità del bot, numeri di emergenza, Wikipedia e Wikizionario.
Funzioni coperte: catalogo #128 UTL-203, 212, 221, 220, 215, 214 (blocco B1, D69)
"""

from __future__ import annotations

import json
import pathlib
import re
import time
import unicodedata
from typing import Any
from urllib.parse import quote

from core.bounded_cache import BoundedCache
from core.safe_http import safe_get

MAX_CARATTERI = 25  # un campo per carattere: tetto dei campi di un embed
MAX_TESTO_CARATTERI = 100
MAX_GIRI = 20
MAX_RICERCA = 100
MAX_PAROLA = 50
NOVITA_PER_PAGINA = 10
CACHE_SECONDI = 3600
RADICE_DATI = pathlib.Path(__file__).resolve().parent.parent / "data"

_ESTRATTO_MAX = 1000


def righe_caratteri(testo: str) -> tuple[list[tuple[str, str]], int]:
    """Fino a 25 caratteri distinti: (titolo, descrizione). Secondo valore = quanti sono stati tagliati."""
    visti: list[str] = []
    for c in testo:
        if c not in visti and not c.isspace():
            visti.append(c)
    righe = []
    for c in visti[:MAX_CARATTERI]:
        nome = unicodedata.name(c, "(senza nome)")
        categoria = unicodedata.category(c)
        mostra = c if categoria[0] not in ("C", "M") else "·"
        righe.append((f"{mostra}  U+{ord(c):04X}", f"{nome}\n`{categoria}` · `\\u{ord(c):04x}`"[:1024]))
    return righe, max(0, len(visti) - MAX_CARATTERI)


# --- cronometro: l'inizio sta nel custom_id, nessun dato salvato ---


def id_cronometro(azione: str, inizio: int) -> str:
    return f"crono:{azione}:{inizio}"


def formatta_durata(secondi: float) -> str:
    secondi = max(0.0, secondi)
    ore, resto = divmod(int(secondi), 3600)
    minuti, sec = divmod(resto, 60)
    decimi = int((secondi - int(secondi)) * 10)
    base = f"{minuti:02d}:{sec:02d}.{decimi}"
    return f"{ore}:{base}" if ore else base


def corpo_cronometro(inizio: int, giri: list[str], fermo: float | None = None) -> str:
    """Il testo del messaggio: l'orario d'inizio e i giri (l'ultimo tetto: 20)."""
    stato = "fermo a " + formatta_durata(fermo) if fermo is not None else f"partito <t:{inizio}:R>"
    righe = [f"Cronometro: {stato}"]
    righe += [f"Giro {i}: {g}" for i, g in enumerate(giri[:MAX_GIRI], 1)]
    return "\n".join(righe)[:2000]


def giri_dal_testo(contenuto: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"^Giro \d+: (.+)$", contenuto, re.M)][:MAX_GIRI]


def aggiungi_giro(contenuto: str, inizio: int, adesso: float | None = None) -> tuple[str, bool]:
    """(nuovo testo, accettato). Oltre 20 giri il giro non si aggiunge."""
    giri = giri_dal_testo(contenuto)
    if len(giri) >= MAX_GIRI:
        return contenuto, False
    giri.append(formatta_durata((adesso if adesso is not None else time.time()) - inizio))
    return corpo_cronometro(inizio, giri), True


def ferma_cronometro(contenuto: str, inizio: int, adesso: float | None = None) -> str:
    return corpo_cronometro(inizio, giri_dal_testo(contenuto), (adesso if adesso is not None else time.time()) - inizio)


# --- file dell'owner: novità ed emergenze ---


def _leggi_json(percorso: pathlib.Path) -> Any:
    try:
        return json.loads(percorso.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def carica_novita(lingua: str, radice: pathlib.Path = RADICE_DATI) -> list[dict[str, str]]:
    """Voci `{data, titolo, testo}` della lingua (ripiego: it), le più nuove prima."""
    for codice in (lingua, "it"):
        dati = _leggi_json(radice / "novita" / f"{codice}.json")
        if isinstance(dati, list):
            voci = [v for v in dati if isinstance(v, dict) and v.get("titolo")]
            return sorted(voci, key=lambda v: str(v.get("data", "")), reverse=True)
    return []


def pagina_novita(voci: list[dict[str, str]], pagina: int) -> tuple[list[dict[str, str]], int]:
    """(voci della pagina, numero di pagine). La pagina è bloccata dentro i limiti."""
    pagine = max(1, -(-len(voci) // NOVITA_PER_PAGINA))
    p = min(max(pagina, 0), pagine - 1)
    return voci[p * NOVITA_PER_PAGINA : (p + 1) * NOVITA_PER_PAGINA], pagine


def carica_emergenze(radice: pathlib.Path = RADICE_DATI) -> dict[str, Any]:
    dati = _leggi_json(radice / "emergenze.json")
    return dati if isinstance(dati, dict) else {"fonte": "", "data": "", "paesi": {}}


def cerca_paesi(testo: str, paesi: dict[str, Any], massimo: int = 25) -> list[str]:
    t = testo.strip().casefold()
    return [p for p in paesi if t in p.casefold()][:massimo]


# --- Wikipedia e Wikizionario ---

_cache: BoundedCache[tuple[str, str, str], tuple[float, dict[str, str] | None]] = BoundedCache(500)


def lingua_wiki(lingua: str | None) -> str:
    """'en-US' -> 'en'; 'zh-CN' -> 'zh'. Senza lingua: italiano."""
    return (lingua or "it").split("-")[0].lower()[:5]


def tronca(testo: str, massimo: int = _ESTRATTO_MAX) -> str:
    testo = testo.strip()
    return testo if len(testo) <= massimo else testo[: massimo - 1].rstrip() + "…"


def url_ricerca_wikipedia(lingua: str, cerca: str) -> str:
    return f"https://{lingua}.wikipedia.org/w/rest.php/v1/search/title?q={quote(cerca[:MAX_RICERCA])}&limit=1"


def url_sommario_wikipedia(lingua: str, chiave: str) -> str:
    return f"https://{lingua}.wikipedia.org/api/rest_v1/page/summary/{quote(chiave, safe='')}"


def url_wikizionario(lingua: str, parola: str) -> str:
    return (
        f"https://{lingua}.wiktionary.org/w/api.php?action=query&prop=extracts&explaintext=1&exintro=1"
        f"&redirects=1&format=json&titles={quote(parola[:MAX_PAROLA])}"
    )


def leggi_chiave_ricerca(testo: str | None) -> str | None:
    try:
        pagine = json.loads(testo or "")["pages"]
        return pagine[0]["key"] if pagine else None
    except (ValueError, KeyError, IndexError, TypeError):
        return None


def leggi_sommario(testo: str | None) -> dict[str, str] | None:
    try:
        d = json.loads(testo or "")
        if d.get("type") == "disambiguation" and not d.get("extract"):
            return None
        estratto = d["extract"]
        return {
            "titolo": str(d["title"])[:256],
            "testo": tronca(str(estratto)),
            "link": str(d.get("content_urls", {}).get("desktop", {}).get("page", "")),
            "immagine": str(d.get("thumbnail", {}).get("source", "")),
        }
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def leggi_wikizionario(testo: str | None, lingua: str) -> dict[str, str] | None:
    try:
        pagine = json.loads(testo or "")["query"]["pages"]
        pagina = next(iter(pagine.values()))
        estratto = pagina.get("extract", "")
        if "missing" in pagina or not estratto.strip():
            return None
        titolo = str(pagina["title"])
        return {
            "titolo": titolo[:256],
            "testo": tronca(estratto),
            "link": f"https://{lingua}.wiktionary.org/wiki/{quote(titolo.replace(' ', '_'))}",
            "immagine": "",
        }
    except (ValueError, KeyError, TypeError, StopIteration, AttributeError):
        return None


async def _con_cache(tipo: str, lingua: str, chiave: str, produci) -> dict[str, str] | None:
    k = (tipo, lingua, chiave.casefold())
    visto = _cache.get(k)
    if visto is not None and time.monotonic() - visto[0] < CACHE_SECONDI:
        return visto[1]
    risultato = await produci()
    if risultato is not None:  # un errore di rete non si ricorda
        _cache.set(k, (time.monotonic(), risultato))
    return risultato


async def cerca_wikipedia(lingua: str, cerca: str) -> dict[str, str] | None:
    """Sommario della prima voce; se la lingua non ha la voce riprova in inglese."""
    cerca = cerca.strip()[:MAX_RICERCA]

    async def produci() -> dict[str, str] | None:
        for lg in dict.fromkeys((lingua, "en")):
            chiave = leggi_chiave_ricerca(await safe_get(url_ricerca_wikipedia(lg, cerca), max_bytes=200_000))
            if chiave:
                s = leggi_sommario(await safe_get(url_sommario_wikipedia(lg, chiave), max_bytes=200_000))
                if s:
                    return s
        return None

    return await _con_cache("wiki", lingua, cerca, produci)


async def cerca_parola(lingua: str, parola: str) -> dict[str, str] | None:
    parola = parola.strip()[:MAX_PAROLA]

    async def produci() -> dict[str, str] | None:
        for lg in dict.fromkeys((lingua, "en")):
            r = leggi_wikizionario(await safe_get(url_wikizionario(lg, parola), max_bytes=200_000), lg)
            if r:
                return r
        return None

    return await _con_cache("dizionario", lingua, parola, produci)
