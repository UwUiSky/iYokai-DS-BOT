"""
tests/test_cricchetti_sicurezza.py
==================================
Cricchetti del blocco A (SICUREZZA.md §4, §6, §7): regole scritte che un test fa rispettare.
1. Nessun `assert` usato come controllo nel codice di produzione: con `python -O` sparisce (usa `raise ValueError`).
2. Nessun `assert ... or True` nei test: una prova che passa sempre non prova niente.
3. Ogni rotta del pannello web sta nella tabella dei livelli: test_web_panel_tabella_rotte.py.
Si aggiunge un file solo se si sa spiegare perché; mai un'eccezione per far passare un test.
"""

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _file_python(*cartelle: str):
    for cartella in cartelle:
        for percorso in sorted((ROOT / cartella).rglob("*.py")):
            if "__pycache__" not in percorso.parts and ".venv" not in percorso.parts:
                yield percorso


def test_nessun_assert_nel_codice_di_produzione():
    trovati = []
    for percorso in [*_file_python("core", "cogs"), ROOT / "main.py"]:
        albero = ast.parse(percorso.read_text(encoding="utf-8"))
        trovati += [f"{percorso.relative_to(ROOT)}:{n.lineno}" for n in ast.walk(albero) if isinstance(n, ast.Assert)]
    assert not trovati, f"`assert` come controllo (sparisce con python -O): usa `raise ValueError`: {trovati}"


def _e_vero_costante(nodo: ast.AST) -> bool:
    return isinstance(nodo, ast.Constant) and nodo.value is True


def _or_true_nel_test(test: ast.AST) -> bool:
    """Un `or True` che decide l'assert. Dentro una lambda non conta: `lambda u: lista.append(u) or True` torna True per sé."""
    pila = [test]
    while pila:
        nodo = pila.pop()
        if isinstance(nodo, ast.Lambda):
            continue
        if isinstance(nodo, ast.BoolOp) and isinstance(nodo.op, ast.Or) and any(_e_vero_costante(v) for v in nodo.values):
            return True
        pila.extend(ast.iter_child_nodes(nodo))
    return False


def test_nessun_or_true_dentro_un_assert_dei_test():
    trovati = []
    for percorso in _file_python("tests"):
        albero = ast.parse(percorso.read_text(encoding="utf-8"))
        for nodo in ast.walk(albero):
            if not isinstance(nodo, ast.Assert):
                continue
            if _or_true_nel_test(nodo.test):
                trovati.append(f"{percorso.relative_to(ROOT)}:{nodo.lineno}")
    assert not trovati, f"un `or True` rende l'assert inutile: {trovati}"


def test_il_cricchetto_riconosce_un_or_true():
    """Il cricchetto non è cieco: su un caso fatto apposta trova il difetto."""
    albero = ast.parse("assert x == 1 or True\nassert y == 2\nassert f(lambda u: g(u) or True) is ok")
    assert [n.lineno for n in ast.walk(albero) if isinstance(n, ast.Assert) and _or_true_nel_test(n.test)] == [1]
