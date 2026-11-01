"""
core/ai_override_logic.py
=========================
Scelte dell'owner sopra il `.env`: modello, fascia e tipi di lavoro di ogni fornitore, e tetto alla lunghezza delle
risposte per tutti i server. Si salvano nel database e si applicano a caldo. Nessuna rete qui.
Funzioni coperte: SPEC §25.82, §25.94 (AI-R-089, AI-R-101)
"""

from __future__ import annotations

import json
import re
from dataclasses import replace

from core.ai_providers import FASCE, TIPI, Fornitore

TETTO_MIN, TETTO_MAX = 100, 4000
_MODELLO = re.compile(r"[\w.:/@-]{1,80}")


def leggi(testo: str | None) -> dict[str, dict]:
    """{nome fornitore: {modello, fascia, tipi}}; un valore rovinato o sconosciuto si ignora."""
    try:
        dati = json.loads(testo) if testo else {}
    except ValueError:
        return {}
    if not isinstance(dati, dict):
        return {}
    pulito: dict[str, dict] = {}
    for nome, voce in dati.items():
        if not isinstance(voce, dict):
            continue
        scelta: dict = {}
        if isinstance(voce.get("modello"), str) and _MODELLO.fullmatch(voce["modello"]):
            scelta["modello"] = voce["modello"]
        if voce.get("fascia") in FASCE:
            scelta["fascia"] = voce["fascia"]
        if isinstance(voce.get("tipi"), list):
            tipi = sorted({t for t in voce["tipi"] if t in TIPI})
            if tipi:
                scelta["tipi"] = tipi
        if scelta:
            pulito[str(nome)] = scelta
    return pulito


def errore_scelta(modello: str | None, fascia: str | None, tipi: str | None) -> str | None:
    """Il motivo per cui la scelta non va, o None."""
    if modello is not None and not _MODELLO.fullmatch(modello):
        return "Il nome del modello ha caratteri non ammessi (lettere, numeri, . : / @ - _; al massimo 80)."
    if fascia is not None and fascia not in FASCE:
        return f"La fascia è una tra: {', '.join(FASCE)}."
    if tipi is not None:
        scelti = [t.strip() for t in tipi.split(",") if t.strip()]
        if not scelti or any(t not in TIPI for t in scelti):
            return f"I tipi sono separati da virgola, tra: {', '.join(TIPI)}."
    return None


def unisci(override: dict[str, dict], nome: str, modello: str | None, fascia: str | None, tipi: str | None) -> dict[str, dict]:
    voce = dict(override.get(nome, {}))
    if modello is not None:
        voce["modello"] = modello
    if fascia is not None:
        voce["fascia"] = fascia
    if tipi is not None:
        voce["tipi"] = sorted({t.strip() for t in tipi.split(",") if t.strip()})
    return {**override, nome: voce}


def applica(fornitori: list[Fornitore], override: dict[str, dict]) -> list[Fornitore]:
    esito = []
    for f in fornitori:
        v = override.get(f.nome)
        if not v:
            esito.append(f)
            continue
        campi = {k: v[k] for k in ("modello", "fascia") if k in v}
        if "tipi" in v:
            campi["tipi"] = frozenset(v["tipi"])
        esito.append(replace(f, **campi))
    return esito


def tetto_valido(valore: str | None) -> int | None:
    try:
        n = int(valore) if valore else None
    except ValueError:
        return None
    return n if n is not None and TETTO_MIN <= n <= TETTO_MAX else None


def riga_fornitore(f: Fornitore) -> str:
    return f"**{f.nome}** · modello `{f.modello or 'predefinito'}` · fascia {f.fascia} · tipi {', '.join(sorted(f.tipi)) or '-'}"
