"""
core/automod_innesco_logic.py
=============================
Quando scatta una regola personale su un testo: regex del server (solo re2), lista di parole (stessa lettura
del filtro delle parole vietate: maiuscole, accenti, simboli al posto delle lettere), domini vietati o permessi,
sole parole permesse. Logica pura, niente Discord né database.
Funzioni coperte: SPEC §6 (AMD-011, AMD-012, AMD-016, AMD-025), D63
"""

from __future__ import annotations

import re
from functools import lru_cache

from core.automod_advanced_logic import _in_lista, extract_domains, normalize_domain
from core.automod_parole_logic import costruisci, normalizza, trova
from core.automod_regole_logic import MAX_TESTO_PROVA

_PAROLA = re.compile(r"[^\W\d_]+", re.UNICODE)


@lru_cache(maxsize=512)
def _regex(modello: str):
    import re2

    return re2.compile(modello)


@lru_cache(maxsize=256)
def _permesse(voci: tuple[str, ...]) -> frozenset[str]:
    return frozenset(x for x in (normalizza(v) for v in voci) if x)


def voci_della_lista(innesco: dict, liste: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    """Le voci dell'innesco: quelle scritte nella regola più quelle delle liste con nome (anche `@parolacce-it`)."""
    voci = list(innesco.get("parole", ()))
    for nome in innesco.get("liste", ()):
        voci += liste.get(nome, ())
    return tuple(dict.fromkeys(voci))


def innesco_scatta(innesco: dict, testo: str, liste: dict[str, tuple[str, ...]] | None = None) -> bool:
    """True se il testo fa scattare l'innesco. Un innesco vuoto o sconosciuto non scatta mai."""
    liste = liste or {}
    tipo = innesco.get("tipo")
    testo = (testo or "")[:MAX_TESTO_PROVA]  # un testo lungo non allunga il lavoro (niente ReDoS)
    if tipo == "sempre":
        return True
    if not testo:
        return False
    if tipo == "regex":
        return any(_regex(m).search(testo) for m in innesco.get("regex", ()))
    voci = voci_della_lista(innesco, liste)
    if tipo == "lista":
        return bool(voci) and trova(testo, costruisci(False, voci)) is not None
    if tipo == "domini":
        domini = extract_domains(testo)
        elenco = {normalize_domain(v) for v in voci} - {""}
        if innesco.get("modo", "vietati") == "permessi":
            return any(not _in_lista(d, elenco) for d in domini)  # un link che non è nella lista
        return any(_in_lista(d, elenco) for d in domini)
    if tipo == "solo_permesse":
        permesse = _permesse(voci)
        parole = [p for p in _PAROLA.findall(testo) if len(p) > 0]
        return any(normalizza(p) not in permesse for p in parole)
    return False
