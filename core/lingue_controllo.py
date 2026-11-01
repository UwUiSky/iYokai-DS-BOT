"""
core/lingue_controllo.py
========================
Controllo e creazione delle lingue (D58, #77): per ogni lingua quante chiavi mancano, quante sono
uguali all'italiano («da tradurre») e quanti segnaposto non coincidono. Usato da
`scripts/controlla_lingue.py` e `scripts/nuova_lingua.py`; provabile senza Discord.
Funzioni coperte: SPEC §21 (NF-06, #77).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from core.i18n import DEFAULT_LANGUAGE, FILE_COMANDI, FILE_TESTI, LINGUA_RIPIEGO, LINGUE, cartella_lingua
from core.command_translator import SEZIONI

_SEGNAPOSTO = re.compile(r"\{(\w+)\}")
_CODICE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,4})?$")


@dataclass
class StatoLingua:
    lingua: str
    totale: int = 0
    mancanti: list[str] = field(default_factory=list)
    uguali: list[str] = field(default_factory=list)
    segnaposto_diversi: list[str] = field(default_factory=list)
    comandi: dict[str, int] = field(default_factory=dict)  # sezione -> voci tradotte
    comandi_mancanti: dict[str, int] = field(default_factory=dict)  # sezione -> voci che l'inglese ha e questa no


def segnaposto(testo: str) -> set[str]:
    return set(_SEGNAPOSTO.findall(testo))


def _leggi(percorso) -> dict:
    try:
        dati = json.loads(percorso.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dati if isinstance(dati, dict) else {}


def _testi(lingua: str) -> dict[str, str]:
    return {k: v for k, v in _leggi(cartella_lingua(lingua) / FILE_TESTI).items() if isinstance(v, str)}


def _comandi(lingua: str) -> dict[str, dict[str, str]]:
    grezzo = _leggi(cartella_lingua(lingua) / FILE_COMANDI)
    return {s: ({k: v for k, v in grezzo[s].items() if isinstance(v, str) and v} if isinstance(grezzo.get(s), dict) else {}) for s in SEZIONI}


def stato_lingua(lingua: str) -> StatoLingua:
    """Lo stato di una lingua rispetto all'italiano (testi) e all'inglese (comandi)."""
    base = _testi(DEFAULT_LANGUAGE)
    mie = _testi(lingua)
    stato = StatoLingua(lingua=lingua, totale=len(base))
    for chiave, testo_it in base.items():
        mio = mie.get(chiave, "")
        if not mio.strip():
            stato.mancanti.append(chiave)
            continue
        if lingua != DEFAULT_LANGUAGE and mio == testo_it and any(c.isalpha() for c in _SEGNAPOSTO.sub("", testo_it)):
            stato.uguali.append(chiave)
        if segnaposto(mio) != segnaposto(testo_it):
            stato.segnaposto_diversi.append(chiave)
    mie_cmd, rif = _comandi(lingua), _comandi(LINGUA_RIPIEGO)
    for sezione in SEZIONI:
        if sezione == "aiuto":
            continue
        stato.comandi[sezione] = len(mie_cmd[sezione])
        if lingua not in (LINGUA_RIPIEGO, DEFAULT_LANGUAGE):  # l'italiano dei comandi è nel codice
            stato.comandi_mancanti[sezione] = len(set(rif[sezione]) - set(mie_cmd[sezione]))
    return stato


def controlla(lingue: tuple[str, ...] | None = None) -> list[StatoLingua]:
    return [stato_lingua(l) for l in (lingue or LINGUE) if cartella_lingua(l).is_dir()]


def riepilogo(stati: list[StatoLingua]) -> str:
    """Il riepilogo in Markdown, una riga per lingua."""
    righe = [
        "# Stato delle lingue",
        "",
        "Testi: chiavi dell'italiano (`it`) che la lingua non ha, che ha uguali all'italiano (da tradurre) o con segnaposto diversi.",
        "Comandi: voci tradotte (nomi / descrizioni / opzioni / menu) e voci che l'inglese ha e questa lingua no.",
        "",
        "| Lingua | Chiavi | Mancanti | Uguali all'italiano | Segnaposto diversi | Comandi tradotti | Comandi mancanti |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in stati:
        tradotti = "/".join(str(s.comandi.get(x, 0)) for x in ("nomi", "descrizioni", "parametri", "menu"))
        mancanti = "/".join(str(s.comandi_mancanti.get(x, 0)) for x in ("nomi", "descrizioni", "parametri", "menu")) if s.comandi_mancanti else "-"
        righe.append(
            f"| {s.lingua} | {s.totale} | {len(s.mancanti)} | {len(s.uguali)} | {len(s.segnaposto_diversi)} | {tradotti} | {mancanti} |"
        )
    return "\n".join(righe) + "\n"


def crea_lingua(codice: str) -> list[str]:
    """
    Crea `locales/<codice>/` con tutte le chiavi vuote («da tradurre»). Solleva ValueError se il codice non è
    valido o la cartella esiste già. Restituisce i file scritti.
    """
    if not _CODICE.match(codice):
        raise ValueError(f"Codice di lingua non valido: {codice!r} (esempi: pt-BR, nl, pl).")
    cartella = cartella_lingua(codice)
    if cartella.exists():
        raise ValueError(f"La cartella locales/{codice} esiste già.")
    testi = {chiave: "" for chiave in _testi(DEFAULT_LANGUAGE)}
    rif = _comandi(LINGUA_RIPIEGO)
    comandi = {s: {k: "" for k in rif[s]} for s in SEZIONI if s != "aiuto"}
    comandi["aiuto"] = {k: "" for k in _comandi(DEFAULT_LANGUAGE)["aiuto"]}
    cartella.mkdir(parents=True)
    scritti = []
    for nome, dati in ((FILE_TESTI, testi), (FILE_COMANDI, comandi)):
        (cartella / nome).write_text(json.dumps(dati, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        scritti.append(f"locales/{codice}/{nome}")
    return scritti
