"""
tests/test_immagini_byte_logic.py
=================================
Controlli sui byte di un'immagine (D62), senza decodificarla: tipo vero, dimensioni dichiarate,
struttura, dati in coda. File costruiti al volo (tests/support/immagini_finte.py).
"""

import hashlib

import pytest

from core import immagini_byte_logic as b
from tests.support import immagini_finte as f


def codici(esito) -> set[str]:
    return {m.codice for m in esito.motivi}


def test_png_valido_e_pulito():
    dati = f.png()
    e = b.controlla_byte(dati, "foto.png", "image/png")
    assert e.tipo == "png" and (e.larghezza, e.altezza) == (32, 24)
    assert e.motivi == () and e.verdetto == b.PULITA
    assert e.sha256 == hashlib.sha256(dati).hexdigest()


@pytest.mark.parametrize(
    "dati,nome,tipo,dim",
    [
        (f.jpeg(), "a.jpg", "jpeg", (64, 48)),
        (f.jpeg(), "a.jpeg", "jpeg", (64, 48)),
        (f.gif(), "a.gif", "gif", (20, 20)),
        (f.gif_animata(), "a.gif", "gif", (16, 16)),
        (f.webp(), "a.webp", "webp", (40, 30)),
    ],
)
def test_formati_validi_puliti(dati, nome, tipo, dim):
    e = b.controlla_byte(dati, nome)
    assert e.tipo == tipo and (e.larghezza, e.altezza) == dim
    assert e.verdetto == b.PULITA, e.motivi


def test_tipo_diverso_dall_estensione():
    e = b.controlla_byte(f.jpeg(), "finta.png")
    assert "tipo_diverso_estensione" in codici(e) and e.verdetto == b.SOSPETTA


def test_tipo_diverso_dal_content_type():
    e = b.controlla_byte(f.png(), "x.png", "image/jpeg")
    assert "tipo_diverso_content_type" in codici(e)


def test_estensione_immagine_ma_byte_di_altro():
    e = b.controlla_byte(f.mp4_finto(), "video.png")
    assert e.tipo is None and "tipo_non_riconosciuto" in codici(e) and e.verdetto == b.SOSPETTA


def test_estensione_non_immagine_non_e_giudicata_dai_byte_del_tipo():
    # il filtro guarda solo allegati immagine: un .txt con byte strani non e' affare suo
    e = b.controlla_byte(b"ciao", "note.txt")
    assert "tipo_non_riconosciuto" not in codici(e)


def test_poliglotta_png_con_zip_in_coda_e_malevola():
    e = b.controlla_byte(f.png_con_coda(f.zip_finto()), "x.png")
    assert "coda_firma_archivio" in codici(e) and e.verdetto == b.MALEVOLA
    assert e.byte_in_coda == len(f.zip_finto())


def test_png_con_eseguibile_in_coda_e_malevolo():
    e = b.controlla_byte(f.png_con_coda(f.eseguibile_finto()), "x.png")
    assert "coda_firma_eseguibile" in codici(e) and e.verdetto == b.MALEVOLA


def test_coda_con_pagina_html_e_malevola():
    e = b.controlla_byte(f.png_con_coda(b"\n<html><script>alert(1)</script>"), "x.png")
    assert e.verdetto == b.MALEVOLA


def test_zip_dopo_riempimento_e_trovato_lo_stesso():
    e = b.controlla_byte(f.png_con_coda(b"\x00" * 50 + f.zip_finto()), "x.png")
    assert e.verdetto == b.MALEVOLA


def test_jpeg_con_zip_in_coda_e_malevolo():
    e = b.controlla_byte(f.jpeg() + f.zip_finto(), "x.jpg")
    assert e.verdetto == b.MALEVOLA


def test_coda_grande_senza_marcatore_e_sospetta():
    e = b.controlla_byte(f.png_con_coda(bytes(range(256)) * 40), "x.png")
    assert "coda_troppo_grande" in codici(e) and e.verdetto == b.SOSPETTA


