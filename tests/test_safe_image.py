"""
tests/test_safe_image.py
============================
Test di core/safe_image.py — SEC-11 (immagini "bomba"): un'immagine
con dimensioni dichiarate enormi ma un file piccolo su disco (una
tinta unita si comprime benissimo) deve essere rifiutata PRIMA che
Pillow decomprima i pixel in RAM, e non più di 2 elaborazioni Pillow
insieme in tutto il processo.
"""

import asyncio
import io

import pytest
from PIL import Image

from core.safe_image import (
    MAX_PIXELS,
    ImmagineTroppoGrande,
    run_image_task,
    safe_open_image,
)


def _immagine_bomba_bytes() -> bytes:
    # 8000x8000 = 64.000.000 di pixel dichiarati (> MAX_PIXELS), ma
    # una tinta unita comprime a pochi KB su disco — esattamente il
    # caso "file piccolo, dimensioni enormi" di REVIEW.md SEC-11.
    img = Image.new("RGB", (8000, 8000), (10, 20, 30))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _immagine_normale_bytes() -> bytes:
    img = Image.new("RGB", (100, 100), (255, 0, 0))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


class TestMaxImagePixels:
    def test_limite_globale_di_pillow_e_impostato(self):
        assert Image.MAX_IMAGE_PIXELS == MAX_PIXELS


class TestSafeOpenImage:
    def test_immagine_bomba_viene_rifiutata(self):
        with pytest.raises(ImmagineTroppoGrande):
            safe_open_image(_immagine_bomba_bytes())

    def test_immagine_bomba_non_viene_mai_caricata_in_ram(self, monkeypatch):
        # I bytes vanno preparati PRIMA di spiare .load(): crearli
        # (Image.new + .save()) chiama .load() a sua volta per
        # codificare il PNG, il che non è quello sotto test qui.
        dati = _immagine_bomba_bytes()

        # .load() è il punto che decomprime i pixel — non deve mai
        # essere chiamato per un'immagine rifiutata dal controllo
        # sulle dimensioni dichiarate.
        chiamato = False
        originale = Image.Image.load

        def load_spia(self):
            nonlocal chiamato
            chiamato = True
            return originale(self)

        monkeypatch.setattr(Image.Image, "load", load_spia)

        with pytest.raises(ImmagineTroppoGrande):
            safe_open_image(dati)

        assert chiamato is False

    def test_immagine_normale_viene_aperta_e_caricata(self):
        img = safe_open_image(_immagine_normale_bytes())
        assert img.size == (100, 100)

    def test_rispetta_un_limite_personalizzato(self):
        # Un'immagine normale (100x100 = 10.000 pixel) supera un
        # limite personalizzato molto basso.
        with pytest.raises(ImmagineTroppoGrande):
            safe_open_image(_immagine_normale_bytes(), max_pixels=100)


class TestRunImageTask:
    @pytest.mark.asyncio
    async def test_esegue_la_funzione_e_restituisce_il_risultato(self):
        risultato = await run_image_task(lambda x: x * 2, 21)
        assert risultato == 42

    @pytest.mark.asyncio
    async def test_non_piu_di_due_elaborazioni_insieme(self):
        import threading
        import time

        in_corso = 0
        massimo_osservato = 0
        lock = threading.Lock()

        def lavoro_lento():
            # Gira DAVVERO in un thread separato (run_image_task usa
            # asyncio.to_thread): serve un lock di thread, non
            # asyncio.Lock, per contare correttamente quante
            # esecuzioni sono in corso insieme.
            nonlocal in_corso, massimo_osservato
            with lock:
                in_corso += 1
                massimo_osservato = max(massimo_osservato, in_corso)
            time.sleep(0.05)
            with lock:
                in_corso -= 1
            return "fatto"

        risultati = await asyncio.gather(*(run_image_task(lavoro_lento) for _ in range(6)))

        assert risultati == ["fatto"] * 6
        assert massimo_osservato <= 2
