"""
tests/test_bot_supervisor.py
===============================
BUG-7 (#12, #28): un solo bot che non parte (es. token musicale sbagliato)
non deve fermare gli altri; se cade il principale il processo esce con un
errore; lo spegnimento chiude bot, sessioni HTTP e database in ordine.
"""

import asyncio
import signal

import pytest

from core.bot_supervisor import (
    VoceBot,
    esegui_bot_isolati,
    installa_gestori_segnali,
    spegni_ordinatamente,
)


async def _fallisce():
    raise RuntimeError("token non valido")


def _principale_che_gira_finche(evento: asyncio.Event):
    async def _avvio():
        await evento.wait()

    return _avvio


@pytest.mark.asyncio
async def test_un_worker_che_fallisce_non_ferma_gli_altri():
    stop = asyncio.Event()
    avvisi = []

    async def notifica(messaggio):
        avvisi.append(messaggio)

    voci = [
        VoceBot("main", _principale_che_gira_finche(stop), critico=True),
        VoceBot("music-3", _fallisce, critico=False),
    ]
    compito = asyncio.create_task(esegui_bot_isolati(voci, notifica))
    await asyncio.sleep(0.05)

    assert not compito.done()  # il principale è ancora su
    assert len(avvisi) == 1 and "music-3" in avvisi[0]

    stop.set()
    await compito  # termina pulito


@pytest.mark.asyncio
async def test_se_cade_il_principale_l_errore_esce_e_gli_altri_vengono_fermati():
    fermato = asyncio.Event()

    async def worker():
        try:
            await asyncio.sleep(60)
        finally:
            fermato.set()

    voci = [VoceBot("main", _fallisce, critico=True), VoceBot("music-1", worker, critico=False)]

    with pytest.raises(RuntimeError):
        await esegui_bot_isolati(voci)

    assert fermato.is_set()


@pytest.mark.asyncio
async def test_notifica_che_fallisce_non_rompe_nulla():
    stop = asyncio.Event()

    async def notifica(_):
        raise RuntimeError("DM chiusi")

    voci = [
        VoceBot("main", _principale_che_gira_finche(stop), critico=True),
        VoceBot("creator", _fallisce, critico=False),
    ]
    compito = asyncio.create_task(esegui_bot_isolati(voci, notifica))
    await asyncio.sleep(0.05)
    assert not compito.done()
    stop.set()
    await compito


@pytest.mark.asyncio
async def test_spegnimento_chiude_bot_poi_sessioni_poi_database_anche_con_errori():
    ordine = []

    class FakeClient:
        def __init__(self, nome, fallisce=False):
            self.nome, self.fallisce = nome, fallisce

        async def close(self):
            ordine.append(f"bot:{self.nome}")
            if self.fallisce:
                raise RuntimeError("boom")

    async def sessione():
        ordine.append("sessione")

    async def database():
        ordine.append("db")

    await spegni_ordinatamente(
        [FakeClient("main", fallisce=True), FakeClient("creator")], [sessione], database
    )

    assert ordine == ["bot:main", "bot:creator", "sessione", "db"]


@pytest.mark.asyncio
async def test_sigterm_cancella_il_task_principale():
    loop = asyncio.get_running_loop()
    compito = asyncio.create_task(asyncio.sleep(60))
    installa_gestori_segnali(compito)
    try:
        signal.raise_signal(signal.SIGTERM)
        with pytest.raises(asyncio.CancelledError):
            await compito
    finally:
        loop.remove_signal_handler(signal.SIGTERM)
        loop.remove_signal_handler(signal.SIGINT)
