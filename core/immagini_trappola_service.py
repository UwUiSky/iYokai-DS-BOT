"""
core/immagini_trappola_service.py
=================================
Libreria delle immagini trappola vista dal filtro (D62): ricerca per SHA-256 e per impronta
percettiva, segnalazione, scelte dell'owner del bot. Le liste per l'impronta stanno in cache breve;
`versione` cresce a ogni cambio che puo' cambiare un verdetto (la usa la cache del filtro).
Un database fermo non ferma mai il filtro: la ricerca da' «non trovata».
Funzioni coperte: SPEC §6 (D62)
Dipende da: core/repositories/immagini_trappola_repo.py
"""

from __future__ import annotations

import logging
import time

from core import immagini_trappola_logic as lg
from core.immagini_trappola_logic import Trovata, Voce
from core.repositories.immagini_trappola_repo import immagini_trappola_repo

logger = logging.getLogger("iyokai.immagini.trappola")

DURATA_CACHE = 300.0
MAX_SERVER_IN_CACHE = 2000


class LibreriaImmagini:
    def __init__(self, repo=None) -> None:
        self.repo = repo or immagini_trappola_repo
        self._globali: tuple[float, list[Voce]] = (0.0, [])
        self._server: dict[int, tuple[float, list[Voce]]] = {}
        self.versione = 0

    def svuota(self) -> None:
        self._globali = (0.0, [])
        self._server.clear()

    async def cerca_sha(self, sha256: str, guild_id: int) -> Voce | None:
        try:
            return await self.repo.valida_per_server(sha256, guild_id)
        except Exception:
            logger.warning("Libreria immagini non leggibile", exc_info=True)
            return None

    async def _liste(self, guild_id: int) -> list[Voce]:
        adesso = time.monotonic()
        scade, globali = self._globali
        if adesso >= scade:
            try:
                globali = await self.repo.globali()
            except Exception:
                logger.warning("Libreria immagini non leggibile", exc_info=True)
                self._globali = (adesso + 30, globali)
                return list(globali)
            self._globali = (adesso + DURATA_CACHE, globali)
        scade_s, locali = self._server.get(guild_id, (0.0, []))
        if adesso >= scade_s:
            try:
                locali = await self.repo.del_server(guild_id)
            except Exception:
                logger.warning("Candidate immagini non leggibili", exc_info=True)
                return list(globali)
            if len(self._server) >= MAX_SERVER_IN_CACHE:
                self._server.clear()
            self._server[guild_id] = (adesso + DURATA_CACHE, locali)
        return list(globali) + list(locali)

    async def cerca_impronta(self, dhash: int, guild_id: int) -> Trovata | None:
        return lg.trova_per_impronta(dhash, await self._liste(guild_id))

    async def segnala(
        self, sha256: str, dhash: int | None, motivo: str, guild_id: int, owner_id: int | None, membri: int
    ) -> Voce | None:
        """Un server segnala. Sotto i 25 membri il server segnala per se' ma non conta per la soglia. Non solleva mai."""
        try:
            conta_come = owner_id if membri >= lg.MIN_MEMBRI_PER_CONTARE else None
            esito = await self.repo.segnala(sha256, dhash, motivo, guild_id, conta_come)
        except Exception:
            logger.exception("Segnalazione dell'immagine non riuscita")
            return None
        self.svuota()
        if esito is not None and esito.stato in lg.STATI_GLOBALI:
            self.versione += 1
        return esito

    async def aggiungi(self, sha256: str, dhash: int | None, motivo: str) -> None:
        await self.repo.aggiungi(sha256, dhash, motivo)
        self.svuota()
        self.versione += 1

    async def imposta_stato(self, riferimento: str, stato: str) -> str:
        """`ok`, `non_valido` (impronta o prefisso illeggibili), `assente` o `ambiguo`."""
        sha = lg.sha_valido(riferimento)
        if sha is None:
            prefisso = lg.prefisso_valido(riferimento)
            if prefisso is None:
                return "non_valido"
            trovate = await self.repo.per_prefisso(prefisso)
            if not trovate:
                return "assente"
            if len(trovate) > 1:
                return "ambiguo"
            sha = trovate[0]
        if not await self.repo.imposta_stato(sha, stato):
            return "assente"
        self.svuota()
        self.versione += 1
        return "ok"

    async def elenca(self, stato: str, limite: int = 25) -> list[Voce]:
        return await self.repo.elenca(stato, limite)

    async def conta(self) -> dict[str, int]:
        return await self.repo.conta()


libreria_immagini = LibreriaImmagini()
