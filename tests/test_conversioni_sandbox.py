"""
tests/test_conversioni_sandbox.py
=================================
Conversioni sicure di PDF, audio, video e testo (D74, #160) con processi veri: ogni tipo esce pulito dal processo a
parte; file storti, troppo lunghi, scaduti o travestiti (playlist, concat) non fanno cadere nulla e non danno copie.
Funzioni coperte: SPEC §8.16 (D74, #160)
"""

import asyncio
import re
import shutil
import tempfile

import pytest

from core import immagini_quarantena as q
from core import immagini_sandbox as sb
from core import immagini_servizio as servizio
from tests.support import conversioni_finte as c

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="serve ffmpeg")
PROIBITE = re.compile(rb"/(JavaScript|JS|OpenAction|AA|EmbeddedFiles?|Launch|URI|AcroForm|Metadata|Names)(?![A-Za-z0-9_])")


@pytest.fixture
def cartella(tmp_path, monkeypatch):
    quarantena = tmp_path / "quarantena"
    quarantena.mkdir()
    temporanea = tmp_path / "tmp"
    temporanea.mkdir()
    monkeypatch.setenv(q.VARIABILE_CARTELLA, str(quarantena))
    monkeypatch.setattr(tempfile, "tempdir", str(temporanea))
    return tmp_path


def _metti(cartella, dati: bytes) -> str:
    nome = "b" * 32
    (cartella / "quarantena" / nome).write_bytes(dati)
    return nome


async def _converti(cartella, tipo: str, dati: bytes, limiti=None):
    return await sb.esegui_locale(_metti(cartella, dati), limiti, tipo=tipo)


def _salva(cartella, r, nome: str):
    percorso = cartella / nome
    percorso.write_bytes(r.png)
    return percorso


# ------------------------------------------------------------------ testo
async def test_testo_diventa_utf8_senza_caratteri_di_controllo(cartella):
    # Il primo blocco e' testo vero (cosi' lo riconoscono i byte); i caratteri strani stanno piu' avanti.
    sporco = ("ciao " * 1000 + "\x00 mondo\x1b[31m\r\nriga\u202e due\u200b\ttab\rfine").encode()
    r = await _converti(cartella, "testo", sporco)
    assert r.riuscita and r.info["estensione"] == "txt" and not r.info["tagliato"]
    assert r.png.decode() == "ciao " * 1000 + " mondo[31m\nriga due\ttab\nfine"


async def test_testo_oltre_256_kib_si_taglia(cartella):
    r = await _converti(cartella, "testo", ("è" * 300_000).encode())
    assert r.riuscita and r.info["tagliato"] and len(r.png) <= 256 * 1024
    r.png.decode("utf-8")  # taglio su un confine di carattere


# ------------------------------------------------------------------ PDF
async def test_pdf_rifatto_senza_javascript_azioni_e_allegati(cartella):
    originale = c.pdf_pericoloso()
    assert PROIBITE.search(originale)  # il file di prova e' davvero pericoloso
    r = await _converti(cartella, "pdf", originale)
    assert r.riuscita, r.info
    assert not PROIBITE.search(r.png) and r.png.startswith(b"%PDF-")
    from io import BytesIO
    from pypdf import PdfReader

    lettore = PdfReader(BytesIO(r.png))
    assert len(lettore.pages) == 2
    assert "/Annots" not in lettore.pages[0]
    assert not lettore.metadata or not (lettore.metadata.get("/Title") or lettore.metadata.get("/Author"))
    assert b"segreto" not in r.png


async def test_pdf_pulito_conserva_il_testo_cercabile_e_le_evidenziazioni(cartella):
    from io import BytesIO
    from pypdf import PdfReader

    r = await _converti(cartella, "pdf", c.pdf_con_testo("Ciao yokai"))
    assert r.riuscita, r.info
    pagina = PdfReader(BytesIO(r.png)).pages[0]
    assert "Ciao yokai" in pagina.extract_text()
    assert [a.get_object()["/Subtype"] for a in pagina["/Annots"]] == ["/Highlight"]


@pytest.mark.parametrize("dati", [b"%PDF-1.4\nnon un pdf vero\n%%EOF", b"%PDF-" + bytes(range(256)) * 20, c.pdf_cifrato()])
async def test_pdf_storto_o_cifrato_non_da_copia(cartella, dati):
    r = await _converti(cartella, "pdf", dati)
    assert r.esito == "errore" and r.png == b""


