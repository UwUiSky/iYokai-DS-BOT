"""
core/bingo_image.py
===================
La cartella del bingo (ECO-112) come immagine PNG di misura fissa: 3 righe da 5 numeri, quelli usciti cerchiati,
le righe complete evidenziate. Lavoro Pillow: si chiama sempre con `run_image_task`. Ripiego: `sala_logic.testo_cartella`.
Funzioni coperte: ECO-112
Dipende da: core/rank_card_image.py (font), core/sala_logic.py
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

from core.rank_card_image import carica_font
from core.sala_logic import COLONNE_CARTELLA, NUMERI_BINGO, RIGHE_CARTELLA

CELLA = 96
MARGINE = 24
LARGHEZZA = COLONNE_CARTELLA * CELLA + 2 * MARGINE
ALTEZZA = RIGHE_CARTELLA * CELLA + 2 * MARGINE
FONDO = (7, 7, 11)  # void
PANNELLO = (42, 41, 40)  # ash
TESTO = (200, 196, 188)  # pale-ink
USCITO = (194, 74, 58)  # cinnabar
RIGA_COMPLETA = (155, 77, 122)  # orchid, uso raro: solo la riga vinta


def render_cartella(cartella: list[list[int]], estratti: set[int]) -> bytes:
    """PNG di misura fissa (LARGHEZZA x ALTEZZA). Numeri fuori da 1..NUMERI_BINGO o forma sbagliata: ValueError."""
    if len(cartella) != RIGHE_CARTELLA or any(len(r) != COLONNE_CARTELLA for r in cartella):
        raise ValueError("Cartella non valida.")
    if any(not 1 <= n <= NUMERI_BINGO for r in cartella for n in r):
        raise ValueError("Numero non valido.")
    tela = Image.new("RGB", (LARGHEZZA, ALTEZZA), FONDO)
    d = ImageDraw.Draw(tela)
    font = carica_font(34)
    for r, riga in enumerate(cartella):
        completa = all(n in estratti for n in riga)
        for c, n in enumerate(riga):
            x0, y0 = MARGINE + c * CELLA, MARGINE + r * CELLA
            box = (x0 + 4, y0 + 4, x0 + CELLA - 4, y0 + CELLA - 4)
            d.rounded_rectangle(box, radius=14, fill=PANNELLO, outline=RIGA_COMPLETA if completa else None, width=3)
            if n in estratti:
                d.ellipse((x0 + 14, y0 + 14, x0 + CELLA - 14, y0 + CELLA - 14), fill=USCITO)
            testo = str(n)
            larghezza = d.textlength(testo, font=font)
            d.text((x0 + (CELLA - larghezza) / 2, y0 + CELLA / 2), testo, font=font, fill=TESTO, anchor="lm")
    fuori = io.BytesIO()
    tela.save(fuori, format="PNG", optimize=True)
    return fuori.getvalue()
