"""
core/music_fleet.py
=======================
Gestore della flotta Music (SPEC.md §9.1/9.2). Il bot principale non
entra MAI in vocale per /play — instrada verso una delle 5 istanze
worker (client Discord separati con il proprio token, connessi allo
stesso Pool Lavalink condiviso — verificato prima di scrivere questo
file: wavelink.Pool è un singleton di processo, ogni Player si lega
al client Discord che lo crea, non serve una connessione Lavalink
separata per bot). Un solo processo Python con 6 connessioni gateway
concorrenti (1 principale + 5 worker), non 6 processi separati — per
non moltiplicare 6 volte l'overhead di interprete su una VM già
limitata.
"""

from __future__ import annotations

from discord.ext import commands

from core.music_fleet_logic import TOTAL_WORKERS, find_free_worker
from core.repositories.music_session_repo import music_session_repo


class MusicFleet:
    def __init__(self, worker_bots: list[commands.Bot]) -> None:
        if len(worker_bots) != TOTAL_WORKERS:
            raise ValueError(
                f"Attesi {TOTAL_WORKERS} bot worker, ricevuti {len(worker_bots)}."
            )
        self._worker_bots = worker_bots

    def get_worker_bot(self, worker_index: int) -> commands.Bot:
        """worker_index è 1-based (worker 1..5) — coerente con
        core/music_fleet_logic.find_free_worker() e la colonna
        worker_index della tabella music_sessions."""
        return self._worker_bots[worker_index - 1]

    async def get_worker_for_guild(self, guild_id: int) -> tuple[int, commands.Bot] | None:
        """
        Sola lettura — la sessione già assegnata a questo server, se
        esiste, SENZA assegnarne una nuova. Usata dai comandi che
        agiscono su una riproduzione già in corso (skip, stop, queue,
        ecc.): se nessun worker è assegnato, quei comandi devono
        fallire pulitamente ("nessuna riproduzione in corso"), non
        avviare per sbaglio una sessione nuova su un worker libero.
        """
        worker_index = await music_session_repo.get_worker_for_guild(guild_id)
        if worker_index is None:
            return None
        return worker_index, self.get_worker_bot(worker_index)

    async def get_or_assign_worker_for_guild(
        self, guild_id: int
    ) -> tuple[int, commands.Bot] | None:
        """
        La sessione già assegnata a questo server, se esiste — così
        un secondo /play nello stesso server non salta a un worker
        diverso a caso. Altrimenti il primo worker libero, assegnato
        e registrato subito. None se tutti e 5 sono occupati altrove
        in questo momento.
        """
        worker_index = await music_session_repo.get_worker_for_guild(guild_id)
        if worker_index is not None:
            return worker_index, self.get_worker_bot(worker_index)

        occupati = await music_session_repo.get_occupied_workers()
        libero = find_free_worker(occupati)
        if libero is None:
            return None

        await music_session_repo.assign_worker(guild_id, libero)
        return libero, self.get_worker_bot(libero)

    async def release_guild(self, guild_id: int) -> None:
        """Chiamata quando una sessione finisce (es. /disconnect) —
        libera il worker per il prossimo server che ne ha bisogno."""
        await music_session_repo.release_guild(guild_id)
