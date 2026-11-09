"""B27: come il cog dei tag fa partire un tag per un innesco, e il bottone di un embed con innesco."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.utility.custom_commands as modulo
import cogs.utility.embed_avanzati as av
from tests.support.discord_fakes import fake_guild, fake_member, fake_role, fake_text_channel
from tests.test_custom_commands import _tag, scena  # noqa: F401


@pytest.fixture(autouse=True)
def senza_db(monkeypatch):
    monkeypatch.setattr(modulo, "tag_script_repo", MagicMock(registra_errore=AsyncMock()))


def _canale(puo=True):
    c = fake_text_channel()
    c.send = AsyncMock()
    c.permissions_for = MagicMock(return_value=SimpleNamespace(send_messages=puo, manage_messages=True))
    return c


def _server():
    s = fake_guild()
    s.me.top_role = fake_role(900, "Bot", position=50)
    s.me.mention = "<@bot>"
    s.me.display_name = "iYokai"
    return s


async def test_a_tempo_parla_il_bot_e_non_tocca_i_ruoli(scena):
    scena.repo.get_tag.return_value = _tag(response="Ciao {username}", role_id=5, role_action="dai")
    server, canale = _server(), _canale()
    assert await scena.esegui_innesco(server, "regole", canale) is None
    assert canale.send.await_args.args[0] == "Ciao iYokai"
    assert canale.send.await_args.kwargs["allowed_mentions"].everyone is False
    scena.repo.add_use.assert_awaited_once()


async def test_con_un_membro_valgono_permesso_e_pausa(scena):
    server, canale = _server(), _canale()
    membro = fake_member(7)
    membro.guild, membro.display_name = server, "Luca"
    scena.repo.get_tag.return_value = _tag(permesso="ban_members")
    membro.guild_permissions = discord.Permissions.none()
    assert await scena.esegui_innesco(server, "regole", canale, membro=membro) == "tag_manca_permesso"
    canale.send.assert_not_awaited()
    scena.repo.get_tag.return_value = _tag(cooldown_seconds=60)
    assert await scena.esegui_innesco(server, "regole", canale, membro=membro) is None
    assert await scena.esegui_innesco(server, "regole", canale, membro=membro) == "inn_pausa"
    assert canale.send.await_count == 1


async def test_senza_permesso_di_scrivere_o_tag_sparito(scena):
    server = _server()
    assert await scena.esegui_innesco(server, "regole", _canale(puo=False)) == "inn_canale_senza_permesso"
    scena.repo.get_tag.return_value = None
    assert await scena.esegui_innesco(server, "regole", _canale()) == "inn_tag_manca"
    scena.repo.get_tag.return_value = _tag(solo_nsfw=True)
    c = _canale()
    c.is_nsfw = MagicMock(return_value=False)
    assert await scena.esegui_innesco(server, "regole", c) == "tag_solo_nsfw"


async def test_bottone_con_innesco_risponde_nel_canale(monkeypatch):
    monkeypatch.setattr(av.tag_inneschi_repo, "bottone", AsyncMock(return_value={"tag": "regole"}))
    tag_cog = MagicMock(esegui_innesco=AsyncMock(return_value=None))
    server, canale = _server(), _canale()
    utente = fake_member(7)
    utente.__class__ = discord.Member
    i = MagicMock()
    i.guild, i.channel, i.user = server, canale, utente
    i.client.get_cog.return_value = tag_cog
    i.response.defer = AsyncMock()
    i.followup.send = AsyncMock()
    i.guild.id = 1
    monkeypatch.setattr(av, "lingua_interazione", AsyncMock(return_value="it"))
    b = av.BottoneTag(1, "benvenuto", 2, "x")
    await b.callback(i)
    tag_cog.esegui_innesco.assert_awaited_once_with(server, "regole", canale, membro=utente)
    i.followup.send.assert_awaited_once()
