"""
core/voice_client.py
====================
Il servizio voce: testo → vocale pronto. Prepara il testo, guarda la cache, altrimenti mette la sintesi in coda
(una alla volta, con tempo massimo). Se il motore manca, è occupato o sbaglia, restituisce None e il bot manda il solo testo.
Funzioni coperte: SPEC §14.19, §25.102 (AI-R-109)
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

from core import voice_cache as cache_mod
from core import voice_text_logic as testo_logic
from core.voice_audio import a_ogg_opus
from core.voice_engine import MotoreVoce, leggi_motore
from core.voice_profile import VoiceProfile, firma

logger = logging.getLogger("iyokai.voce")

CODA_MASSIMA = 8
TIMEOUT_SECONDI = 90


@dataclass(frozen=True)
class Vocale:
    ogg: bytes
    durata: float
    onda: str
    testo: str  # il testo pronunciato (già ripulito)
    da_cache: bool = False


class ServizioVoce:
    def __init__(self, motore: MotoreVoce | None, cache: cache_mod.CacheVoce | None = None, *, timeout: float = TIMEOUT_SECONDI, coda_massima: int = CODA_MASSIMA) -> None:
        self.motore = motore
        self.cache = cache
        self.timeout = timeout
        self.coda_massima = coda_massima
        self._turno = asyncio.Semaphore(1)
        self._in_coda = 0

    @property
    def attivo(self) -> bool:
        return self.motore is not None

    async def genera(self, testo: str, profilo: VoiceProfile, *, nomi: dict[int, str] | None = None, fisso: bool = False) -> Vocale | None:
        """Il vocale per il testo, o None (motore spento, coda piena, errore): chi chiama manda solo il testo."""
        pronto = testo_logic.prepara(testo, nomi)
        if not pronto or self.motore is None:
            return None
        k = cache_mod.chiave(pronto, firma(profilo), self.motore.nome, self.motore.versione)
        if self.cache is not None:
            trovato = await asyncio.to_thread(self.cache.leggi, k)
            if trovato is not None:
                return Vocale(trovato.ogg, trovato.durata, trovato.onda, pronto, True)
        if self._in_coda >= self.coda_massima:
            logger.warning("Coda della voce piena: solo testo.")
            return None
        self._in_coda += 1
        try:
            async with self._turno:
                wav = await asyncio.wait_for(self.motore.sintetizza(testo_logic.frasi(pronto), profilo), self.timeout)
            ogg, durata, onda = await a_ogg_opus(wav)
        except Exception:  # noqa: BLE001 - la voce è un di più: mai blocca chi la chiede
            logger.warning("Sintesi vocale non riuscita.", exc_info=True)
            return None
        finally:
            self._in_coda -= 1
        if self.cache is not None:
            await asyncio.to_thread(self.cache.scrivi, k, cache_mod.VocaleSalvato(ogg, durata, onda), fisso)
        return Vocale(ogg, durata, onda, pronto)


_servizio: ServizioVoce | None = None


def servizio_voce() -> ServizioVoce:
    global _servizio
    if _servizio is None:
        cartella = os.environ.get("VOCE_CACHE_DIR") or "data/voce_cache"
        _servizio = ServizioVoce(leggi_motore(), cache_mod.CacheVoce(cartella))
    return _servizio


def imposta_servizio_voce(s: ServizioVoce | None) -> None:
    """Per i test."""
    global _servizio
    _servizio = s
