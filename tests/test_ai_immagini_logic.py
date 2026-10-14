"""
tests/test_ai_immagini_logic.py
===============================
Ingrandimento locale (SPEC §25.61, §25.62): raddoppia i lati, rispetta il lato
massimo, rifiuta un file che non è un'immagine, resta sotto 10 MiB.
"""

import io

import pytest
from PIL import Image

from core.ai_immagini_logic import MAX_BYTES, MAX_LATO, ImmagineNonValida, ingrandisci


def _png(lato_x, lato_y, modo="RGB"):
    buf = io.BytesIO()
    Image.new(modo, (lato_x, lato_y), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


def test_raddoppia():
    dati, est = ingrandisci(_png(20, 10))
    assert est == "png" and Image.open(io.BytesIO(dati)).size == (40, 20)


def test_trasparenza_e_lato_massimo():
    dati, _ = ingrandisci(_png(3000, 100, "RGBA"))
    img = Image.open(io.BytesIO(dati))
    assert img.size[0] == MAX_LATO and img.mode == "RGBA"
    assert len(dati) <= MAX_BYTES


def test_file_non_valido():
    with pytest.raises(ImmagineNonValida):
        ingrandisci(b"non sono un'immagine")
