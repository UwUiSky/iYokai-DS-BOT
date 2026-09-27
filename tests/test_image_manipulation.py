"""
tests/test_image_manipulation.py
=====================================
Test di core/image_manipulation.py — immagini VERE generate in
memoria con Pillow (non file su disco), stesso principio di
tests/test_image_thumbnail.py se presente altrove nel progetto.
"""

import io

from PIL import Image

from core.image_manipulation import (
    apply_blur,
    apply_grayscale,
    apply_invert,
    apply_pixelate,
)


def _immagine_di_prova(width: int = 100, height: int = 100, color=(255, 0, 0)) -> bytes:
    img = Image.new("RGB", (width, height), color)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


class TestApplyGrayscale:
    def test_restituisce_bytes_validi(self):
        risultato = apply_grayscale(_immagine_di_prova())
        assert risultato is not None
        img = Image.open(io.BytesIO(risultato))
        assert img.size == (100, 100)

    def test_immagine_grigia_ha_canali_rgb_uguali_per_pixel(self):
        risultato = apply_grayscale(_immagine_di_prova(color=(200, 50, 10)))
        img = Image.open(io.BytesIO(risultato))
        r, g, b = img.getpixel((0, 0))
        assert r == g == b

    def test_bytes_non_validi_restituisce_none(self):
        assert apply_grayscale(b"non sono affatto un'immagine") is None


class TestApplyInvert:
    def test_inverte_i_colori(self):
        risultato = apply_invert(_immagine_di_prova(color=(255, 0, 0)))
        img = Image.open(io.BytesIO(risultato))
        assert img.getpixel((0, 0)) == (0, 255, 255)

    def test_bytes_non_validi_restituisce_none(self):
        assert apply_invert(b"non valido") is None


class TestApplyBlur:
    def test_restituisce_unimmagine_valida_delle_stesse_dimensioni(self):
        risultato = apply_blur(_immagine_di_prova())
        img = Image.open(io.BytesIO(risultato))
        assert img.size == (100, 100)

    def test_raggio_fuori_range_viene_limitato_non_solleva(self):
        assert apply_blur(_immagine_di_prova(), radius=9999) is not None
        assert apply_blur(_immagine_di_prova(), radius=-5) is not None

    def test_bytes_non_validi_restituisce_none(self):
        assert apply_blur(b"non valido") is None


class TestApplyPixelate:
    def test_restituisce_unimmagine_valida_delle_stesse_dimensioni(self):
        risultato = apply_pixelate(_immagine_di_prova())
        img = Image.open(io.BytesIO(risultato))
        assert img.size == (100, 100)

    def test_block_size_fuori_range_viene_limitato_non_solleva(self):
        assert apply_pixelate(_immagine_di_prova(), block_size=9999) is not None
        assert apply_pixelate(_immagine_di_prova(), block_size=0) is not None

    def test_bytes_non_validi_restituisce_none(self):
        assert apply_pixelate(b"non valido") is None
