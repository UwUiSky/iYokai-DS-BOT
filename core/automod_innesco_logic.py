"""
core/automod_innesco_logic.py
=============================
Quando scatta una regola personale su un testo: regex del server (solo re2), lista di parole (stessa lettura
del filtro delle parole vietate: maiuscole, accenti, simboli al posto delle lettere), domini vietati o permessi,
sole parole permesse. Logica pura, niente Discord né database.
Funzioni coperte: SPEC §6 (AMD-011, AMD-012, AMD-016, AMD-025, AMD-075), D63
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


# ---------------------------------------------------------------- ruoli e casi (eventi ruolo_dato, ruolo_tolto, caso)

_ID_RUOLO = re.compile(r"(?:<@&)?(\d{15,20})>?")
EVENTI_RUOLO = ("ruolo_dato", "ruolo_tolto")


def _leggi_ruoli(testo: str, ruolo_esiste) -> list[int]:
    """Ogni voce dev'essere un ID o una menzione di un ruolo del server: un nome non diventa «qualsiasi ruolo»."""
    from core.automod_regole_logic import RegolaNonValida

    ruoli = []
    for voce in (v for v in re.split(r"[\s,;]+", testo) if v):
        m = _ID_RUOLO.fullmatch(voce)
        if m is None:
            raise RegolaNonValida(f"ruoli: «{voce[:40]}» non è un ID né una menzione di ruolo")
        if ruolo_esiste is not None and not ruolo_esiste(int(m.group(1))):
            raise RegolaNonValida(f"ruoli: {m.group(1)} non è un ruolo di questo server")
        ruoli.append(int(m.group(1)))
    return list(dict.fromkeys(ruoli))


def leggi_filtro_evento(evento: str, testo: str, ruolo_esiste=None) -> dict:
    """Dal testo della finestra: i ruoli (id o menzioni, solo del server se `ruolo_esiste` è dato) per ruolo_dato e
    ruolo_tolto, i tipi di caso per caso. Vuoto = qualsiasi. Gli altri eventi non hanno filtro."""
    testo = (testo or "").strip()
    if not testo:
        return {}
    if evento in EVENTI_RUOLO:
        return {"ruoli": _leggi_ruoli(testo, ruolo_esiste)}
    if evento == "caso":
        return {"casi": list(dict.fromkeys(p.lower() for p in re.split(r"[\s,;]+", testo) if p))}
    return {}


def scrivi_filtro_evento(evento: str, innesco: dict) -> str:
    """Il testo da mostrare nella finestra per il filtro già salvato."""
    if evento in EVENTI_RUOLO:
        return ", ".join(str(i) for i in innesco.get("ruoli", ()))
    if evento == "caso":
        return ", ".join(innesco.get("casi", ()))
    return ""


# ---------------------------------------------------------------- soglia per canale (AMD-008)

SOGLIA_CANALE_DI_BASE = (10, 10)  # messaggi, secondi


def parametri_soglia_canale(innesco: dict) -> tuple[int, int]:
    return innesco.get("numero", SOGLIA_CANALE_DI_BASE[0]), innesco.get("secondi", SOGLIA_CANALE_DI_BASE[1])


def leggi_soglia_canale(testo: str) -> dict:
    """«12/8» = 12 messaggi in 8 secondi, in tutto il canale. Vuoto = niente. Storto: RegolaNonValida."""
    from core.automod_regole_logic import RegolaNonValida

    testo = (testo or "").strip()
    if not testo:
        return {}
    pezzi = [p.strip() for p in testo.split("/")]
    if len(pezzi) != 2 or not all(p.isdigit() for p in pezzi):
        raise RegolaNonValida("soglia: scrivi messaggi/secondi, per esempio 10/10")
    numero, secondi = int(pezzi[0]), int(pezzi[1])
    if not 1 <= numero <= 10_000 or not 1 <= secondi <= 86_400:
        raise RegolaNonValida("soglia: da 1 a 10000 messaggi, da 1 a 86400 secondi")
    return {"numero": numero, "secondi": secondi}


def scrivi_soglia_canale(innesco: dict) -> str:
    return f"{innesco['numero']}/{innesco['secondi']}" if "numero" in innesco and "secondi" in innesco else ""
