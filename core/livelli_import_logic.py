"""
core/livelli_import_logic.py
============================
Import dei livelli da un file esportato dall'admin (JSON o CSV): ogni campo si controlla, un solo errore blocca tutto.
Mai da API di altri bot. Funzioni pure, senza Discord né database.
Funzioni coperte: LIV-072
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass

MAX_BYTE_FILE = 2 * 1024 * 1024
MAX_RIGHE = 50_000
MAX_XP = 1_000_000_000
MAX_ID = 2**63 - 1
MAX_ERRORI_MOSTRATI = 5
_CHIAVI_ID = ("id", "user_id", "userid", "user")
_CHIAVI_XP = ("xp", "total_xp", "totalxp", "exp")


class ImportNonValido(ValueError):
    """Il file non si può importare; il messaggio dice dove (in italiano, già pronto per l'admin)."""


@dataclass(frozen=True)
class RigaImport:
    user_id: int
    xp: int


def _intero(valore, nome: str, dove: str, minimo: int, massimo: int) -> int:
    if isinstance(valore, bool) or valore is None:
        raise ImportNonValido(f"{dove}: «{nome}» non è un numero.")
    if isinstance(valore, float):
        if not valore.is_integer():
            raise ImportNonValido(f"{dove}: «{nome}» non è un numero intero.")
        valore = int(valore)
    if isinstance(valore, str):
        testo = valore.strip()
        if not testo.isascii() or not testo.lstrip("+").isdigit():
            raise ImportNonValido(f"{dove}: «{nome}» non è un numero intero positivo.")
        valore = int(testo)
    if not isinstance(valore, int) or not minimo <= valore <= massimo:
        raise ImportNonValido(f"{dove}: «{nome}» deve stare tra {minimo} e {massimo}.")
    return valore


def _prendi(riga: dict, chiavi: tuple[str, ...]):
    minuscole = {str(k).strip().lower(): v for k, v in riga.items()}
    for k in chiavi:
        if k in minuscole:
            return minuscole[k]
    return None


def _righe_da_json(testo: str) -> list:
    try:
        dati = json.loads(testo)
    except ValueError as errore:
        raise ImportNonValido("Il file non è un JSON valido.") from errore
    if isinstance(dati, dict):  # formato con un elenco dentro («players», «users», «levels»)
        elenchi = [v for v in dati.values() if isinstance(v, list)]
        if len(elenchi) != 1:
            raise ImportNonValido("Nel JSON serve un elenco di persone (una chiave sola con una lista).")
        dati = elenchi[0]
    if not isinstance(dati, list):
        raise ImportNonValido("Nel JSON serve un elenco di persone.")
    return dati


def _righe_da_csv(testo: str) -> list:
    try:
        lettore = csv.DictReader(io.StringIO(testo))
        return list(lettore)
    except csv.Error as errore:
        raise ImportNonValido("Il file CSV non è valido.") from errore


def leggi_file(contenuto: bytes, nome_file: str) -> list[RigaImport]:
    """
    Le righe valide del file. Estensione `.json` o `.csv`. ImportNonValido al primo problema
    (file troppo grande, troppe righe, id o XP non validi, persona ripetuta).
    """
    if len(contenuto) > MAX_BYTE_FILE:
        raise ImportNonValido(f"Il file supera {MAX_BYTE_FILE // 1024 // 1024} MB.")
    try:
        testo = contenuto.decode("utf-8-sig")
    except UnicodeDecodeError as errore:
        raise ImportNonValido("Il file deve essere in UTF-8.") from errore
    nome = nome_file.lower()
    if nome.endswith(".json"):
        grezze = _righe_da_json(testo)
    elif nome.endswith(".csv"):
        grezze = _righe_da_csv(testo)
    else:
        raise ImportNonValido("Il file deve finire con .json o .csv.")
    if not grezze:
        raise ImportNonValido("Il file non contiene nessuna persona.")
    if len(grezze) > MAX_RIGHE:
        raise ImportNonValido(f"Troppe righe: al massimo {MAX_RIGHE}.")
    viste: set[int] = set()
    righe: list[RigaImport] = []
    for n, riga in enumerate(grezze, 1):
        dove = f"Riga {n}"
        if not isinstance(riga, dict):
            raise ImportNonValido(f"{dove}: non è una persona con id e xp.")
        id_grezzo, xp_grezzo = _prendi(riga, _CHIAVI_ID), _prendi(riga, _CHIAVI_XP)
        user_id = _intero(id_grezzo, "id", dove, 1, MAX_ID)
        xp = _intero(xp_grezzo, "xp", dove, 0, MAX_XP)
        if user_id in viste:
            raise ImportNonValido(f"{dove}: l'id {user_id} compare due volte.")
        viste.add(user_id)
        righe.append(RigaImport(user_id, xp))
    return righe
