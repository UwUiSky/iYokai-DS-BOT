"""
tests/test_i18n_risposte_r12.py
===============================
SPEC 21.6: role menu, verifica, spam-trap e benvenuti non rispondono più con frasi inglesi scritte nel codice:
passano dal catalogo (italiano e inglese).
"""

import ast
import pathlib
import re

import pytest

from core.i18n import t

RADICE = pathlib.Path(__file__).resolve().parent.parent
FILE = ["cogs/utility/role_menus.py", "cogs/security/verify.py", "cogs/security/spam_trap.py", "cogs/utility/greetings.py"]
INGLESE = re.compile(r"\b(the|you|your|has|have|been|couldn't|please)\b", re.I)


def _stringhe_inviate(percorso):
    for nodo in ast.walk(ast.parse((RADICE / percorso).read_text(encoding="utf-8"))):
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute) and nodo.func.attr in {"send_message", "send", "edit_message", "edit_original_response"}:
            for a in nodo.args[:1]:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    yield nodo.lineno, a.value
                elif isinstance(a, ast.JoinedStr):
                    yield nodo.lineno, "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in a.values)


@pytest.mark.parametrize("percorso", FILE)
def test_nessuna_risposta_inglese_nel_codice(percorso):
    trovate = [f"{percorso}:{riga}: {s[:50]!r}" for riga, s in _stringhe_inviate(percorso) if INGLESE.search(s)]
    assert trovate == []


@pytest.mark.parametrize("chiave,it,en", [
    ("rm_ruoli_aggiornati", "I tuoi ruoli sono stati aggiornati.", "Your roles have been updated."),
    ("verify_gia_verificato", "Sei già verificato.", "You are already verified."),
    ("trap_appello_limite", "Puoi mandare un solo appello", "You can only submit one appeal"),
])
def test_catalogo_in_due_lingue(chiave, it, en):
    assert it in t(chiave, "it") and en in t(chiave, "en")


def test_testi_di_base_dei_benvenuti_nelle_due_lingue():
    assert "{user}" in t("greet_base_welcome", "it") and t("greet_base_welcome", "it") != t("greet_base_welcome", "en")
    assert "{server}" in t("greet_base_boost", "en") and "{username}" in t("greet_base_goodbye", "en")
    assert t("trap_appello_approvato", "en", server="X") == "Your ban appeal for **X** was approved. You can rejoin the server."
