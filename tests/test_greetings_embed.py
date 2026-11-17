"""
tests/test_greetings_embed.py
=============================
Benvenuto, DM e addio dentro un embed salvato (RUO-001, 014, 015; #123).
"""

import dataclasses
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.utility.greetings as modulo
from cogs.utility.greetings import GreetingsCog
from core.greetings_embed_logic import embed_con_segnaposto
from core.repositories.greetings_repo import GreetingsConfig, GreetingsRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel

DATI = {
    "title": "Benvenuto {username}", "description": "Sei il {membercount}º su {server}", "color": "#C24A3A",
    "image_url": None, "thumbnail_url": None, "footer": "{server}", "fields": [["Regole", "Leggile {user}", False]],
}


def test_RUO_001_segnaposto_in_titolo_testo_piede_e_campi():


    # RUO-001
    e = embed_con_segnaposto(DATI, lambda t: t.replace("{username}", "mario").replace("{server}", "S").replace("{membercount}", "7").replace("{user}", "<@5>"))
    assert e.title == "Benvenuto mario" and e.description == "Sei il 7º su S" and e.footer.text == "S"
    assert e.fields[0].value == "Leggile <@5>"


def test_RUO_001_testi_tagliati_e_embed_non_valido_diventa_none():


    # RUO-001
    lungo = dict(DATI, description="x", title="t", fields=[], footer=None)
    assert len(embed_con_segnaposto(lungo, lambda t: t * 5000).description) == 4096
    assert embed_con_segnaposto({"title": None, "description": None, "fields": []}, lambda t: t) is None
    assert embed_con_segnaposto({"fields": "rotto"}, lambda t: t) is None


@pytest.fixture
def repo(clean_db):
    return GreetingsRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_RUO_001_RUO_014_RUO_015_nomi_degli_embed_salvati_e_riletti(repo):
    # RUO-001, RUO-014, RUO-015
    await repo.set_embed(1, "benvenuto", "bene")
    await repo.set_embed(1, "dm", "privato")
    await repo.set_embed(1, "addio", "ciao")
    config = await repo.get_config(1)
    assert (config.welcome_embed, config.dm_embed, config.goodbye_embed) == ("bene", "privato", "ciao")
    await repo.set_embed(1, "dm", "")
    assert (await repo.get_config(1)).dm_embed == ""
    with pytest.raises(ValueError):
        await repo.set_embed(1, "altro", "x")


class _Scena:
    def __init__(self, monkeypatch, **campi):
        self.cog = GreetingsCog(MagicMock())
        self.canale = fake_text_channel(55)
        self.canale.send = AsyncMock()
        self.server = fake_guild()
        self.server.member_count = 10
        self.server.get_channel = lambda cid: self.canale
        config = GreetingsConfig(
            guild_id=666, welcome_enabled=True, welcome_channel_id=55, welcome_message="Ciao {user}", welcome_dm=True,
            goodbye_enabled=True, goodbye_channel_id=55, goodbye_message="Addio {username}", boost_enabled=False,
            boost_channel_id=None, boost_message="", **campi,
        )
        self.repo = MagicMock()
        self.repo.get_config = AsyncMock(return_value=config)
        self.repo.get_grafica = AsyncMock(return_value=None)
        self.repo.set_embed = AsyncMock()
        monkeypatch.setattr(modulo, "greetings_repo", self.repo)
        db_finto = MagicMock()
        db_finto.is_module_active_for_guild = AsyncMock(return_value=True)
        monkeypatch.setattr(modulo, "db", db_finto)
        monkeypatch.setattr(modulo, "raid_in_corso", lambda gid: False)
        monkeypatch.setattr(modulo.uscite, "addio_soppresso", AsyncMock(return_value=False))
        incorporato = SimpleNamespace(data=DATI)
        self.salvati = MagicMock(get=AsyncMock(return_value=incorporato))
        monkeypatch.setattr(modulo, "saved_embed_repo", self.salvati)
        self.membro = fake_member(5, "mario")
        self.membro.guild = self.server
        self.membro.send = AsyncMock()


@pytest.mark.asyncio
async def test_RUO_001_benvenuto_con_embed_salvato(monkeypatch):
    # RUO-001
    s = _Scena(monkeypatch, welcome_embed="bene")
    await s.cog.on_member_join(s.membro)
    embed = s.canale.send.await_args.kwargs["embed"]
    assert embed.title == "Benvenuto mario"
    s.salvati.get.assert_awaited_with(s.server.id, "bene")


@pytest.mark.asyncio
async def test_RUO_001_embed_cancellato_il_testo_parte_lo_stesso(monkeypatch):
    # RUO-001
    s = _Scena(monkeypatch, welcome_embed="sparito")
    s.salvati.get.return_value = None
    await s.cog.on_member_join(s.membro)
    assert "embed" not in s.canale.send.await_args.kwargs and s.canale.send.await_args.args


@pytest.mark.asyncio
async def test_RUO_014_dm_con_embed(monkeypatch):
    # RUO-014
    s = _Scena(monkeypatch, dm_embed="privato")
    await s.cog.on_member_join(s.membro)
    assert s.membro.send.await_args.kwargs["embed"].title == "Benvenuto mario"
    assert s.membro.send.await_args.kwargs["allowed_mentions"].roles is False


@pytest.mark.asyncio
async def test_RUO_015_addio_con_embed(monkeypatch):
    # RUO-015
    s = _Scena(monkeypatch, goodbye_embed="ciao")
    await s.cog.on_member_remove(s.membro)
    assert s.canale.send.await_args.kwargs["embed"].footer.text == s.server.name


@pytest.mark.asyncio
async def test_RUO_001_il_comando_embed_salva_o_toglie_e_controlla_il_nome(monkeypatch):
    # RUO-001
    s = _Scena(monkeypatch)
    i = fake_interaction(guild=s.server, user=s.membro)
    await s.cog.embed_cmd.callback(s.cog, i, "benvenuto", "bene")
    s.repo.set_embed.assert_awaited_once_with(s.server.id, "benvenuto", "bene")
    s.repo.set_embed.reset_mock()
    await s.cog.embed_cmd.callback(s.cog, i, "dm", "togli")
    s.repo.set_embed.assert_awaited_once_with(s.server.id, "dm", "")
    s.repo.set_embed.reset_mock()
    s.salvati.get.return_value = None  # embed che non esiste
    await s.cog.embed_cmd.callback(s.cog, i, "addio", "nonce")
    s.repo.set_embed.assert_not_awaited()
