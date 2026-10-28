"""
core/odio_libreria_service.py
=============================
Libreria mondiale delle parole d'odio (D35) vista dai filtri: le varianti globali
(base e approvate) valgono in tutti i server, le candidate solo in quelli che le
hanno segnalate. Letture con cache breve; la segnalazione di una variante nuova
trovata dall'AI passa da qui.
Funzioni coperte: SPEC §6 (D35)
Dipende da: core/repositories/odio_libreria_repo.py
"""

from __future__ import annotations

import logging
import time

from core.odio_libreria_logic import pulisci_lingua, variante_segnalabile
from core.repositories.odio_libreria_repo import ParolaOdio, odio_libreria_repo

logger = logging.getLogger("iyokai.odio_libreria")

DURATA_CACHE = 300.0
MAX_SERVER_IN_CACHE = 2000


class LibreriaOdio:
    def __init__(self, repo=None) -> None:
        self.repo = repo or odio_libreria_repo
        self._globali: tuple[float, tuple[str, ...]] = (0.0, ())
        self._candidate: dict[int, tuple[float, tuple[str, ...]]] = {}

    def svuota(self) -> None:
        self._globali = (0.0, ())
        self._candidate.clear()

    async def globali(self) -> tuple[str, ...]:
        scade, valori = self._globali
        if time.monotonic() >= scade:
            try:
                valori = await self.repo.globali()
            except Exception:  # database fermo: si tiene l'ultimo elenco, la lista di base resta
                logger.warning("Libreria delle parole non leggibile", exc_info=True)
                self._globali = (time.monotonic() + 30, valori)
                return valori
            self._globali = (time.monotonic() + DURATA_CACHE, valori)
        return valori

    async def candidate(self, guild_id: int) -> tuple[str, ...]:
        scade, valori = self._candidate.get(guild_id, (0.0, ()))
        if time.monotonic() >= scade:
            try:
                valori = await self.repo.candidate_del_server(guild_id)
            except Exception:
                logger.warning("Candidate della libreria non leggibili", exc_info=True)
                return valori
            if len(self._candidate) >= MAX_SERVER_IN_CACHE:
                self._candidate.clear()
            self._candidate[guild_id] = (time.monotonic() + DURATA_CACHE, valori)
        return valori

    async def segnala(
        self, guild_id: int, parole: tuple[str, ...], lingua: str = "", owner_id: int | None = None
    ) -> list[ParolaOdio]:
        """
        Le parole offensive che l'AI ha indicato: ognuna e' una variante da proporre (owner_id None:
        il server non conta per la soglia globale). Non solleva mai.
        """
        fatte: list[ParolaOdio] = []
        for parola in parole:
            variante = variante_segnalabile(parola)
            if variante is None:
                continue
            try:
                esito = await self.repo.segnala(variante, pulisci_lingua(lingua), guild_id, owner_id)
            except Exception:  # la libreria non deve mai fermare la moderazione
                logger.exception("Segnalazione della variante non riuscita")
                continue
            if esito is not None:
                fatte.append(esito)
        if fatte:
            self.svuota()
        return fatte


libreria_odio = LibreriaOdio()
