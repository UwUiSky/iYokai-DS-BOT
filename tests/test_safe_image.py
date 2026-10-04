"""
tests/test_safe_image.py
============================
Test di core/safe_image.py — SEC-11 (immagini "bomba"): un'immagine
con dimensioni dichiarate enormi ma un file piccolo su disco (una
tinta unita si comprime benissimo) deve essere rifiutata PRIMA che
Pillow decomprima i pixel in RAM, e non più di 2 elaborazioni Pillow
insieme in tutto il processo.

SEC-20: limite a 16 megapixel dichiarati, riduzione a 2048 px di lato
massimo già all'apertura (prima di qualsiasi filtro), memoria misurata
in un processo vero sulla più grande immagine accettata, e una corsia
separata per le miniature dello spam-trap.
"""

import asyncio
import io
import subprocess
import sys
import textwrap
import threading
from pathlib import Path
from unittest.mock import create_autospec

import pytest
from PIL import Image

import core.safe_image as safe_image
from core.safe_image import (
    MAX_IMAGE_BYTES,
    MAX_PIXELS,
    ImmagineTroppoGrande,
    run_image_task,
    run_spam_trap_image_task,
    safe_open_image,
)


@pytest.fixture(autouse=True)
def semafori_nuovi(monkeypatch):
    """
    Un asyncio.Semaphore che ha già fatto aspettare qualcuno resta
    legato a quell'event loop; ogni test ha il suo loop, quindi qui i
    semafori di modulo vengono sostituiti con due nuovi.
    """
    monkeypatch.setattr(safe_image, "_SEMAFORO_FUN", asyncio.Semaphore(2))
    monkeypatch.setattr(safe_image, "_SEMAFORO_SPAM_TRAP", asyncio.Semaphore(1))


def _immagine_bomba_bytes() -> bytes:
    # 8000x8000 = 64.000.000 di pixel dichiarati (> MAX_PIXELS), ma
    # una tinta unita comprime a pochi KB su disco — esattamente il
    # caso "file piccolo, dimensioni enormi" di REVIEW.md SEC-11.
    img = Image.new("RGB", (8000, 8000), (10, 20, 30))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _immagine_bytes(
    larghezza: int, altezza: int, mode: str = "RGB", formato: str = "PNG", **opzioni
) -> bytes:
    if formato == "PNG":
        opzioni.setdefault("compress_level", 1)
    img = Image.new(mode, (larghezza, altezza))
    buffer = io.BytesIO()
    img.save(buffer, format=formato, **opzioni)
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


class TestLimiteMegapixel:
    def test_un_png_da_39_7_megapixel_viene_rifiutato(self):
        # SEC-20: 6300x6300 passava il vecchio limite di 40 milioni di
        # pixel e un solo filtro arrivava a circa 470 MB.
        with pytest.raises(ImmagineTroppoGrande):
            safe_open_image(_immagine_bytes(6300, 6300))

    def test_sedici_megapixel_esatti_sono_accettati(self):
        img = safe_open_image(_immagine_bytes(4000, 4000))
        assert max(img.size) <= 2048

    def test_un_pixel_oltre_i_sedici_megapixel_viene_rifiutato(self):
        with pytest.raises(ImmagineTroppoGrande):
            safe_open_image(_immagine_bytes(4001, 4000))

    @pytest.mark.parametrize(
        "formato,opzioni", [("WEBP", {}), ("JPEG", {"progressive": True})]
    )
    def test_webp_e_jpeg_progressivi_hanno_un_quarto_del_limite(self, formato, opzioni):
        # Il loro decoder usa 3-4 volte la memoria degli altri formati.
        accettata = _immagine_bytes(2000, 2000, formato=formato, **opzioni)
        rifiutata = _immagine_bytes(2001, 2000, formato=formato, **opzioni)

        assert safe_open_image(accettata).size == (2000, 2000)
        with pytest.raises(ImmagineTroppoGrande):
            safe_open_image(rifiutata)


class TestFormatiAmmessi:
    @pytest.mark.parametrize("formato", ["PNG", "JPEG", "GIF", "WEBP", "BMP"])
    def test_i_formati_di_discord_si_aprono(self, formato):
        assert safe_open_image(_immagine_bytes(64, 48, formato=formato)).size == (64, 48)

    @pytest.mark.parametrize("formato", ["TIFF", "ICO", "PPM"])
    def test_gli_altri_formati_sono_rifiutati_anche_se_piccoli(self, formato):
        from core.image_manipulation import apply_grayscale
        from core.image_thumbnail import generate_thumbnail

        dati = _immagine_bytes(64, 48, formato=formato)

        with pytest.raises(Image.UnidentifiedImageError):
            safe_open_image(dati)
        # I chiamanti lo trattano come qualunque immagine non valida.
        assert apply_grayscale(dati) is None
        assert generate_thumbnail(dati) is None


