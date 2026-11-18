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


def render_bar_chart(etichette: list[str], valori: list[int], title: str = "") -> bytes:
    """Barre verticali (ore del giorno, giorni della settimana, messaggi per giorno). PNG, al massimo 2400 px di larghezza."""
    n = max(1, len(valori))
    larghezza = min(2400, max(400, MARGIN * 2 + 30 * n))
    img = Image.new("RGB", (larghezza, CHART_HEIGHT), COLOR_BACKGROUND)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    draw.text((MARGIN, 10), title, fill=COLOR_TEXT, font=font)
    massimo = max(valori, default=0) or 1
    base = CHART_HEIGHT - MARGIN
    altezza_utile = CHART_HEIGHT - 2 * MARGIN - 10
    passo = min(30.0, (larghezza - 2 * MARGIN) / n)
    for i, (etichetta, valore) in enumerate(zip(etichette, valori)):
        x = MARGIN + passo * i
        top = base - altezza_utile * valore / massimo
        draw.rectangle([x + 3, top, x + max(4.0, passo - 6), base], fill=COLOR_POSITIVE if valore else COLOR_ZERO)
        if passo >= 24:  # con tante barre le etichette si sovrapporrebbero
            draw.text((x + 3, base + 6), str(etichetta)[:4], fill=COLOR_TEXT, font=font)
            if valore:
                draw.text((x + 3, top - 12), str(valore), fill=COLOR_TEXT, font=font)
    if passo < 24 and etichette:  # con tante barre solo il primo e l'ultimo giorno
        draw.text((MARGIN, base + 6), str(etichette[0])[:10], fill=COLOR_TEXT, font=font)
        ultima = str(etichette[-1])[:10]
        draw.text((larghezza - MARGIN - len(ultima) * 6, base + 6), ultima, fill=COLOR_TEXT, font=font)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


MAX_LARGHEZZA_LINEE = 1400
COLORI_SERIE = ((67, 181, 129), (240, 71, 71), (88, 101, 242), (250, 166, 26))


def render_line_chart(etichette: list[str], serie: list[tuple[str, list[int]]], title: str = "") -> bytes:
    """Una o più linee (al massimo 4) su un asse comune; larghezza e punti con un tetto. PNG.

    Usata per il totale dei membri, ingressi e uscite insieme, membri online (STA-018, 019, 008).
    """
    serie = serie[:4]
    n = max([len(v) for _, v in serie] + [1])
    larghezza = min(MAX_LARGHEZZA_LINEE, max(400, MARGIN * 2 + 14 * n))
    img = Image.new("RGB", (larghezza, CHART_HEIGHT), COLOR_BACKGROUND)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    draw.text((MARGIN, 10), title[:120], fill=COLOR_TEXT, font=font)
    massimo = max([max(v, default=0) for _, v in serie] + [1])
    minimo = min([min(v, default=0) for _, v in serie] + [0])
    intervallo = (massimo - minimo) or 1
    base = CHART_HEIGHT - MARGIN
    alto = CHART_HEIGHT - 2 * MARGIN - 10
    passo = (larghezza - 2 * MARGIN) / max(1, n - 1)
    draw.line([(MARGIN, base), (larghezza - MARGIN, base)], fill=COLOR_ZERO, width=1)
    for indice, (nome, valori) in enumerate(serie):
        colore = COLORI_SERIE[indice % len(COLORI_SERIE)]
        punti = [(MARGIN + passo * i, base - alto * (v - minimo) / intervallo) for i, v in enumerate(valori)]
        if len(punti) > 1:
            draw.line(punti, fill=colore, width=2)
        elif punti:
            draw.ellipse([punti[0][0] - 3, punti[0][1] - 3, punti[0][0] + 3, punti[0][1] + 3], fill=colore)
        draw.text((MARGIN + 140 * indice, 24), f"{nome[:18]}: {valori[-1] if valori else 0}", fill=colore, font=font)
    if etichette:
        draw.text((MARGIN, CHART_HEIGHT - 20), str(etichette[0])[:12], fill=COLOR_TEXT, font=font)
        if len(etichette) > 1:
            ultima = str(etichette[-1])[:12]
            draw.text((larghezza - MARGIN - len(ultima) * 6, CHART_HEIGHT - 20), ultima, fill=COLOR_TEXT, font=font)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
