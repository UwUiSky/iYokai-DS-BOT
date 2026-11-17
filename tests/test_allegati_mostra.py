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


@pytest.mark.asyncio
async def test_stessa_immagine_due_volte_da_la_copia_due_volte(ambiente):  # noqa: F811
    uguale = f.png(33, 22)
    file, righe = await m.prepara([Finto("a.png", uguale, "image/png"), Finto("b.png", uguale, "image/png")], 1)
    assert [n for n, _ in file] == ["a.png", "b.png"] and righe == []
