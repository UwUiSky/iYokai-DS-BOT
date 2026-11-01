"""
tests/test_gitignore_segreti.py
===============================
I segreti e i file generati restano fuori dal repository: ogni regola di `.gitignore` sta su una riga sua
(una regola attaccata a un commento non vale). Funzioni coperte: CLAUDE.md, Divieti.
"""

import pathlib
import subprocess

RADICE = pathlib.Path(__file__).resolve().parent.parent
DA_IGNORARE = (".env", "logs/bot.log", "core/__pycache__/x.pyc", ".pytest_cache/v", "data/hot_patch/x.py", "locales/RIEPILOGO.md")


def test_ogni_regola_sta_su_una_riga_sua():
    righe = (RADICE / ".gitignore").read_text(encoding="utf-8").splitlines()
    for regola in (".env", "__pycache__/", "logs/*.log", ".vscode/", ".pytest_cache/"):
        assert regola in righe, regola


def test_git_ignora_segreti_e_file_generati():
    esito = subprocess.run(
        ["git", "check-ignore", "--no-index", *DA_IGNORARE], cwd=RADICE, capture_output=True, text=True
    )
    assert sorted(esito.stdout.split()) == sorted(DA_IGNORARE)
