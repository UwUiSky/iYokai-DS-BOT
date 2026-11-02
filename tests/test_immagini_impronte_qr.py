"""
tests/test_immagini_impronte_qr.py
==================================
dHash, lettura dei QR e PNG ricodificato nel processo figlio vero (D62).
"""

import io
import struct
import zlib

import pytest
from PIL import Image, ImageDraw

from core import immagini_impronte as imp
from core import immagini_quarantena as q
from core import immagini_sandbox as sb
from tests.support import immagini_finte as f


def _foto(seme: int, lato: int = 200) -> Image.Image:
    img = Image.new("RGB", (lato, lato), (seme * 20 % 255, 80, 160))
    d = ImageDraw.Draw(img)
    for i in range(6):
        d.ellipse(((i * seme * 13) % lato // 2, (i * 31) % lato // 2, lato - i * 11, lato - i * 17), outline=(255 - i * 30, i * 40, seme * 7 % 255), width=6)
    return img


def test_dhash_uguale_dopo_ridimensionamento_e_ricompressione():
    a = _foto(3)
    b = Image.open(io.BytesIO(f._salva(a.resize((100, 100)), "JPEG", quality=60)))
    assert imp.distanza(imp.dhash(a), imp.dhash(b)) <= imp.DISTANZA_UGUALE


def test_dhash_diverso_per_immagini_diverse():
    assert imp.distanza(imp.dhash(_foto(3)), imp.dhash(_foto(9))) > imp.DISTANZA_SIMILE


def test_dhash_e_64_bit_e_distanza_conta_i_bit():
    h = imp.dhash(_foto(5))
    assert 0 <= h < 2**64
    assert imp.distanza(0b1011, 0b0001) == 2
    assert imp.esito_distanza(0) == "uguale" and imp.esito_distanza(6) == "simile" and imp.esito_distanza(30) == "diversa"


@pytest.fixture
def cartella(tmp_path, monkeypatch):
    monkeypatch.setenv(q.VARIABILE_CARTELLA, str(tmp_path))
    return tmp_path


async def _esegui(cartella, dati: bytes):
    (cartella / ("d" * 32)).write_bytes(dati)
    return await sb.analizza("d" * 32)


@pytest.mark.asyncio
async def test_il_worker_da_dhash_uguale_a_quello_locale(cartella):
    img = _foto(4)
    r = await _esegui(cartella, f._salva(img, "PNG"))
    assert r.riuscita
    assert int(r.info["dhash"], 16) == imp.dhash(img)


@pytest.mark.asyncio
async def test_il_worker_legge_un_qr_con_link_di_login_finto(cartella):
    r = await _esegui(cartella, f.foto_con_qr("https://discord-login.example/nitro-gift?claim=1"))
    assert r.riuscita and r.info["qr"] == ["https://discord-login.example/nitro-gift?claim=1"]


@pytest.mark.asyncio
async def test_immagine_senza_qr_ha_elenco_vuoto(cartella):
    r = await _esegui(cartella, f.png(200, 200))
    assert r.riuscita and r.info["qr"] == []


@pytest.mark.asyncio
async def test_qr_in_un_immagine_grande_si_legge_dopo_la_riduzione(cartella):
    grande = Image.new("RGB", (2400, 2400), (240, 240, 240))
    grande.paste(f.qr("https://esempio.test/x", 900), (700, 700))
    r = await _esegui(cartella, f._salva(grande, "PNG"))
    assert r.riuscita and r.info["qr"] == ["https://esempio.test/x"]


@pytest.mark.asyncio
async def test_png_ricodificato_senza_metadati_e_lato_massimo(cartella):
    grande = Image.new("RGB", (3000, 1500), (10, 90, 200))
    dati = f._salva(grande, "PNG", pnginfo=_con_testo("Comment", "segreto-nascosto"), icc_profile=b"x" * 200)
    r = await _esegui(cartella, dati)
    assert r.riuscita and r.png.startswith(b"\x89PNG")
    nuovo = Image.open(io.BytesIO(r.png))
    assert max(nuovo.size) <= 1024 and nuovo.size[0] == 2 * nuovo.size[1]
    assert nuovo.info.get("icc_profile") is None and "Comment" not in nuovo.text if hasattr(nuovo, "text") else True
    assert b"segreto-nascosto" not in r.png and b"iCCP" not in r.png and b"tEXt" not in r.png


@pytest.mark.asyncio
async def test_png_ricodificato_tiene_la_trasparenza(cartella):
    img = Image.new("RGBA", (30, 30), (255, 0, 0, 0))
    r = await _esegui(cartella, f._salva(img, "PNG"))
    assert Image.open(io.BytesIO(r.png)).mode == "RGBA"


@pytest.mark.asyncio
async def test_gif_animata_da_il_primo_fotogramma(cartella):
    r = await _esegui(cartella, f.gif_animata(4))
    assert r.riuscita and Image.open(io.BytesIO(r.png)).size == (16, 16)


def _con_testo(chiave, valore):
    from PIL import PngImagePlugin

    info = PngImagePlugin.PngInfo()
    info.add_text(chiave, valore)
    return info
