"""
core/gif_preferenze_logic.py
============================
Preferenze delle GIF di ogni persona (FUN-138, D124): genere dei personaggi, personaggi preferiti scelti dal
catalogo (massimo 10) e tipo (anime, non anime, entrambi). Qui il catalogo, i controlli e il modo in cui le
preferenze cambiano una voce di ricerca. Senza preferenze la voce resta com'è.
Funzioni coperte: SPEC §16 (FUN-138; D124)
Dipende da: core/gif_catalogo.py, core/gif_fonti.py
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, replace  # noqa: F401 - `replace` lo usa anche il comando
from functools import lru_cache
from pathlib import Path

from core.gif_catalogo import MAX_NOME, MAX_SUGGERIMENTI, Voce, _norma
from core.gif_fonti import categoria_sfw

PERCORSO = Path(__file__).resolve().parent.parent / "data" / "gif_personaggi.json"
MAX_PREFERITI = 10
GENERI = ("qualsiasi", "femminile", "maschile", "neutro")
TIPI = ("entrambi", "anime", "non_anime")
_GENERE_CODICE = {"femminile": "f", "maschile": "m", "neutro": "n"}
_TIPO_CODICE = {"anime": "anime", "non_anime": "altro"}


@dataclass(frozen=True)
class Personaggio:
    id: str
    nome: str
    genere: str  # f, m, n
    tipo: str  # anime, altro


@dataclass(frozen=True)
class Preferenze:
    genere: str = "qualsiasi"
    tipo: str = "entrambi"
    personaggi: tuple[str, ...] = ()

    @property
    def vuote(self) -> bool:
        return self.genere == "qualsiasi" and self.tipo == "entrambi" and not self.personaggi


@lru_cache(maxsize=1)
def catalogo() -> dict[str, Personaggio]:
    grezzo = json.loads(PERCORSO.read_text(encoding="utf-8"))["personaggi"]
    return {p["id"]: Personaggio(p["id"], p["nome"], p["genere"], p["tipo"]) for p in grezzo}


def trova(scelto: str) -> Personaggio | None:
    """Il personaggio di un valore scelto (id o nome esatto). Fuori dal catalogo: None, nessun testo libero."""
    chiave = _norma(scelto or "")
    for p in catalogo().values():
        if chiave in (p.id, _norma(p.nome)):
            return p
    return None


def suggerimenti(digitato: str) -> list[tuple[str, str]]:
    """Fino a 25 coppie (nome, id): prima chi inizia con il testo, poi chi lo contiene. Solo dati locali."""
    chiave = _norma(digitato or "")
    inizio = [p for p in catalogo().values() if _norma(p.nome).startswith(chiave)]
    dentro = [p for p in catalogo().values() if chiave and chiave in _norma(p.nome) and p not in inizio]
    return [(p.nome[:MAX_NOME], p.id[:MAX_NOME]) for p in (inizio + dentro)[:MAX_SUGGERIMENTI]]


def aggiungi_preferito(preferenze: Preferenze, scelto: str) -> tuple[Preferenze, str]:
    """(nuove preferenze, esito): 'ok', 'sconosciuto', 'gia' o 'tetto'."""
    p = trova(scelto)
    if p is None:
        return preferenze, "sconosciuto"
    if p.id in preferenze.personaggi:
        return preferenze, "gia"
    if len(preferenze.personaggi) >= MAX_PREFERITI:
        return preferenze, "tetto"
    return replace(preferenze, personaggi=(*preferenze.personaggi, p.id)), "ok"


def togli_preferito(preferenze: Preferenze, scelto: str) -> tuple[Preferenze, bool]:
    p = trova(scelto)
    if p is None or p.id not in preferenze.personaggi:
        return preferenze, False
    return replace(preferenze, personaggi=tuple(i for i in preferenze.personaggi if i != p.id)), True


def personaggio_per(preferenze: Preferenze, rng: random.Random) -> Personaggio | None:
    """Il personaggio da cercare: un preferito (del genere scelto, se ce n'è), altrimenti uno del catalogo di quel genere e tipo."""
    tutti = catalogo()
    codice = _GENERE_CODICE.get(preferenze.genere)
    tipo = _TIPO_CODICE.get(preferenze.tipo)
    preferiti = [tutti[i] for i in preferenze.personaggi if i in tutti]
    if preferiti:
        del_genere = [p for p in preferiti if codice is None or p.genere == codice]
        return rng.choice(del_genere or preferiti)
    if codice is None:
        return None
    candidati = [p for p in tutti.values() if p.genere == codice and (tipo is None or p.tipo == tipo)]
    return rng.choice(candidati) if candidati else None


def voce_con_preferenze(voce: Voce, preferenze: Preferenze, rng: random.Random) -> Voce:
    """
    La voce con la ricerca adattata alle preferenze (vale solo per le fonti che cercano testo: Giphy). La voce
    nuova ha un id suo, così la cache non mescola le GIF di persone diverse. Senza preferenze torna la stessa voce.
    """
    if preferenze.vuote or not voce.ricerca:
        return voce
    parti = [voce.ricerca]
    personaggio = personaggio_per(preferenze, rng)
    if personaggio is not None:
        parti.insert(0, personaggio.nome)
    if preferenze.tipo == "anime" and "anime" not in voce.ricerca.casefold():
        parti.append("anime")
    elif preferenze.tipo == "non_anime":
        parti.append("-anime")
    ricerca = " ".join(parti)[:50]
    if not categoria_sfw(ricerca):
        return voce
    impronta = hashlib.sha1(ricerca.casefold().encode("utf-8")).hexdigest()[:10]
    return replace(voce, id=f"{voce.id}~{impronta}", ricerca=ricerca)


def preferenze_da_riga(riga) -> Preferenze:
    if riga is None:
        return Preferenze()
    genere = riga["genere"] if riga["genere"] in GENERI else "qualsiasi"
    tipo = riga["tipo"] if riga["tipo"] in TIPI else "entrambi"
    return Preferenze(genere, tipo, tuple(i for i in riga["personaggi"] if i in catalogo())[:MAX_PREFERITI])
