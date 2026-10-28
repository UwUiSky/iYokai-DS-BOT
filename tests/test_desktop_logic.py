"""
tests/test_desktop_logic.py
===========================
SPEC D.1, D.5, D.6 (#108): token personale, parole chiave, chi avvisare, link al messaggio.
"""

import pytest

from core import desktop_logic as dl


def test_token_nuovo_e_impronta():
    a, b = dl.nuovo_token(), dl.nuovo_token()
    assert a != b and dl.token_ben_formato(a)
    assert len(dl.impronta(a)) == 64 and dl.impronta(a) != a and dl.impronta(a) == dl.impronta(a)


@pytest.mark.parametrize("brutto", [None, "", "dsk_corto", "xxx_" + "a" * 43, "dsk_" + "a" * 44, "dsk_" + "a" * 42 + "!"])
def test_token_mal_formato(brutto):
    assert not dl.token_ben_formato(brutto)


def test_token_dall_intestazione():
    t = dl.nuovo_token()
    assert dl.token_dall_intestazione(f"Bearer {t}") == t and dl.token_dall_intestazione(f"bearer  {t} ") == t
    for no in (None, "", t, f"Basic {t}", "Bearer abc"):
        assert dl.token_dall_intestazione(no) is None


def test_parole_chiave():
    assert dl.normalizza_parole("Ciao, ciao\n  Il  Mio Nome ,") == ["ciao", "il mio nome"]
    assert dl.normalizza_parole("") == []
    for storto in ("a", "x" * 31):
        with pytest.raises(dl.ErroreDesktop) as e:
            dl.normalizza_parole(storto)
        assert e.value.chiave == "app_desktop_parola_non_valida"
    with pytest.raises(dl.ErroreDesktop) as e:
        dl.normalizza_parole(",".join(f"parola{i}" for i in range(11)))
    assert e.value.chiave == "app_desktop_troppe_parole"


def test_testo_breve_e_link():
    assert dl.testo_breve("a\n  b") == "a b"
    lungo = dl.testo_breve("x" * 500)
    assert len(lungo) == dl.MAX_TESTO_EVENTO and lungo.endswith("…")
    assert dl.link_messaggio(1, 2, 3) == "https://discord.com/channels/1/2/3"
    assert dl.link_messaggio(None, 2, 3) == "https://discord.com/channels/@me/2/3"


def _chi(**kw):
    base = dict(autore_id=1, contenuto="", menzionati=(), risposta_a=None, attivi={10: [], 11: ["ciao"]}, vede=lambda u: True)
    base.update(kw)
    return dl.chi_avvisare(**base)


def test_chi_avvisare_menzione_risposta_parola():
    assert _chi(menzionati=(10, 99)) == {10: "menzione"}
    assert _chi(risposta_a=10) == {10: "risposta"}
    assert _chi(menzionati=(10,), risposta_a=10) == {10: "risposta"}
    assert _chi(contenuto="Ciao a tutti") == {11: "parola"}
    assert _chi(contenuto="ciaone") == {}  # parola intera, non un pezzo
    assert _chi(menzionati=(11,), contenuto="ciao") == {11: "menzione"}


def test_chi_avvisare_mai_se_stessi_e_solo_chi_vede():
    assert _chi(autore_id=10, menzionati=(10,)) == {}
    assert _chi(menzionati=(10, 11), vede=lambda u: u == 11) == {11: "menzione"}
    assert _chi(attivi={}, menzionati=(10,)) == {}
