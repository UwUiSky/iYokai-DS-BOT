"""
tests/test_greetings_limiti.py
=================================
M 10.2 (LIM-10), M 10.6 (D12) e difetti trovati in greetings.py:
lunghezza controllata DOPO i segnaposto, anteprima che non va in errore,
ping di ruolo solo con "Menziona tutti", `dm` non azzerato, nessun
addio per i bot.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.utility.greetings as greetings_module
from cogs.utility.greetings import GreetingsCog
from core.greetings_logic import lunghezza_dopo_segnaposto
from core.repositories.greetings_repo import GreetingsRepository
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_text_channel,
)


@pytest.fixture
def repo(clean_db, monkeypatch):
    r = GreetingsRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(greetings_module, "greetings_repo", r)
    return r


def _cog():
    return GreetingsCog(bot=MagicMock())


def test_lunghezza_conta_i_segnaposto_espansi():
    # {server} da 100 caratteri: il testo da 1950 diventa più lungo di 2000.
    template = "{server}" + "a" * 1901
    assert lunghezza_dopo_segnaposto(template, "S" * 100, 10) > 2000
    assert lunghezza_dopo_segnaposto("ciao", "S", 1) == 4
    # {user} è una menzione (fino a 23 caratteri), {username} fino a 32.
    assert lunghezza_dopo_segnaposto("{user}", "S", 1) >= 21
    assert lunghezza_dopo_segnaposto("{username}", "S", 1) == 32


@pytest.mark.asyncio
async def test_benvenuto_che_diventa_troppo_lungo_e_rifiutato(repo):
    guild = fake_guild(guild_id=100, name="S" * 100)
    interazione = fake_interaction(guild=guild)
    canale = fake_text_channel(channel_id=5)
    testo = "{server}" + "a" * 1950  # 1958 grezzo, 2058 espanso

    await _cog().welcome_setup.callback(
        _cog(), interazione, enabled=True, channel=canale, message=testo, dm=None
    )

    interazione.response.send_message.assert_awaited_once()
    assert "2000" in interazione.response.send_message.await_args.args[0]
    assert (await repo.get_config(100)).welcome_enabled is False


@pytest.mark.asyncio
async def test_addio_e_boost_rifiutano_il_testo_troppo_lungo(repo):
    guild = fake_guild(guild_id=100, name="S" * 100)
    canale = fake_text_channel(channel_id=5)
    testo = "{server}" + "a" * 1950
    for metodo in ("goodbye_setup", "boost_setup"):
        interazione = fake_interaction(guild=guild)
        cog = _cog()
        await getattr(cog, metodo).callback(
            cog, interazione, enabled=True, channel=canale, message=testo
        )
        assert "2000" in interazione.response.send_message.await_args.args[0]
    config = await repo.get_config(100)
    assert not config.goodbye_enabled and not config.boost_enabled


@pytest.mark.asyncio
async def test_senza_dm_nel_comando_il_valore_salvato_resta(repo):
    await repo.set_welcome(100, enabled=True, channel_id=5, message="Ciao", dm=True)
    guild = fake_guild(guild_id=100)
    guild.get_channel = MagicMock(return_value=fake_text_channel(channel_id=5))
    interazione = fake_interaction(guild=guild)
    cog = _cog()

    await cog.welcome_setup.callback(
        cog, interazione, enabled=True, channel=None, message="Nuovo", dm=None
    )

    config = await repo.get_config(100)
    assert config.welcome_dm is True
    assert config.welcome_message == "Nuovo"


@pytest.mark.asyncio
async def test_ping_ruoli_ricordato_solo_se_chi_configura_puo(repo):
    canale = fake_text_channel(channel_id=5)
    guild = fake_guild(guild_id=100)
    cog = _cog()

    con_permesso = fake_member(guild_permissions=discord.Permissions(mention_everyone=True))
    await cog.welcome_setup.callback(
        cog, fake_interaction(guild=guild, user=con_permesso),
        enabled=True, channel=canale, message="Ciao <@&9>", dm=None,
    )
    assert (await repo.get_config(100)).welcome_ping_ruoli is True

    senza_permesso = fake_member(guild_permissions=discord.Permissions(manage_guild=True))
    await cog.welcome_setup.callback(
        cog, fake_interaction(guild=guild, user=senza_permesso),
        enabled=True, channel=canale, message="Ciao <@&9>", dm=None,
    )
    assert (await repo.get_config(100)).welcome_ping_ruoli is False


@pytest.mark.asyncio
async def test_benvenuto_invia_con_menzioni_esplicite(repo, monkeypatch):
    monkeypatch.setattr(greetings_module.db, "is_module_active_for_guild", AsyncMock(return_value=True))
    await repo.set_welcome(
        100, enabled=True, channel_id=5, message="Ciao {user} <@&9> @everyone", dm=False,
        ping_ruoli=True,
    )
    canale = fake_text_channel(channel_id=5)
    canale.__class__ = discord.TextChannel
    guild = fake_guild(guild_id=100)
    guild.member_count = 3
    guild.get_channel = MagicMock(return_value=canale)
    membro = fake_member(user_id=42, name="nuovo")
    membro.guild = guild

    await _cog().on_member_join(membro)

    canale.send.assert_awaited_once()
    menzioni = canale.send.await_args.kwargs["allowed_mentions"]
    assert menzioni.everyone is False
    assert menzioni.roles is True
    assert [u.id for u in menzioni.users] == [42]


@pytest.mark.asyncio
async def test_senza_permesso_i_ruoli_sono_muti(repo, monkeypatch):
    monkeypatch.setattr(greetings_module.db, "is_module_active_for_guild", AsyncMock(return_value=True))
    await repo.set_welcome(100, enabled=True, channel_id=5, message="Ciao <@&9>", dm=False)
    canale = fake_text_channel(channel_id=5)
    canale.__class__ = discord.TextChannel
    guild = fake_guild(guild_id=100)
    guild.get_channel = MagicMock(return_value=canale)
    membro = fake_member(user_id=42)
    membro.guild = guild

    await _cog().on_member_join(membro)

    assert canale.send.await_args.kwargs["allowed_mentions"].roles is False


@pytest.mark.asyncio
async def test_nessun_addio_per_i_bot(repo, monkeypatch):
    monkeypatch.setattr(greetings_module.db, "is_module_active_for_guild", AsyncMock(return_value=True))
    await repo.set_goodbye(100, enabled=True, channel_id=5, message="Ciao {username}")
    canale = fake_text_channel(channel_id=5)
    canale.__class__ = discord.TextChannel
    guild = fake_guild(guild_id=100)
    guild.get_channel = MagicMock(return_value=canale)
    bot_uscito = fake_member(user_id=43, bot=True)
    bot_uscito.guild = guild

    await _cog().on_member_remove(bot_uscito)

    canale.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_anteprima_non_va_in_errore_con_testo_salvato_troppo_lungo(repo):
    # Un testo salvato prima del controllo (o diventato lungo dopo un
    # cambio di nome del server) non deve far fallire l'anteprima.
    await repo.set_welcome(100, enabled=True, channel_id=5, message="a" * 2500, dm=False)
    guild = fake_guild(guild_id=100)
    guild.member_count = 1
    utente = fake_member(user_id=1)
    utente.guild = guild
    interazione = fake_interaction(guild=guild, user=utente)
    scelta = MagicMock()
    scelta.value = "welcome"
    cog = _cog()

    await cog.preview.callback(cog, interazione, scelta)

    inviato = interazione.response.send_message.await_args.args[0]
    assert len(inviato) <= 2000
    assert interazione.response.send_message.await_args.kwargs["allowed_mentions"].roles is False
