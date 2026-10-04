"""
tests/test_bot_ready_bug19.py
=============================
BUG-19: un worker di core/ avviato prima del login non deve morire.
`wait_until_ready()` prima del login solleva RuntimeError e
discord.ext.tasks chiude il loop per sempre: qui si usa un
`commands.Bot` VERO non loggato (un MagicMock nascondeva il problema).
"""

import ast
import asyncio
from pathlib import Path

import discord
import pytest
from discord.ext import commands

from core.backup_queue_worker import BackupQueueWorker
from core.backup_snapshot_worker import BackupSnapshotWorker
from core.clan_leaderboard_announcer import ClanLeaderboardAnnouncer
from core.event_log_retention import EventLogRetentionService
from core.giveaway_worker import GiveawayWorker
from core.guild_clan_expiry_worker import GuildClanExpiryWorker
from core.guild_clan_treasury_decay_worker import GuildClanTreasuryDecayWorker
from core.guild_clan_voice_worker import GuildClanVoiceWorker
from core.memory_guard import MemoryGuard
from core.monthly_winners_announcer import MonthlyWinnersAnnouncer
from core.scheduler import Scheduler
from core.soundboard_log_service import SoundboardLogService
from core.weekly_personal_decay_worker import WeeklyPersonalDecayWorker

CORE_DIR = Path(__file__).parent.parent / "core"

# File di core/ che chiamano ancora wait_until_ready() in un before_loop.
# feed_watcher.py viene avviato da setup_hook (dopo il login), quindi
# oggi funziona. Non aggiungere nomi: l'insieme può solo svuotarsi.
KNOWN_WAIT_UNTIL_READY_DIRETTO = {"feed_watcher.py"}

WORKER_CON_UN_SOLO_BOT = [
    BackupSnapshotWorker,
    ClanLeaderboardAnnouncer,
    EventLogRetentionService,
    GiveawayWorker,
    GuildClanExpiryWorker,
    GuildClanTreasuryDecayWorker,
    GuildClanVoiceWorker,
    MemoryGuard,
    MonthlyWinnersAnnouncer,
    Scheduler,
    SoundboardLogService,
    WeeklyPersonalDecayWorker,
]


def _bot_non_loggato() -> commands.Bot:
    return commands.Bot(command_prefix="!", intents=discord.Intents.default())


async def _rendi_pronto(bot: commands.Bot) -> None:
    """Quello che fa discord.py: login crea l'evento, READY lo imposta."""
    await bot._async_setup_hook()
    bot._ready.set()


def _loop_vivo(worker) -> bool:
    compito = worker._loop_task.get_task()
    return compito is not None and not compito.done()


async def test_attendi_bot_pronto_non_solleva_prima_del_login_e_finisce_quando_e_pronto():
    from core.bot_ready import attendi_bot_pronto

    bot = _bot_non_loggato()
    attesa = asyncio.create_task(attendi_bot_pronto(bot, intervallo=0.01))
    await asyncio.sleep(0.05)
    assert not attesa.done()  # né finita né fallita con RuntimeError

    await _rendi_pronto(bot)
    await asyncio.wait_for(attesa, timeout=1)
    await bot.close()


@pytest.mark.parametrize("classe", WORKER_CON_UN_SOLO_BOT, ids=lambda c: c.__name__)
async def test_worker_avviato_prima_del_login_resta_vivo(classe):
    bot = _bot_non_loggato()
    worker = classe()
    worker.start(bot)
    try:
        await asyncio.sleep(0.05)
        assert _loop_vivo(worker)
    finally:
        worker._loop_task.cancel()
        await bot.close()


async def test_worker_della_coda_avviato_prima_del_login_resta_vivo():
    main_bot, creator = _bot_non_loggato(), _bot_non_loggato()
    worker = BackupQueueWorker()
    worker.start(creator, main_bot, discord.Permissions.none())
    try:
        await asyncio.sleep(0.05)
        assert _loop_vivo(worker)
    finally:
        worker._loop_task.cancel()
        await main_bot.close()
        await creator.close()


