"""
tests/test_counters_extra.py
============================
Contatori: numeri abbreviati {breve} (STA-042), ticket aperti (STA-047), ruoli, canali ed emoji (STA-039).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core.counter_logic import (
    ETICHETTE_DI_BASE,
    TIPI,
    Istantanea,
    abbrevia,
    nome_canale,
    valida_etichetta,
    valore_del_contatore,
)
from core.counter_worker import CounterWorker
from tests.support.discord_fakes import fake_guild


@pytest.mark.parametrize(
    "numero, atteso",
    [(0, "0"), (999, "999"), (1000, "1K"), (1211, "1,21K"), (1500, "1,5K"), (999_999, "999,99K"),
     (1_000_000, "1M"), (2_345_678, "2,34M")],
)
def test_abbrevia(numero, atteso):
    assert abbrevia(numero) == atteso


def test_breve_nel_nome_e_nella_validazione():
    assert nome_canale("Membri: {breve}", 1211, None) == "Membri: 1,21K"
    assert nome_canale("{n} / {breve}", 1211, None) == "1211 / 1,21K"
    assert valida_etichetta("Membri: {breve}", "members") is None
    assert valida_etichetta("Membri", "members") is not None


def test_nuovi_tipi_hanno_etichetta_di_base_e_valore():
    for tipo in ("tickets", "roles", "channels", "emojis"):
        assert tipo in TIPI and tipo in ETICHETTE_DI_BASE
    snap = Istantanea(10, None, 0, ticket_aperti=4, ruoli=12, canali=30, emoji=8)
    assert valore_del_contatore("tickets", snap) == 4
    assert valore_del_contatore("roles", snap) == 12
    assert valore_del_contatore("channels", snap) == 30
    assert valore_del_contatore("emojis", snap) == 8
    assert valore_del_contatore("tickets", Istantanea(10, None, 0)) is None


@pytest.mark.asyncio
async def test_il_giro_legge_ticket_ruoli_canali_ed_emoji():
    guild = fake_guild(guild_id=1)
    guild.member_count = 10
    guild.premium_subscription_count = 0
    guild.roles = [object()] * 7
    guild.channels = [object()] * 9
    guild.emojis = [object()] * 3
    canale = MagicMock(spec=discord.VoiceChannel)
    canale.id = 10
    canale.name = "vecchio"
    guild.get_channel = lambda cid: canale
    bot = MagicMock()
    bot.get_guild = lambda gid: guild
    contatori = [
        SimpleNamespace(id=1, guild_id=1, channel_id=10, kind=k, label="{n}", target=None, last_value=None)
        for k in ("tickets", "roles", "channels", "emojis")
    ]
    repo = MagicMock()
    repo.list_all = AsyncMock(return_value=contatori)
    repo.set_last_value = AsyncMock()
    rinomina = AsyncMock()
    db_finto = MagicMock()
    db_finto.is_module_active_for_guild = AsyncMock(return_value=True)
    conta_ticket = AsyncMock(return_value=4)
    worker = CounterWorker(repo, rename=rinomina, db=db_finto, conta_ticket=conta_ticket)

    await worker.tick(bot)

    conta_ticket.assert_awaited_once_with(1)
    assert [c.args[1] for c in rinomina.await_args_list] == ["4", "7", "9", "3"]
