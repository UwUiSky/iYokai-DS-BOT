"""
core/music_lyrics_logic.py
==========================
Testi delle canzoni (MUS-046) da LRCLIB (lrclib.net): servizio gratuito, senza chiave, con testi sincronizzati (LRC).
Ogni richiesta passa da core/safe_http (`safe_get` con tetto di byte). Qui: pulizia del titolo, richieste, lettura
del formato LRC, riga corrente per il karaoke e una piccola memoria. Nessuna dipendenza da Discord.
Funzioni coperte: SPEC §9 (catalogo MUS-046)
Dipende da: core/safe_http.py
"""

from __future__ import annotations

import bisect
import json
import re
import time
from dataclasses import dataclass
from urllib.parse import urlencode

from core.safe_http import safe_get

URL_GET = "https://lrclib.net/api/get"
URL_SEARCH = "https://lrclib.net/api/search"
MAX_BYTE_RISPOSTA = 300_000  # un testo è di pochi KB; le ricerche portano più risultati
TOLLERANZA_DURATA_S = 5  # un testo vale per il brano se la durata differisce meno di così
CACHE_SECONDI = 3600
CACHE_MAX = 100
MAX_RIGHE = 500  # una canzone non ha più righe di così
MAX_RIGA = 200  # caratteri per riga mostrata
TESTO_MAX = 3000  # caratteri mostrati con /music brano testo

_cache: dict[tuple[str, str, int], tuple[float, "Testi | None"]] = {}

_RIGA_LRC = re.compile(r"^((?:\[\d{1,3}:\d{2}(?:[.:]\d{1,3})?\])+)(.*)$")
_TEMPO_LRC = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")
_RUMORE = re.compile(
    r"[\(\[][^)\]]*(official|video|audio|lyrics?|testo|visuali[sz]er|hd|4k|remaster\w*|live|clip)[^)\]]*[\)\]]", re.I
)
_CODA_CANALE = re.compile(r"\s*(-\s*topic|vevo|official)$", re.I)


class ServizioNonRisponde(Exception):
    """LRCLIB non ha risposto (rete, errore del servizio o risposta troppo grande)."""


@dataclass(frozen=True)
class Testi:
    titolo: str
    artista: str
    semplice: str  # senza tempi ("" se manca)
    sincronizzato: str  # LRC ("" se manca)


def ripulisci_titolo(titolo: str, autore: str) -> tuple[str, str]:
    """Da «Artista - Titolo (Official Video)» e dal canale «Artista - Topic» a (titolo, artista) più puliti."""
    pulito = _RUMORE.sub("", titolo or "").strip(" -–")
    artista = _CODA_CANALE.sub("", autore or "").strip()
    for trattino in (" - ", " – ", " — "):
        if trattino in pulito:
            primo, resto = pulito.split(trattino, 1)
            if primo.strip() and resto.strip():
                return resto.strip(), primo.strip()
    return pulito or (titolo or "").strip(), artista


def _a_testi(voce) -> Testi | None:
    if not isinstance(voce, dict) or voce.get("instrumental"):
        return None
    semplice = voce.get("plainLyrics") if isinstance(voce.get("plainLyrics"), str) else ""
    sync = voce.get("syncedLyrics") if isinstance(voce.get("syncedLyrics"), str) else ""
    if not semplice.strip() and not sync.strip():
        return None
    return Testi(str(voce.get("trackName") or "")[:150], str(voce.get("artistName") or "")[:150], semplice, sync)


def _durata_vicina(voce, durata_s: int) -> bool:
    d = voce.get("duration") if isinstance(voce, dict) else None
    return durata_s <= 0 or not isinstance(d, (int, float)) or abs(d - durata_s) <= TOLLERANZA_DURATA_S


def _json(testo: str | None):
    try:
        return json.loads(testo) if testo else None
    except ValueError:
        return None


async def cerca_testi(titolo: str, autore: str, durata_ms: int, *, scarica=safe_get) -> Testi | None:
    """I testi del brano, o None se non ci sono. Solleva `ServizioNonRisponde` se il servizio non risponde."""
    nome, artista = ripulisci_titolo(titolo, autore)
    durata_s = max(0, int(durata_ms // 1000))
    chiave = (nome.lower(), artista.lower(), durata_s)
    adesso = time.monotonic()
    trovato = _cache.get(chiave)
    if trovato and adesso - trovato[0] < CACHE_SECONDI:
        return trovato[1]
    if not nome:
        return None

    esatto = None
    if artista:
        dati = _json(await scarica(
            f"{URL_GET}?{urlencode({'track_name': nome, 'artist_name': artista, 'duration': durata_s})}",
            max_bytes=MAX_BYTE_RISPOSTA,
        ))
        esatto = _a_testi(dati) if isinstance(dati, dict) else None
    risultato = esatto
    if risultato is None:
        # /api/get dà 404 quando non trova: la ricerca risponde 200 anche senza risultati, quindi dice se il servizio c'è
        grezzo = await scarica(
            f"{URL_SEARCH}?{urlencode({'q': f'{artista} {nome}'.strip()})}", max_bytes=MAX_BYTE_RISPOSTA
        )
        elenco = _json(grezzo)
        if not isinstance(elenco, list):
            raise ServizioNonRisponde()
        for voce in elenco[:20]:
            if _durata_vicina(voce, durata_s):
                candidato = _a_testi(voce)
                if candidato is not None:
                    risultato = candidato
                    break
    if len(_cache) >= CACHE_MAX:
        _cache.clear()
    _cache[chiave] = (adesso, risultato)
    return risultato


def svuota_memoria() -> None:
    _cache.clear()


def leggi_lrc(lrc: str) -> list[tuple[int, str]]:
    """Righe «[mm:ss.xx]testo» -> [(millisecondi, testo)] in ordine di tempo. Etichette e righe rotte sono ignorate."""
    righe: list[tuple[int, str]] = []
    for riga in (lrc or "").splitlines():
        m = _RIGA_LRC.match(riga.strip())
        if not m:
            continue
        testo = m.group(2).strip()[:MAX_RIGA]
        for minuti, secondi, frazione in _TEMPO_LRC.findall(m.group(1)):
            decimi = (frazione or "0").ljust(3, "0")[:3]
            righe.append((int(minuti) * 60_000 + int(secondi) * 1000 + int(decimi), testo))
        if len(righe) >= MAX_RIGHE:
            break
    righe.sort(key=lambda r: r[0])
    return righe[:MAX_RIGHE]


def indice_riga(righe: list[tuple[int, str]], posizione_ms: int) -> int:
    """L'indice della riga da cantare ora (-1 prima della prima riga)."""
    return bisect.bisect_right([r[0] for r in righe], posizione_ms) - 1


def testo_karaoke(righe: list[tuple[int, str]], indice: int, massimo: int = 1000) -> str:
    """Riga precedente, riga corrente in grassetto e le due seguenti. Mai più di `massimo` caratteri."""
    def riga(i: int) -> str:
        return righe[i][1] if 0 <= i < len(righe) and righe[i][1] else ""

    pezzi = [riga(indice - 1), f"**{riga(indice) or '♪'}**" if indice >= 0 else "♪", riga(indice + 1), riga(indice + 2)]
    testo = "\n".join(p for p in pezzi if p)
    return testo[:massimo]


def tronca_testo(testo: str, massimo: int = TESTO_MAX) -> str:
    testo = (testo or "").strip()
    return testo if len(testo) <= massimo else testo[: massimo - 1].rstrip() + "…"
