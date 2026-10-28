"""
core/profile_logic.py
=====================
Profilo personale: il catalogo degli oggetti da collezionare (badge e sfondi, comprati o vinti)
e le regole sul testo di presentazione. Il catalogo è nel codice, uguale per
tutti i server; cosa possiede ciascuno sta in `profile_repo`.
Funzioni coperte: SPEC §23.16 (NF-40)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TIPO_BADGE = "badge"
TIPO_SFONDO = "sfondo"
TIPI = (TIPO_BADGE, TIPO_SFONDO)

MAX_BIO = 140


@dataclass(frozen=True)
class Oggetto:
    id: str
    nome: str
    tipo: str  # badge | sfondo
    rarita: str  # comune | raro | leggendario
    prezzo: int
    emoji: str = ""  # dei badge
    colore: int = 0  # degli sfondi (RGB)
    premio: str = ""  # se c'è, l'oggetto non si compra: lo dà un premio (serie, pass) e dice quale


CATALOGO: tuple[Oggetto, ...] = (
    Oggetto("stella", "Stella", TIPO_BADGE, "comune", 150, emoji="⭐"),
    Oggetto("fiamma", "Fiamma", TIPO_BADGE, "comune", 200, emoji="🔥"),
    Oggetto("gatto", "Gatto", TIPO_BADGE, "comune", 250, emoji="🐱"),
    Oggetto("luna", "Luna", TIPO_BADGE, "comune", 300, emoji="🌙"),
    Oggetto("cuore", "Cuore viola", TIPO_BADGE, "raro", 600, emoji="💜"),
    Oggetto("spada", "Spade incrociate", TIPO_BADGE, "raro", 800, emoji="⚔️"),
    Oggetto("corona", "Corona", TIPO_BADGE, "leggendario", 5000, emoji="👑"),
    Oggetto("drago", "Drago", TIPO_BADGE, "leggendario", 8000, emoji="🐉"),
    Oggetto("tramonto", "Tramonto", TIPO_SFONDO, "comune", 200, colore=0xFF7A59),
    Oggetto("oceano", "Oceano", TIPO_SFONDO, "comune", 200, colore=0x1E90FF),
    Oggetto("foresta", "Foresta", TIPO_SFONDO, "comune", 300, colore=0x2E8B57),
    Oggetto("notte", "Notte profonda", TIPO_SFONDO, "raro", 700, colore=0x2B2D6E),
    Oggetto("aurora", "Aurora", TIPO_SFONDO, "raro", 900, colore=0x7DF9C2),
    Oggetto("oro", "Oro", TIPO_SFONDO, "leggendario", 4000, colore=0xFFD700),
    # Premi solo estetici (SPEC 23.17): non si comprano, li danno la serie di giorni e il pass.
    Oggetto("scintilla", "Scintilla", TIPO_BADGE, "raro", 0, emoji="✨", premio="7 giorni di serie"),
    Oggetto("cometa", "Cometa", TIPO_BADGE, "raro", 0, emoji="☄️", premio="14 giorni di serie"),
    Oggetto("alba", "Alba", TIPO_SFONDO, "raro", 0, colore=0xFFB347, premio="30 giorni di serie"),
    Oggetto("aquila", "Aquila", TIPO_BADGE, "leggendario", 0, emoji="🦅", premio="60 giorni di serie"),
    Oggetto("cosmo", "Cosmo", TIPO_SFONDO, "leggendario", 0, colore=0x4B0082, premio="100 giorni di serie"),
    Oggetto("sigillo", "Sigillo del pass", TIPO_BADGE, "raro", 0, emoji="🏵️", premio="livello 10 del pass premium"),
    Oggetto("zenit", "Zenit", TIPO_SFONDO, "raro", 0, colore=0x00CED1, premio="livello 25 del pass premium"),
    Oggetto("trofeo", "Trofeo del pass", TIPO_BADGE, "leggendario", 0, emoji="🏆", premio="livello 50 del pass premium"),
)
IN_VENDITA = tuple(o for o in CATALOGO if not o.premio)
PER_ID = {o.id: o for o in CATALOGO}
COLORE_DI_BASE = 0x5865F2


def oggetto(id_oggetto: str) -> Oggetto | None:
    return PER_ID.get(id_oggetto)


def pulisci_bio(testo: str) -> str:
    """Testo di presentazione su una riga sola, senza spazi in eccesso, entro MAX_BIO caratteri."""
    una_riga = re.sub(r"\s+", " ", testo).strip()
    return una_riga[:MAX_BIO]


def riga_oggetto(o: Oggetto, posseduto: bool) -> str:
    segno = "✅" if posseduto else (f"premio: {o.premio}" if o.premio else f"{o.prezzo} coin")
    simbolo = o.emoji or "🎨"
    return f"{simbolo} **{o.nome}** ({o.rarita}) — {segno}"