class TestRiduzioneAllApertura:
    @pytest.mark.parametrize("mode,formato", [("RGB", "PNG"), ("RGBA", "PNG"), ("RGB", "JPEG")])
    def test_il_lato_piu_lungo_non_supera_2048(self, mode, formato):
        img = safe_open_image(_immagine_bytes(4000, 1000, mode=mode, formato=formato))
        assert img.size == (2048, 512)
        assert img.mode == mode

    def test_un_immagine_piccola_resta_com_e(self):
        img = safe_open_image(_immagine_bytes(300, 200))
        assert img.size == (300, 200)

    def test_il_lato_massimo_si_puo_abbassare(self):
        img = safe_open_image(_immagine_bytes(1000, 500), max_side=100)
        assert img.size == (100, 50)

    def test_la_trasparenza_sopravvive_alla_riduzione(self):
        # Metà sinistra opaca rossa, metà destra del tutto trasparente.
        originale = Image.new("RGBA", (4000, 1000), (0, 0, 0, 0))
        originale.paste((255, 0, 0, 255), (0, 0, 2000, 1000))
        buffer = io.BytesIO()
        originale.save(buffer, format="PNG", compress_level=1)

        img = safe_open_image(buffer.getvalue())

        assert img.getpixel((100, 100)) == (255, 0, 0, 255)
        assert img.getpixel((2000, 100))[3] == 0

    def test_i_filtri_lavorano_sull_immagine_gia_ridotta(self):
        from core.image_manipulation import apply_blur
        from core.meme_logic import render_meme

        dati = _immagine_bytes(4000, 2000)

        for risultato in (apply_blur(dati, 5), render_meme(dati, "sopra", "sotto")):
            assert Image.open(io.BytesIO(risultato)).size == (2048, 1024)


# Eseguito in un processo figlio: misura di quanto sale il picco di
# memoria residente (VmHWM) eseguendo i lavori immagine indicati, uno
# dopo l'altro, sulla stessa immagine. tracemalloc non basta: Pillow
# alloca i pixel con malloc.
_SCRIPT_MISURA = textwrap.dedent(
    """
    import sys

    def vm_mb(campo):
        for riga in open("/proc/self/status"):
            if riga.startswith(campo + ":"):
                return int(riga.split()[1]) / 1024

    from core.image_manipulation import apply_blur, apply_grayscale, apply_invert, apply_pixelate
    from core.image_thumbnail import generate_thumbnail
    from core.meme_logic import render_meme

    LAVORI = {
        "blur": lambda dati: apply_blur(dati, 50),
        "pixelate": lambda dati: apply_pixelate(dati, 2),
        "grayscale": apply_grayscale,
        "invert": apply_invert,
        "meme": lambda dati: render_meme(dati, "sopra " * 10, "sotto " * 10),
        "miniatura": generate_thumbnail,
    }

    dati = open(sys.argv[1], "rb").read()
    base = vm_mb("VmRSS")
    for nome in sys.argv[2].split(","):
        assert LAVORI[nome](dati) is not None, nome
    print(vm_mb("VmHWM") - base)
    """
)

_TUTTI_I_LAVORI = "blur,pixelate,grayscale,invert,meme,miniatura"


