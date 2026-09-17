"""
tests/test_main_bot.py
=========================
main.py non aveva NESSUN test — vuoto scoperto mentre si modificava
il file per aggiungere on_error (SPEC.md §1.6). Colmato qui, non
solo per la parte nuova.
"""

import discord
import logging
import pytest

from main import iYokaiBot


def test_iyokaibot_si_istanzia_senza_eccezioni():
    bot = iYokaiBot()
    assert bot.intents.members is True
    assert bot.intents.message_content is False
    # L'error handler dei comandi slash deve risultare registrato.
    assert bot.tree.on_error is not None
    # Il dizionario di cooldown per on_error parte vuoto.
    assert bot._last_error_alert_at == {}


def test_setup_logging_scrive_davvero_un_file_json_valido():
    # Integrazione reale, non solo unit test del formatter isolato
    # (già in tests/test_json_log_formatter.py): chiama la funzione
    # vera di main.py, logga qualcosa con un logger qualsiasi, e
    # legge il file JSON scritto su disco.
    import json
    from pathlib import Path
    from main import setup_logging

    setup_logging()

    logger_di_prova = logging.getLogger("test.setup_logging.integrazione")
    marcatore = "marcatore-unico-9f3a21"
    logger_di_prova.info("riga di prova con marcatore %s", marcatore)

    # Forza lo scaricamento su disco di tutti gli handler del file
    # (RotatingFileHandler bufferizza a livello di sistema operativo,
    # non serve altro, ma flush esplicito non fa mai male in un test).
    for handler in logging.getLogger().handlers:
        handler.flush()

    log_path = Path(__file__).parent.parent / "logs" / "iyokai.log"
    assert log_path.exists()

    contenuto = log_path.read_text(encoding="utf-8")
    righe_con_marcatore = [r for r in contenuto.splitlines() if marcatore in r]
    assert len(righe_con_marcatore) >= 1

    parsed = json.loads(righe_con_marcatore[-1])
    assert parsed["message"] == f"riga di prova con marcatore {marcatore}"
    assert parsed["logger"] == "test.setup_logging.integrazione"


class _FakeUser:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []

    async def send(self, content: str) -> None:
        self.sent_messages.append(content)


@pytest.mark.asyncio
async def test_on_error_logga_e_avvisa_owner_al_primo_errore(monkeypatch):
    bot = iYokaiBot()
    fake_owner = _FakeUser()

    async def fake_fetch_user(user_id):
        return fake_owner

    monkeypatch.setattr(bot, "fetch_user", fake_fetch_user)

    try:
        raise RuntimeError("errore di prova")
    except RuntimeError:
        # on_error va chiamato DA DENTRO un blocco except, esattamente
        # come fa discord.py stesso — altrimenti sys.exc_info() non
        # avrebbe nulla da loggare (vedi commento in main.py).
        await bot.on_error("test_event")

    assert len(fake_owner.sent_messages) == 1
    assert "test_event" in fake_owner.sent_messages[0]


@pytest.mark.asyncio
async def test_on_error_rispetta_il_cooldown_tra_due_chiamate_ravvicinate(monkeypatch):
    bot = iYokaiBot()
    fake_owner = _FakeUser()

    async def fake_fetch_user(user_id):
        return fake_owner

    monkeypatch.setattr(bot, "fetch_user", fake_fetch_user)

    try:
        raise RuntimeError("primo errore")
    except RuntimeError:
        await bot.on_error("test_event")

    try:
        raise RuntimeError("secondo errore, subito dopo")
    except RuntimeError:
        await bot.on_error("test_event")

    # Il secondo errore è troppo ravvicinato al primo: un solo DM,
    # non due — è esattamente il cooldown che dovrebbe prevenire lo
    # spam durante un evento che fallisce ripetutamente in poco tempo.
    assert len(fake_owner.sent_messages) == 1


@pytest.mark.asyncio
async def test_on_error_eventi_diversi_hanno_cooldown_indipendenti(monkeypatch):
    bot = iYokaiBot()
    fake_owner = _FakeUser()

    async def fake_fetch_user(user_id):
        return fake_owner

    monkeypatch.setattr(bot, "fetch_user", fake_fetch_user)

    try:
        raise RuntimeError("errore in on_message")
    except RuntimeError:
        await bot.on_error("on_message")

    try:
        raise RuntimeError("errore in on_member_join")
    except RuntimeError:
        await bot.on_error("on_member_join")

    # Due event_method diversi: entrambi devono generare un alert,
    # il cooldown dell'uno non deve silenziare l'altro.
    assert len(fake_owner.sent_messages) == 2


