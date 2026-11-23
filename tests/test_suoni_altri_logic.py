"""FUN-075 (D127, D129): suoni di altri server: scelta dei candidati, origine pubblica, pausa e tetto per persona."""
from core import suoni_altri_logic as L


def _s(i, nome, g, pubblico=False, emoji=None):
    return L.SuonoAltro(i, nome, emoji, g, f"Server {g}", pubblico)


def test_solo_i_suoni_dei_server_che_li_condividono_e_non_i_propri():
    suoni = [_s(1, "Boom", 10), _s(2, "Bip", 20), _s(3, "Bop", 30), _s(4, "Mio", 99)]
    assert [s.id for s in L.candidati(suoni, 99, {10, 99, 30})] == [1, 3]  # il proprio server non conta, 20 non condivide
    assert L.candidati(suoni, 99, set()) == []  # di base nessuno: serve la scelta del server d'origine
    assert [s.id for s in L.candidati(suoni, 99, {10, 20, 30}, "BO")] == [1, 3]


def test_il_menu_ha_al_massimo_25_voci_in_ordine_di_nome():
    suoni = [_s(i, f"s{i:02d}", 10) for i in range(40)]
    scelti = L.candidati(suoni, 1, {10})
    assert len(scelti) == 25 and scelti[0].nome == "s00"


def test_il_server_d_origine_si_dice_solo_se_e_pubblico():
    assert _s(1, "a", 10, pubblico=True).origine() == "Server 10"
    assert _s(1, "a", 10, pubblico=False).origine() is None
    assert L.server_pubblico(["COMMUNITY", "DISCOVERABLE"]) and not L.server_pubblico(["COMMUNITY"]) and not L.server_pubblico([])


def test_valore_e_trova():
    s = _s(7, "x", 10, emoji="🔊")
    assert s.valore == "10:7" and s.etichetta == "🔊 x"
    assert L.trova([s], "10:7") is s and L.trova([s], "11:7") is None and L.trova([s], "") is None


def test_pausa_e_tetto_orario_per_persona():
    t = [0.0]
    tetto = L.TettoPersona(pausa=15, massimo=3, orologio=lambda: t[0])
    assert tetto.controlla(5) is None
    tetto.segna(5)
    assert tetto.controlla(5) == ("pausa", 15.0) and tetto.controlla(6) is None
    for quando in (16, 32):
        t[0] = quando
        assert tetto.controlla(5) is None
        tetto.segna(5)
    t[0] = 50
    motivo, resta = tetto.controlla(5)
    assert motivo == "ora" and resta == 3600 - 50
    t[0] = 3601
    assert tetto.controlla(5) is None
