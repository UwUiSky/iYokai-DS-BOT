"""
core/boss_image.py
==================
Immagine dell'annuncio del World Boss, disegnata con Pillow (non dall'AI): sfondo a colori
del tema, nome del mostro, aspetto e barra della vita. Funzione sincrona, da eseguire fuori
dal ciclo principale (`core.safe_image.run_image_task`).
Funzioni coperte: SPEC §25.64 (AI-R-070)
Dipende da: core/rank_card_image.py (font), core/safe_image.py (limiti)
"""

from __future__ import annotations

import io
import textwrap

from PIL import Image, ImageDraw

from core.rank_card_image import carica_font, senza_quadrati

LARGHEZZA, ALTEZZA = 800, 300
MAX_BYTE = 10 * 1024 * 1024
COLORI_TEMA: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "yokai": ((60, 20, 50), (150, 40, 60)),
    "fantasy": ((30, 40, 80), (120, 70, 150)),
    "cyberpunk": ((10, 10, 40), (0, 140, 160)),
    "horror": ((10, 10, 10), (90, 10, 10)),
    "spazio": ((5, 10, 35), (60, 40, 120)),
    "pirati": ((15, 45, 70), (160, 110, 40)),
}


def _sfondo(tema: str | None) -> Image.Image:
    alto, basso = COLORI_TEMA.get(tema or "", COLORI_TEMA["yokai"])
    immagine = Image.new("RGB", (LARGHEZZA, ALTEZZA), alto)
    pennello = ImageDraw.Draw(immagine)
    for y in range(ALTEZZA):
        t = y / (ALTEZZA - 1)
        pennello.line([(0, y), (LARGHEZZA, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(alto, basso)))
    return immagine


def disegna_boss(nome: str, aspetto: str, vita: int, vita_max: int, tema: str | None = None) -> bytes:
    """PNG dell'annuncio (800x300). Testi senza caratteri che il font non sa disegnare."""
    immagine = _sfondo(tema)
    pennello = ImageDraw.Draw(immagine)
    titolo, corpo, piccolo = carica_font(48), carica_font(22), carica_font(20)
    pennello.text((40, 30), senza_quadrati(nome, titolo)[:30], font=titolo, fill=(255, 255, 255))
    riga_y = 100
    for riga in textwrap.wrap(senza_quadrati(aspetto, corpo), 52)[:4]:
        pennello.text((40, riga_y), riga, font=corpo, fill=(235, 235, 235))
        riga_y += 30
    x0, y0, x1, y1 = 40, 240, LARGHEZZA - 40, 270
    pennello.rounded_rectangle((x0, y0, x1, y1), radius=8, fill=(30, 30, 30), outline=(255, 255, 255), width=2)
    quota = 0 if vita_max <= 0 else max(0.0, min(1.0, vita / vita_max))
    if quota > 0:
        pennello.rounded_rectangle((x0 + 2, y0 + 2, x0 + 2 + (x1 - x0 - 4) * quota, y1 - 2), radius=6, fill=(220, 60, 60))
    pennello.text((x0, y0 - 28), f"Vita {max(0, vita)}/{vita_max}", font=piccolo, fill=(255, 255, 255))
    uscita = io.BytesIO()
    immagine.save(uscita, format="PNG", optimize=True)
    dati = uscita.getvalue()
    if len(dati) > MAX_BYTE:  # non succede con 800x300, ma il limite si controlla
        raise ValueError("Immagine del boss troppo grande.")
    return dati
