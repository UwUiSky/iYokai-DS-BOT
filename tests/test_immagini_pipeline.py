"""
tests/test_immagini_pipeline.py
===============================
Percorso unico dell'immagine (D61, D62) con sandbox vera e database vero: pulita, poliglotta,
foto in movimento (non e' un falso positivo), QR con link di login finto, libreria, coda piena,
processo ucciso, cache dei verdetti.
"""

import io

import pytest
from PIL import Image, ImageDraw

from core import immagini_coda as coda_mod
from core import immagini_pipeline as pl
from core import immagini_quarantena as q
from core import immagini_sandbox as sb
from core import immagini_trappola_logic as lg
from core.immagini_trappola_service import LibreriaImmagini
from core.repositories.immagini_trappola_repo import ImmaginiTrappolaRepository
from tests.support import immagini_finte as f

GUILD = 777000802


@pytest.fixture
async def ambiente(clean_db, tmp_path, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    monkeypatch.setenv(q.VARIABILE_CARTELLA, str(tmp_path / "quar"))
    lib = LibreriaImmagini(repo=ImmaginiTrappolaRepository(pool_provider=lambda: clean_db))
    monkeypatch.setattr(pl, "libreria_immagini", lib)
    monkeypatch.setattr(pl, "coda_immagini", coda_mod.CodaImmagini())
    pl.svuota_cache()
    return lib, tmp_path / "quar", clean_db


def _vuota(cartella) -> bool:
    return not cartella.exists() or not list(cartella.iterdir())


def _foto(seme: int) -> Image.Image:
    img = Image.new("RGB", (240, 240), (seme * 20 % 255, 80, 160))
    d = ImageDraw.Draw(img)
    for i in range(6):
        d.ellipse(((i * seme * 13) % 120, (i * 31) % 120, 240 - i * 11, 240 - i * 17), outline=(255 - i * 30, i * 40, seme * 7 % 255), width=6)
    return img


@pytest.mark.asyncio
async def test_immagine_pulita_da_la_copia_ricodificata_e_non_lascia_file(ambiente):
    _, quar, _ = ambiente
    e = await pl.analizza_immagine(f.png(), "a.png", "image/png", GUILD)
    assert e.verdetto == "pulita" and e.non_analizzata is None
    assert e.png.startswith(b"\x89PNG") and e.dhash is not None
    assert _vuota(quar)


@pytest.mark.asyncio
async def test_poliglotta_e_malevola_senza_toccare_il_decoder(ambiente, monkeypatch):
    _, quar, _ = ambiente

    async def mai(*a, **k):
        raise AssertionError("la sandbox non deve partire")

    monkeypatch.setattr(sb, "analizza", mai)
    e = await pl.analizza_immagine(f.png_con_coda(f.zip_finto()), "x.png", "image/png", GUILD)
    assert e.verdetto == "malevola" and "coda_firma_archivio" in e.motivi and e.png == b""
    assert len(list(quar.iterdir())) == 1  # l'originale resta in quarantena (72 ore)


@pytest.mark.asyncio
async def test_foto_in_movimento_non_e_un_falso_positivo(ambiente):
    e = await pl.analizza_immagine(f.jpeg_con_mp4(6000), "PXL.jpg", "image/jpeg", GUILD)
    assert e.verdetto == "pulita" and e.non_analizzata is None


@pytest.mark.asyncio
async def test_qr_con_link_di_login_finto_e_malevolo(ambiente):
    e = await pl.analizza_immagine(f.foto_con_qr("https://discord.com/ra/FINTO-1234"), "qr.png", "image/png", GUILD)
    assert e.verdetto == "malevola" and "qr_login_discord" in e.motivi and e.qr


@pytest.mark.asyncio
async def test_qr_innocuo_resta_pulito(ambiente):
    e = await pl.analizza_immagine(f.foto_con_qr("https://www.youtube.com/watch?v=abc"), "qr.png", "image/png", GUILD)
    assert e.verdetto == "pulita" and e.qr == ("https://www.youtube.com/watch?v=abc",)


@pytest.mark.asyncio
async def test_sha_nota_in_libreria_si_ferma_prima_della_sandbox(ambiente, monkeypatch):
    lib, _, _ = ambiente
    dati = f.png(33, 33)
    sha = pl.controlla_byte(dati).sha256
    await lib.aggiungi(sha, None, "prova")

    async def mai(*a, **k):
        raise AssertionError("la sandbox non deve partire")

    monkeypatch.setattr(sb, "analizza", mai)
    e = await pl.analizza_immagine(dati, "x.png", None, GUILD)
    assert e.verdetto == "malevola" and e.da_libreria and not e.da_segnalare


@pytest.mark.asyncio
async def test_impronta_percettiva_trova_la_versione_ritoccata(ambiente):
    lib, _, _ = ambiente
    originale = f._salva(_foto(4), "PNG")
    sha, dh = await pl.impronte(originale)
    assert dh is not None
    await lib.aggiungi(sha, dh, "prova")
    ritoccata = f._salva(_foto(4).resize((180, 180)), "JPEG", quality=60)
    e = await pl.analizza_immagine(ritoccata, "x.jpg", None, GUILD)
    assert e.verdetto == "malevola" and any(m.startswith("libreria_approvata") for m in e.motivi)


@pytest.mark.asyncio
async def test_simile_avvisa_soltanto(ambiente):
    lib, _, _ = ambiente
    sha, dh = await pl.impronte(f._salva(_foto(4), "PNG"))
    await lib.aggiungi(sha, dh ^ 0b111111, "prova")  # 6 bit di distanza
    e = await pl.analizza_immagine(f._salva(_foto(4), "PNG", optimize=True) + b"", "y.png", None, GUILD)
    # Stesso contenuto: SHA diverso solo se i byte cambiano; qui puo' essere identico, quindi si forza un file diverso.
    altro = f._salva(_foto(4).resize((239, 239)), "PNG")
    e = await pl.analizza_immagine(altro, "y.png", None, GUILD)
    assert e.solo_avviso and "libreria_simile" in e.motivi and not e.da_segnalare


@pytest.mark.asyncio
async def test_coda_piena_lascia_passare_ma_lo_dice(ambiente, monkeypatch):
    monkeypatch.setattr(pl, "coda_immagini", coda_mod.CodaImmagini(max_totale=0))
    e = await pl.analizza_immagine(f.png(), "a.png", None, GUILD)
    assert e.verdetto == "pulita" and e.non_analizzata == pl.NON_ANALIZZATA_CODA


@pytest.mark.asyncio
async def test_coda_piena_non_ferma_i_controlli_sui_byte(ambiente, monkeypatch):
    monkeypatch.setattr(pl, "coda_immagini", coda_mod.CodaImmagini(max_totale=0))
    e = await pl.analizza_immagine(f.png_con_coda(f.eseguibile_finto()), "a.png", None, GUILD)
    assert e.verdetto == "malevola" and e.non_analizzata is None


@pytest.mark.asyncio
async def test_processo_ucciso_dai_limiti_e_malevolo_e_si_conserva(ambiente, monkeypatch):
    _, quar, _ = ambiente

    async def ucciso(nome, limiti=None):
        return sb.RisultatoSandbox("ucciso")

    monkeypatch.setattr(sb, "analizza", ucciso)
    e = await pl.analizza_immagine(f.png(), "a.png", None, GUILD)
    assert e.verdetto == "malevola" and "sandbox_ucciso" in e.motivi
    assert len(list(quar.iterdir())) == 1
    # Resta per il tempo delle sospette (72 ore), non per quello di sicurezza delle pulite (1 ora).
    ore = await ambiente[2].fetchval("SELECT extract(epoch FROM scade_il - now()) / 3600 FROM quarantena_file")
    assert ore > q.ORE_SOSPETTA - 1


@pytest.mark.asyncio
async def test_errore_del_decoder_e_sospetto(ambiente, monkeypatch):
    async def errore(nome, limiti=None):
        return sb.RisultatoSandbox("errore", {"motivo": "decodifica"})

    monkeypatch.setattr(sb, "analizza", errore)
    e = await pl.analizza_immagine(f.png(), "a.png", None, GUILD)
    assert e.verdetto == "sospetta" and e.motivi == ("sandbox_decodifica",)


@pytest.mark.asyncio
async def test_sandbox_che_non_parte_non_blocca_nessuno(ambiente, monkeypatch):
    async def giu(nome, limiti=None):
        return sb.RisultatoSandbox("non_disponibile")

    monkeypatch.setattr(sb, "analizza", giu)
    e = await pl.analizza_immagine(f.png(), "a.png", None, GUILD)
    assert e.verdetto == "pulita" and e.non_analizzata == pl.NON_ANALIZZATA_SANDBOX


@pytest.mark.asyncio
async def test_stessa_immagine_si_analizza_una_volta_sola(ambiente, monkeypatch):
    chiamate = []
    originale = sb.analizza

    async def conta(nome, limiti=None):
        chiamate.append(nome)
        return await originale(nome, limiti)

    monkeypatch.setattr(sb, "analizza", conta)
    dati = f.png(41, 17)
    for _ in range(5):
        await pl.analizza_immagine(dati, "a.png", None, GUILD)
    assert len(chiamate) == 1


@pytest.mark.asyncio
async def test_troppo_grande_non_si_analizza(ambiente):
    e = await pl.analizza_immagine(f.png() + b"\x00" * (8 * 1024 * 1024), "a.png", None, GUILD)
    assert e.non_analizzata == pl.NON_ANALIZZATA_GRANDE and e.verdetto == "pulita"


def test_da_segnalare_solo_per_i_casi_nuovi():
    assert pl.EsitoImmagine("malevola", "a").da_segnalare
    assert not pl.EsitoImmagine("pulita", "a").da_segnalare
    assert not pl.EsitoImmagine("malevola", "a", da_libreria=True).da_segnalare


def test_una_sospetta_non_diventa_segnalazione():
    # Solo le malevole vanno in libreria: una sospetta (metadati grossi, coda strana) vista in 3 server
    # diventerebbe «condivisa», cioe' malevola con timeout ovunque.
    assert not pl.EsitoImmagine("sospetta", "a", ("png_testo_enorme",)).da_segnalare


@pytest.mark.asyncio
async def test_immagine_resa_certa_dopo_la_cache_si_blocca_subito(ambiente):
    # La cache dei verdetti dura 24 ore: una scelta dell'owner sulla libreria vale subito, non il giorno dopo.
    lib, _, _ = ambiente
    dati = f._salva(_foto(6), "PNG")
    assert (await pl.analizza_immagine(dati, "a.png", None, GUILD)).verdetto == "pulita"
    sha, dh = await pl.impronte(dati)
    await lib.aggiungi(sha, dh, "prova")
    assert (await pl.analizza_immagine(dati, "a.png", None, GUILD)).verdetto == "malevola"
    await lib.imposta_stato(sha, lg.RIFIUTATA)
    assert (await pl.analizza_immagine(dati, "a.png", None, GUILD)).verdetto == "pulita"


@pytest.mark.asyncio
async def test_impronta_simile_resa_certa_dopo_la_cache_si_blocca_subito(ambiente):
    lib, _, _ = ambiente
    ritoccata = f._salva(_foto(8).resize((180, 180)), "JPEG", quality=60)
    assert (await pl.analizza_immagine(ritoccata, "x.jpg", None, GUILD)).verdetto == "pulita"
    sha, dh = await pl.impronte(f._salva(_foto(8), "PNG"))
    await lib.aggiungi(sha, dh, "prova")
    assert (await pl.analizza_immagine(ritoccata, "x.jpg", None, GUILD)).verdetto == "malevola"
