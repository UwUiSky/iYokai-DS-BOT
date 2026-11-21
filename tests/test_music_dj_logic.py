"""
tests/test_music_dj_logic.py
============================
MUS-051 (ruolo e modalità DJ), MUS-052 (voto per saltare), MUS-034 (posizione «mm:ss»): logica pura.
"""

from types import SimpleNamespace

from core.music_dj_logic import (
    VotiSalto, e_privilegiato, parse_posizione, puo_comandare, puo_toccare_brano, voti_necessari,
)
from core.music_settings_logic import MusicSettings, summary_lines


def _s(**kw):
    return MusicSettings(**kw)


def test_modalita_spenta_tutti_comandano():
    assert puo_comandare(_s(), 1, [], False, [1, 2])


def test_modalita_accesa_solo_dj_staff_o_da_soli():
    s = _s(dj_mode=True, dj_role_id=50)
    assert not puo_comandare(s, 1, [7], False, [1, 2])
    assert puo_comandare(s, 1, [50], False, [1, 2])  # DJ
    assert puo_comandare(s, 1, [], True, [1, 2])  # staff
    assert puo_comandare(s, 1, [], False, [1])  # da solo con il bot
    assert not puo_comandare(s, 1, [], False, [2])  # non è lui il solo presente


def test_senza_ruolo_dj_conta_solo_lo_staff():
    s = _s(dj_mode=True)
    assert not e_privilegiato(s, 1, [50], False, [1, 2])


def test_brano_proprio_o_privilegiato():
    assert puo_toccare_brano(False, 5, 5)
    assert not puo_toccare_brano(False, 6, 5)
    assert not puo_toccare_brano(False, None, 5)
    assert puo_toccare_brano(True, 6, 5)


def test_voti_necessari_arrotonda_in_su_e_mai_zero():
    assert voti_necessari(50, 4) == 2
    assert voti_necessari(50, 3) == 2
    assert voti_necessari(50, 0) == 1
    assert voti_necessari(100, 5) == 5
    assert voti_necessari(500, 4) == 4  # tetto 100%
    

def test_un_voto_per_persona_e_solo_chi_e_nel_canale():
    v = VotiSalto()
    umani = [1, 2, 3, 4]
    e = v.vota("a", 1, umani, 50, adesso=1)
    assert (e.gia_votato, e.voti, e.necessari, e.raggiunto) == (False, 1, 2, False)
    e = v.vota("a", 1, umani, 50, adesso=2)
    assert e.gia_votato and e.voti == 1
    e = v.vota("a", 9, umani, 50, adesso=3)  # non è nel canale
    assert e.voti == 1 and not e.raggiunto
    e = v.vota("a", 2, umani, 50, adesso=4)
    assert e.raggiunto


def test_chi_esce_dal_canale_perde_il_voto_e_il_brano_nuovo_azzera():
    v = VotiSalto()
    v.vota("a", 1, [1, 2, 3, 4], 75, adesso=1)
    assert v.vota("a", 2, [2, 3, 4], 75, adesso=2).voti == 1  # il voto di 1 non vale più
    assert v.vota("b", 2, [2, 3], 50, adesso=3).voti == 1  # brano diverso: si riparte


def test_i_voti_scadono():
    v = VotiSalto()
    v.vota("a", 1, [1, 2], 100, adesso=0)
    assert v.vota("a", 2, [1, 2], 100, adesso=100000).voti == 1


def test_posizione_assoluta_e_relativa():
    d = 200_000
    assert parse_posizione("1:30", 0, d) == 90_000
    assert parse_posizione("90", 0, d) == 90_000
    assert parse_posizione("0:01:05", 0, d) == 65_000
    assert parse_posizione("+0:30", 60_000, d) == 90_000
    assert parse_posizione("-0:30", 60_000, d) == 30_000
    assert parse_posizione("-5:00", 60_000, d) == 0
    assert parse_posizione("99:00", 0, d) == 199_000  # tagliato alla fine
    for brutto in ("", "abc", "1:99", "1::2", "1:2:3:4", "-", "١٢", "1" * 20):
        assert parse_posizione(brutto, 0, d) is None


def test_riepilogo_ha_le_righe_dj_e_voto():
    righe = "\n".join(summary_lines(_s(dj_mode=True, dj_role_id=5, skip_vote_percent=60)))
    assert "accesa" in righe and "<@&5>" in righe and "60%" in righe
