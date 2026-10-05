"""
tests/test_channel_rename.py
============================
Rinomina di un canale entro il limite di Discord (LIM-3): 2 rinomine
ogni 10 minuti per canale. Alla terza il bot risponde subito "riprova
tra N minuti" invece di restare in attesa fino a 10 minuti.
"""

import asyncio
from unittest.mock import MagicMock

import discord
import pytest

import core.channel_rename as modulo
from core.channel_rename import (
    ChannelRenameTracker,
    RenameRateLimited,
    rename_channel,
    rename_limit_message,
)
from tests.support.discord_fakes import fake_text_channel, fake_voice_channel


class Orologio:
    def __init__(self) -> None:
        self.adesso = 1000.0

    def __call__(self) -> float:
        return self.adesso


@pytest.fixture
def orologio():
    return Orologio()


@pytest.fixture
def registro(orologio):
    return ChannelRenameTracker(clock=orologio)


def test_due_rinomine_passano_la_terza_deve_aspettare(registro, orologio):
    assert registro.seconds_until_allowed(1) == 0
    registro.record(1)
    orologio.adesso += 60
    assert registro.seconds_until_allowed(1) == 0
    registro.record(1)

    # 2 fatte: la prima scade dopo 600 secondi, ne sono passati 60.
    assert registro.seconds_until_allowed(1) == pytest.approx(540)
    # Un altro canale ha il suo conto.
    assert registro.seconds_until_allowed(2) == 0


def test_passata_la_finestra_si_puo_rinominare_di_nuovo(registro, orologio):
    registro.record(1)
    registro.record(1)
    orologio.adesso += 601

    assert registro.seconds_until_allowed(1) == 0


def test_il_registro_dimentica_i_canali_con_rinomine_scadute(registro, orologio):
    for canale in range(50):
        registro.record(canale)
    orologio.adesso += 601
    registro.record(999)

    assert registro.tracked_channels() == 1


@pytest.mark.parametrize(
    "secondi, atteso",
    [(1, "1 minuto"), (60, "1 minuto"), (61, "2 minuti"), (540, "9 minuti"), (600, "10 minuti")],
)
def test_messaggio_riprova_tra_n_minuti(secondi, atteso):
    assert f"Riprova tra circa {atteso}." in rename_limit_message(secondi)


async def test_rename_channel_rinomina_e_tiene_il_conto(registro):
    canale = fake_voice_channel(5)

    await rename_channel(canale, "uno", tracker=registro)
    await rename_channel(canale, "due", reason="prova", tracker=registro)

    assert [c.kwargs["name"] for c in canale.edit.call_args_list] == ["uno", "due"]
    assert canale.edit.call_args.kwargs["reason"] == "prova"
    with pytest.raises(RenameRateLimited) as limite:
        await rename_channel(canale, "tre", tracker=registro)
    assert 0 < limite.value.retry_after <= 600
    assert canale.edit.await_count == 2  # la terza non è arrivata a Discord


async def test_errore_di_discord_non_conta_come_rinomina(registro):
    canale = fake_text_channel(5)
    canale.edit.side_effect = discord.Forbidden(
        MagicMock(status=403, reason="Forbidden"), "Missing Permissions"
    )

    for _ in range(3):
        with pytest.raises(discord.Forbidden):
            await rename_channel(canale, "nome", tracker=registro)

    assert registro.seconds_until_allowed(5) == 0


async def test_discord_fa_aspettare_il_bot_risponde_subito(registro, monkeypatch):
    """
    Il limite è già pieno per rinomine che il bot non ha visto (fatte a
    mano, o prima di un riavvio): discord.py resterebbe in attesa fino
    a 10 minuti. La chiamata viene interrotta e il canale segnato pieno.
    """
    monkeypatch.setattr(modulo, "RENAME_TIMEOUT_SECONDS", 0.05)
    canale = fake_voice_channel(5)
    interrotta = asyncio.Event()

    async def _attesa_infinita(**kwargs):
        try:
            await asyncio.sleep(600)
        except asyncio.CancelledError:
            interrotta.set()
            raise

    canale.edit.side_effect = _attesa_infinita

    with pytest.raises(RenameRateLimited):
        await asyncio.wait_for(rename_channel(canale, "nome", tracker=registro), timeout=2)

    assert interrotta.is_set()
    assert registro.seconds_until_allowed(5) > 0


async def test_limite_segnalato_da_discord_py_diventa_riprova(registro):
    """Con `max_ratelimit_timeout` impostato discord.py solleva RateLimited."""
    canale = fake_voice_channel(5)
    canale.edit.side_effect = discord.RateLimited(420.0)

    with pytest.raises(RenameRateLimited) as limite:
        await rename_channel(canale, "nome", tracker=registro)

    assert limite.value.retry_after == pytest.approx(420.0)
    assert registro.seconds_until_allowed(5) > 0
