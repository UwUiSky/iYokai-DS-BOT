"""
tests/test_image_thumbnail.py
================================
Test di core/image_thumbnail.py con immagini VERE, generate da
Pillow stesso al volo — nessun mock dell'elaborazione immagine,
questi test verificano che l'output sia realmente un'immagine WebP
valida e ridimensionata, non solo che la funzione non sollevi.
"""

import io

import pytest
from PIL import Image

from core.image_thumbnail import generate_thumbnail
from core.image_thumbnail_logic import THUMBNAIL_MAX_DIMENSION


def _make_image_bytes(width: int, height: int, mode: str = "RGB", fmt: str = "PNG") -> bytes:
    colore = (255, 0, 0, 128) if mode == "RGBA" else (255, 0, 0)
    img = Image.new(mode, (width, height), color=colore)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


class TestGenerateThumbnail:
    def test_immagine_valida_produce_bytes_webp_veri(self):
        originale = _make_image_bytes(800, 600)
        risultato = generate_thumbnail(originale)

        assert risultato is not None
        # Riapriamo il risultato con Pillow stesso: se non fosse un
        # WebP valido, Image.open() solleverebbe qui.
        with Image.open(io.BytesIO(risultato)) as img:
            assert img.format == "WEBP"

    def test_immagine_grande_viene_ridimensionata(self):
        originale = _make_image_bytes(2000, 1000)
        risultato = generate_thumbnail(originale)

        with Image.open(io.BytesIO(risultato)) as img:
            # Proporzioni 2:1 mantenute, lato più lungo (larghezza)
            # non supera il massimo configurato.
            assert img.width <= THUMBNAIL_MAX_DIMENSION
            assert img.height <= THUMBNAIL_MAX_DIMENSION
            assert img.width == 2 * img.height  # proporzioni conservate

    def test_immagine_piccola_non_viene_ingrandita(self):
        # thumbnail() di Pillow non ingrandisce mai un'immagine più
        # piccola del limite — verifichiamo che questo comportamento
        # (di libreria, non nostro) sia davvero quello che otteniamo.
        originale = _make_image_bytes(50, 50)
        risultato = generate_thumbnail(originale)

        with Image.open(io.BytesIO(risultato)) as img:
            assert img.width == 50
            assert img.height == 50

    def test_immagine_con_trasparenza_rgba_gestita(self):
        originale = _make_image_bytes(100, 100, mode="RGBA")
        risultato = generate_thumbnail(originale)

        assert risultato is not None
        with Image.open(io.BytesIO(risultato)) as img:
            assert img.format == "WEBP"

    def test_immagine_palette_gif_gestita(self):
        # Una GIF usa la modalità "P" (palette) — punto esplicito nel
        # commento del codice sorgente: verifichiamo che sia davvero
        # gestita, non solo assunto.
        originale = _make_image_bytes(100, 100, mode="P", fmt="GIF")
        risultato = generate_thumbnail(originale)

        assert risultato is not None
        with Image.open(io.BytesIO(risultato)) as img:
            assert img.format == "WEBP"

    def test_bytes_non_immagine_restituisce_none_non_solleva(self):
        risultato = generate_thumbnail(b"questo non e' assolutamente un'immagine")
        assert risultato is None

    def test_bytes_vuoti_restituisce_none_non_solleva(self):
        risultato = generate_thumbnail(b"")
        assert risultato is None

    def test_dimensione_massima_personalizzata(self):
        originale = _make_image_bytes(1000, 1000)
        risultato = generate_thumbnail(originale, max_dimension=100)

        with Image.open(io.BytesIO(risultato)) as img:
            assert img.width <= 100
            assert img.height <= 100

    def test_output_e_sempre_piu_piccolo_o_uguale_alloriginale(self):
        # Sanity check generale: la thumbnail non deve mai essere più
        # pesante del file originale per un caso semplice come questo.
        originale = _make_image_bytes(1500, 1500)
        risultato = generate_thumbnail(originale)
        assert len(risultato) < len(originale)
