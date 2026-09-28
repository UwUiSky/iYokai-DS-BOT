"""
tests/test_ui_base_wiring.py
================================
SEC-10, cricchetto: nessuna classe in cogs/ deve ereditare
DIRETTAMENTE da discord.ui.View o discord.ui.Modal (deve passare da
core.ui_base.BaseView/BaseModal, che aggiungono il controllo
blacklist), e nessun punto di cogs/ deve istanziare
discord.ui.View(...)/discord.ui.Modal(...) al posto di
BaseView(...)/BaseModal(...) per una view costruita dinamicamente.

KNOWN_RAW_VIEWS contiene i punti che oggi violano questa regola
(REVIEW.md SEC-10). Ogni fix toglie il nome; un nome nuovo fa
fallire il test — stesso principio di KNOWN_UNCALLED in
tests/test_repository_callers.py.
"""

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Vuoto: tutte le View/Modal del progetto ereditano già da
# core.ui_base.BaseView/BaseModal (SEC-10). Un nome aggiunto qui
# andrebbe rimosso appena sistemato, mai lasciato per far passare il
# test.
KNOWN_RAW_VIEWS = frozenset()


def _nome_base_class(base: ast.expr) -> str | None:
    """Restituisce 'discord.ui.View'/'discord.ui.Modal' per una base
    class scritta come discord.ui.View o come ui.View (import
    diverso), None per qualunque altra base."""
    if isinstance(base, ast.Attribute) and base.attr in ("View", "Modal"):
        valore = base.value
        if isinstance(valore, ast.Attribute) and valore.attr == "ui":
            return f"discord.ui.{base.attr}"
    return None


def _violazioni_ereditarieta(percorso: pathlib.Path, testo: str) -> list[str]:
    violazioni = []
    for nodo in ast.walk(ast.parse(testo)):
        if not isinstance(nodo, ast.ClassDef):
            continue
        for base in nodo.bases:
            tipo = _nome_base_class(base)
            if tipo is not None:
                violazioni.append(f"{percorso.relative_to(ROOT)}:{nodo.lineno} class {nodo.name}({tipo})")
    return violazioni


def _violazioni_istanziazione(percorso: pathlib.Path, testo: str) -> list[str]:
    violazioni = []
    for nodo in ast.walk(ast.parse(testo)):
        if not isinstance(nodo, ast.Call):
            continue
        func = nodo.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr in ("View", "Modal")
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "ui"
        ):
            violazioni.append(f"{percorso.relative_to(ROOT)}:{nodo.lineno} discord.ui.{func.attr}(...)")
    return violazioni


def _tutte_le_violazioni() -> list[str]:
    violazioni = []
    for file in sorted(ROOT.glob("cogs/**/*.py")):
        testo = file.read_text(encoding="utf-8")
        violazioni += _violazioni_ereditarieta(file, testo)
        violazioni += _violazioni_istanziazione(file, testo)
    return violazioni


def test_nessuna_view_o_modal_raw_in_cogs():
    trovate = set(_tutte_le_violazioni())

    nuove = sorted(trovate - KNOWN_RAW_VIEWS)
    assert nuove == [], (
        f"View/Modal che ereditano direttamente da discord.ui invece di "
        f"core.ui_base.BaseView/BaseModal (SEC-10): {nuove}"
    )

    sistemate = sorted(KNOWN_RAW_VIEWS - trovate)
    assert sistemate == [], f"Queste non violano più la regola: toglile da KNOWN_RAW_VIEWS: {sistemate}"
