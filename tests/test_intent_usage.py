"""
tests/test_intent_usage.py
==========================
SPEC §19.8: l'elenco degli usi degli intent privilegiati è completo e il documento è aggiornato.
"""

import ast
from pathlib import Path

import pytest

from core import intent_usage as iu

RADICE = Path(__file__).resolve().parent.parent


def _cog_con_eventi(eventi: tuple[str, ...]) -> set[str]:
    trovati = set()
    for percorso in (RADICE / "cogs").rglob("*.py"):
        albero = ast.parse(percorso.read_text(encoding="utf-8"))
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.AsyncFunctionDef) and nodo.name in eventi:
                trovati.add(percorso.relative_to(RADICE).as_posix())
    return trovati


@pytest.mark.parametrize("intent", [iu.INTENT_MEMBERS, iu.INTENT_MESSAGE_CONTENT])
def test_i_file_elencati_esistono(intent):
    for file in iu.file_elencati(intent):
        assert (RADICE / file).is_file(), file


def test_ogni_cog_che_ascolta_i_membri_e_nell_elenco():
    mancanti = _cog_con_eventi(iu.EVENTI_MEMBRI) - iu.file_elencati(iu.INTENT_MEMBERS)
    assert not mancanti, f"Aggiungi a core/intent_usage.py (GUILD_MEMBERS): {sorted(mancanti)}"


def test_ogni_cog_che_ascolta_i_messaggi_e_nell_elenco():
    mancanti = _cog_con_eventi(iu.EVENTI_MESSAGGI) - iu.file_elencati(iu.INTENT_MESSAGE_CONTENT)
    assert not mancanti, f"Aggiungi a core/intent_usage.py (MESSAGE_CONTENT): {sorted(mancanti)}"


def test_gli_intent_accesi_in_main_sono_quelli_dell_elenco():
    sorgente = (RADICE / "main.py").read_text(encoding="utf-8")
    assert "intents.members = True" in sorgente and "intents.message_content = True" in sorgente
    assert "intents.presences = True" not in sorgente
    assert iu.USI[iu.INTENT_PRESENCES] == ()


def test_il_documento_e_aggiornato():
    documento = (RADICE / "docs" / "INTENT_PRIVILEGIATI.md").read_text(encoding="utf-8")
    assert documento == iu.genera_documento(), "Rigenera docs/INTENT_PRIVILEGIATI.md da core/intent_usage.py"
