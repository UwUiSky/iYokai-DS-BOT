"""
core/fun_piccoli_logic.py
=========================
Logica pura dei giochi piccoli senza stato (#131, D70, B2): campo minato con spoiler, striscia di monete
(Pillow), classe a caso di un gioco. Nessuna rete, nessun database.
Funzioni coperte: SPEC §16 (FUN-009, 026, 072)
Dipende da: core/safe_image.py, data/giochi_classi.json
"""

from __future__ import annotations

import io
import json
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps

from core.safe_image import safe_open_image

MINA = -1
# Livello -> (lato, mine). 9x9 = 81 celle: sotto i 2000 caratteri di un messaggio.
MINATO_LIVELLI = {"facile": (5, 4), "medio": (7, 9), "difficile": (9, 14)}
_NUMERI = ("⬜", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣")
_EMOJI_MINA = "💥"
MAX_MESSAGGIO = 2000

LATO_MONETA = 128
MAX_MONETE = 10
_DATI = Path(__file__).resolve().parent.parent / "data"
_MONETA_BASE = Path(__file__).resolve().parent.parent / "assets" / "moneta_iyokai.png"


@dataclass
class CampoMinato:
    numeri: list[list[int]]  # MINA oppure il numero di mine vicine
    aperte: list[list[bool]]


def _vicini(x: int, y: int, lato: int):
    for j in range(max(0, y - 1), min(lato, y + 2)):
        for i in range(max(0, x - 1), min(lato, x + 2)):
            if (i, j) != (x, y):
                yield i, j


def crea_minato(difficolta: str, rng: random.Random) -> CampoMinato:
    """Campo con le mine lontane da una cella di partenza; la zona vuota intorno a lei è già aperta."""
    if difficolta not in MINATO_LIVELLI:
        raise ValueError(difficolta)
    lato, mine = MINATO_LIVELLI[difficolta]
    inizio = (rng.randrange(lato), rng.randrange(lato))
    vietate = {inizio, *_vicini(*inizio, lato)}
    libere = [(x, y) for y in range(lato) for x in range(lato) if (x, y) not in vietate]
    numeri = [[0] * lato for _ in range(lato)]
    for x, y in rng.sample(libere, mine):
        numeri[y][x] = MINA
    for y in range(lato):
        for x in range(lato):
            if numeri[y][x] != MINA:
                numeri[y][x] = sum(numeri[j][i] == MINA for i, j in _vicini(x, y, lato))
    aperte = [[False] * lato for _ in range(lato)]
    pila = [inizio]
    while pila:  # la cella di partenza non ha mine vicine: si apre tutta la zona vuota e il suo bordo
        x, y = pila.pop()
        if aperte[y][x]:
            continue
        aperte[y][x] = True
        if numeri[y][x] == 0:
            pila.extend(_vicini(x, y, lato))
    return CampoMinato(numeri, aperte)


def testo_minato(campo: CampoMinato) -> str:
    """Una riga per fila; le celle chiuse sono in spoiler. Sempre sotto MAX_MESSAGGIO caratteri."""
    righe = []
    for numeri, aperte in zip(campo.numeri, campo.aperte):
        righe.append(
            "".join(
                _NUMERI[n] if (aperta and n != MINA) else (f"||{_EMOJI_MINA if n == MINA else _NUMERI[n]}||")
                for n, aperta in zip(numeri, aperte)
            )
        )
    return "\n".join(righe)[:MAX_MESSAGGIO]


def tira_monete(quante: int, rng: random.Random) -> list[str]:
    quante = max(1, min(MAX_MONETE, quante))
    return [rng.choice(("testa", "croce")) for _ in range(quante)]


def striscia_monete(esiti: list[str], moneta: bytes | None = None) -> bytes:
    """
    PNG con una moneta per esito: la testa è la moneta del server, la croce la sua faccia scura e rovesciata.
    Se l'immagine non si apre ricade sulla moneta di iYokai. Pillow è sincrono: va chiamata con run_image_task.
    """
    try:
        base = safe_open_image(moneta).convert("RGBA") if moneta else safe_open_image(_MONETA_BASE.read_bytes()).convert("RGBA")
    except Exception:
        base = safe_open_image(_MONETA_BASE.read_bytes()).convert("RGBA")
    testa = ImageOps.fit(base, (LATO_MONETA, LATO_MONETA), Image.LANCZOS)
    croce = ImageOps.mirror(ImageEnhance.Brightness(testa).enhance(0.55))
    tela = Image.new("RGBA", (LATO_MONETA * len(esiti), LATO_MONETA), (0, 0, 0, 0))
    for i, esito in enumerate(esiti):
        tela.paste(testa if esito == "testa" else croce, (i * LATO_MONETA, 0))
    buffer = io.BytesIO()
    tela.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _carica_classi() -> dict[str, dict]:
    with open(_DATI / "giochi_classi.json", encoding="utf-8") as file:
        return json.load(file)


GIOCHI_CLASSI = _carica_classi()


def classe_a_caso(gioco: str, rng: random.Random) -> str | None:
    voce = GIOCHI_CLASSI.get(gioco)
    return rng.choice(voce["classi"]) if voce else None


def suggerisci_giochi(digitato: str) -> list[tuple[str, str]]:
    """(nome, valore) per il completamento: solo dati locali, al massimo 25."""
    cerca = digitato.strip().lower()
    return [(v["nome"], k) for k, v in GIOCHI_CLASSI.items() if cerca in v["nome"].lower() or cerca in k][:25]
