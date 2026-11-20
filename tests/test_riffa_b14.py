"""
tests/test_riffa_b14.py
=======================
Riffa pagata dalla cassa del server (#125 B14): ECO-119. Un solo vincitore, premio dalla cassa nella stessa
transazione, nessuna moneta se la cassa non basta o se tutti sono in blacklist.
Funzioni coperte: catalogo #125
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cogs.leveling.riffa import RiffaView
from core.repositories.guild_chest_repo import GuildChestRepository
from core.repositories.leveling_repo import LevelingRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

G = 100


@pytest.fixture
def r(clean_db, monkeypatch):
    import cogs.leveling.riffa as m
    import core.ui_base as ui

    async def nessuno(*a, **k):
        return False

    monkeypatch.setattr(ui, "_utente_o_server_in_blacklist", nessuno)
    cassa = GuildChestRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(m, "guild_chest_repo", cassa)
    monkeypatch.setattr(m, "blacklist_repo", SimpleNamespace(is_user_blacklisted=AsyncMock(return_value=False)))
    return SimpleNamespace(cassa=cassa, lev=LevelingRepository(pool_provider=lambda: clean_db), m=m)


@pytest.mark.asyncio
async def test_estrazione_paga_il_vincitore_dalla_cassa_una_volta(r):
    await r.cassa.deposit(G, 100, "test")
    v = RiffaView(G, 60, 5, "coin", 1)
    for u in (1, 2, 3):
        i = fake_interaction(guild=fake_guild(G), user=fake_member(u))
        await v.partecipa.callback(i)
        await v.partecipa.callback(i)  # il secondo clic non lo fa entrare di nuovo
    assert v.iscritti == {1, 2, 3}
    vincitore, esito = await v.estrai()
    assert esito == "ok" and vincitore in (1, 2, 3)
    assert (await r.lev.get_totals(G, vincitore)).coins_total == 60 and await r.cassa.get_balance(G) == 40
    assert await v.estrai() == (None, "chiusa")
    assert await r.cassa.get_balance(G) == 40


@pytest.mark.asyncio
async def test_cassa_che_non_basta_e_nessun_partecipante_e_blacklist(r):
    await r.cassa.deposit(G, 30, "test")
    v = RiffaView(G, 60, 5, "coin", 1)
    await v.partecipa.callback(fake_interaction(guild=fake_guild(G), user=fake_member(1)))
    assert await v.estrai() == (None, "cassa")
    assert await r.cassa.get_balance(G) == 30 and (await r.lev.get_totals(G, 1)).coins_total == 0
    assert await RiffaView(G, 10, 5, "coin", 1).estrai() == (None, "nessuno")
    r.m.blacklist_repo.is_user_blacklisted = AsyncMock(return_value=True)
    v2 = RiffaView(G, 10, 5, "coin", 1)
    await v2.partecipa.callback(fake_interaction(guild=fake_guild(G), user=fake_member(2)))
    assert await v2.estrai() == (None, "nessuno")
    bot = fake_interaction(guild=fake_guild(G), user=fake_member(7, bot=True))
    await RiffaView(G, 10, 5, "coin", 1).partecipa.callback(bot)
    assert bot.response.send_message.await_args.kwargs["ephemeral"] is True
