"""
scripts/smoke.py
================
Smoke test mirato: esegue solo i test legati ai file cambiati, più i
controlli sull'albero dei comandi. Si usa a gruppo di lavoro chiuso o
dopo un fix grosso, al posto della suite completa (vedi CLAUDE.md).

Uso:
    python3 scripts/smoke.py                 # file cambiati rispetto a origin/main
    python3 scripts/smoke.py --base <sha>    # file cambiati da quel commit
    python3 scripts/smoke.py cogs/x/y.py     # file indicati a mano
    python3 scripts/smoke.py --lista         # mostra i test scelti, non li esegue
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

RADICE = pathlib.Path(__file__).resolve().parent.parent

# Controlli che guardano tutto il bot insieme: costano pochi secondi e
# trovano i problemi "di struttura" (limiti dei comandi, permessi, View).
TEST_SEMPRE = (
    "tests/test_cog_manager_load_all.py",
    "tests/test_command_policy.py",
    "tests/test_command_tree_invariants.py",
    "tests/test_repository_callers.py",
    "tests/test_ui_base_wiring.py",
    "tests/test_bot_ready_bug19.py",
)

# Se cambia uno di questi, lo smoke non basta: serve la suite completa.
FILE_CHE_VOGLIONO_LA_SUITE = (
    "main.py",
    "core/database.py",
    "tests/conftest.py",
)
CARTELLE_CHE_VOGLIONO_LA_SUITE = ("core/migrations/",)


def file_cambiati(base: str) -> list[str]:
    """File cambiati rispetto a `base`, compresi quelli non ancora committati."""
    comandi = (
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    )
    trovati: set[str] = set()
    for comando in comandi:
        esito = subprocess.run(comando, cwd=RADICE, capture_output=True, text=True)
        trovati.update(riga.strip() for riga in esito.stdout.splitlines() if riga.strip())
    return sorted(trovati)


def _nome_modulo(percorso: str) -> str:
    return percorso[: -len(".py")].replace("/", ".")


def seleziona_test(cambiati: list[str], radice: pathlib.Path = RADICE) -> list[str]:
    """
    Sceglie i file di test da eseguire:
    - i test cambiati;
    - i test che importano o citano un modulo cambiato;
    - i controlli di struttura, sempre.
    """
    cartella_test = radice / "tests"
    testi_dei_test = {
        f"tests/{percorso.name}": percorso.read_text(encoding="utf-8")
        for percorso in sorted(cartella_test.glob("test_*.py"))
    }

    scelti: set[str] = set()
    for percorso in cambiati:
        if not percorso.endswith(".py"):
            continue
        if percorso in testi_dei_test:
            scelti.add(percorso)
            continue
        if percorso.startswith("tests/"):
            continue
        modulo = _nome_modulo(percorso)
        pacchetto, _, nome = modulo.rpartition(".")
        # "import cogs.x.y", "from cogs.x.y import ...", "from cogs.x import y"
        schema = re.compile(
            rf"\b{re.escape(modulo)}\b|from\s+{re.escape(pacchetto)}\s+import\s+[^\n]*\b{re.escape(nome)}\b"
        )
        for nome_test, testo in testi_dei_test.items():
            if schema.search(testo):
                scelti.add(nome_test)

    scelti.update(nome for nome in TEST_SEMPRE if (radice / nome).exists())
    return sorted(scelti)


def serve_la_suite_completa(cambiati: list[str]) -> list[str]:
    """Restituisce i file cambiati per cui lo smoke da solo non basta."""
    return [
        percorso
        for percorso in cambiati
        if percorso in FILE_CHE_VOGLIONO_LA_SUITE
        or any(percorso.startswith(cartella) for cartella in CARTELLE_CHE_VOGLIONO_LA_SUITE)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test mirato sui file cambiati.")
    parser.add_argument("file", nargs="*", help="file cambiati (se assenti si chiede a git)")
    parser.add_argument("--base", default="origin/main", help="commit o ramo di confronto")
    parser.add_argument("--lista", action="store_true", help="mostra i test scelti senza eseguirli")
    argomenti = parser.parse_args()

    cambiati = argomenti.file or file_cambiati(argomenti.base)
    test = seleziona_test(cambiati)

    print(f"File cambiati: {len(cambiati)} — test scelti: {len(test)}")
    for nome in test:
        print(f"  {nome}")
    delicati = serve_la_suite_completa(cambiati)
    if delicati:
        print("\nATTENZIONE: sono cambiati file che toccano tutto il bot:")
        for percorso in delicati:
            print(f"  {percorso}")
        print("Dopo lo smoke esegui anche la suite completa: python3 -m pytest -q")
    if argomenti.lista or not test:
        return 0

    comando = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *test]
    return subprocess.run(comando, cwd=RADICE).returncode


if __name__ == "__main__":
    raise SystemExit(main())
