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
    assert menzioni.users is True  # un <@utente> scritto dall'admin avvisa


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


@pytest.mark.asyncio
async def test_set_goodbye_e_set_boost_salvano_ping_ruoli(repo):
    await repo.set_goodbye(100, enabled=True, channel_id=1, message="x", ping_ruoli=True)
    await repo.set_boost(100, enabled=True, channel_id=2, message="y", ping_ruoli=True)
    config = await repo.get_config(100)
    assert config.goodbye_ping_ruoli is True and config.boost_ping_ruoli is True
    assert config.welcome_ping_ruoli is False
    await repo.set_goodbye(100, enabled=True, channel_id=1, message="x")
    assert (await repo.get_config(100)).goodbye_ping_ruoli is False


@pytest.mark.asyncio
async def test_un_mod_senza_menziona_tutti_non_spegne_il_ping_dell_admin(repo):
    # L'admin ha scritto il testo con il ping acceso; un moderatore con solo
    # "Gestisci server" cambia soltanto lo stato: il ping non deve cambiare.
    await repo.set_welcome(100, enabled=True, channel_id=5, message="Ciao <@&9>", dm=False, ping_ruoli=True)
    await repo.set_goodbye(100, enabled=True, channel_id=5, message="Ciao <@&9>", ping_ruoli=True)
    await repo.set_boost(100, enabled=True, channel_id=5, message="Ciao <@&9>", ping_ruoli=True)
    guild = fake_guild(guild_id=100)
    guild.get_channel = MagicMock(return_value=fake_text_channel(channel_id=5))
    mod = fake_member(guild_permissions=discord.Permissions(manage_guild=True))
    cog = _cog()

    await cog.welcome_setup.callback(cog, fake_interaction(guild=guild, user=mod), enabled=True)
    await cog.goodbye_setup.callback(cog, fake_interaction(guild=guild, user=mod), enabled=True)
    await cog.boost_setup.callback(cog, fake_interaction(guild=guild, user=mod), enabled=True)

    config = await repo.get_config(100)
    assert config.welcome_ping_ruoli and config.goodbye_ping_ruoli and config.boost_ping_ruoli

    # Se il mod riscrive il testo, il ping segue il SUO permesso.
    await cog.welcome_setup.callback(
        cog, fake_interaction(guild=guild, user=mod), enabled=True, message="Nuovo <@&9>"
    )
    assert (await repo.get_config(100)).welcome_ping_ruoli is False


@pytest.mark.asyncio
async def test_dm_addio_e_boost_hanno_menzioni_esplicite(repo, monkeypatch):
    monkeypatch.setattr(greetings_module.db, "is_module_active_for_guild", AsyncMock(return_value=True))
    await repo.set_welcome(100, enabled=True, channel_id=5, message="Ciao @everyone", dm=True)
    await repo.set_goodbye(100, enabled=True, channel_id=5, message="Ciao @everyone <@&9>", ping_ruoli=True)
    await repo.set_boost(100, enabled=True, channel_id=5, message="Grazie @everyone")
    monkeypatch.setattr(greetings_module, "raid_in_corso", lambda _g: False)
    canale = fake_text_channel(channel_id=5)
    canale.__class__ = discord.TextChannel
    guild = fake_guild(guild_id=100)
    guild.get_channel = MagicMock(return_value=canale)
    membro = fake_member(user_id=42)
    membro.guild = guild
    cog = _cog()

    await cog.on_member_join(membro)
    menzioni_dm = membro.send.await_args.kwargs["allowed_mentions"]
    assert menzioni_dm.everyone is False and menzioni_dm.roles is False

    canale.send.reset_mock()
    await cog.on_member_remove(membro)
    addio = canale.send.await_args.kwargs["allowed_mentions"]
    assert addio.everyone is False and addio.roles is True

    canale.send.reset_mock()
    prima = fake_member(user_id=42)
    prima.premium_since = None
    prima.guild = guild
    dopo = fake_member(user_id=42)
    dopo.premium_since = __import__("datetime").datetime(2026, 1, 1)
    dopo.guild = guild
    await cog.on_member_update(prima, dopo)
    boost = canale.send.await_args.kwargs["allowed_mentions"]
    assert boost.everyone is False and boost.roles is False


@pytest.mark.asyncio
async def test_testo_salvato_troppo_lungo_viene_tagliato_all_invio(repo, monkeypatch):
    monkeypatch.setattr(greetings_module.db, "is_module_active_for_guild", AsyncMock(return_value=True))
    await repo.set_welcome(100, enabled=True, channel_id=5, message="a" * 2600, dm=False)
    canale = fake_text_channel(channel_id=5)
    canale.__class__ = discord.TextChannel
    guild = fake_guild(guild_id=100)
    guild.get_channel = MagicMock(return_value=canale)
    membro = fake_member(user_id=42)
    membro.guild = guild

    await _cog().on_member_join(membro)

    assert len(canale.send.await_args.args[0]) == 2000


@pytest.mark.asyncio
async def test_il_messaggio_dei_comandi_ha_il_limite_2000(clean_db):
    from discord.ext import commands

    from tests.support.percorsi import comando_nel_gruppo

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await greetings_module.setup(bot)
    for percorso in ("benvenuto benvenuto", "benvenuto addio", "benvenuto boost"):
        opzioni = {o["name"]: o for o in comando_nel_gruppo("gestione", percorso).to_dict(bot.tree)["options"]}
        assert opzioni["message"]["max_length"] == 2000, percorso


@pytest.mark.asyncio
async def test_anteprima_con_rendering_che_solleva_risponde_senza_errore(repo, monkeypatch):
    def _rotto(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(greetings_module, "_render_for_member", _rotto)
    guild = fake_guild(guild_id=100)
    interazione = fake_interaction(guild=guild, user=fake_member(user_id=1))
    scelta = MagicMock()
    scelta.value = "welcome"
    cog = _cog()

    await cog.preview.callback(cog, interazione, scelta)

    assert "anteprima" in interazione.response.send_message.await_args.args[0].lower()
