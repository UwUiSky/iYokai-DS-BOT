"""
tests/test_meme_logic.py
============================
Test di core/meme_logic.py — immagini VERE generate in memoria.
"""

import io

from PIL import Image

from core.meme_logic import render_meme


def _immagine_di_prova(width: int = 300, height: int = 300) -> bytes:
    img = Image.new("RGB", (width, height), (100, 150, 200))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


class TestRenderMeme:
    def test_restituisce_unimmagine_valida_delle_stesse_dimensioni(self):
        risultato = render_meme(_immagine_di_prova(), top_text="Ciao", bottom_text="Mondo")
        assert risultato is not None
        img = Image.open(io.BytesIO(risultato))
        assert img.size == (300, 300)

    def test_senza_alcun_testo_restituisce_comunque_unimmagine(self):
        risultato = render_meme(_immagine_di_prova())
        assert risultato is not None

    def test_solo_top_text(self):
        assert render_meme(_immagine_di_prova(), top_text="Solo sopra") is not None

    def test_solo_bottom_text(self):
        assert render_meme(_immagine_di_prova(), bottom_text="Solo sotto") is not None

    def test_testo_lungo_va_a_capo_senza_sollevare(self):
        testo_lungo = "Questo è un testo decisamente troppo lungo per una singola riga di meme"
        assert render_meme(_immagine_di_prova(), top_text=testo_lungo) is not None

    def test_immagine_modificata_e_diversa_dall_originale(self):
        originale = _immagine_di_prova()
        risultato = render_meme(originale, top_text="Testo")
        assert risultato != originale

    def test_bytes_non_validi_restituisce_none(self):
        assert render_meme(b"non e' un'immagine", top_text="x") is None
