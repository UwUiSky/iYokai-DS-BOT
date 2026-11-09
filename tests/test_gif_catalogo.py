"""Catalogo delle GIF di reazione e azione (FUN-081..135) e limiti di Discord del completamento (#131)."""
import json

from core import gif_catalogo as c
from core.gif_fonti import FONTI
from core.i18n import percorso_testi, t


def test_il_catalogo_copre_tutte_le_voci_081_135():
    ids = sorted(v.fun for v in c.tutte())
    assert ids == [f"FUN-{n:03d}" for n in range(81, 136)]
    assert len(c.voci("reazione")) == 29 and len(c.voci("azione")) == 26
    assert len({v.id for v in c.tutte()}) == 55


def test_nomi_e_id_nei_limiti_per_ogni_lingua():
    for v in c.tutte():
        assert 1 <= len(v.id) <= 32 and v.id == v.id.lower() and " " not in v.id
        assert {"it", "en"} <= set(v.nomi)
        for nome in [*v.nomi.values(), *v.sinonimi]:
            assert 1 <= len(nome) <= 32, (v.id, nome)
        assert set(v.fonti) <= set(FONTI)


def test_ogni_voce_ha_la_frase_nelle_due_lingue_e_l_azione_ha_il_bersaglio():
    for v in c.tutte():
        for lingua in ("it", "en"):
            frase = t(v.chiave_frase, lingua, autore="A", bersaglio="B")
            assert frase != v.chiave_frase and "{" not in frase, (v.id, lingua)
            assert ("B" in frase) == (v.tipo == "azione"), (v.id, lingua)


def test_testi_gif_uguali_nelle_due_lingue():
    it = json.loads(percorso_testi("it").read_text(encoding="utf-8"))
    en = json.loads(percorso_testi("en-US").read_text(encoding="utf-8"))
    assert {k for k in it if k.startswith("gif_")} == {k for k in en if k.startswith("gif_")}


def test_completamento_al_massimo_25_con_nome_e_valore_nei_limiti():
    for tipo in c.TIPI:
        for digitato in ("", "a", "e", "zzz", "x" * 300, "  "):
            r = c.suggerimenti(tipo, digitato, "it")
            assert len(r) <= 25
            assert all(1 <= len(n) <= 100 and 1 <= len(v) <= 100 for n, v in r)
    assert len(c.suggerimenti("reazione", "")) == 25  # 29 reazioni: il tetto taglia


def test_completamento_per_inizio_poi_contenuto_e_sinonimi():
    nomi = [n for n, _ in c.suggerimenti("azione", "abb", "it")]
    assert nomi == ["Abbraccia"]
    assert ("Abbraccia", "abbraccia") in c.suggerimenti("azione", "hug", "it")
    assert c.suggerimenti("azione", "zzzz") == []
    assert c.suggerimenti("azione", "ABBR")[0][1] == "abbraccia"


def test_trova_riconvalida_il_valore_scritto_a_mano():
    assert c.trova("azione", "Abbraccia").id == "abbraccia"
    assert c.trova("azione", "hug") is None or c.trova("azione", "hug").id == "abbraccia"
    assert c.trova("azione", "piange") is None  # è una reazione
    assert c.trova("reazione", "piange").id == "piange"
    assert c.trova("reazione", "") is None and c.trova("reazione", "inventata") is None
