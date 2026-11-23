"""
core/tela_image.py
==================
Disegna la tela di pixel (o una zona ingrandita) come PNG, con i numeri delle coordinate ai margini. Lavoro Pillow:
si chiama sempre con `run_image_task`, mai nel ciclo principale. In ingresso solo caselle già validate dal database.
Funzioni coperte: FUN-013, FUN-014
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

from core import tela_logic as tl

MARGINE = 28
SFONDO = (7, 7, 11)
TESTO = (138, 134, 128)
GRIGLIA = (42, 41, 40)


def disegna(caselle: list[tuple[int, int, int]], x0: int, y0: int, lato: int) -> bytes:
    """`caselle`: (x, y, colore) dentro la zona. Le caselle non elencate sono vuote."""
    if lato not in tl.ZOOM.values() or not (0 <= x0 <= tl.LATO - lato and 0 <= y0 <= tl.LATO - lato):
        raise ValueError("Zona non valida.")
    base = Image.new("RGB", (lato, lato), tl.rgb(0))
    px = base.load()
    for x, y, colore in caselle:
        if x0 <= x < x0 + lato and y0 <= y < y0 + lato and tl.colore_valido(colore):
            px[x - x0, y - y0] = tl.rgb(colore)
    s = tl.scala(lato)
    ingrandita = base.resize((lato * s, lato * s), Image.NEAREST)
    pennello = ImageDraw.Draw(ingrandita)
    if s >= 16:  # griglia leggera solo quando le caselle sono grandi
        for i in range(1, lato):
            pennello.line([(i * s, 0), (i * s, lato * s)], fill=GRIGLIA)
            pennello.line([(0, i * s), (lato * s, i * s)], fill=GRIGLIA)
    tela = Image.new("RGB", (lato * s + MARGINE, lato * s + MARGINE), SFONDO)
    tela.paste(ingrandita, (MARGINE, MARGINE))
    pennello = ImageDraw.Draw(tela)
    font = ImageFont.load_default()
    passo = 10 if lato == tl.LATO else 5 if lato >= 25 else 1
    for i in range(0, lato, passo):
        pennello.text((MARGINE + i * s + 2, 8), str(x0 + i), fill=TESTO, font=font)
        pennello.text((2, MARGINE + i * s + 2), str(y0 + i), fill=TESTO, font=font)
    fuori = io.BytesIO()
    tela.save(fuori, format="PNG", optimize=True)
    return fuori.getvalue()
