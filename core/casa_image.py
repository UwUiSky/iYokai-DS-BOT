"""
core/casa_image.py
==================
La casa del `/mondo casa` (ECO-087) come immagine PNG di misura fissa: la stanza 4x3 con ogni mobile posseduto
come tessera con il suo nome, i posti vuoti scuri. Lavoro Pillow: si chiama sempre con `run_image_task`.
Ripiego: `mondo_logic.disegna_casa` (emoji).
Funzioni coperte: ECO-087
Dipende da: core/rank_card_image.py (font), core/mondo_logic.py
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

from core import mondo_logic as ml
from core.rank_card_image import carica_font, senza_quadrati, taglia_al_largo

CELLA = 160
MARGINE = 24
COLONNE = ml.COLONNE_CASA
RIGHE = 3
LARGHEZZA = COLONNE * CELLA + 2 * MARGINE
ALTEZZA = RIGHE * CELLA + 2 * MARGINE
FONDO = (7, 7, 11)  # void
VUOTO = (24, 24, 26)
TESTO = (200, 196, 188)  # pale-ink
BORDO = (42, 41, 40)  # ash
# Un colore tenue per mobile (caldo, mai neon); i mobili sconosciuti restano grigi.
COLORI = {
    "letto": (110, 52, 46), "scrivania": (84, 66, 52), "lampada": (150, 96, 50), "finestra": (58, 74, 88),
    "tatami": (96, 84, 56), "tavolino": (74, 58, 48), "pianta": (52, 82, 60), "libreria": (92, 62, 44),
    "tv": (46, 50, 62), "gatto": (120, 90, 70), "bonsai": (60, 90, 66), "specchio": (84, 88, 96),
}


def render_casa(posseduti: set[str], etichette: dict[str, str]) -> bytes:
    """PNG di misura fissa (LARGHEZZA x ALTEZZA). `etichette`: nome del mobile nella lingua di chi guarda."""
    tela = Image.new("RGB", (LARGHEZZA, ALTEZZA), FONDO)
    d = ImageDraw.Draw(tela)
    font = carica_font(26)
    for nome, (_, _, posto) in ml.MOBILI.items():
        x0, y0 = MARGINE + (posto % COLONNE) * CELLA, MARGINE + (posto // COLONNE) * CELLA
        box = (x0 + 5, y0 + 5, x0 + CELLA - 5, y0 + CELLA - 5)
        if nome not in posseduti:
            d.rounded_rectangle(box, radius=16, fill=VUOTO, outline=BORDO, width=2)
            continue
        d.rounded_rectangle(box, radius=16, fill=COLORI.get(nome, (70, 70, 72)), outline=BORDO, width=2)
        testo = taglia_al_largo(d, senza_quadrati(etichette.get(nome, nome), font), font, CELLA - 24)
        d.text((x0 + CELLA / 2, y0 + CELLA / 2), testo, font=font, fill=TESTO, anchor="mm")
    fuori = io.BytesIO()
    tela.save(fuori, format="PNG", optimize=True)
    return fuori.getvalue()