async def test_pdf_con_troppe_pagine_non_da_copia(cartella):
    r = await _converti(cartella, "pdf", c.pdf_semplice(201))
    assert r.esito == "errore" and r.info["motivo"] == "pagine"


# ------------------------------------------------------------------ audio
@pytest.mark.parametrize(("formato", "canali"), [("wav", 1), ("flac", 2), ("mp3", 2), ("ogg", 1)])
async def test_audio_diventa_opus_in_ogg_senza_metadati(cartella, formato, canali):
    r = await _converti(cartella, "audio", c.audio(cartella, canali=canali, formato=formato))
    assert r.riuscita, r.info
    s = c.sonda(_salva(cartella, r, "fuori.ogg"))
    assert s["format"]["format_name"] == "ogg"
    assert [x["codec_name"] for x in s["streams"]] == ["opus"] and s["streams"][0]["channels"] == canali
    assert "title" not in {k.lower() for k in s["format"].get("tags", {})} and not s["streams"][0].get("tags", {}).get("artist")
    assert b"segreto" not in r.png and not r.info["tagliato"]


async def test_audio_oltre_10_minuti_si_taglia_e_lo_dice(cartella):
    r = await _converti(cartella, "audio", c.audio(cartella, secondi=630, formato="wav"))
    assert r.riuscita and r.info["tagliato"]
    assert float(c.sonda(_salva(cartella, r, "f.ogg"))["format"]["duration"]) <= 601


async def test_audio_storto_non_da_copia(cartella):
    r = await _converti(cartella, "audio", b"RIFF\x24\x00\x00\x00WAVEfmt " + bytes(40))
    assert r.esito == "errore" and r.png == b""


# ------------------------------------------------------------------ video
async def test_video_diventa_h264_aac_in_mp4_720p_senza_metadati(cartella):
    r = await _converti(cartella, "video", c.video(cartella))
    assert r.riuscita, r.info
    s = c.sonda(_salva(cartella, r, "fuori.mp4"))
    tipi = {x["codec_type"]: x for x in s["streams"]}
    assert tipi["video"]["codec_name"] == "h264" and (tipi["video"]["width"], tipi["video"]["height"]) == (1280, 720)
    assert tipi["audio"]["codec_name"] == "aac" and len(s["streams"]) == 2
    assert not s["format"].get("tags", {}).get("title") and b"segreto" not in r.png and b"nascosto" not in r.png
    assert len(r.png) < int(9.5 * 1024 * 1024)


async def test_video_senza_audio_e_piccolo_resta_com_e(cartella):
    r = await _converti(cartella, "video", c.video(cartella, larghezza=320, altezza=180, con_audio=False))
    assert r.riuscita
    s = c.sonda(_salva(cartella, r, "f.mp4"))
    assert [x["codec_type"] for x in s["streams"]] == ["video"] and s["streams"][0]["width"] == 320


async def test_video_oltre_2_minuti_si_taglia_e_lo_dice(cartella):
    r = await _converti(cartella, "video", c.video(cartella, secondi=130, larghezza=160, altezza=90, con_audio=False, rate=5))
    assert r.riuscita and r.info["tagliato"]
    assert float(c.sonda(_salva(cartella, r, "f.mp4"))["format"]["duration"]) <= 121


@pytest.mark.parametrize("tipo", ["video", "audio"])
@pytest.mark.parametrize(
    "dati",
    [
        b"#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:5,\nfile:///etc/passwd\n",
        b"ffconcat version 1.0\nfile '/etc/passwd'\n",
        b"<MPD xmlns=\"urn:mpeg:dash:schema:mpd:2011\"></MPD>",
        b"#EXTM3U\n" + bytes(3000),
    ],
)
async def test_playlist_e_concat_travestiti_da_media_sono_rifiutati(cartella, tipo, dati):
    r = await _converti(cartella, tipo, dati)
    assert r.esito == "errore" and r.info["motivo"] in ("tipo", "formato") and r.png == b""


