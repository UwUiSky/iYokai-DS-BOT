"""
tests/support/flotta_finta.py
=============================
Base per le flotte musicali finte dei test: ha la `sessione` VERA di `MusicFleet` (rilascio dello slot a
ogni uscita), così i test provano anche quel percorso. La flotta finta aggiunge i suoi metodi sopra.
"""

from core.music_fleet import MusicFleet


class FlottaFinta:
    sessione = MusicFleet.sessione

    def indice_di(self, worker_bot):
        return getattr(worker_bot, "worker_index", None)
