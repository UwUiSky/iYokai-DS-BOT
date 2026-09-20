"""
core/server_stats_image.py
=============================
Rendering VERO del grafico di crescita giornaliera (SPEC.md §14.18)
— stesso principio di core/image_thumbnail.py: Pillow è sincrono e
CPU-bound, il chiamante lo esegue in asyncio.to_thread, non qui
dentro. Barre disegnate a mano con ImageDraw invece di aggiungere
matplotlib come nuova dipendenza — un grafico a barre semplice non ha
bisogno di una libreria di plotting completa, e matplotlib
trascinerebbe numpy con sé su una macchina già limitata (Oracle Free
Tier, vedi PROGRESS.md).
"""

from __future__ import annotations

import io
from datetime import date

from PIL import Image, ImageDraw, ImageFont

WIDTH_PER_DAY = 40
CHART_HEIGHT = 300
MARGIN = 40
COLOR_POSITIVE = (67, 181, 129)   # verde Discord
COLOR_NEGATIVE = (240, 71, 71)    # rosso Discord
COLOR_ZERO = (114, 118, 125)      # grigio neutro
COLOR_BACKGROUND = (47, 49, 54)   # sfondo scuro Discord
COLOR_TEXT = (220, 221, 222)


def render_growth_chart(daily_counts: dict[date, int], title: str = "Crescita membri") -> bytes:
    """
    Un giorno per barra, ordinati cronologicamente. Barre verdi sopra
    la linea dello zero (crescita netta quel giorno), rosse sotto
    (calo netto), grigie se il netto è zero. Restituisce PNG.
    """
    giorni_ordinati = sorted(daily_counts.keys())
    if not giorni_ordinati:
        giorni_ordinati = [date.today()]
        daily_counts = {giorni_ordinati[0]: 0}

    larghezza = max(400, MARGIN * 2 + WIDTH_PER_DAY * len(giorni_ordinati))
    altezza = CHART_HEIGHT

    valore_massimo = max(abs(v) for v in daily_counts.values()) or 1
    zero_y = altezza // 2
    scala = (altezza // 2 - MARGIN) / valore_massimo

    img = Image.new("RGB", (larghezza, altezza), COLOR_BACKGROUND)
    draw = ImageDraw.Draw(img)

    font = ImageFont.load_default()

    draw.text((MARGIN, 10), title, fill=COLOR_TEXT, font=font)
    draw.line([(MARGIN, zero_y), (larghezza - MARGIN, zero_y)], fill=COLOR_TEXT, width=1)

    larghezza_barra = max(4, WIDTH_PER_DAY - 8)
    for indice, giorno in enumerate(giorni_ordinati):
        valore = daily_counts[giorno]
        x_centro = MARGIN + WIDTH_PER_DAY * indice + WIDTH_PER_DAY // 2
        altezza_barra = abs(valore) * scala

        if valore > 0:
            colore = COLOR_POSITIVE
            top = zero_y - altezza_barra
            bottom = zero_y
        elif valore < 0:
            colore = COLOR_NEGATIVE
            top = zero_y
            bottom = zero_y + altezza_barra
        else:
            colore = COLOR_ZERO
            top = zero_y - 1
            bottom = zero_y + 1

        draw.rectangle(
            [x_centro - larghezza_barra // 2, top, x_centro + larghezza_barra // 2, bottom],
            fill=colore,
        )

    # Etichette solo per il primo e l'ultimo giorno — con molti
    # giorni, un'etichetta per barra diventerebbe illeggibile.
    draw.text(
        (MARGIN, altezza - 20), giorni_ordinati[0].isoformat(), fill=COLOR_TEXT, font=font
    )
    if len(giorni_ordinati) > 1:
        ultimo_testo = giorni_ordinati[-1].isoformat()
        draw.text(
            (larghezza - MARGIN - len(ultimo_testo) * 6, altezza - 20),
            ultimo_testo,
            fill=COLOR_TEXT,
            font=font,
        )

    output = io.BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()