def _picco_mb(tmp_path, dati: bytes, lavori: str) -> float:
    sorgente = tmp_path / "immagine"
    sorgente.write_bytes(dati)
    esito = subprocess.run(
        [sys.executable, "-c", _SCRIPT_MISURA, str(sorgente), lavori],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=Path(__file__).resolve().parent.parent,
    )
    assert esito.returncode == 0, esito.stderr
    return float(esito.stdout.strip())


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="usa /proc/self/status")
class TestMemoriaSullImmaginePiuGrandeAccettata:
    # La più grande immagine accettata per ogni tipo di decodifica, nel
    # modo più pesante in memoria.
    @pytest.mark.parametrize(
        "lato,mode,formato,opzioni",
        [
            (4000, "RGBA", "PNG", {}),
            (4000, "RGB", "JPEG", {}),
            (2000, "CMYK", "JPEG", {"progressive": True, "subsampling": 0}),
            (2000, "RGBA", "WEBP", {}),
        ],
        ids=["png-rgba-16MP", "jpeg-16MP", "jpeg-progressivo-4MP", "webp-4MP"],
    )
    def test_il_picco_di_ogni_lavoro_resta_sotto_150_mb(
        self, tmp_path, lato, mode, formato, opzioni
    ):
        dati = _immagine_bytes(lato, lato, mode=mode, formato=formato, **opzioni)
        assert len(dati) <= MAX_IMAGE_BYTES, "deve passare anche il limite sui byte"

        picco = _picco_mb(tmp_path, dati, _TUTTI_I_LAVORI)

        assert picco < 150, f"picco di {picco:.0f} MB per un solo lavoro immagine"

    def test_la_miniatura_di_un_jpeg_grande_non_decodifica_l_immagine_intera(self, tmp_path):
        # Decodificare 16 megapixel costa 64 MB: con la riduzione fatta
        # dal decoder JPEG la miniatura dello spam-trap ne usa una frazione.
        dati = _immagine_bytes(4000, 4000, formato="JPEG")

        picco = _picco_mb(tmp_path, dati, "miniatura")

        assert picco < 30, f"picco di {picco:.0f} MB per una miniatura"


def _allegato_png():
    import discord

    contenuto = _immagine_normale_bytes()
    allegato = create_autospec(discord.Attachment, instance=True)
    allegato.filename = "foto.png"
    allegato.content_type = "image/png"
    allegato.size = len(contenuto)
    allegato.read.return_value = contenuto
    return allegato


class _LavoriFermi:
    """Occupa i due posti dei comandi /fun con lavori che non finiscono."""

    def __init__(self) -> None:
        self._sblocca = threading.Event()
        self._partiti = [threading.Event(), threading.Event()]
        self._task: list[asyncio.Task] = []

    def _lavoro(self, indice: int) -> None:
        self._partiti[indice].set()
        self._sblocca.wait(timeout=10)

    async def __aenter__(self) -> "_LavoriFermi":
        self._task = [asyncio.create_task(run_image_task(self._lavoro, i)) for i in range(2)]
        while not all(evento.is_set() for evento in self._partiti):
            await asyncio.sleep(0.01)
        return self

    async def __aexit__(self, *exc) -> None:
        self._sblocca.set()
        await asyncio.gather(*self._task)


class TestCorsiaSeparataPerLoSpamTrap:
    # SEC-20: con i due posti di /fun occupati, lo spam-trap deve
    # lavorare lo stesso — altrimenti un'ondata di /fun ritarda i ban.

    @pytest.mark.asyncio
    async def test_un_lavoro_dello_spam_trap_non_aspetta_i_comandi_fun(self):
        async with _LavoriFermi():
            esito = await asyncio.wait_for(
                run_spam_trap_image_task(lambda x: x * 2, 21), timeout=3
            )

        assert esito == 42

    @pytest.mark.asyncio
    async def test_le_miniature_degli_allegati_non_aspettano_i_comandi_fun(self):
        from cogs.security.spam_trap import SpamTrapCog

        async with _LavoriFermi():
            miniature = await asyncio.wait_for(
                SpamTrapCog(bot=None)._build_thumbnails([_allegato_png()]), timeout=3
            )

        assert len(miniature) == 1

    @pytest.mark.asyncio
    async def test_la_miniatura_dell_avatar_non_aspetta_i_comandi_fun(self):
        import discord

        from cogs.security.spam_trap import SpamTrapCog

        utente = create_autospec(discord.User, instance=True)
        utente.display_avatar = create_autospec(discord.Asset, instance=True)
        utente.display_avatar.read.return_value = _immagine_normale_bytes()

        async with _LavoriFermi():
            avatar = await asyncio.wait_for(
                SpamTrapCog(bot=None)._build_author_avatar(utente), timeout=3
            )

        assert avatar.startswith("data:image/webp;base64,")

    @pytest.mark.asyncio
    async def test_lo_spam_trap_elabora_una_miniatura_alla_volta(self):
        in_corso = 0
        massimo_osservato = 0
        lock = threading.Lock()

        def lavoro_lento():
            nonlocal in_corso, massimo_osservato
            with lock:
                in_corso += 1
                massimo_osservato = max(massimo_osservato, in_corso)
            threading.Event().wait(0.05)
            with lock:
                in_corso -= 1

        await asyncio.gather(*(run_spam_trap_image_task(lavoro_lento) for _ in range(4)))

        assert massimo_osservato == 1
