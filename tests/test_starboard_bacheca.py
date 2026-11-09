"""
tests/test_starboard_bacheca.py
===============================
D69 B8 (UTL-148, 149, 151, 152): classifica delle stelle, messaggio a caso,
bacheca bloccata, canale sorgente che manda tutto in bacheca.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import cogs.utility.starboard as modulo

from core.repositories.starboard_repo import StarboardRepository
from core.starboard_logic import link_bacheca, messaggio_valido_per_auto, riga_classifica
from tests.support.discord_fakes import fake_interaction, fake_text_channel
from tests.support.percorsi import comando_nel_gruppo
from tests.test_starboard import _Scena


@pytest.fixture
def repo(clean_db):
    return StarboardRepository(pool_provider=lambda: clean_db)


async def _post(repo, autore, msg, stelle):
    await repo.claim_post(1, 10, msg, autore)
    await repo.set_board_message(1, msg, msg + 1000, stelle)


@pytest.mark.asyncio
async def test_classifica_somma_le_stelle_per_autore(repo):
    await _post(repo, 5, 1, 3)
    await _post(repo, 5, 2, 4)
    await _post(repo, 6, 3, 5)
    await repo.claim_post(1, 10, 4, 7)  # prenotato ma mai pubblicato: non conta
    top = await repo.classifica_autori(1, 10)
    assert [(a.author_id, a.stelle, a.messaggi) for a in top] == [(5, 7, 2), (6, 5, 1)]
    assert await repo.conta_autori(1) == 2
    assert [a.author_id for a in await repo.classifica_autori(1, 1, 1)] == [6]


@pytest.mark.asyncio
async def test_messaggio_a_caso_solo_pubblicati_e_del_server(repo):
    assert await repo.post_a_caso(1) is None
    await repo.claim_post(1, 10, 9, 5)
    assert await repo.post_a_caso(1) is None
    await _post(repo, 5, 1, 3)
    assert (await repo.post_a_caso(1)).board_message_id == 1001
    assert await repo.post_a_caso(2) is None


@pytest.mark.asyncio
async def test_opzioni_blocca_e_canale_auto(repo):
    assert await repo.set_opzioni(1, blocca=True) is False
    await repo.set_config(1, 50, 3, "⭐")
    await repo.set_opzioni(1, blocca=True, canale_auto=77)
    c = await repo.get_config(1)
    assert (c.blocca, c.canale_auto) == (True, 77)
    await repo.set_opzioni(1)  # niente: resta
    assert (await repo.get_config(1)).canale_auto == 77
    await repo.togli_canale(1, 99)
    assert (await repo.get_config(1)).canale_auto == 77
    await repo.togli_canale(1, 77)
    assert (await repo.get_config(1)).canale_auto is None
    await repo.set_opzioni(1, canale_auto=78)
    await repo.set_opzioni(1, togli_auto=True)
    assert (await repo.get_config(1)).canale_auto is None


def test_logica_righe_e_filtro():
    assert "<@5>" in riga_classifica(1, 5, 7, 2, "⭐") and "7" in riga_classifica(1, 5, 7, 2, "⭐")
    assert link_bacheca(1, 2, 3) == "https://discord.com/channels/1/2/3"
    assert messaggio_valido_per_auto(bot=False, tipo_sistema=False)
    assert not messaggio_valido_per_auto(bot=True, tipo_sistema=False)
    assert not messaggio_valido_per_auto(bot=False, tipo_sistema=True)


@pytest.mark.asyncio
async def test_comandi_in_level_stelle():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    assert comando_nel_gruppo("level", "stelle classifica")
    assert comando_nel_gruppo("level", "stelle caso")


def _messaggio_auto(s, canale_id=10, bot=False, tipo=discord.MessageType.default):
    s.messaggio.guild = s.guild
    s.messaggio.channel = SimpleNamespace(
        id=canale_id, is_nsfw=s.canale.is_nsfw, permissions_for=s.canale.permissions_for
    )
    s.messaggio.author.bot = bot
    s.messaggio.type = tipo
    return s.messaggio


@pytest.mark.asyncio
async def test_canale_auto_manda_tutto_in_bacheca_senza_stelle(monkeypatch):
    s = _Scena(monkeypatch, stelle=0)
    s.config.canale_auto = 10
    s.config.blocca = False
    s.guild.get_channel = lambda cid: {50: s.bacheca}.get(cid)
    await s.cog.on_message(_messaggio_auto(s))
    s.bacheca.send.assert_awaited_once()
    assert s.bacheca.send.await_args.kwargs["allowed_mentions"].everyone is False
    s.repo.set_board_message.assert_awaited_once_with(s.guild.id, 100, 999, 0)


@pytest.mark.asyncio
async def test_canale_auto_ignora_bot_sistema_e_altri_canali(monkeypatch):
    s = _Scena(monkeypatch, stelle=0)
    s.config.canale_auto = 10
    s.guild.get_channel = lambda cid: {50: s.bacheca}.get(cid)
    await s.cog.on_message(_messaggio_auto(s, bot=True))
    await s.cog.on_message(_messaggio_auto(s, tipo=discord.MessageType.new_member))
    await s.cog.on_message(_messaggio_auto(s, canale_id=11))
    s.bacheca.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_canale_auto_non_si_riempie_la_cache_se_la_lettura_fallisce(monkeypatch):
    s = _Scena(monkeypatch, stelle=0)
    s.repo.get_config = AsyncMock(side_effect=RuntimeError("db"))
    with pytest.raises(RuntimeError):
        await s.cog._canale_auto(s.guild.id)
    assert s.guild.id not in s.cog._cache_auto


@pytest.mark.asyncio
async def test_imposta_blocca_nega_scrivere_a_everyone_e_tiene_il_bot(monkeypatch):
    s = _Scena(monkeypatch)
    s.repo.set_config = AsyncMock()
    s.repo.set_opzioni = AsyncMock()
    canale = fake_text_channel(50, "bacheca")
    canale.permissions_for = MagicMock(return_value=discord.Permissions(send_messages=True, embed_links=True, manage_roles=True))
    canale.set_permissions = AsyncMock()
    interazione = fake_interaction(guild=s.guild)
    await s.cog.imposta.callback(s.cog, interazione, canale, 3, "⭐", None, None, True)
    primo, secondo = canale.set_permissions.await_args_list
    assert primo.args[0] is s.guild.me and primo.kwargs["send_messages"] is True
    assert secondo.args[0] is s.guild.default_role and secondo.kwargs["send_messages"] is False


@pytest.mark.asyncio
async def test_imposta_blocca_senza_permesso_non_tocca_nulla(monkeypatch):
    s = _Scena(monkeypatch)
    s.repo.set_config = AsyncMock()
    s.repo.set_opzioni = AsyncMock()
    canale = fake_text_channel(50, "bacheca")
    canale.permissions_for = MagicMock(return_value=discord.Permissions(send_messages=True, embed_links=True))
    canale.set_permissions = AsyncMock()
    interazione = fake_interaction(guild=s.guild)
    await s.cog.imposta.callback(s.cog, interazione, canale, 3, "⭐", None, None, True)
    canale.set_permissions.assert_not_awaited()


@pytest.mark.asyncio
async def test_imposta_rifiuta_sorgente_uguale_alla_bacheca(monkeypatch):
    s = _Scena(monkeypatch)
    s.repo.set_config = AsyncMock()
    canale = fake_text_channel(50, "bacheca")
    canale.permissions_for = MagicMock(return_value=discord.Permissions(send_messages=True, embed_links=True))
    interazione = fake_interaction(guild=s.guild)
    await s.cog.imposta.callback(s.cog, interazione, canale, 3, "⭐", None, None, None, canale)
    s.repo.set_config.assert_not_awaited()


@pytest.mark.asyncio
async def test_classifica_vuota_e_con_dati(monkeypatch):
    s = _Scena(monkeypatch)
    s.repo.conta_autori = AsyncMock(return_value=0)
    interazione = fake_interaction(guild=s.guild)
    await s.cog.stelle_classifica.callback(s.cog, interazione, 1)
    assert "bacheca" in interazione.followup.send.await_args.args[0].lower()
    s.repo.conta_autori = AsyncMock(return_value=25)
    s.repo.classifica_autori = AsyncMock(return_value=[SimpleNamespace(author_id=5, stelle=7, messaggi=2)])
    interazione = fake_interaction(guild=s.guild)
    await s.cog.stelle_classifica.callback(s.cog, interazione, 99)  # oltre l'ultima: ultima pagina
    s.repo.classifica_autori.assert_awaited_once_with(s.guild.id, 10, 20)
    embed = interazione.followup.send.await_args.kwargs["embed"]
    assert "<@5>" in embed.description and "3 di 3" in embed.footer.text


@pytest.mark.asyncio
async def test_caso_manda_il_link_al_post(monkeypatch):
    s = _Scena(monkeypatch)
    s.repo.post_a_caso = AsyncMock(return_value=SimpleNamespace(board_message_id=999))
    interazione = fake_interaction(guild=s.guild)
    await s.cog.stelle_caso.callback(s.cog, interazione)
    assert interazione.response.send_message.await_args.args[0].endswith("/50/999")


def _canale_con_permessi(cid, nome):
    canale = fake_text_channel(cid, nome)
    canale.permissions_for = MagicMock(return_value=discord.Permissions(send_messages=True, embed_links=True, manage_roles=True))
    canale.set_permissions = AsyncMock()
    return canale


@pytest.mark.asyncio
async def test_cambio_canale_sblocca_il_vecchio_e_blocca_il_nuovo(monkeypatch):
    s = _Scena(monkeypatch)
    s.config.blocca, s.config.channel_id = True, 40
    s.repo.set_config = AsyncMock()
    s.repo.set_opzioni = AsyncMock()
    vecchio, nuovo = _canale_con_permessi(40, "vecchia"), _canale_con_permessi(50, "nuova")
    s.guild.get_channel = lambda cid: {40: vecchio, 50: nuovo}.get(cid)
    await s.cog.imposta.callback(s.cog, fake_interaction(guild=s.guild), nuovo, 3, "⭐", None, None, None)
    assert vecchio.set_permissions.await_args.args[0] is s.guild.default_role
    assert vecchio.set_permissions.await_args.kwargs["send_messages"] is None  # tornato libero
    assert nuovo.set_permissions.await_args_list[-1].kwargs["send_messages"] is False  # il blocco passa al nuovo


@pytest.mark.asyncio
async def test_stesso_canale_senza_blocca_non_tocca_i_permessi(monkeypatch):
    s = _Scena(monkeypatch)
    s.config.blocca = True
    s.repo.set_config = AsyncMock()
    s.repo.set_opzioni = AsyncMock()
    canale = _canale_con_permessi(50, "bacheca")
    await s.cog.imposta.callback(s.cog, fake_interaction(guild=s.guild), canale, 3, "⭐", None, None, None)
    canale.set_permissions.assert_not_awaited()
