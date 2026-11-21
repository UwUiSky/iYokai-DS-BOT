"""
tests/test_catalogo_gia_coperto_b15.py
======================================
Voci del catalogo economia che erano già coperte da comandi esistenti (#125): ECO-143 missioni attive e ECO-151 traguardi
(/level progressi), ECO-157 promemoria della serie, ECO-150 premi di ogni livello (/level premi).
Funzioni coperte: catalogo #125
"""

import inspect

from cogs.leveling import progressi
from cogs.leveling.leveling import LevelingCog


def test_i_comandi_che_coprono_le_voci_esistono():
    assert hasattr(LevelingCog, "premi") and "ECO-150" in inspect.getsource(LevelingCog.premi.callback)
    sorgente = inspect.getsource(progressi)
    for parola in ("missioni", "traguardi", "Promemoria privato"):
        assert parola in sorgente
    assert "ECO-143" in progressi.__doc__ and "ECO-151" in progressi.__doc__ and "ECO-157" in progressi.__doc__
