"""
tests/test_allegati_cancello.py
===============================
Il cancello dei download (blocco B): tetti di attesa, di byte in volo, di download insieme e della coda della sandbox,
controllati PRIMA di scaricare; i posti si liberano anche con un errore.
Funzioni coperte: SPEC §6 (D62), SICUREZZA.md §7
"""

import asyncio

import pytest

from core import allegati_cancello as ac
from core.immagini_coda import coda_immagini


async def test_con_posto_si_scarica_e_poi_si_libera():
    c = ac.CancelloDownload()
    async with c.posto(1000) as ok:
        assert ok and c.in_attesa == 1 and c.byte_in_volo == 1000
    assert c.in_attesa == 0 and c.byte_in_volo == 0


async def test_il_posto_si_libera_anche_con_un_errore():
    c = ac.CancelloDownload()
    with pytest.raises(RuntimeError):
        async with c.posto(500):
            raise RuntimeError("download fallito")
    assert c.in_attesa == 0 and c.byte_in_volo == 0


async def test_oltre_il_tetto_di_byte_non_si_scarica():
    c = ac.CancelloDownload(max_byte=1000)
    async with c.posto(800) as primo:
        assert primo
        async with c.posto(300) as secondo:
            assert not secondo
        assert c.byte_in_volo == 800  # un rifiuto non tocca i conti


async def test_oltre_il_tetto_di_attesa_non_si_scarica():
    c = ac.CancelloDownload(contemporanei=1, max_in_attesa=2)
    via = asyncio.Event()

    async def tiene():
        async with c.posto(10) as ok:
            assert ok
            await via.wait()

    a, b = asyncio.create_task(tiene()), asyncio.create_task(tiene())
    await asyncio.sleep(0.05)
    assert c.in_attesa == 2
    async with c.posto(10) as terzo:
        assert not terzo
    via.set()
    await asyncio.gather(a, b)
    assert c.in_attesa == 0


async def test_i_download_insieme_sono_limitati():
    c = ac.CancelloDownload(contemporanei=2, max_in_attesa=10)
    attivi = massimo = 0
    via = asyncio.Event()

    async def scarica():
        nonlocal attivi, massimo
        async with c.posto(1) as ok:
            assert ok
            attivi += 1
            massimo = max(massimo, attivi)
            await via.wait()
            attivi -= 1

    lavori = [asyncio.create_task(scarica()) for _ in range(5)]
    await asyncio.sleep(0.05)
    assert attivi == 2
    via.set()
    await asyncio.gather(*lavori)
    assert massimo == 2


async def test_coda_della_sandbox_sopra_la_meta_non_si_scarica(monkeypatch):
    c = ac.CancelloDownload()
    monkeypatch.setattr(coda_immagini, "_totale", ac.SOGLIA_CODA_SANDBOX)
    async with c.posto(10) as ok:
        assert not ok
    monkeypatch.setattr(coda_immagini, "_totale", ac.SOGLIA_CODA_SANDBOX - 1)
    async with c.posto(10) as ok:
        assert ok
