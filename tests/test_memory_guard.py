"""
tests/test_memory_guard.py
==============================
Test di core/memory_guard.py. read_rss_bytes() è testato con una
chiamata VERA a psutil (nessun mock — è un numero reale del processo
di test in esecuzione). Il resto usa oggetti finti minimali per bot,
utenti e voice client, sullo stesso stile già consolidato nel
progetto (vedi tests/test_premium_error_handler.py).
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from core.memory_guard import MemoryGuard


def test_read_rss_bytes_restituisce_un_numero_reale_e_positivo():
    guard = MemoryGuard()
    rss = guard.read_rss_bytes()
    # Nessun mock: è la RAM VERA del processo pytest in esecuzione in
    # questo momento. Deve essere un intero positivo e ragionevole
    # (un processo Python con discord.py caricato occupa almeno
    # qualche MB, sicuramente meno di qualche decina di GB).
    assert isinstance(rss, int)
    assert rss > 1_000_000  # più di 1 MB
    assert rss < 50_000_000_000  # meno di 50 GB (sanity check, non un limite vero)


class _FakeUser:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []

    async def send(self, content: str) -> None:
        self.sent_messages.append(content)


class _FakeBotForAlert:
    def __init__(self, owner: _FakeUser) -> None:
        self._owner = owner
        self.voice_clients: list = []

    async def fetch_user(self, user_id: int) -> _FakeUser:
        return self._owner


@pytest.mark.asyncio
async def test_send_alert_invia_dm_e_aggiorna_ultimo_alert():
    guard = MemoryGuard()
    owner = _FakeUser()
    bot = _FakeBotForAlert(owner)

    assert guard._last_alert_at is None
    await guard._send_alert(bot, rss_bytes=1000 * 1024 * 1024)

    assert len(owner.sent_messages) == 1
    assert "Memory Guard" in owner.sent_messages[0]
    assert guard._last_alert_at is not None


class _FakeMember:
    def __init__(self, is_bot: bool) -> None:
        self.bot = is_bot


class _FakeVoiceChannel:
    def __init__(self, channel_id: int, members: list[_FakeMember]) -> None:
        self.id = channel_id
        self.members = members


class _FakeVoiceClient:
    def __init__(self, channel: _FakeVoiceChannel | None) -> None:
        self.channel = channel
        self.disconnected = False

    async def disconnect(self, force: bool = False) -> None:
        self.disconnected = True


class _FakeBotForVoice:
    def __init__(self, voice_clients: list[_FakeVoiceClient]) -> None:
        self.voice_clients = voice_clients


@pytest.mark.asyncio
async def test_cleanup_disconnette_voice_client_in_canale_vuoto():
    guard = MemoryGuard()
    canale_vuoto = _FakeVoiceChannel(1, members=[_FakeMember(is_bot=True)])  # solo il bot
    vc = _FakeVoiceClient(canale_vuoto)
    bot = _FakeBotForVoice([vc])

    await guard._cleanup_idle_voice_clients(bot)

    assert vc.disconnected is True


@pytest.mark.asyncio
async def test_cleanup_non_disconnette_voice_client_con_persone():
    guard = MemoryGuard()
    canale_pieno = _FakeVoiceChannel(
        1, members=[_FakeMember(is_bot=True), _FakeMember(is_bot=False)]
    )
    vc = _FakeVoiceClient(canale_pieno)
    bot = _FakeBotForVoice([vc])

    await guard._cleanup_idle_voice_clients(bot)

    assert vc.disconnected is False


@pytest.mark.asyncio
async def test_cleanup_ignora_voice_client_senza_canale():
    # Un VoiceClient con .channel None (stato transitorio/anomalo):
    # non deve far esplodere il cleanup.
    guard = MemoryGuard()
    vc = _FakeVoiceClient(channel=None)
    bot = _FakeBotForVoice([vc])

    await guard._cleanup_idle_voice_clients(bot)  # non deve sollevare eccezioni

    assert vc.disconnected is False


class _FakeBotForTick(_FakeBotForAlert, _FakeBotForVoice):
    def __init__(self, owner: _FakeUser, voice_clients: list) -> None:
        _FakeBotForAlert.__init__(self, owner)
        self.voice_clients = voice_clients


@pytest.mark.asyncio
async def test_tick_forza_gc_quando_sopra_soglia():
    guard = MemoryGuard()
    owner = _FakeUser()
    bot = _FakeBotForTick(owner, voice_clients=[])

    with patch("core.memory_guard.config") as fake_config:
        # Qualunque RSS reale supera una soglia di 0 MB: attraversa
        # sempre il ramo che forza il garbage collection.
        fake_config.MEMORY_ALERT_THRESHOLD_MB = 0
        fake_config.OWNER_ID = 1

        with patch("core.memory_guard.gc.collect") as fake_gc_collect:
            await guard.tick(bot)
            fake_gc_collect.assert_called_once()


@pytest.mark.asyncio
async def test_tick_non_forza_gc_quando_sotto_soglia():
    guard = MemoryGuard()
    owner = _FakeUser()
    bot = _FakeBotForTick(owner, voice_clients=[])

    with patch("core.memory_guard.config") as fake_config:
        fake_config.MEMORY_ALERT_THRESHOLD_MB = 999_999_999  # praticamente irraggiungibile
        fake_config.OWNER_ID = 1

        with patch("core.memory_guard.gc.collect") as fake_gc_collect:
            await guard.tick(bot)
            fake_gc_collect.assert_not_called()

    assert owner.sent_messages == []


@pytest.mark.asyncio
async def test_tick_livello_warning_forza_gc_ma_non_manda_alert():
    # Il comportamento nuovo dei quattro livelli: a WARNING (70-100%
    # della soglia) il GC scatta comunque (prima solo a CRITICAL),
    # ma NESSUN DM parte — non è ancora un'emergenza.
    guard = MemoryGuard()
    owner = _FakeUser()
    bot = _FakeBotForTick(owner, voice_clients=[])

    rss_reale_mb = guard.read_rss_bytes() / (1024 * 1024)
    # La soglia configurata è scelta apposta perché l'RSS reale del
    # processo di test ricada all'80% di quella soglia (WARNING).
    soglia_per_warning = int(rss_reale_mb / 0.8)

    with patch("core.memory_guard.config") as fake_config:
        fake_config.MEMORY_ALERT_THRESHOLD_MB = soglia_per_warning
        fake_config.OWNER_ID = 1

        with patch("core.memory_guard.gc.collect") as fake_gc_collect:
            await guard.tick(bot)
            fake_gc_collect.assert_called_once()

    assert owner.sent_messages == []


@pytest.mark.asyncio
async def test_tick_livello_emergency_manda_alert_anche_con_cooldown_attivo():
    # Il secondo comportamento nuovo: a EMERGENCY (oltre il 130%
    # della soglia) il DM parte SEMPRE, anche se un alert è appena
    # stato mandato — a differenza di CRITICAL, che rispetta il
    # cooldown di 30 minuti.
    guard = MemoryGuard()
    guard._last_alert_at = datetime.now(timezone.utc)
    owner = _FakeUser()
    bot = _FakeBotForTick(owner, voice_clients=[])

    with patch("core.memory_guard.config") as fake_config:
        # Soglia di 1MB: qualunque RSS reale del processo di test è
        # ben oltre il 130% di 1MB, quindi sicuramente in EMERGENCY.
        fake_config.MEMORY_ALERT_THRESHOLD_MB = 1
        fake_config.OWNER_ID = 1

        await guard.tick(bot)

    assert len(owner.sent_messages) == 1
