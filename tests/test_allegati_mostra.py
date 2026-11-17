"""
tests/test_allegati_mostra.py
=============================
Allegati di un utente mostrati o inoltrati dal bot (D74, risposta 4): mai il link all'originale; un'immagine vera
torna come copia PNG rifatta dalla sandbox, ogni altro file come riga di scheda o di avviso.
Funzioni coperte: SPEC §8.16 (D74, #160)
"""

import discord
import pytest

from core import allegati_mostra as m
from tests.support import immagini_finte as f
from tests.test_immagini_pipeline import ambiente  # noqa: F401 - fixture: DB vero, quarantena di prova


class Finto:
    def __init__(self, nome, dati, content_type=None, size=None, rotto=False):
        self.filename, self.content_type, self._dati, self._rotto = nome, content_type, dati, rotto
        self.size = len(dati) if size is None else size
        self.url = "https://cdn.discordapp.com/attachments/1/2/" + nome
        self.letto = False

    async def read(self):
        self.letto = True
        if self._rotto:
            raise discord.HTTPException(type("R", (), {"status": 404, "reason": "x"})(), "sparito")
        return self._dati


@pytest.mark.asyncio
async def test_immagine_vera_torna_png_rifatto_e_nessun_link(ambiente):  # noqa: F811
    file, righe = await m.prepara([Finto("foto.bmp", f.bmp(), "image/bmp")], 1)
    assert [n for n, _ in file] == ["foto.png"] and file[0][1].startswith(b"\x89PNG") and righe == []


@pytest.mark.asyncio
async def test_altri_file_solo_scheda_o_avviso_senza_url(ambiente):  # noqa: F811
    pdf = b"%PDF-1.4\n" + b"x" * 200
    exe = b"MZ" + b"\0" * 200
    file, righe = await m.prepara([Finto("a.pdf", pdf), Finto("b.exe", exe)], 1)
    assert file == [] and len(righe) == 2
    assert "pdf" in righe[0] and "b.exe" in righe[1]
    assert not any("http" in r or "discordapp" in r for r in righe)


@pytest.mark.asyncio
async def test_file_troppo_grande_non_si_scarica_e_ha_la_scheda(ambiente):  # noqa: F811
    grande = Finto("film.mp4", b"\0\0\0\x18ftypmp42" + b"0" * 20, size=50 * 1024 * 1024)
    file, righe = await m.prepara([grande], 1)
    assert not grande.letto and file == [] and "film.mp4" in righe[0]


@pytest.mark.asyncio
async def test_lettura_fallita_e_oltre_il_tetto(ambiente):  # noqa: F811
    allegati = [Finto(f"x{i}.png", f.png(30 + i, 20 + i), "image/png", rotto=(i == 0)) for i in range(8)]
    file, righe = await m.prepara(allegati, 1, massimo=3)
    assert len(file) == 2 and any("x0.png" in r for r in righe) and any("5" in r for r in righe[-1:])


@pytest.mark.asyncio
async def test_nome_con_inversione_e_pericoloso_non_esce_nella_riga(ambiente):  # noqa: F811
    file, righe = await m.prepara([Finto("foto‮gnp.exe", b"MZ" + b"\0" * 100)], 1)
    assert file == [] and "‮" not in righe[0]



# ------------------------------------------------------------------ copie convertite (D74, parte 2b)
@pytest.fixture
async def servizio_attivo(ambiente, tmp_path, monkeypatch):  # noqa: F811
    from core import allegati_copia, immagini_servizio, immagini_sandbox

    percorso = str(tmp_path / "sbx.sock")
    monkeypatch.setenv(immagini_sandbox.VARIABILE_SOCKET, percorso)
    server = await immagini_servizio.serve(percorso)
    allegati_copia.azzera_tempo()
    yield
    server.close()
    await server.wait_closed()
    allegati_copia.azzera_tempo()


async def test_pdf_e_testo_tornano_come_copia_convertita_e_il_video_solo_se_chiesto(servizio_attivo, tmp_path):
    from tests.support import conversioni_finte as c

    pdf, testo = Finto("a.pdf", c.pdf_pericoloso()), Finto("n.txt", b"ciao\r\nmondo\n")
    video = Finto("v.mp4", c.video(tmp_path, larghezza=160, altezza=90))
    copie, righe = await m.prepara([pdf, testo, video], 1)
    assert [n for n, _ in copie] == ["a.pdf", "n.txt"] and len(righe) == 1 and "v.mp4" in righe[0]
    assert b"/JavaScript" not in copie[0][1] and copie[1][1] == b"ciao\nmondo\n"
    copie, righe = await m.prepara([video], 1, con_video=True)
    assert [n for n, _ in copie] == ["v.mp4"] and righe == []


async def test_le_copie_di_un_messaggio_non_superano_il_tetto_di_peso(servizio_attivo, monkeypatch):
    monkeypatch.setattr(m, "MAX_TOTALE_COPIE", 15)
    copie, righe = await m.prepara([Finto("a.txt", b"0123456789\n"), Finto("b.txt", b"0123456789\n")], 1)
    assert [n for n, _ in copie] == ["a.txt"] and len(righe) == 1 and "b.txt" in righe[0]


def test_file_da_chiama_png_gli_embed_e_lascia_il_nome_agli_altri():
    file, primo = m.file_da([("foto.png", b"\x89PNG"), ("a.pdf", b"%PDF-"), ("b.png", b"\x89PNG")])
    assert [x.filename for x in file] == ["allegato0.png", "a.pdf", "allegato2.png"] and primo == "allegato0.png"
    assert m.file_da([("a.pdf", b"%PDF-")])[1] is None
