"""
tests/test_premium_error_handler.py
=======================================
Test di handle_app_command_error() (core/premium.py) con
un'Interaction finta minimale — non serve una connessione Discord
vera, basta un oggetto che espone gli stessi metodi che l'handler
chiama davvero (response.is_done, response.send_message,
followup.send), per verificare la logica di smistamento.
"""

import pytest

from core.premium import (
    ModuleNotUnlockedError,
    PremiumCheckOutsideGuildError,
    handle_app_command_error,
)


class _FakeResponse:
    def __init__(self, already_done: bool = False) -> None:
        self._done = already_done
        self.sent_messages: list[tuple[str, bool]] = []

    def is_done(self) -> bool:
        return self._done

    async def send_message(self, content: str, ephemeral: bool = False) -> None:
        self.sent_messages.append((content, ephemeral))


class _FakeFollowup:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[str, bool]] = []

    async def send(self, content: str, ephemeral: bool = False) -> None:
        self.sent_messages.append((content, ephemeral))


class _FakeInteraction:
    def __init__(self, already_done: bool = False) -> None:
        self.response = _FakeResponse(already_done)
        self.followup = _FakeFollowup()


@pytest.mark.asyncio
async def test_module_not_unlocked_produce_messaggio_premium():
    interaction = _FakeInteraction()
    error = ModuleNotUnlockedError("spam_trap", "Spam Trap")

    await handle_app_command_error(interaction, error)

    assert len(interaction.response.sent_messages) == 1
    messaggio, ephemeral = interaction.response.sent_messages[0]
    assert "Spam Trap" in messaggio
    assert "Premium" in messaggio
    assert ephemeral is True


@pytest.mark.asyncio
async def test_outside_guild_produce_messaggio_corretto():
    interaction = _FakeInteraction()
    error = PremiumCheckOutsideGuildError()

    await handle_app_command_error(interaction, error)

    messaggio, ephemeral = interaction.response.sent_messages[0]
    assert "solo dentro un server" in messaggio
    assert ephemeral is True


@pytest.mark.asyncio
async def test_errore_generico_produce_messaggio_di_fallback():
    interaction = _FakeInteraction()
    errore_qualsiasi = RuntimeError("qualcosa è andato storto")

    await handle_app_command_error(interaction, errore_qualsiasi)

    messaggio, ephemeral = interaction.response.sent_messages[0]
    assert "errore imprevisto" in messaggio
    assert ephemeral is True


@pytest.mark.asyncio
async def test_usa_followup_se_la_risposta_e_gia_stata_data():
    # Simula un comando che ha già fatto defer()/risposto prima di
    # sollevare l'errore (es. /clear, che fa defer subito).
    interaction = _FakeInteraction(already_done=True)
    error = ModuleNotUnlockedError("clear", "Clear")

    await handle_app_command_error(interaction, error)

    # Non deve usare response.send_message (fallirebbe su Discord
    # vero, "interaction already acknowledged"), deve usare followup.
    assert interaction.response.sent_messages == []
    assert len(interaction.followup.sent_messages) == 1
