"""
tests/test_log_coda.py
======================
I log vanno su disco da un thread a parte: chi scrive non aspetta il disco e una coda piena non ferma il bot.
Funzioni coperte: consiglio 25/11/2026, seri di stabilità (blocco C)
"""

from __future__ import annotations

import logging
import queue
import threading
import time

import pytest

from core import log_coda


@pytest.fixture(autouse=True)
def _ripristina_log():
    radice = logging.getLogger()
    prima = list(radice.handlers), radice.level
    yield
    log_coda.ferma_log_in_coda()
    radice.handlers[:] = prima[0]
    radice.setLevel(prima[1])


class _DiscoLento(logging.Handler):
    """Un handler che scrive piano e ricorda in quale thread lo fa."""

    def __init__(self, pausa=0.0):
        super().__init__()
        self.righe: list[str] = []
        self.thread: set[str] = set()
        self.pausa = pausa

    def emit(self, record):
        time.sleep(self.pausa)
        self.thread.add(threading.current_thread().name)
        self.righe.append(record.getMessage())


def test_la_scrittura_avviene_in_un_altro_thread_e_chi_logga_non_aspetta_il_disco():
    disco = _DiscoLento(pausa=0.05)
    log_coda.avvia_log_in_coda([disco], logging.INFO)
    inizio = time.monotonic()
    for i in range(20):
        logging.getLogger("prova").info("riga %d", i)
    assert time.monotonic() - inizio < 0.5  # 20 righe da 50 ms sul disco = 1 s: qui nessuno aspetta
    log_coda.ferma_log_in_coda()  # scrive quello che resta in coda
    assert len(disco.righe) == 20
    assert threading.current_thread().name not in disco.thread


def test_con_la_coda_piena_si_scarta_e_si_conta_senza_bloccare():
    disco = _DiscoLento(pausa=0.2)
    gestore = log_coda.avvia_log_in_coda([disco], logging.INFO, tetto=3)
    inizio = time.monotonic()
    for i in range(50):
        logging.getLogger("prova").info("riga %d", i)
    assert time.monotonic() - inizio < 0.5
    assert gestore.scartati > 0
    log_coda.ferma_log_in_coda()


def test_l_eccezione_nel_log_arriva_intera_al_file():
    disco = _DiscoLento()
    log_coda.avvia_log_in_coda([disco], logging.INFO)
    try:
        raise ValueError("guasto")
    except ValueError:
        logging.getLogger("prova").exception("Errore vero")
    log_coda.ferma_log_in_coda()
    assert disco.righe and "Errore vero" in disco.righe[0]


def test_main_mette_console_e_file_dietro_la_coda(tmp_path, monkeypatch):
    import main

    main.setup_logging()
    try:
        radice = logging.getLogger()
        assert len(radice.handlers) == 1 and isinstance(radice.handlers[0], log_coda.CodaLimitata)
    finally:
        log_coda.ferma_log_in_coda()
