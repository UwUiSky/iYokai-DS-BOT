"""
tests/test_greetings_ingresso_bot.py
====================================
LC-6: un bot aggiunto al server non riceve il benvenuto. Un bot non
può ricevere messaggi privati da un altro bot, e un "benvenuto" a
un'applicazione nel canale pubblico non serve a nessuno.
"""

from unittest.mock import create_autospec

import pytest

import cogs.utility.greetings as modulo
from core.database import Database
from core.repositories.greetings_repo import GreetingsConfig, GreetingsRepository
from tests.support.discord_fakes import fake_guild, fake_member, fake_text_channel

ID_CANALE_BENVENUTO = 5151


@pytest.fixture
def canale_benvenuto(monkeypatch):
    db_finto = create_autospec(Database, instance=True)
    db_finto.is_module_active_for_guild.return_value = True
    monkeypatch.setattr(modulo, "db", db_finto)

    repo_finto = create_autospec(GreetingsRepository, instance=True)
    repo_finto.get_config.return_value = GreetingsConfig(
        guild_id=666,
        welcome_enabled=True,
        welcome_channel_id=ID_CANALE_BENVENUTO,
        welcome_message="Benvenuto {user}!",
        welcome_dm=True,
        goodbye_enabled=False,
        goodbye_channel_id=None,
        goodbye_message="",
        boost_enabled=False,
        boost_channel_id=None,
        boost_message="",
    )
    monkeypatch.setattr(modulo, "greetings_repo", repo_finto)
    return fake_text_channel(channel_id=ID_CANALE_BENVENUTO)


def _membro_appena_entrato(canale, *, bot: bool):
    server = fake_guild()
    server.member_count = 10
    server.get_channel.return_value = canale
    membro = fake_member(user_id=42, bot=bot)
    membro.guild = server
    return membro


async def test_un_bot_non_riceve_il_benvenuto(canale_benvenuto):
    membro = _membro_appena_entrato(canale_benvenuto, bot=True)
    cog = modulo.GreetingsCog(bot=None)

    await cog.on_member_join(membro)

    membro.send.assert_not_awaited()
    canale_benvenuto.send.assert_not_awaited()


async def test_una_persona_riceve_il_benvenuto_nel_canale_e_in_privato(canale_benvenuto):
    membro = _membro_appena_entrato(canale_benvenuto, bot=False)
    cog = modulo.GreetingsCog(bot=None)

    await cog.on_member_join(membro)

    membro.send.assert_awaited_once()
    canale_benvenuto.send.assert_awaited_once()


async def test_durante_un_raid_niente_dm_di_benvenuto_ma_il_canale_si(canale_benvenuto):
    """M 10.16: il DM non parte mentre l'anti-raid ha un raid in corso."""
    from core import security_raid_state

    membro = _membro_appena_entrato(canale_benvenuto, bot=False)
    cog = modulo.GreetingsCog(bot=None)
    security_raid_state.segna_raid(membro.guild.id)
    try:
        await cog.on_member_join(membro)
    finally:
        security_raid_state.azzera(membro.guild.id)

    membro.send.assert_not_awaited()
    canale_benvenuto.send.assert_awaited_once()
