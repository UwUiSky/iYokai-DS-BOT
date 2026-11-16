"""
tests/test_sicurezza_modello_env.py
===================================
Il modello `.env.example` e le dipendenze fissate non devono lasciare
aperta una porta a chi installa il bot copiando i file così come sono.
Funzioni coperte: SPEC §2 (SEC-13), registro aggiornamenti #143
"""

from __future__ import annotations

import re
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
# Prima versione di aiohttp senza le vulnerabilità note della 3.14.3.
AIOHTTP_MINIMA = (3, 14, 4)


def _versione(testo: str) -> tuple[int, ...]:
    return tuple(int(parte) for parte in testo.split("."))


def test_il_modello_env_parte_in_produzione():
    """Chi copia il modello non deve ritrovarsi /owner eval e il premium sbloccato per tutti."""
    testo = (RADICE / ".env.example").read_text(encoding="utf-8")
    valori = re.findall(r"^ENVIRONMENT=(.*)$", testo, flags=re.MULTILINE)
    assert valori == ["production"]


def test_il_modello_env_non_accende_eval_ne_hot_patch():
    testo = (RADICE / ".env.example").read_text(encoding="utf-8")
    assert re.findall(r"^ENABLE_EVAL=(.*)$", testo, flags=re.MULTILINE) == [""]
    assert re.findall(r"^ENABLE_HOT_PATCH=(.*)$", testo, flags=re.MULTILINE) == ["0"]


def test_aiohttp_fissato_senza_vulnerabilita_note():
    blocco = (RADICE / "requirements.lock").read_text(encoding="utf-8")
    fissata = re.search(r"^aiohttp==([0-9.]+)$", blocco, flags=re.MULTILINE)
    assert fissata is not None
    assert _versione(fissata.group(1)) >= AIOHTTP_MINIMA

    richieste = (RADICE / "requirements.txt").read_text(encoding="utf-8")
    minima = re.search(r"^aiohttp>=([0-9.]+)$", richieste, flags=re.MULTILINE)
    assert minima is not None
    assert _versione(minima.group(1)) >= AIOHTTP_MINIMA
