"""
tests/test_anti_nuke_allarmi.py
===============================
#59 riga 3.18: il canale degli allarmi dell'anti-nuke ha una scelta sua
(tramite il router dei canali), non dipende piu' dall'anti-raid.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.security.anti_nuke as modulo
from core import channel_router as router
from core.repositories.output_channel_repo import output_channel_repo
from core.repositories.security_repo import security_repo
from tests.support.discord_fakes import fake_text_channel
from tests.test_anti_nuke_f1 import (  # noqa: F401  (fixture condivise)
    GUILD_ID,
    _interazione,
    _server,
    attese,
    cog,
    db_finto,
)
from tests.support.discord_fakes import fake_member


@pytest.fixture(autouse=True)
def _router_su_db(clean_db, monkeypatch):
    monkeypatch.setattr(output_channel_repo, "_pool_provider", lambda: clean_db)
    router._avvisati.clear()


async def test_allarme_con_solo_l_anti_nuke_attivo_va_nel_canale_scelto(cog):
    canale = fake_text_channel(channel_id=808)
    server = _server(fake_member(user_id=4242), [[]])
    server.get_channel.side_effect = lambda i: canale if i == 808 else None

    interazione = _interazione()
    interazione.guild.get_channel.side_effect = server.get_channel.side_effect
    server = interazione.guild
    server.owner = None
    await cog.canale_allarmi.callback(cog, interazione, canale)

    settings = await security_repo.get_settings(GUILD_ID)
    assert settings.alert_channel_id is None  # niente anti-raid: la scelta e' solo del router
    embed = discord.Embed(title="Allarme")
    await modulo._alert_staff(server, settings, embed)
    canale.send.assert_awaited_once()
    assert canale.send.await_args.kwargs["embed"] is embed


async def test_senza_scelta_resta_il_canale_dell_anti_raid(cog):
    canale = fake_text_channel(channel_id=909)
    server = _server(fake_member(user_id=4242), [[]])
    server.get_channel.side_effect = lambda i: canale if i == 909 else None
    settings = await security_repo.get_settings(GUILD_ID)
    settings = modulo._replace(settings, alert_channel_id=909)
    await modulo._alert_staff(server, settings, discord.Embed(title="x"))
    canale.send.assert_awaited_once()


async def test_solo_chi_gestisce_cambia_il_canale_allarmi(cog):
    canale = fake_text_channel(channel_id=808)
    altro = _interazione()
    altro.user = fake_member(user_id=31337)
    await cog.canale_allarmi.callback(cog, altro, canale)
    assert await output_channel_repo.ottieni(GUILD_ID, router.TIPO_ALLARMI) is None
