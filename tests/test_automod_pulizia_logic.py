"""
tests/test_automod_pulizia_logic.py
===================================
Pulizia di un canale ogni tanto (AMD-073) e per tipo di messaggio (AMD-074): intervallo, tipi, scelta dei
messaggi, divisione fra cancellazione in blocco e una per una, limiti di Discord.
"""

import pytest

from core import automod_pulizia_logic as lg

GIORNO = 86400


def test_intervallo_si_legge_con_unita():
    assert lg.leggi_ogni("6h") == 6 * 3600
    assert lg.leggi_ogni(" 2D ") == 2 * GIORNO
    assert lg.leggi_ogni("90m") == 5400
    assert lg.leggi_ogni("1h30m") == 5400


@pytest.mark.parametrize("testo", ["", "abc", "30s", "59m", "31d", "0h", "-5h", "1.5h", "6", "h6", "99999999999d"])
def test_intervallo_non_valido(testo):
    with pytest.raises(lg.PuliziaNonValida):
        lg.leggi_ogni(testo)


def test_scrive_l_intervallo_in_modo_leggibile():
    assert lg.scrivi_ogni(5400) == "1h30m"
    assert lg.scrivi_ogni(2 * GIORNO) == "2d"
    assert lg.scrivi_ogni(6 * 3600) == "6h"


@pytest.mark.parametrize("tipo, bot, testo, allegati, atteso", [
    ("persone", False, "ciao", 0, True), ("persone", True, "ciao", 0, False),
    ("bot", True, "ciao", 0, True), ("bot", False, "ciao", 0, False),
    ("tutti", True, "x", 0, True), ("tutti", False, "", 0, True),
    ("link", False, "guarda https://esempio.it/a", 0, True), ("link", False, "senza", 0, False),
    ("inviti", False, "entra discord.gg/abcdef", 0, True), ("inviti", False, "https://esempio.it", 0, False),
    ("allegati", False, "", 2, True), ("allegati", False, "testo", 0, False),
])
def test_tipi_di_messaggio(tipo, bot, testo, allegati, atteso):
    assert lg.corrisponde(tipo, e_bot=bot, testo=testo, allegati=allegati) is atteso


def test_tipo_sconosciuto_non_corrisponde_mai():
    assert lg.corrisponde("inventato", e_bot=False, testo="x", allegati=0) is False


def test_messaggi_fissati_restano_salvo_scelta():
    assert lg.da_cancellare(fissato=True, incluso_fissati=False) is False
    assert lg.da_cancellare(fissato=True, incluso_fissati=True) is True
    assert lg.da_cancellare(fissato=False, incluso_fissati=False) is True


def test_divisione_blocco_e_uno_per_uno():
    # (id, età in giorni): quelli sotto i 14 giorni (con margine) vanno in blocco, gli altri uno per uno
    voci = [(i, 1) for i in range(250)] + [(1000 + i, 20) for i in range(150)]
    blocchi, singoli = lg.dividi(voci)
    assert [len(b) for b in blocchi] == [100, 100, 50]
    assert len(singoli) == lg.MAX_SINGOLI == 100  # tetto per giro


def test_un_blocco_da_un_solo_messaggio_diventa_singolo():
    blocchi, singoli = lg.dividi([(1, 1), (2, 1), (3, 1), (9, 30)])
    assert blocchi == [[1, 2, 3]] and singoli == [9]
    blocchi, singoli = lg.dividi([(1, 1)] * 1 + [(9, 30)])
    assert blocchi == [] and sorted(singoli) == [1, 9]


def test_il_margine_dei_14_giorni():
    blocchi, singoli = lg.dividi([(1, 13.8), (2, 13.8), (3, 13.95), (4, 14.0)])
    assert blocchi == [[1, 2]] and singoli == [3, 4]


def test_dopo_tre_403_ci_si_ferma():
    s = lg.Esito()
    assert not s.fermo
    s.vieta(); s.vieta()
    assert not s.fermo
    s.vieta()
    assert s.fermo
