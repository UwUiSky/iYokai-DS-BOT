"""
tests/test_embed_r2utl.py
=========================
Catalogo #128, giro r2utl: autore, link del titolo e data nell'embed (UTL-074), colore predefinito del server (UTL-084),
un invio al minuto per server (UTL-085).
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.utility.embed_builder as modulo
from cogs.utility.embed_builder import EmbedBuilderCog
from core.embed_builder_logic import DatiEmbed, MAX_AUTORE, a_json, costruisci, da_json, da_json_discord, valida
from core.repositories.saved_embed_repo import SavedEmbedRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel


def test_utl_074_autore_link_e_data_nell_embed_e_nel_json():
    """UTL-074: autore (256), link del titolo e data; vanno nel JSON, tornano indietro e finiscono nell'embed."""
    dati = DatiEmbed(title="T", author="Mario", url="https://example.org/x", timestamp=True)
    assert valida(dati) == []
    embed = costruisci(dati)
    assert embed.author.name == "Mario" and embed.url == "https://example.org/x" and embed.timestamp is not None
    assert da_json(json.loads(a_json(dati))) == dati
    assert valida(DatiEmbed(title="T", author="a" * (MAX_AUTORE + 1)))
    assert valida(DatiEmbed(title="T", url="javascript:alert(1)"))
    d = da_json_discord({"title": "T", "url": "https://example.org", "author": {"name": "Io"}, "timestamp": "2026-01-01T00:00:00"})
    assert d.author == "Io" and d.url == "https://example.org" and d.timestamp is True


@pytest.mark.asyncio
async def test_utl_084_colore_predefinito_per_server(clean_db):
    """UTL-084: si salva, si cambia e si toglie; ogni server ha il suo."""
    repo = SavedEmbedRepository(pool_provider=lambda: clean_db)
    assert await repo.colore_predefinito(1) is None
    await repo.imposta_colore(1, "#FF8800")
    await repo.imposta_colore(2, "#112233")
    await repo.imposta_colore(1, "#00FF00")
    assert await repo.colore_predefinito(1) == "#00FF00" and await repo.colore_predefinito(2) == "#112233"
    await repo.imposta_colore(1, None)
    assert await repo.colore_predefinito(1) is None


@pytest.fixture
def scena(monkeypatch):
    cog = EmbedBuilderCog(MagicMock())
    repo = MagicMock()
    repo.get = AsyncMock(return_value=SimpleNamespace(name="a", data={"title": "T"}, channel_id=None, message_id=None, formato="classico"))
    repo.colore_predefinito = AsyncMock(return_value="#112233")
    repo.imposta_colore = AsyncMock()
    repo.set_published = AsyncMock()
    repo.create = AsyncMock(return_value="ok")
    monkeypatch.setattr(modulo, "saved_embed_repo", repo)
    monkeypatch.setattr(modulo.embed_bottoni_repo, "elenco", AsyncMock(return_value=[]))
    monkeypatch.setattr(modulo, "url_e_sicuro", AsyncMock(return_value=True))
    d = MagicMock()
    d.is_module_active_for_guild = AsyncMock(return_value=True)
    monkeypatch.setattr(modulo, "db", d)
    modulo._ultima_pubblicazione.__init__(100)
    cog.repo = repo
    return cog


@pytest.mark.asyncio
async def test_utl_084_il_colore_predefinito_vale_solo_se_l_embed_non_ne_ha_uno(scena):
    i = fake_interaction(guild=fake_guild(), user=fake_member(5))
    await scena.crea.callback(scena, i, "uno", "Titolo", "Testo")
    assert i.followup.send.await_args.kwargs["embed"].colour.value == 0x112233
    i2 = fake_interaction(guild=fake_guild(), user=fake_member(5))
    await scena.crea.callback(scena, i2, "due", "Titolo", "Testo", "#ff0000")
    assert i2.followup.send.await_args.kwargs["embed"].colour.value == 0xFF0000
    i3 = fake_interaction(guild=fake_guild(), user=fake_member(5))
    await scena.colore_predefinito.callback(scena, i3, "zz")
    scena.repo.imposta_colore.assert_not_awaited()
    await scena.colore_predefinito.callback(scena, i3, "#ff8800")
    scena.repo.imposta_colore.assert_awaited_once_with(i3.guild.id, "#FF8800")


@pytest.mark.asyncio
async def test_utl_085_un_solo_invio_al_minuto_per_server(scena):
    canale = MagicMock(spec=discord.TextChannel)
    canale.id = 9
    canale.send = AsyncMock(return_value=SimpleNamespace(id=77))
    canale.permissions_for.return_value = SimpleNamespace(send_messages=True, embed_links=True)
    server = fake_guild()
    i = fake_interaction(guild=server, user=fake_member(5))
    await scena.pubblica.callback(scena, i, "a", canale)
    canale.send.assert_awaited_once()
    i2 = fake_interaction(guild=server, user=fake_member(5))
    await scena.pubblica.callback(scena, i2, "a", canale)
    canale.send.assert_awaited_once()  # il secondo no
    assert "ephemeral" in i2.response.send_message.await_args.kwargs
    assert canale.send.await_args.kwargs["embed"].colour.value == 0x112233