def test_coda_piccola_innocua_non_e_un_problema():
    e = b.controlla_byte(f.png_con_coda(b"\x00" * 16), "x.png")
    assert e.verdetto == b.PULITA and e.byte_in_coda == 16


def test_foto_in_movimento_jpeg_piu_video_non_e_falso_positivo():
    dati = f.jpeg_con_mp4(6000)
    e = b.controlla_byte(dati, "PXL_20260101.jpg", "image/jpeg")
    assert e.byte_in_coda > len(dati) // 2  # il video e' piu' della meta': e' il caso difficile
    assert e.verdetto == b.PULITA, e.motivi
    assert "foto_in_movimento" in codici_info(e)


def codici_info(esito) -> set[str]:
    return set(esito.note)


def test_foto_in_movimento_con_eseguibile_dentro_resta_pulita_solo_se_e_un_video():
    # un finto video che e' in realta' un eseguibile non ha `ftyp`: non e' una foto in movimento
    e = b.controlla_byte(f.jpeg() + f.eseguibile_finto() + b"\x00" * 6000, "x.jpg")
    assert e.verdetto == b.MALEVOLA


def test_jpeg_multi_immagine_mpf_non_e_sospetto():
    e = b.controlla_byte(f.jpeg() + f.jpeg(32, 32), "x.jpg")
    assert e.verdetto == b.PULITA, e.motivi


@pytest.mark.parametrize("w,h", [(60000, 60000), (0, 10), (10, 0), (4001, 4001)])
def test_dimensioni_assurde(w, h):
    e = b.controlla_byte(f.png_dichiarato(w, h), "bomba.png")
    assert "dimensioni_assurde" in codici(e) and e.verdetto == b.SOSPETTA


def test_dimensioni_al_limite_passano():
    e = b.controlla_byte(f.png_dichiarato(4000, 4000), "ok.png")
    assert "dimensioni_assurde" not in codici(e)


def test_png_con_crc_rotto():
    e = b.controlla_byte(f.png_crc_rotto(), "x.png")
    assert "png_crc" in codici(e) and e.verdetto == b.SOSPETTA


def test_png_troncato():
    dati = f.png()
    e = b.controlla_byte(dati[: len(dati) - 20], "x.png")
    assert e.verdetto == b.SOSPETTA


def test_webp_con_coda_oltre_la_misura_riff():
    e = b.controlla_byte(f.webp() + f.zip_finto(), "x.webp")
    assert e.verdetto == b.MALEVOLA


def test_gif_con_coda_dopo_il_trailer():
    e = b.controlla_byte(f.gif() + f.eseguibile_finto(), "x.gif")
    assert e.verdetto == b.MALEVOLA


def test_dati_vuoti_o_minuscoli_non_sollevano():
    for dati in (b"", b"\x89PNG", b"\xff\xd8", b"GIF8", b"RIFF"):
        e = b.controlla_byte(dati, "x.png")
        assert e.verdetto == b.SOSPETTA


def test_testo_png_enorme_e_sospetto():
    import struct
    import zlib

    dati = bytearray(f.png())
    testo = b"Comment\x00" + b"A" * (1024 * 1024 + 10)
    blocco = struct.pack(">I", len(testo)) + b"tEXt" + testo + struct.pack(">I", zlib.crc32(b"tEXt" + testo))
    punto = dati.rindex(b"IEND") - 4
    dati[punto:punto] = blocco
    e = b.controlla_byte(bytes(dati), "x.png")
    assert "png_testo_enorme" in codici(e)


def test_troppo_grande_non_si_decodifica():
    dati = f.png() + b"\x00" * (b.MAX_IMAGE_BYTES + 1)
    e = b.controlla_byte(dati, "x.png")
    assert e.troppo_grande


def test_il_nome_del_file_non_fa_mai_sollevare():
    for nome in ("", "senzaestensione", "a.PNG", "a.b.c.jpg", "\x00.png", "😀.webp"):
        b.controlla_byte(f.png(), nome)
