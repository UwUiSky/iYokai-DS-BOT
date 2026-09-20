"""
tests/test_server_stats_image.py
====================================
Test di core/server_stats_image.py — Pillow VERO (non mock), stesso
principio già usato per test_spam_trap_thumbnails.py: verifica che
l'immagine prodotta sia davvero apribile e abbia le proprietà attese,
non solo che la funzione non sollevi.
"""

import io
from datetime import date

from PIL import Image

from core.server_stats_image import CHART_HEIGHT, WIDTH_PER_DAY, render_growth_chart


def test_render_produce_un_png_valido():
    dati = {date(2026, 1, 1): 5, date(2026, 1, 2): -2, date(2026, 1, 3): 0}
    risultato = render_growth_chart(dati)

    immagine = Image.open(io.BytesIO(risultato))
    assert immagine.format == "PNG"


def test_larghezza_cresce_con_il_numero_di_giorni():
    pochi_giorni = {date(2026, 1, 1): 1, date(2026, 1, 2): 1}
    molti_giorni = {date(2026, 1, i): 1 for i in range(1, 25)}

    img_pochi = Image.open(io.BytesIO(render_growth_chart(pochi_giorni)))
    img_molti = Image.open(io.BytesIO(render_growth_chart(molti_giorni)))

    assert img_molti.width > img_pochi.width


def test_altezza_e_sempre_quella_fissa():
    dati = {date(2026, 1, 1): 100}
    immagine = Image.open(io.BytesIO(render_growth_chart(dati)))
    assert immagine.height == CHART_HEIGHT


def test_dizionario_vuoto_non_solleva():
    # Un server senza eventi nella finestra richiesta (es. server
    # appena aggiunto) non deve far fallire il comando — un grafico
    # "piatto" con un solo giorno a zero è un esito accettabile.
    risultato = render_growth_chart({})
    immagine = Image.open(io.BytesIO(risultato))
    assert immagine.format == "PNG"


def test_valori_solo_positivi():
    dati = {date(2026, 1, 1): 10, date(2026, 1, 2): 5}
    risultato = render_growth_chart(dati)
    immagine = Image.open(io.BytesIO(risultato))
    assert immagine.format == "PNG"


def test_valori_solo_negativi():
    dati = {date(2026, 1, 1): -10, date(2026, 1, 2): -5}
    risultato = render_growth_chart(dati)
    immagine = Image.open(io.BytesIO(risultato))
    assert immagine.format == "PNG"


def test_un_solo_giorno_non_solleva_divisione_per_larghezza_minima():
    dati = {date(2026, 1, 1): 3}
    risultato = render_growth_chart(dati)
    immagine = Image.open(io.BytesIO(risultato))
    # Con un solo giorno, la larghezza minima (400) deve valere,
    # non 2*MARGIN + WIDTH_PER_DAY che sarebbe più piccola.
    assert immagine.width >= 400
