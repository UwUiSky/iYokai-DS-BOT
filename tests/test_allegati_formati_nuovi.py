"""
tests/test_allegati_formati_nuovi.py
====================================
BMP, TIFF, ICO e AVIF (D74, risposta 3 dell'owner): riconosciuti dai byte, passano dalla sandbox e tornano PNG
rifatto dai soli pixel; file storti o con troppe pagine non fanno cadere nulla e non danno nessuna copia.
Funzioni coperte: SPEC §8.16 (D74, #160)
"""

import struct

import pytest

from core import allegati_tipo_logic as at
from core import immagini_pipeline as pl
from core import immagini_quarantena as q
from core import immagini_sandbox as sb
from core.immagini_byte_logic import PULITA, controlla_byte, riconosci_tipo
from tests.support import immagini_finte as f
from tests.test_immagini_pipeline import ambiente  # noqa: F401 - fixture: DB vero, quarantena in cartella di prova

GUILD = 777000860
NUOVI = [("bmp", f.bmp, "image/bmp"), ("tiff", f.tiff, "image/tiff"), ("ico", f.ico, "image/x-icon"), ("avif", f.avif, "image/avif")]


@pytest.mark.parametrize(("tipo", "crea", "ct"), NUOVI)
def test_tipo_dai_byte_e_decisione_immagine(tipo, crea, ct):
    dati = crea()
    assert riconosci_tipo(dati) == tipo
    d = at.decidi(dati, f"foto.{tipo}", ct)
    assert d.azione == at.IMMAGINE and d.tipo.formato == tipo and not d.travestito


@pytest.mark.parametrize(("tipo", "crea", "ct"), NUOVI)
def test_controllo_byte_pulito_con_le_dimensioni(tipo, crea, ct):
    e = controlla_byte(crea(), f"foto.{tipo}", ct)
    assert e.verdetto == PULITA and e.tipo == tipo and e.larghezza and e.altezza, e.motivi


def test_dimensioni_lette_giuste():
    assert (controlla_byte(f.bmp(30, 20)).larghezza, controlla_byte(f.bmp(30, 20)).altezza) == (30, 20)
    assert (controlla_byte(f.tiff(31, 21)).larghezza, controlla_byte(f.tiff(31, 21)).altezza) == (31, 21)
    assert (controlla_byte(f.avif(40, 30)).larghezza, controlla_byte(f.avif(40, 30)).altezza) == (40, 30)
    assert (controlla_byte(f.ico(48, 48)).larghezza, controlla_byte(f.ico(48, 48)).altezza) == (48, 48)


def test_estensione_pericolosa_o_diversa_resta_rifiuto():
    assert at.decidi(f.bmp(), "x.bmp.exe", "image/bmp").azione == at.RIFIUTA
    assert at.decidi(f.tiff(), "x.png", "image/png").azione in (at.IMMAGINE, at.RIFIUTA)
    assert controlla_byte(f.tiff(), "x.png", "image/png").verdetto != PULITA


def test_finti_che_somigliano_restano_scheda():
    # Testo che comincia con BM, ICO con zero immagini, TIFF con l'indirizzo fuori dal file: mai immagine.
    assert at.decidi(b"BM e' una sigla " * 10, "a.bmp").azione != at.IMMAGINE
    assert at.decidi(b"\x00\x00\x01\x00\x00\x00" + b"\x00" * 40, "a.ico").azione != at.IMMAGINE
    assert at.decidi(b"II*\x00" + struct.pack("<I", 9999999) + b"\x00" * 40, "a.tif").azione != at.IMMAGINE


@pytest.mark.parametrize(("tipo", "crea", "ct"), NUOVI)
@pytest.mark.asyncio
async def test_passa_dalla_sandbox_e_torna_png(ambiente, tipo, crea, ct):  # noqa: F811
    copia, d = await pl.esamina_allegato(crea(), f"foto.{tipo}", ct, GUILD)
    assert d.azione == at.IMMAGINE
    assert copia is not None and copia[0] == "foto.png" and copia[1].startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.asyncio
async def test_sandbox_riconosce_il_formato(ambiente, tmp_path):  # noqa: F811
    _, quar, _ = ambiente
    for tipo, crea, _ct in NUOVI:
        voce = await q.salva(crea(), GUILD, "a" * 64, ore=q.ORE_PULITA)
        r = await sb.analizza(voce.nome)
        assert r.riuscita and r.info["formato"] == tipo.upper() and r.info["fotogrammi"] == 1, (tipo, r.info)
        await q.cancella(voce.nome)


