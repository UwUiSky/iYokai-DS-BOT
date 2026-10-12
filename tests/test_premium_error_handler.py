"""
tests/test_premium_error_handler.py
=======================================
Test di handle_app_command_error() (core/premium.py) con
un'Interaction finta minimale — non serve una connessione Discord
vera, basta un oggetto che espone gli stessi metodi che l'handler
chiama davvero (response.is_done, response.send_message,
followup.send), per verificare la logica di smistamento.
"""

import discord
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

    async def original_response(self):
        return _Messaggio(False)

    async def delete_original_response(self) -> None:
        raise AssertionError("non va cancellata una risposta già sostituita")


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


@pytest.mark.asyncio
async def test_ogni_errore_incrementa_il_contatore_globale(monkeypatch):
    import core.premium as premium_module
    from core.bot_stats import RollingCounter

    contatore_di_test = RollingCounter()
    monkeypatch.setattr(premium_module, "error_counter", contatore_di_test)

    interaction = _FakeInteraction()
    await handle_app_command_error(interaction, ModuleNotUnlockedError("spam_trap", "Spam Trap"))

    assert contatore_di_test.count_in_window() == 1


# ----------------------------------------------------------------------
# M 14.2 (BUG-13): un rifiuto per permessi non è un errore imprevisto
# ----------------------------------------------------------------------
import logging

from discord import app_commands


@pytest.mark.asyncio
async def test_permessi_mancanti_messaggio_chiaro_e_log_info(caplog):
    interaction = _FakeInteraction()
    errore = app_commands.MissingPermissions(["manage_guild", "ban_members"])

    with caplog.at_level(logging.DEBUG, logger="iyokai.premium"):
        await handle_app_command_error(interaction, errore)

    messaggio, ephemeral = interaction.response.sent_messages[0]
    assert "permessi" in messaggio
    assert "errore imprevisto" not in messaggio
    assert ephemeral is True
    livelli = {r.levelno for r in caplog.records if r.name == "iyokai.premium"}
    assert livelli == {logging.INFO}


@pytest.mark.asyncio
async def test_no_private_message_messaggio_solo_server(caplog):
    interaction = _FakeInteraction()
    with caplog.at_level(logging.DEBUG, logger="iyokai.premium"):
        await handle_app_command_error(interaction, app_commands.NoPrivateMessage())

    messaggio, ephemeral = interaction.response.sent_messages[0]
    assert "solo dentro un server" in messaggio
    assert ephemeral is True
    assert all(r.levelno == logging.INFO for r in caplog.records if r.name == "iyokai.premium")


@pytest.mark.asyncio
async def test_check_failure_generico_messaggio_non_consentito(caplog):
    interaction = _FakeInteraction()
    with caplog.at_level(logging.DEBUG, logger="iyokai.premium"):
        await handle_app_command_error(interaction, app_commands.CheckFailure("no"))

    messaggio, ephemeral = interaction.response.sent_messages[0]
    assert "non puoi usare" in messaggio.lower()
    assert "errore imprevisto" not in messaggio
    assert ephemeral is True
    assert all(r.levelno == logging.INFO for r in caplog.records if r.name == "iyokai.premium")


# ----------------------------------------------------------------------
# M 14.3: errore dopo un defer() pubblico -> mai visibile a tutti
# ----------------------------------------------------------------------
class _Flags:
    def __init__(self, loading: bool) -> None:
        self.loading = loading


class _Messaggio:
    def __init__(self, loading: bool) -> None:
        self.flags = _Flags(loading)


class _InterazioneConDefer(_FakeInteraction):
    def __init__(self, loading: bool) -> None:
        super().__init__(already_done=True)
        self._loading = loading
        self.eventi: list[str] = []
        self.followup.sent_messages = []

        async def _send(content: str, ephemeral: bool = False) -> None:
            self.eventi.append("followup")
            self.followup.sent_messages.append((content, ephemeral))

        self.followup.send = _send

    async def original_response(self):
        return _Messaggio(self._loading)

    async def delete_original_response(self) -> None:
        self.eventi.append("delete")


@pytest.mark.asyncio
async def test_defer_pubblico_poi_errore_cancella_il_segnaposto_e_manda_effimero():
    interaction = _InterazioneConDefer(loading=True)
    await handle_app_command_error(interaction, RuntimeError("boom"))

    assert interaction.eventi == ["delete", "followup"]
    assert interaction.followup.sent_messages[0][1] is True


@pytest.mark.asyncio
async def test_risposta_gia_data_non_viene_cancellata():
    interaction = _InterazioneConDefer(loading=False)
    await handle_app_command_error(interaction, RuntimeError("boom"))

    assert interaction.eventi == ["followup"]


@pytest.mark.asyncio
async def test_cancellazione_del_segnaposto_fallita_non_blocca_il_followup():
    interaction = _InterazioneConDefer(loading=True)

    async def _fallisce():
        raise discord.NotFound(type("R", (), {"status": 404, "reason": "x"})(), "gone")

    interaction.delete_original_response = _fallisce
    await handle_app_command_error(interaction, RuntimeError("boom"))

    assert interaction.eventi == ["followup"]


# ----------------------------------------------------------------------
# Revisione 12/10: cooldown, BotMissingPermissions, contatore dei rifiuti, risposta non ancora data
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_il_cooldown_dice_quanti_secondi_attendere():
    interaction = _FakeInteraction()
    errore = app_commands.CommandOnCooldown(app_commands.Cooldown(1, 60.0), 41.2)

    await handle_app_command_error(interaction, errore)

    messaggio, ephemeral = interaction.response.sent_messages[0]
    assert "42 secondi" in messaggio and "non puoi usare" not in messaggio.lower()
    assert ephemeral is True


@pytest.mark.asyncio
async def test_il_bot_senza_permessi_ha_un_messaggio_suo():
    interaction = _FakeInteraction()

    await handle_app_command_error(interaction, app_commands.BotMissingPermissions(["manage_roles"]))

    assert "Al bot mancano dei permessi" in interaction.response.sent_messages[0][0]


@pytest.mark.asyncio
async def test_un_rifiuto_per_permessi_non_conta_come_errore_ma_un_errore_vero_si(monkeypatch):
    import core.premium as premium_module
    from core.bot_stats import RollingCounter

    contatore = RollingCounter()
    monkeypatch.setattr(premium_module, "error_counter", contatore)

    await handle_app_command_error(_FakeInteraction(), app_commands.MissingPermissions(["ban_members"]))
    await handle_app_command_error(_FakeInteraction(), app_commands.CommandOnCooldown(app_commands.Cooldown(1, 5.0), 1.0))
    assert contatore.count_in_window() == 0

    await handle_app_command_error(_FakeInteraction(), RuntimeError("boom"))
    assert contatore.count_in_window() == 1


@pytest.mark.asyncio
async def test_se_non_si_e_ancora_risposto_non_si_cerca_il_segnaposto():
    class Interazione(_FakeInteraction):
        async def original_response(self):
            raise AssertionError("niente risposta data: non c'e' nessun segnaposto da cercare")

    interaction = Interazione(already_done=False)

    await handle_app_command_error(interaction, RuntimeError("boom"))

    assert len(interaction.response.sent_messages) == 1
