"""Logica pura delle voci piccole di /fun (FUN-023..048, 058..061)."""
import io
import random

import pytest
from PIL import Image

from core.fun_extra_logic import (
    STILI_TESTO,
    argomento,
    consiglio,
    google_link,
    lancia_oggetto,
    numero_casuale,
    oggetto_magico,
    preferiresti,
    presa_in_giro,
    scegli_tra,
    tira_formula,
    trasforma_testo,
)
from core.image_effects_logic import effetto_arcobaleno, effetto_rip, effetto_ricercato, effetto_triggered


def _png(w=64, h=64):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


def test_formula_dado_base_e_modificatore():
    rng = random.Random(1)
    r = tira_formula("3d6+2", rng)
    assert r.errore is None and len(r.tiri) == 3 and r.totale == sum(r.tiri) + 2
    r = tira_formula("d20-1", rng)
    assert len(r.tiri) == 1 and r.totale == r.tiri[0] - 1


@pytest.mark.parametrize("f", ["", "abc", "0d6", "21d6", "2d1", "2d1001", "3d6+99999", "3d6;"])
def test_formula_dado_rifiuta_valori_fuori_limite(f):
    assert tira_formula(f, random.Random(1)).errore


def test_scegli_tra_separa_e_limita():
    rng = random.Random(2)
    assert scegli_tra("pizza, sushi ; kebab | pasta", rng).scelta in {"pizza", "sushi", "kebab", "pasta"}
    assert scegli_tra("solo una", rng).errore
    assert scegli_tra(",".join(str(i) for i in range(30)), rng).errore  # tetto 20


def test_numero_casuale_estremi():
    rng = random.Random(3)
    assert 5 <= numero_casuale(5, 9, rng) <= 9
    assert numero_casuale(9, 5, rng) is None


def test_stili_testo_conosciuti():
    assert trasforma_testo("largo", "Ab 1") == "Ａｂ　１"
    assert trasforma_testo("doppio", "Hi") == "ℍ𝕚"           # buco di H
    assert trasforma_testo("corsivo", "eB") == "ℯℬ"          # buchi dello script
    assert trasforma_testo("gotico", "C") == "ℭ"
    assert trasforma_testo("corsivo-grassetto", "a") == "𝒂"
    assert trasforma_testo("gotico-grassetto", "a") == "𝖆"
    assert trasforma_testo("maiuscoletto", "ciao") == "ᴄɪᴀᴏ"
    assert trasforma_testo("emoji", "a1") == "🇦 1️⃣"
    assert trasforma_testo("applauso", "uno due tre") == "uno 👏 due 👏 tre"
    assert trasforma_testo("separato", "uno due", separatore="-") == "uno-due"
    assert trasforma_testo("owo", "ciao raro") .endswith("owo")
    assert set(STILI_TESTO) >= {"largo", "corsivo", "corsivo-grassetto", "gotico", "gotico-grassetto",
                                "doppio", "maiuscoletto", "emoji", "applauso", "separato", "owo"}


def test_testo_lungo_tagliato_a_2000():
    assert len(trasforma_testo("emoji", "a" * 1500)) <= 2000


def test_contenuti_casuali_non_vuoti():
    rng = random.Random(4)
    for f in (preferiresti, argomento, consiglio, oggetto_magico):
        assert f(rng).strip()
    assert "@" not in lancia_oggetto(rng)
    assert presa_in_giro(rng)


def test_google_link_codifica():
    assert google_link("come si fa? a&b") == "https://www.google.com/search?q=come+si+fa%3F+a%26b"


@pytest.mark.parametrize("fn", [effetto_arcobaleno, effetto_rip, effetto_ricercato, effetto_triggered])
def test_effetti_immagine(fn):
    out = fn(_png(), "Mario") if fn in (effetto_rip, effetto_ricercato) else fn(_png())
    assert out and Image.open(io.BytesIO(out)).size[0] > 0
    assert fn(b"non-un-immagine", "x") is None if fn in (effetto_rip, effetto_ricercato) else fn(b"no") is None