@pytest.mark.parametrize("storto", [
    f.tiff()[:40], b"II*\x00" + struct.pack("<I", 8) + b"\xff" * 60, f.ico()[:30],
    b"\x00\x00\x01\x00\x05\x00" + b"\x01" * 20, f.bmp()[:30], f.avif()[:50],
])
@pytest.mark.asyncio
async def test_file_storto_non_fa_cadere_nulla_e_non_da_copia(ambiente, storto):  # noqa: F811
    copia, d = await pl.esamina_allegato(storto, "x.bin", None, GUILD)
    assert copia is None
    assert d.azione != at.RIFIUTA or d.tipo.categoria in ("sconosciuto", "testo", "eseguibile", "web")


@pytest.mark.asyncio
async def test_troppe_pagine_tiff_nessuna_copia(ambiente):  # noqa: F811
    copia, d = await pl.esamina_allegato(f.tiff_pagine(230), "scansione.tiff", "image/tiff", GUILD)
    assert copia is None and d.tipo.formato == "tiff"


@pytest.mark.asyncio
async def test_tiff_con_catena_di_pagine_infinita_non_blocca(ambiente):  # noqa: F811
    # Prima pagina il cui "prossimo" punta a se' stessa: il lettore dei byte deve fermarsi.
    base = bytearray(f.tiff(4, 4))
    assert base[:2] == b"II"
    ifd = struct.unpack("<I", base[4:8])[0]
    n = struct.unpack("<H", base[ifd:ifd + 2])[0]
    base[ifd + 2 + n * 12: ifd + 6 + n * 12] = struct.pack("<I", ifd)
    e = controlla_byte(bytes(base), "x.tiff", "image/tiff")
    assert e.verdetto != PULITA
    copia, _ = await pl.esamina_allegato(bytes(base), "x.tiff", "image/tiff", GUILD)
    assert copia is None


@pytest.mark.asyncio
async def test_ico_con_troppe_immagini_nessuna_copia(ambiente):  # noqa: F811
    voce = f.ico()
    troppe = voce[:4] + struct.pack("<H", 300) + voce[6:]
    copia, _ = await pl.esamina_allegato(troppe, "x.ico", "image/x-icon", GUILD)
    assert copia is None


# ------------------------------------------------------------------ HEIC/HEIF (D74, parte 2b)
def test_heic_riconosciuto_dai_byte_con_le_dimensioni():
    dati = f.heic(48, 36)
    assert riconosci_tipo(dati) == "heic"
    e = controlla_byte(dati, "foto.heic", "image/heic")
    # La scatola `ispe` da' la misura codificata (a blocchi), mai meno di quella vera: il tetto di pixel resta prudente.
    assert e.verdetto == PULITA and 48 <= e.larghezza <= 64 and 36 <= e.altezza <= 64, e.motivi
    d = at.decidi(dati, "IMG_1.HEIC", "image/heic")
    assert d.azione == at.IMMAGINE and d.tipo.formato == "heic" and not d.travestito


def test_avif_resta_avif_e_non_diventa_heic():
    assert riconosci_tipo(f.avif()) == "avif"


@pytest.mark.asyncio
async def test_heic_passa_dalla_sandbox_e_torna_png(ambiente):  # noqa: F811
    copia, d = await pl.esamina_allegato(f.heic(), "foto.heic", "image/heic", GUILD)
    assert d.azione == at.IMMAGINE and copia is not None and copia[0] == "foto.png"
    assert copia[1].startswith(b"\x89PNG\r\n\x1a\n")
    from PIL import Image
    import io

    assert Image.open(io.BytesIO(copia[1])).size == (40, 30)


@pytest.mark.parametrize("storto", [f.heic()[:60], f.heic()[:200], b"\x00\x00\x00\x18ftypheic" + b"\xff" * 40])
@pytest.mark.asyncio
async def test_heic_storto_non_fa_cadere_nulla_e_non_da_copia(ambiente, storto):  # noqa: F811
    copia, _ = await pl.esamina_allegato(storto, "x.heic", "image/heic", GUILD)
    assert copia is None


def test_il_bot_non_importa_pillow_heif_fuori_dal_worker():
    import pathlib

    radice = pathlib.Path(__file__).resolve().parent.parent
    dentro = [p for p in list(radice.glob("core/*.py")) + list(radice.glob("cogs/**/*.py")) if "pillow_heif" in p.read_text()]
    assert [p.name for p in dentro] == ["immagini_worker.py"]
