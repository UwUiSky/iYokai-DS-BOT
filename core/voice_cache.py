"""
core/voice_cache.py
===================
Cache su disco dei vocali: stessa frase, stesso profilo, stesso motore e stessa voce di riferimento danno lo stesso
file. Le frasi fisse non scadono; il resto sì; la cartella ha un tetto di spazio.
Funzioni coperte: SPEC §14.19, §25.102 (AI-R-109)
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

TTL_PREDEFINITO = 7 * 24 * 3600
TETTO_PREDEFINITO = 300 * 1024 * 1024


def chiave(testo: str, profilo: str, motore: str, versione_voce: str) -> str:
    """SHA256 di testo normalizzato, profilo, motore e versione della voce (cambiare voce svuota la cache)."""
    grezzo = "\x1f".join([" ".join(testo.split()), profilo, motore, versione_voce])
    return hashlib.sha256(grezzo.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VocaleSalvato:
    ogg: bytes
    durata: float
    onda: str


def _impacchetta(v: VocaleSalvato) -> bytes:
    meta = json.dumps({"durata": v.durata, "onda": v.onda}).encode()
    return len(meta).to_bytes(4, "big") + meta + v.ogg


def _spacchetta(dati: bytes) -> VocaleSalvato:
    n = int.from_bytes(dati[:4], "big")
    meta = json.loads(dati[4 : 4 + n])
    return VocaleSalvato(ogg=dati[4 + n :], durata=float(meta["durata"]), onda=str(meta["onda"]))


class CacheVoce:
    def __init__(self, cartella: str | Path, ttl: int = TTL_PREDEFINITO, tetto_byte: int = TETTO_PREDEFINITO) -> None:
        self.cartella = Path(cartella)
        self.ttl = ttl
        self.tetto_byte = tetto_byte

    def _percorso(self, k: str, fisso: bool) -> Path:
        return self.cartella / f"{k}{'.fisso' if fisso else ''}.voce"

    def leggi(self, k: str, adesso: float | None = None) -> VocaleSalvato | None:
        adesso = adesso or time.time()
        for fisso in (True, False):
            p = self._percorso(k, fisso)
            try:
                if not fisso and adesso - p.stat().st_mtime > self.ttl:
                    p.unlink(missing_ok=True)
                    continue
                return _spacchetta(p.read_bytes())
            except (OSError, ValueError, KeyError):
                continue
        return None

    def scrivi(self, k: str, v: VocaleSalvato, fisso: bool = False) -> None:
        self.cartella.mkdir(parents=True, exist_ok=True)
        p = self._percorso(k, fisso)
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(_impacchetta(v))
        os.replace(tmp, p)

    def pulisci(self, adesso: float | None = None) -> int:
        """Toglie i file scaduti e, se la cartella supera il tetto, i più vecchi non fissi. Restituisce quanti ne toglie."""
        adesso = adesso or time.time()
        if not self.cartella.is_dir():
            return 0
        file = [(p, p.stat()) for p in self.cartella.glob("*.voce")]
        tolti = 0
        for p, st in list(file):
            if ".fisso" not in p.name and adesso - st.st_mtime > self.ttl:
                p.unlink(missing_ok=True)
                file.remove((p, st))
                tolti += 1
        totale = sum(st.st_size for _, st in file)
        for p, st in sorted((x for x in file if ".fisso" not in x[0].name), key=lambda x: x[1].st_mtime):
            if totale <= self.tetto_byte:
                break
            p.unlink(missing_ok=True)
            totale -= st.st_size
            tolti += 1
        return tolti
