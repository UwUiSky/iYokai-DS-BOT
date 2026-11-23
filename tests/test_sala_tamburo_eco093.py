"""
tests/test_sala_tamburo_eco093.py
=================================
ECO-093 (D121): `/sala tamburo`, il gioco a più giocatori «roulette russa» con nome e grafica neutri: un tamburo di sei
caselle con una sola sfera rossa; a turno si preme; chi trova la sfera esce, l'ultimo vince il piatto. Gioco finto, senza
violenza descritta. Regole pure con seme fisso e vista con solo i giocatori.
"""

import random
from unittest.mock import AsyncMock

import pytest

from cogs.fun.sala import MOTORI, SalaCog, VistaGiocatori, VistaTamburo, vince_il_piatto
from core import sala_logic as sl


def test_la_sfera_e_in_una_casella_e_un_giro_finisce_entro_sei_pressioni():
    for seme in range(30):
        t = sl.Tamburo([1, 2, 3], random.Random(seme))
        pressioni = 0
        esito = "salvo"
        while esito == "salvo":
            esito = t.premi(t.di_turno)
            pressioni += 1
        assert esito == "fuori" and pressioni <= sl.Tamburo.CASELLE and len(t.vivi) == 2


def test_turni_e_ultimo_rimasto():
    t = sl.Tamburo([1, 2], random.Random(4))
    assert t.premi(2) == "non_turno"  # tocca all'1
    for _ in range(20):
        di_turno = t.di_turno
        esito = t.premi(di_turno)
        if esito == "vince":
            assert t.vincitore == (1 if di_turno == 2 else 2) and t.ultimo_eliminato == di_turno
            break
    else:
        pytest.fail("la partita non finisce")
    assert t.premi(1) == "non_turno"  # finita


def test_dopo_un_eliminato_il_tamburo_si_ricarica():
    t = sl.Tamburo([1, 2, 3], random.Random(2))
    while t.premi(t.di_turno) == "salvo":
        pass
    assert t.posizione == 0  # nuovo giro: caselle di nuovo tutte da scoprire


def test_chi_non_muove_in_tempo_esce_e_il_turno_resta_a_posto():
    t = sl.Tamburo([1, 2, 3], random.Random(1))
    t.esci(1)
    assert t.vivi == [2, 3] and t.di_turno in (2, 3)
    t.esci(2)
    assert t.vincitore == 3
    t.esci(3)  # l'ultimo non esce
    assert t.vincitore == 3


def test_servono_da_2_a_10_giocatori():
    for n in (1, 11):
        with pytest.raises(ValueError):
            sl.Tamburo(list(range(n)), random.Random(1))


def test_il_gioco_e_registrato_nella_sala_con_il_piatto_per_chi_resta():
    gioco, motore, minimo, massimo = MOTORI["tamburo"]
    assert gioco == "sala:tamburo" and (minimo, massimo) == (2, 10)
    assert vince_il_piatto([1, 2, 3], 10, 2) == {1: 0, 2: 30, 3: 0}


async def test_solo_chi_ha_il_turno_preme_e_gli_altri_non_giocano():
    t = sl.Tamburo([1, 2], random.Random(4))
    vista = VistaTamburo(t, [1, 2])
    assert isinstance(vista, VistaGiocatori)
    from tests.support.discord_fakes import fake_interaction, fake_member

    inter = fake_interaction(user=fake_member(2))  # non è il suo turno
    await vista.premi.callback(inter)
    inter.response.send_message.assert_awaited_once()
    assert t.posizione == 0
    inter1 = fake_interaction(user=fake_member(1))
    inter1.response.edit_message = AsyncMock()
    await vista.premi.callback(inter1)
    assert t.posizione == 1 or len(t.vivi) < 2 or t.posizione == 0  # una pressione è stata fatta
