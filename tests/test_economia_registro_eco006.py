"""
tests/test_economia_registro_eco006.py
======================================
ECO-006 (D121): il canale con il registro dei movimenti di monete. Un riepilogo a lotti (non un messaggio per
movimento), con un tetto di righe per messaggio e per giro. Database vero, canale finto.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core import economia_registro as er
from core.database import db

G = 930001


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    yield


async def _mov(utente, delta, motivo="daily", gid=G):
    await db.pool.execute(
        "INSERT INTO economia_movimenti (guild_id, user_id, delta, motivo) VALUES ($1,$2,$3,$4)", gid, utente, delta, motivo
    )


def _bot(canale):
    guild = MagicMock()
    guild.get_channel.return_value = canale
    guild.me = MagicMock()
    bot = MagicMock()
    bot.get_guild.return_value = guild
    return bot


def _canale():
    c = MagicMock(spec=discord.TextChannel)
    c.id = 5
    c.permissions_for.return_value = discord.Permissions(view_channel=True, send_messages=True, embed_links=True)
    c.send = AsyncMock()
    return c


def test_riepilogo_ha_tetti_e_totali():
    righe = [(i, 100 + i, 10, "daily") for i in range(1, 60)] + [(99, 7, -500, "negozio")]
    t = er.riepilogo(righe)
    assert len(t) <= 4000
    assert "+" in t and "-500" in t
    assert "altri" in t  # oltre le righe mostrate
    assert "@everyone" not in t


def test_riepilogo_motivo_non_pinga():
    t = er.riepilogo([(1, 2, 5, "@everyone `x`")])
    assert "@everyone" not in t.replace("@​everyone", "")


async def test_attivando_non_si_raccontano_i_movimenti_vecchi():
    await _mov(1, 50)
    await er.imposta(G, 5)
    c = _canale()
    await er.tick(_bot(c))
    c.send.assert_not_awaited()


async def test_un_solo_messaggio_per_lotto_e_poi_niente():
    await er.imposta(G, 5)
    for i in range(30):
        await _mov(100 + i, 10)
    c = _canale()
    bot = _bot(c)
    await er.tick(bot)
    assert c.send.await_count == 1
    kw = c.send.await_args.kwargs
    assert kw["allowed_mentions"].users is False or kw["allowed_mentions"] == discord.AllowedMentions.none()
    await er.tick(bot)
    assert c.send.await_count == 1  # niente di nuovo, niente messaggio


async def test_il_giro_ha_un_tetto_e_il_resto_va_al_giro_dopo():
    await er.imposta(G, 5)
    for i in range(er.MAX_PER_GIRO + 10):
        await _mov(1, 1)
    c = _canale()
    bot = _bot(c)
    await er.tick(bot)
    await er.tick(bot)
    assert c.send.await_count == 2


async def test_senza_permessi_non_si_perde_il_lotto():
    await er.imposta(G, 5)
    await _mov(1, 10)
    c = _canale()
    c.permissions_for.return_value = discord.Permissions(view_channel=True)
    await er.tick(_bot(c))
    c.send.assert_not_awaited()
    c.permissions_for.return_value = discord.Permissions(view_channel=True, send_messages=True, embed_links=True)
    await er.tick(_bot(c))
    c.send.assert_awaited_once()


async def test_altro_server_non_si_mescola_e_togli():
    await er.imposta(G, 5)
    await _mov(1, 10, gid=G + 1)
    c = _canale()
    await er.tick(_bot(c))
    c.send.assert_not_awaited()
    assert await er.togli(G) is True
    assert await er.togli(G) is False
