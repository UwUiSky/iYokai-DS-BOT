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
    ferma_servizi_periodici,
    ignora_altri_segnali,
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


# ---------------------------------------------------------------------------
# Secondo segnale durante la chiusura e arresto dei servizi periodici
# ---------------------------------------------------------------------------


@pytest.fixture
async def senza_gestori_alla_fine():
    """Toglie i gestori dei segnali installati dal test sul loop."""
    yield
    loop = asyncio.get_running_loop()
    loop.remove_signal_handler(signal.SIGTERM)
    loop.remove_signal_handler(signal.SIGINT)


@pytest.mark.parametrize("segnale", [signal.SIGTERM, signal.SIGINT])
async def test_un_secondo_segnale_durante_la_chiusura_non_la_interrompe(
    senza_gestori_alla_fine, segnale, caplog
):
    passi = []

    async def principale():
        installa_gestori_segnali(asyncio.current_task())
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            pass
        finally:
            ignora_altri_segnali()
            for passo in ("bot", "sessioni", "database"):
                await asyncio.sleep(0.05)
                passi.append(passo)

    compito = asyncio.create_task(principale())
    await asyncio.sleep(0.01)
    signal.raise_signal(signal.SIGTERM)
    await asyncio.sleep(0.07)  # la chiusura è a metà
    assert passi == ["bot"]
    signal.raise_signal(segnale)

    await compito  # finisce pulita, non con CancelledError

    assert passi == ["bot", "sessioni", "database"]
    assert "chiusura già in corso" in caplog.text


async def test_due_segnali_uno_dopo_l_altro_la_chiusura_arriva_in_fondo(senza_gestori_alla_fine):
    passi = []

    async def principale():
        installa_gestori_segnali(asyncio.current_task())
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            pass
        finally:
            ignora_altri_segnali()
            await asyncio.sleep(0.05)
            passi.append("database")

    compito = asyncio.create_task(principale())
    await asyncio.sleep(0.01)
    signal.raise_signal(signal.SIGTERM)
    signal.raise_signal(signal.SIGTERM)

    await compito

    assert passi == ["database"]


class _ServizioFinto:
    """Come i servizi di core/: un tasks.loop tenuto in `_loop_task`."""

    def __init__(self) -> None:
        self._loop_task = None
        self.giri = 0

    def start(self) -> None:
        from discord.ext import tasks

        @tasks.loop(seconds=0.01)
        async def _loop():
            self.giri += 1

        self._loop_task = _loop
        _loop.start()


async def test_ferma_servizi_periodici_cancella_i_loop_e_aspetta_che_finiscano():
    avviato, mai_avviato = _ServizioFinto(), _ServizioFinto()
    avviato.start()
    await asyncio.sleep(0.03)
    compito = avviato._loop_task.get_task()

    await ferma_servizi_periodici([avviato, mai_avviato])

    assert compito.done()
    assert avviato._loop_task is None  # si può riavviare
    giri = avviato.giri
    await asyncio.sleep(0.03)
    assert avviato.giri == giri  # nessun giro dopo l'arresto


async def test_spegnimento_ferma_i_servizi_prima_di_bot_sessioni_e_database():
    ordine = []
    servizio = _ServizioFinto()
    servizio.start()
    compito = servizio._loop_task.get_task()

    class FakeClient:
        async def close(self):
            ordine.append(("bot", compito.done()))

    async def sessione():
        ordine.append(("sessione", compito.done()))

    async def database():
        ordine.append(("db", compito.done()))

    await spegni_ordinatamente([FakeClient()], [sessione], database, servizi=[servizio])

    assert ordine == [("bot", True), ("sessione", True), ("db", True)]


def test_main_ferma_tutti_i_servizi_periodici_che_importa():
    """Invariante: un servizio di core/ nuovo in main.py va anche fermato."""
    import main as main_module

    con_loop = {
        nome
        for nome, oggetto in vars(main_module).items()
        if hasattr(oggetto, "_loop_task") and not isinstance(oggetto, type)
    }
    fermati = {
        nome for nome, oggetto in vars(main_module).items()
        if any(oggetto is servizio for servizio in main_module._servizi_periodici())
    }
    assert len(con_loop) >= 16
    assert con_loop == fermati


async def test_main_con_due_sigterm_chiude_tutti_i_bot_i_loop_e_il_database(
    clean_db, monkeypatch, senza_gestori_alla_fine
):
    """Cablaggio vero di main(): il secondo SIGTERM arriva a chiusura iniziata."""
    import discord

    import main as main_module
    from core.database import db

    async def _start_finto(self, token, *, reconnect=True):
        await asyncio.Event().wait()

    chiusi = []

    def _rallenta_close(classe) -> None:
        close_vero = classe.close

        async def _close_lento(self):
            await asyncio.sleep(0.05)  # dà tempo al secondo segnale di arrivare
            chiusi.append(self)
            # Su un AutoShardedBot mai loggato la close() vera solleva
            # (coda interna non creata): lo spegnimento lo registra e va avanti.
            await close_vero(self)

        monkeypatch.setattr(classe, "close", _close_lento)

    monkeypatch.setattr(discord.Client, "start", _start_finto)
    _rallenta_close(discord.Client)
    _rallenta_close(discord.AutoShardedClient)  # il bot principale ha la sua close()
    monkeypatch.setattr(main_module, "setup_logging", lambda: None)

    compito = asyncio.create_task(main_module.main())
    for _ in range(200):
        if main_module.backup_snapshot_worker._loop_task is not None:
            break
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.1)
    loop_del_backup = [
        main_module.backup_queue_worker._loop_task.get_task(),
        main_module.backup_snapshot_worker._loop_task.get_task(),
    ]
    assert not any(t.done() for t in loop_del_backup)

    signal.raise_signal(signal.SIGTERM)
    await asyncio.sleep(0.08)  # la chiusura dei bot è iniziata
    assert not compito.done()
    signal.raise_signal(signal.SIGTERM)

    await asyncio.wait_for(compito, timeout=15)  # nessun CancelledError

    assert len(chiusi) == 7  # principale, Creator, 5 worker musicali
    assert all(t.done() for t in loop_del_backup)
    assert main_module.backup_queue_worker._loop_task is None
    assert db._pool is None  # il pool è stato chiuso davvero