async def test_worker_della_coda_non_aspetta_il_creator_e_salta_il_giro(monkeypatch, caplog):
    """Il Creator può non essere partito: il loop gira lo stesso e salta."""
    main_bot, creator = _bot_non_loggato(), _bot_non_loggato()
    await _rendi_pronto(main_bot)

    worker = BackupQueueWorker()
    chiamate = []

    async def _tick(*args, **kwargs):
        chiamate.append(args)

    monkeypatch.setattr(worker, "tick", _tick)
    caplog.set_level("DEBUG", logger="iyokai.backup_queue_worker")

    worker.start(creator, main_bot, discord.Permissions.none())
    try:
        await asyncio.sleep(0.1)
        assert _loop_vivo(worker)
        assert chiamate == []  # Creator non pronto: giro saltato
        assert "Creator non è pronto" in caplog.text

        await _rendi_pronto(creator)
        await worker._giro(creator, main_bot, discord.Permissions.none())
        assert len(chiamate) == 1
    finally:
        worker._loop_task.cancel()
        await main_bot.close()
        await creator.close()


async def test_snapshot_parte_solo_quando_il_bot_vero_e_pronto(monkeypatch):
    """Il primo giro non deve partire prima del login (guild vuote = 0 utenti)."""
    bot = _bot_non_loggato()
    worker = BackupSnapshotWorker()
    partito = asyncio.Event()

    async def _tick(main_bot):
        partito.set()

    monkeypatch.setattr(worker, "tick", _tick)
    worker.start(bot)
    try:
        await asyncio.sleep(0.05)
        assert not partito.is_set()

        await _rendi_pronto(bot)
        await asyncio.wait_for(partito.wait(), timeout=3)
    finally:
        worker.stop()
        await bot.close()


async def test_main_avvia_i_due_worker_del_backup_e_restano_in_esecuzione(clean_db, monkeypatch):
    """Cablaggio vero di main(): solo Client.start e il logging sono finti."""
    import main as main_module

    async def _start_finto(self, token, *, reconnect=True):
        await asyncio.Event().wait()

    coda, snapshot = BackupQueueWorker(), BackupSnapshotWorker()
    monkeypatch.setattr(discord.Client, "start", _start_finto)
    monkeypatch.setattr(main_module, "setup_logging", lambda: None)
    monkeypatch.setattr(main_module, "installa_gestori_segnali", lambda *a, **k: None)
    monkeypatch.setattr(main_module, "backup_queue_worker", coda)
    monkeypatch.setattr(main_module, "backup_snapshot_worker", snapshot)

    compito = asyncio.create_task(main_module.main())
    try:
        for _ in range(200):
            if coda._loop_task is not None and snapshot._loop_task is not None:
                break
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.2)

        assert not compito.done()
        assert coda._loop_task.is_running() and _loop_vivo(coda)
        assert snapshot._loop_task.is_running() and _loop_vivo(snapshot)
    finally:
        compito.cancel()
        await asyncio.gather(compito, return_exceptions=True)
        for worker in (coda, snapshot):
            if worker._loop_task is not None:
                worker._loop_task.cancel()


def _before_loop_che_chiamano_wait_until_ready(percorso: Path) -> list[int]:
    """Righe dove una funzione decorata con `.before_loop` chiama wait_until_ready()."""
    righe = []
    albero = ast.parse(percorso.read_text(encoding="utf-8"))
    for nodo in ast.walk(albero):
        if not isinstance(nodo, ast.AsyncFunctionDef):
            continue
        decorata = any(
            isinstance(d, ast.Attribute) and d.attr == "before_loop" for d in nodo.decorator_list
        )
        if not decorata:
            continue
        for interno in ast.walk(nodo):
            if isinstance(interno, ast.Attribute) and interno.attr == "wait_until_ready":
                righe.append(interno.lineno)
    return righe


def test_nessun_before_loop_di_core_chiama_wait_until_ready():
    """Invariante: i before_loop di core/ usano core.bot_ready.attendi_bot_pronto."""
    trovati = {
        percorso.name: righe
        for percorso in sorted(CORE_DIR.glob("*.py"))
        if (righe := _before_loop_che_chiamano_wait_until_ready(percorso))
    }
    assert set(trovati) == KNOWN_WAIT_UNTIL_READY_DIRETTO, trovati
