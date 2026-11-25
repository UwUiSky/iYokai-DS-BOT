"""
tests/support/percorsi.py
=========================
Aiuto per i test dei gruppi F7: l'elenco dei percorsi ("sottogruppo comando")
dei comandi registrati in un gruppo condiviso di core/command_groups.py.
"""

from __future__ import annotations

import re
from pathlib import Path

from discord import app_commands

from core.command_groups import GRUPPI


def _coppie_d60() -> dict[str, str]:
    """vecchio -> nuovo percorso dello spostamento D60 (dalla migrazione 0488)."""
    sql = (Path(__file__).resolve().parents[2] / "core/migrations/0488_percorsi_comandi_ruoli.sql").read_text(encoding="utf-8")
    return dict(re.findall(r"\('([^']+)', '([^']+)'\)", sql.split("WITH m(vecchio, nuovo)", 2)[1]))


def _coppie_d137() -> dict[str, str]:
    """vecchio -> nuovo percorso del riordino D137 (dalla migrazione 0972)."""
    from tests.support.percorsi_d137 import D137

    return D137


def _foglie_attuali(nome_gruppo: str) -> set[str]:
    trovati: set[str] = set()

    def scendi(gruppo: app_commands.Group, prefisso: str) -> None:
        for figlio in gruppo.commands:
            if isinstance(figlio, app_commands.Group):
                scendi(figlio, f"{prefisso}{figlio.name} ")
            else:
                trovati.add(f"{prefisso}{figlio.name}")

    if nome_gruppo in GRUPPI:
        scendi(GRUPPI[nome_gruppo], "")
    return trovati


def _percorso_attuale(vecchio: str) -> str | None:
    """Dove sta oggi un percorso di prima (D60 poi D137): il percorso nuovo se esiste come comando, altrimenti None."""
    for candidato in (vecchio, _coppie_d60().get(vecchio), None):
        if candidato is None:
            return None
        for c in (candidato, _coppie_d137().get(candidato)):
            if c is None:
                continue
            radice, _, resto = c.partition(" ")
            if radice in GRUPPI and resto in _foglie_attuali(radice):
                return c
    return None


def percorsi_del_gruppo(nome_gruppo: str) -> set[str]:
    """Es. {"config history", "setup attiva", "ping"} per `/admin-bot`.

    Oltre ai comandi del gruppo, include quelli che il gruppo AVEVA prima dei riordini D60 e D137 e che oggi esistono
    sotto un altro nome (ritrovati dai percorsi vecchi delle migrazioni 0488 e 0972)."""
    trovati = _foglie_attuali(nome_gruppo)
    vecchi = {v for v in (*_coppie_d60(), *_coppie_d137()) if v.startswith(nome_gruppo + " ")}
    vecchi |= {n for n in _coppie_d60().values() if n.startswith(nome_gruppo + " ")}  # percorsi D60 poi spostati da D137
    for v in vecchi:
        if _percorso_attuale(v) is not None:
            trovati.add(v[len(nome_gruppo) + 1:])
    return trovati


def comando_nel_gruppo(nome_gruppo: str, percorso: str) -> app_commands.Command:
    """Il comando `/gruppo percorso`; AssertionError se non c'è. Accetta anche i percorsi di prima di D60 e D137."""
    if nome_gruppo in GRUPPI:
        nodo = GRUPPI[nome_gruppo]
        for parte in percorso.split():
            nodo = nodo.get_command(parte) if isinstance(nodo, app_commands.Group) else None
            if nodo is None:
                break
        if nodo is not None:
            return nodo
    nuovo = _percorso_attuale(f"{nome_gruppo} {percorso}") or f"{nome_gruppo} {percorso}"
    nome_gruppo, _, percorso = nuovo.partition(" ")
    nodo = GRUPPI[nome_gruppo]
    for parte in percorso.split():
        nodo = nodo.get_command(parte)
        assert nodo is not None, f"/{nome_gruppo} {percorso}: manca '{parte}'"
    return nodo