class _FakePermissions:
    def __init__(self, send_messages: bool) -> None:
        self.send_messages = send_messages


class _FakeHTTPResponse:
    status = 500
    reason = "Internal Server Error"


class _FakeChannel:
    def __init__(self, name: str, can_send: bool, fail_on_send: bool = False) -> None:
        self.name = name
        self._can_send = can_send
        self._fail_on_send = fail_on_send
        self.sent_embeds: list = []

    def permissions_for(self, member) -> _FakePermissions:
        return _FakePermissions(send_messages=self._can_send)

    async def send(self, embed=None) -> None:
        if self._fail_on_send:
            raise discord.HTTPException(response=_FakeHTTPResponse(), message="errore simulato")
        self.sent_embeds.append(embed)


class _FakeOwner:
    def __init__(self) -> None:
        self.sent_embeds: list = []

    async def send(self, embed=None) -> None:
        self.sent_embeds.append(embed)


class _FakeGuildForWelcome:
    def __init__(
        self,
        system_channel=None,
        text_channels=None,
        owner=None,
        owner_fetch_result=None,
    ) -> None:
        self.id = 100
        self.name = "Server di prova"
        self.system_channel = system_channel
        self.text_channels = text_channels or []
        self.me = object()
        self.owner = owner
        self.owner_id = 999
        self._owner_fetch_result = owner_fetch_result

    async def fetch_member(self, member_id: int):
        if self._owner_fetch_result is None:
            raise discord.HTTPException(response=_FakeHTTPResponse(), message="non trovato")
        return self._owner_fetch_result


@pytest.mark.asyncio
async def test_welcome_usa_system_channel_quando_disponibile():
    bot = iYokaiBot()
    system = _FakeChannel("generale", can_send=True)
    guild = _FakeGuildForWelcome(system_channel=system, text_channels=[system])

    await bot._send_welcome_message(guild)

    assert len(system.sent_embeds) == 1


@pytest.mark.asyncio
async def test_welcome_usa_primo_canale_scrivibile_senza_system_channel():
    bot = iYokaiBot()
    non_scrivibile = _FakeChannel("annunci", can_send=False)
    scrivibile = _FakeChannel("chat", can_send=True)
    guild = _FakeGuildForWelcome(
        system_channel=None, text_channels=[non_scrivibile, scrivibile]
    )

    await bot._send_welcome_message(guild)

    assert len(scrivibile.sent_embeds) == 1
    assert len(non_scrivibile.sent_embeds) == 0


@pytest.mark.asyncio
async def test_welcome_system_channel_fallisce_ricade_sul_canale_scrivibile():
    bot = iYokaiBot()
    system_che_fallisce = _FakeChannel("generale", can_send=True, fail_on_send=True)
    scrivibile = _FakeChannel("chat", can_send=True)
    guild = _FakeGuildForWelcome(
        system_channel=system_che_fallisce,
        text_channels=[system_che_fallisce, scrivibile],
    )

    await bot._send_welcome_message(guild)

    assert len(scrivibile.sent_embeds) == 1


@pytest.mark.asyncio
async def test_welcome_nessun_canale_ricade_su_dm_owner_gia_in_cache():
    bot = iYokaiBot()
    owner = _FakeOwner()
    guild = _FakeGuildForWelcome(system_channel=None, text_channels=[], owner=owner)

    await bot._send_welcome_message(guild)

    assert len(owner.sent_embeds) == 1


@pytest.mark.asyncio
async def test_welcome_owner_non_in_cache_viene_recuperato_con_fetch():
    bot = iYokaiBot()
    owner_recuperato = _FakeOwner()
    guild = _FakeGuildForWelcome(
        system_channel=None,
        text_channels=[],
        owner=None,  # non in cache
        owner_fetch_result=owner_recuperato,
    )

    await bot._send_welcome_message(guild)

    assert len(owner_recuperato.sent_embeds) == 1


@pytest.mark.asyncio
async def test_welcome_fallimento_completo_non_solleva_eccezioni():
    # Nessun canale, nessun owner recuperabile: la catena si esaurisce,
    # ma il metodo deve concludersi normalmente (loggando un avviso),
    # non propagare un'eccezione che romperebbe on_guild_join.
    bot = iYokaiBot()
    guild = _FakeGuildForWelcome(
        system_channel=None, text_channels=[], owner=None, owner_fetch_result=None
    )

    await bot._send_welcome_message(guild)  # non deve sollevare eccezioni
