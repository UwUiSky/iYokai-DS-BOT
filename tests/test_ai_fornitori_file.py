"""
tests/test_ai_fornitori_file.py
===============================
Il file di esempio dei servizi AI gratuiti (D54, D55) si legge senza errori: ogni modello ha
indirizzo, tipi, fascia e dichiarazione sull'addestramento; nessuna chiave è scritta nel file.
"""

from pathlib import Path

from dotenv import dotenv_values

from core.ai_providers import FASCE, TIPI, leggi_fornitori
from tests.support.ai_finto import chiave_finta

ESEMPIO = Path(__file__).resolve().parent.parent / "config" / "ai_fornitori.env.example"


def _valori() -> dict[str, str]:
    return {k: (v or "") for k, v in dotenv_values(ESEMPIO).items()}


def test_nessuna_chiave_nel_file_di_esempio():
    chiavi = {k: v for k, v in _valori().items() if k.startswith("AI_KEY_") and v}
    assert chiavi == {}


def test_senza_chiavi_nessun_fornitore_e_solo_chiavi_mancanti():
    fornitori, scarti = leggi_fornitori(_valori())
    assert fornitori == []
    assert scarti and all("manca AI_KEY_" in s for s in scarti)


def test_con_le_chiavi_tutti_i_fornitori_elencati_si_leggono():
    env = _valori()
    for nome in env["AI_FORNITORI"].split(","):
        env[f"AI_KEY_{nome.upper().split('_')[0]}"] = chiave_finta(nome)
    fornitori, scarti = leggi_fornitori(env)
    assert scarti == []
    assert len(fornitori) == len(env["AI_FORNITORI"].split(","))
    for f in fornitori:
        assert f.url.startswith("https://") and f.modello
        assert f.tipi and f.tipi <= set(TIPI) and f.fascia in FASCE
        assert not f.a_pagamento and f.costo_cent_milione == 0
    assert any(f.addestra for f in fornitori) and any(not f.addestra for f in fornitori)


def test_ogni_blocco_dichiara_l_addestramento_e_nessun_pagamento():
    env = _valori()
    nomi = [k[len("AI_MODELLO_"):] for k in env if k.startswith("AI_MODELLO_") and not k.startswith("AI_MODELLO_IMMAGINI_")]
    assert len(nomi) >= 25
    for n in nomi:
        assert env[f"AI_ADDESTRA_{n}"] in ("si", "no"), n
        assert env[f"AI_PAGAMENTO_{n}"] == "no" and env[f"AI_COSTO_{n}"] == "0", n


def test_il_file_vero_e_fuori_dal_repository():
    ignorati = (Path(__file__).resolve().parent.parent / ".gitignore").read_text(encoding="utf-8")
    assert "config/ai_fornitori.env" in ignorati.splitlines()
