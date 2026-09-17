"""
tests/test_main_bot.py
=========================
main.py non aveva NESSUN test — vuoto scoperto mentre si modificava
il file per aggiungere on_error (SPEC.md §1.6). Colmato qui, non
solo per la parte nuova.
"""

import discord
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
