"""
core/music_anteprime_logic.py
=============================
Brani della cartella dell'owner (MUS-018) pronti per la coda: il brano letto da Lavalink perde percorso,
nome del file e copertina e prende il titolo pulito. Gli utenti vedono solo questo.
Funzioni coperte: SPEC §9 (catalogo MUS-018)
Dipende da: core/music_cartella_logic.py
"""

from __future__ import annotations

import asyncio
import copy
import logging
from dataclasses import dataclass

import wavelink

from core.music_cartella_logic import percorso_per_il_nodo, titolo_dai_metadati
from core.repositories.music_cartella_repo import BranoSalvato

logger = logging.getLogger("iyokai.music.anteprime")

AUTORE = "Anteprima"
SORGENTE_LOCALE = "local"
CONCORRENZA = 5


@dataclass(frozen=True)
class BranoPronto:
    brano_id: int
    titolo: str
    durata_ms: int
    dati: dict  # il payload di Lavalink, ripulito


def dati_traccia_pulita(dati, brano: BranoSalvato) -> BranoPronto | None:
    """
    Da un brano di Lavalink al brano mostrabile. None se non e' un file locale vero (sorgente diversa da `local`
    o dati storti): da una cartella non deve uscire altro. Via percorso (`identifier`, `uri`), copertina e autore.
    """
    if not isinstance(dati, dict) or not isinstance(dati.get("info"), dict) or not dati.get("encoded"):
        return None
    info = dati["info"]
    if str(info.get("sourceName") or "").lower() != SORGENTE_LOCALE:
        return None
    pulito = copy.deepcopy(dati)
    titolo = titolo_dai_metadati(info.get("title"), brano.titolo)
    durata = info.get("length")
    durata = durata if isinstance(durata, int) and not isinstance(durata, bool) and durata >= 0 else 0
    pulito["info"].update({
        "title": titolo, "author": AUTORE, "uri": None, "artworkUrl": None, "isrc": None,
        "identifier": f"anteprima-{brano.id}", "length": durata,
    })
    pulito["pluginInfo"] = {}
    pulito["userData"] = {}
    return BranoPronto(brano.id, titolo, durata, pulito)


async def _uno(nodo: wavelink.Node, radice_nodo: str, brano: BranoSalvato, limite: asyncio.Semaphore) -> BranoPronto | None:
    async with limite:
        try:
            trovati = await wavelink.Pool.fetch_tracks(percorso_per_il_nodo(radice_nodo, brano.percorso), node=nodo)
        except wavelink.exceptions.WavelinkException:
            logger.warning("Brano della cartella %s non letto dal nodo.", brano.id, exc_info=True)
            return None
    if not trovati or isinstance(trovati, wavelink.Playlist):
        return None
    return dati_traccia_pulita(trovati[0].raw_data, brano)


async def risolvi_brani(nodo: wavelink.Node, radice_nodo: str, brani: list[BranoSalvato]) -> list[BranoPronto]:
    """I brani che il nodo locale riesce a leggere, nell'ordine dato."""
    limite = asyncio.Semaphore(CONCORRENZA)
    pronti = await asyncio.gather(*(_uno(nodo, radice_nodo, b, limite) for b in brani))
    return [p for p in pronti if p is not None]


def come_ricerca(pronti: list[BranoPronto], nome: str) -> wavelink.Search:
    """Un brano solo: una lista; piu' brani: una playlist con il nome dato."""
    if len(pronti) == 1:
        return [wavelink.Playable(pronti[0].dati)]
    return wavelink.Playlist({
        "info": {"name": nome, "selectedTrack": -1}, "pluginInfo": {}, "tracks": [p.dati for p in pronti],
    })
