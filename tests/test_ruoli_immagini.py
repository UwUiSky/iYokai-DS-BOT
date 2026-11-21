"""
tests/test_ruoli_immagini.py
============================
RUO-053 / RUO-012 (#123, D74): le immagini si salvano solo ricodificate da core/safe_image.
"""

import io

import pytest
from PIL import Image, UnidentifiedImageError

from core.ruoli_immagini import ricodifica_per_menu
from core.safe_image import ImmagineTroppoGrande


def _png(w=40, h=30):
    b = io.BytesIO()
    Image.new("RGBA", (w, h), (200, 10, 10, 255)).save(b, "PNG")
    return b.getvalue()


def test_RUO_053_esce_una_copia_nuova_non_l_originale():
    # RUO-053
    originale = _png()
    copia = ricodifica_per_menu(originale)
    assert Image.open(io.BytesIO(copia)).size == (40, 30)


def test_RUO_053_i_metadati_dell_originale_non_passano():
    # RUO-053
    from PIL import PngImagePlugin

    info = PngImagePlugin.PngInfo()
    info.add_text("segreto", "posizione-gps")
    b = io.BytesIO()
    Image.new("RGB", (10, 10)).save(b, "PNG", pnginfo=info)
    assert b"posizione-gps" in b.getvalue()
    assert b"posizione-gps" not in ricodifica_per_menu(b.getvalue())


def test_RUO_053_una_immagine_grande_si_riduce():
    # RUO-053
    copia = ricodifica_per_menu(_png(3000, 100))
    assert max(Image.open(io.BytesIO(copia)).size) <= 1280


def test_RUO_053_un_file_che_non_e_un_immagine_si_rifiuta():
    # RUO-053
    with pytest.raises(UnidentifiedImageError):
        ricodifica_per_menu(b"<svg>non sono un'immagine</svg>")


def test_RUO_053_troppi_pixel_si_rifiutano():
    # RUO-053
    b = io.BytesIO()
    Image.new("1", (5000, 5000)).save(b, "PNG")
    with pytest.raises(ImmagineTroppoGrande):
        ricodifica_per_menu(b.getvalue())
