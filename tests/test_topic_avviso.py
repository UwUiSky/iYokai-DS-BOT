"""
tests/test_topic_avviso.py
==========================
Avviso quando cambia l'argomento di un canale (RUO-027; #123).
"""

import time
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.utility.greetings as modulo
from cogs.utility.greetings import GreetingsCog
from core.repositories.greetings_repo import GreetingsConfig, GreetingsRepository
from core.topic_avviso_logic import MAX_ARGOMENTO, pulisci_argomento, messaggio_avviso, va_annunciato
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_text_channel


def test_RUO_027_l_argomento_si_pulisce():


    # RUO-027
    sporco = "@everyone **ciao** [clic](https://x.it)\n\n`codice` <@123456789012345678>"
    pulito = pulisci_argomento(sporco)
    assert "@everyone" not in pulito and "\n" not in pulito  # tra @ e everyone c'è un carattere invisibile
    assert "\\[clic]" in pulito and "<@123456789012345678>" not in pulito  # parentesi e menzioni resi innocui
    assert len(pulisci_argomento("x" * 5000)) == MAX_ARGOMENTO


def test_RUO_027_testo_con_prima_e_ora_e_nessuno_se_vuoto():


    # RUO-027
    assert "Prima: nessuno" in messaggio_avviso("<#5>", None, "nuovo")
    assert "Ora: nessuno" in messaggio_avviso("<#5>", "vecchio", "")
    assert va_annunciato(None, "") is False and va_annunciato("a", "b") is True


@pytest.mark.asyncio
async def test_RUO_027_repo_salva_il_canale_dell_avviso(clean_db):
    # RUO-027
    repo = GreetingsRepository(pool_provider=lambda: clean_db)
    assert (await repo.get_config(1)).topic_notice_channel_id is None
    await repo.set_topic_notice(1, 77)
    assert (await repo.get_config(1)).topic_notice_channel_id == 77
    await repo.set_topic_notice(1, None)
    assert (await repo.get_config(1)).topic_notice_channel_id is None


def _config(canale):
    return GreetingsConfig(
        guild_id=666, welcome_enabled=False, welcome_channel_id=None, welcome_message="", welcome_dm=False,
        goodbye_enabled=False, goodbye_channel_id=None, goodbye_message="", boost_enabled=False,
        boost_channel_id=None, boost_message="", topic_notice_channel_id=canale,
    )


class _Scena:
    def __init__(self, monkeypatch, canale_avvisi=55, pubblico=True):
        self.cog = GreetingsCog(MagicMock())
        self.avvisi = fake_text_channel(55)
        self.avvisi.send = AsyncMock()
        self.server = fake_guild()
        self.server.get_channel = lambda cid: self.avvisi if cid == 55 else None
        self.repo = MagicMock(get_config=AsyncMock(return_value=_config(canale_avvisi)), set_topic_notice=AsyncMock())
        monkeypatch.setattr(modulo, "greetings_repo", self.repo)
        monkeypatch.setattr(modulo, "db", MagicMock(is_module_active_for_guild=AsyncMock(return_value=True)))
        self.canale = fake_text_channel(9)
        self.canale.guild = self.server
        self.canale.mention = "<#9>"
        self.canale.permissions_for = MagicMock(return_value=discord.Permissions(view_channel=pubblico))
        self.prima = MagicMock(topic="vecchio", guild=self.server)
        self.dopo = self.canale
        self.canale.topic = "nuovo"


@pytest.mark.asyncio
async def test_RUO_027_avviso_inviato_senza_menzioni(monkeypatch):
    # RUO-027
    s = _Scena(monkeypatch)
    await s.cog.on_guild_channel_update(s.prima, s.dopo)
    testo = s.avvisi.send.await_args.args[0]
    assert "Prima: vecchio" in testo and "Ora: nuovo" in testo
    assert s.avvisi.send.await_args.kwargs["allowed_mentions"].everyone is False


@pytest.mark.asyncio
async def test_RUO_027_niente_avviso_se_spento_privato_o_uguale(monkeypatch):
    # RUO-027
    s = _Scena(monkeypatch, canale_avvisi=None)
    await s.cog.on_guild_channel_update(s.prima, s.dopo)
    s.avvisi.send.assert_not_awaited()
    s = _Scena(monkeypatch, pubblico=False)  # canale che @everyone non vede: l'argomento non si rivela
    await s.cog.on_guild_channel_update(s.prima, s.dopo)
    s.avvisi.send.assert_not_awaited()
    s = _Scena(monkeypatch)
    s.prima.topic = "nuovo"
    await s.cog.on_guild_channel_update(s.prima, s.dopo)
    s.avvisi.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_RUO_027_pausa_per_canale(monkeypatch):
    # RUO-027
    s = _Scena(monkeypatch)
    await s.cog.on_guild_channel_update(s.prima, s.dopo)
    await s.cog.on_guild_channel_update(s.prima, s.dopo)
    assert s.avvisi.send.await_count == 1


@pytest.mark.asyncio
async def test_RUO_027_il_comando_salva_e_spegne(monkeypatch):
    # RUO-027
    s = _Scena(monkeypatch)
    i = fake_interaction(guild=s.server)
    await s.cog.avviso_topic.callback(s.cog, i, s.avvisi)
    s.repo.set_topic_notice.assert_awaited_once_with(s.server.id, 55)
    s.repo.set_topic_notice.reset_mock()
    await s.cog.avviso_topic.callback(s.cog, i, None)
    s.repo.set_topic_notice.assert_awaited_once_with(s.server.id, None)
