"""
core/music_sorveglianza.py
==========================
Due controlli periodici per la musica, che girano da soli:
- ogni 30 secondi: i nodi Lavalink caduti ripartono (con pause crescenti) e, quando tornano,
  i player nuovi li riusano (i nodi preferiti vengono per primi); se un Lavalink che prima
  funzionava resta giù per più di 2 minuti, l'owner riceve un DM, e un altro quando torna;
- ogni 60 secondi: gli slot dei worker rimasti occupati senza un player vengono liberati.
Lavalink è facoltativo: se non c'è mai stato, nessun avviso e il bot funziona lo stesso.
Funzioni coperte: consiglio 25/11/2026, critici 7 e 8 (blocco C)
Dipende da: core/music_nodes.py, core/music_fleet.py, core/avvisi_owner.py
"""

from __future__ import annotations

import logging
import time

from core.avvisi_owner import avvisi_owner
from core.bot_ready import attendi_bot_pronto
from core.giro_periodico import giro_periodico

logger = logging.getLogger("iyokai.music")

ATTESA_AVVISO_GIU_SECONDI = 120.0


class SorveglianzaMusica:
    """Tiene il conto di quali servizi Lavalink hanno funzionato e da quando sono giù."""

    def __init__(self, bot, gestore, flotta) -> None:
        self._bot = bot
        self._gestore = gestore
        self._flotta = flotta
        self._visto_collegato: set[str] = set()
        self._giu_dal: dict[str, float] = {}

    def controlla_nodi(self, adesso: float | None = None) -> None:
        """Un giro: fa ripartire i nodi caduti e avvisa l'owner se un servizio resta giù troppo."""
        adesso = time.monotonic() if adesso is None else adesso
        self._gestore.riparti_nodi_caduti()
        for servizio, collegato in self._gestore.stato_per_servizio().items():
            if collegato:
                self._visto_collegato.add(servizio)
                self._giu_dal.pop(servizio, None)
                avvisi_owner.tornato(self._bot, f"lavalink:{servizio}")
                continue
            if servizio not in self._visto_collegato:
                continue  # non è mai partito: Lavalink è facoltativo, non è una caduta
            dal = self._giu_dal.setdefault(servizio, adesso)
            if adesso - dal >= ATTESA_AVVISO_GIU_SECONDI:
                avvisi_owner.caduto(self._bot, f"lavalink:{servizio}", "nodo non raggiungibile")

    async def libera_slot(self) -> int:
        return await self._flotta.libera_slot_persi()


def avvia_sorveglianza(bot, gestore, flotta) -> list:
    """Fa partire i due giri. Si chiama una sola volta, dopo che i nodi sono stati avviati."""
    sorveglianza = SorveglianzaMusica(bot, gestore, flotta)

    @giro_periodico(seconds=30, subito=True)
    async def _controlla_nodi_lavalink() -> None:
        sorveglianza.controlla_nodi()

    @_controlla_nodi_lavalink.before_loop
    async def _pronto_nodi() -> None:
        await attendi_bot_pronto(bot)

    giri = [_controlla_nodi_lavalink]
    if flotta is not None:

        @giro_periodico(seconds=60, subito=True)
        async def _libera_slot_musicali() -> None:
            liberati = await sorveglianza.libera_slot()
            if liberati:
                logger.info("Controllo slot musicali: %d liberati.", liberati)

        @_libera_slot_musicali.before_loop
        async def _pronto_slot() -> None:
            await attendi_bot_pronto(bot)

        giri.append(_libera_slot_musicali)
    for giro in giri:
        giro.start()
    return giri
