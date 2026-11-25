"""
tests/test_avvia_script.py
==========================
avvia.sh: Lavalink è facoltativo (assente = avviso, il bot parte lo stesso) e la password di Lavalink
non finisce mai sulla riga di comando (curl legge la configurazione da stdin).
Si esegue lo script vero, con `curl`, `docker` e Python finti che registrano come vengono chiamati.
Funzioni coperte: consiglio 25/11/2026, critico 12 (blocco C)
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parent.parent
PASSWORD = 'segreto"con\\caratteri'


def _prepara(tmp_path: Path, docker: bool) -> tuple[Path, dict[str, str]]:
    cartella = tmp_path / "bot"
    (cartella / ".venv" / "bin").mkdir(parents=True)
    (cartella / "deploy" / "lavalink").mkdir(parents=True)
    shutil.copy(RADICE / "avvia.sh", cartella / "avvia.sh")
    (cartella / "requirements.lock").write_text("x\n")
    # L'impronta dei requisiti già uguale: lo script non prova a installare niente.
    impronta = subprocess.run(["cksum", str(cartella / "requirements.lock")], capture_output=True, text=True).stdout.split()[0]
    (cartella / ".venv" / ".requisiti").write_text(impronta)
    python = cartella / ".venv" / "bin" / "python"
    python.write_text("#!/bin/sh\nexit 0\n")  # il «database» risponde, il «bot» parte ed esce
    python.chmod(0o755)
    (cartella / ".env").write_text(
        f"DATABASE_URL=postgresql://u:p@127.0.0.1/db\nLAVALINK_HOST=127.0.0.1\nLAVALINK_PORT=2333\nLAVALINK_PASSWORD={PASSWORD}\n"
    )
    stub = tmp_path / "stub"
    stub.mkdir()
    curl = stub / "curl"
    curl.write_text(
        f'#!/bin/sh\nprintf "%s\\n" "$@" > "{tmp_path}/curl_argv"\ncat > "{tmp_path}/curl_stdin"\nexit 22\n'
    )
    curl.chmod(0o755)
    if docker:
        d = stub / "docker"
        d.write_text("#!/bin/sh\nexit 1\n")  # docker compose non parte
        d.chmod(0o755)
    percorso = f"{stub}:/usr/bin:/bin"
    return cartella, {"PATH": percorso, "HOME": str(tmp_path)}


def _lancia(cartella: Path, env: dict[str, str]):
    return subprocess.run(
        ["bash", str(cartella / "avvia.sh"), ], cwd=cartella, env=env, capture_output=True, text=True, timeout=60
    )


def test_senza_docker_lavalink_assente_e_un_avviso_e_il_bot_parte(tmp_path):
    cartella, env = _prepara(tmp_path, docker=False)
    # Il PATH contiene solo i finti e gli strumenti che lo script usa: `docker` non c'è davvero.
    env["PATH"] = str(tmp_path / "stub")
    for nome in ("bash", "cksum", "grep", "tail", "cat", "printf", "sed", "cut", "tr", "dirname"):
        alt = shutil.which(nome)
        if alt and not (tmp_path / "stub" / nome).exists():
            os.symlink(alt, tmp_path / "stub" / nome)
    esito = _lancia(cartella, env)
    assert esito.returncode == 0, esito.stderr
    assert "AVVISO" in esito.stderr and "ERRORE" not in esito.stderr
    assert "Avvio il bot" in esito.stdout  # il bot è partito lo stesso


def test_docker_compose_che_non_parte_e_un_avviso(tmp_path):
    cartella, env = _prepara(tmp_path, docker=True)
    esito = _lancia(cartella, env)
    assert esito.returncode == 0, esito.stderr
    assert "docker compose non è partito" in esito.stderr
    assert "ERRORE" not in esito.stderr and "Avvio il bot" in esito.stdout


def test_la_password_non_e_sulla_riga_di_comando_di_curl(tmp_path):
    cartella, env = _prepara(tmp_path, docker=True)
    _lancia(cartella, env)
    argv = (tmp_path / "curl_argv").read_text()
    stdin = (tmp_path / "curl_stdin").read_text()
    assert "segreto" not in argv and "Authorization" not in argv  # niente `-H "Authorization: ..."`
    assert "--config" in argv
    assert stdin.strip() == 'header = "Authorization: segreto\\"con\\\\caratteri"'  # virgolette e barre protette


def test_cricchetto_gli_script_non_mettono_la_password_in_un_argomento():
    sh = (RADICE / "avvia.sh").read_text(encoding="utf-8")
    assert '-H "Authorization' not in sh and "-H 'Authorization" not in sh
    ps = (RADICE / "avvia.ps1").read_text(encoding="utf-8")
    assert "Errore \"Lavalink" not in ps and 'Errore "imposta LAVALINK' not in ps  # Lavalink assente: solo Avviso
    assert 'errore "Lavalink' not in sh and 'errore "imposta LAVALINK' not in sh
