"""
core/sfondi_pronti.py
=====================
Sfondi pronti per la rank card e il profilo (LIV-053): sfumature disegnate con Pillow, senza file esterni. Il risultato
è uno sfondo come quello che si carica a mano (JPEG della misura di `LATO_SFONDO`, sotto `MAX_BYTE_SFONDO`).
Funzioni coperte: LIV-053
Dipende da: core/rank_card_image.py
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

from core.rank_card_image import LATO_SFONDO, MAX_BYTE_SFONDO

# id -> (nome, colore in alto, colore in basso)
_DEFINIZIONI: dict[str, tuple[str, tuple[int, int, int], tuple[int, int, int]]] = {
    "notte": ("Notte profonda", (12, 14, 38), (44, 30, 84)),
    "tramonto": ("Tramonto", (255, 140, 66), (120, 30, 90)),
    "oceano": ("Oceano", (8, 60, 110), (14, 150, 160)),
    "foresta": ("Foresta", (10, 50, 34), (74, 130, 70)),
    "ciliegio": ("Ciliegio", (255, 190, 210), (170, 60, 110)),
    "brace": ("Brace", (40, 8, 8), (200, 60, 20)),
    "ghiaccio": ("Ghiaccio", (200, 235, 255), (70, 120, 190)),
    "grafite": ("Grafite", (30, 32, 36), (90, 96, 104)),
}

SFONDI_PRONTI: dict[str, str] = {id_sfondo: d[0] for id_sfondo, d in _DEFINIZIONI.items()}


def disegna_sfondo_pronto(id_sfondo: str) -> bytes:
    """JPEG dello sfondo scelto; KeyError se l'id non esiste. Lavoro di Pillow: va chiamato fuori dal ciclo principale."""
    _, alto, basso = _DEFINIZIONI[id_sfondo]
    larghezza, altezza = LATO_SFONDO
    immagine = Image.new("RGB", LATO_SFONDO, alto)
    disegno = ImageDraw.Draw(immagine)
    for y in range(altezza):
        t = y / max(1, altezza - 1)
        colore = tuple(round(a + (b - a) * t) for a, b in zip(alto, basso))
        disegno.line([(0, y), (larghezza, y)], fill=colore)
    # Una luce morbida in un angolo, perché la sfumatura sola è piatta.
    luce = Image.new("RGB", LATO_SFONDO, (255, 255, 255))
    maschera = Image.radial_gradient("L").resize(LATO_SFONDO).point(lambda v: max(0, 70 - v // 2))
    immagine = Image.composite(luce, immagine, maschera)
    for qualita in (88, 75, 60, 45):
        buffer = io.BytesIO()
        immagine.save(buffer, format="JPEG", quality=qualita, optimize=True)
        if buffer.tell() <= MAX_BYTE_SFONDO:
            return buffer.getvalue()
    raise ValueError("Sfondo troppo pesante.")  # non succede con sfumature: lo vede il test