async def test_media_con_tipo_sbagliato_non_si_converte(cartella):
    r = await _converti(cartella, "video", c.audio(cartella, formato="wav"))
    assert r.esito == "errore" and r.info["motivo"] == "tipo"
    r = await _converti(cartella, "pdf", c.pdf_semplice().replace(b"%PDF-", b"JUNK-", 1))
    assert r.esito == "errore"


# ------------------------------------------------------------------ limiti
async def test_conversione_che_non_finisce_in_tempo_viene_uccisa_e_non_lascia_file(cartella):
    lungo = c.video(cartella, secondi=100, larghezza=640, altezza=360, con_audio=False)
    piccoli = sb.Limiti(memoria=1536 * 1024 * 1024, cpu=60, reale=0.4, scrittura=12 * 1024 * 1024, uscita=sb.MAX_USCITA_CONVERSIONE)
    r = await asyncio.wait_for(_converti(cartella, "video", lungo, piccoli), 20)
    assert r.esito == "ucciso_tempo" and r.png == b""
    assert list((cartella / "tmp").iterdir()) == []  # la cartella temporanea e' sparita


async def test_ogni_conversione_toglie_la_sua_cartella_temporanea(cartella):
    await _converti(cartella, "audio", c.audio(cartella))
    await _converti(cartella, "pdf", b"%PDF-1.4 rotto")
    assert list((cartella / "tmp").iterdir()) == []


async def test_scrittura_oltre_il_tetto_non_da_copia(cartella):
    stretti = sb.Limiti(memoria=1024 * 1024 * 1024, cpu=30, reale=30, file_aperti=64, scrittura=2000, uscita=sb.MAX_USCITA_CONVERSIONE)
    r = await _converti(cartella, "audio", c.audio(cartella, secondi=20, formato="wav"), stretti)
    assert not r.riuscita and r.png == b""


# ------------------------------------------------------------------ servizio
async def test_il_servizio_converte_su_richiesta_e_senza_servizio_non_c_e_ripiego(cartella, monkeypatch):
    nome = _metti(cartella, "testo di prova".encode())
    monkeypatch.setenv(sb.VARIABILE_SOCKET, str(cartella / "assente.sock"))
    assert (await sb.converti("testo", nome)).esito == "non_disponibile"
    percorso = str(cartella / "s.sock")
    monkeypatch.setenv(sb.VARIABILE_SOCKET, percorso)
    server = await servizio.serve(percorso)
    try:
        r = await sb.converti("testo", nome)
        assert r.riuscita and r.png == b"testo di prova" and r.modo == sb.MODO_SERVIZIO
        r = await sb.converti("pdf", _metti(cartella, c.pdf_pericoloso()))
        assert r.riuscita and not PROIBITE.search(r.png)
    finally:
        server.close()
        await server.wait_closed()


async def test_il_servizio_rifiuta_richieste_storte(cartella, monkeypatch):
    percorso = str(cartella / "s.sock")
    monkeypatch.setenv(sb.VARIABILE_SOCKET, percorso)
    server = await servizio.serve(percorso)
    try:
        for riga in (b"conv shell " + b"a" * 32, b"conv pdf ../../etc/passwd", b"conv pdf", b"conv pdf " + b"a" * 32 + b" x"):
            lettore, scrittore = await asyncio.open_unix_connection(percorso)
            scrittore.write(riga + b"\n")
            info, _ = sb.leggi_uscita(await lettore.read())
            assert info["stato"] == "errore" and info["info"]["motivo"] == "nome"
            scrittore.close()
    finally:
        server.close()
        await server.wait_closed()


def test_controllo_finale_del_pdf_vede_le_azioni_ma_non_le_chiavi_innocue():
    """La rete di sicurezza sui byte in uscita: `/A` (azione) fa scartare la copia; `/AP`, `/Annots`, `/ArtBox` no."""
    from core.conversioni_worker import _PROIBITE

    for pericoloso in (b"<< /A 5 0 R >>", b"<</A<</S/URI>>>>", b"/AA 3 0 R", b"/OpenAction[1 0 R]", b"/JS(app.alert(1))"):
        assert _PROIBITE.search(pericoloso), pericoloso
    for innocuo in (b"/AP << /N 4 0 R >>", b"/Annots [3 0 R]", b"/ArtBox [0 0 1 1]", b"/ASCIIHexDecode", b"/Author"):
        assert not _PROIBITE.search(innocuo), innocuo
