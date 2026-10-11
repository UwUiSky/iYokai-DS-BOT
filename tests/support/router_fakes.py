"""
tests/support/router_fakes.py
=============================
Repository finto del router dei canali (NF-01) per i test dei log che non
usano il database: nessuna scelta per tipo, nessun avviso già mandato.
"""

from unittest.mock import create_autospec

import core.channel_router as router
from core.repositories.output_channel_repo import OutputChannelRepository


def router_senza_scelte(monkeypatch):
    finto = create_autospec(OutputChannelRepository, instance=True)
    finto.ottieni.return_value = None
    finto.elenco.return_value = []
    finto.segna_avvisato.return_value = True
    monkeypatch.setattr(router, "output_channel_repo", finto)
    router._avvisati.clear()
    return finto
