"""
tests/test_evento_monete_b5.py
==============================
Evento di monete in un canale (#125 B5): ECO-057. Il tetto non si supera mai, anche con messaggi insieme.
Funzioni coperte: catalogo #125
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import discord
import pytest

from cogs.leveling.evento_monete import EventoMoneteCog
from core.repositories.economia_repo import EconomiaRepository
from core.repositories.leveling_repo import LevelingRepository
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.moduli import attiva_livelli

G = 100


@pytest.fixture
def r(clean_db):
    return SimpleNamespace(eco=EconomiaRepository(pool_provider=lambda: clean_db),
                           lev=LevelingRepository(pool_provider=lambda: clean_db), pool=clean_db)


@pytest.mark.asyncio
async def test_un_solo_evento_attivo_e_valori_validi(r):
    assert await r.eco.avvia_evento(G, 5, 10, 100, 1) is not None
    assert await r.eco.avvia_evento(G, 6, 10, 100, 1) is None
    assert await r.eco.avvia_evento(G + 1, 6, 10, 100, 1) is not None
    for brutto in ((0, 100), (10, 5), (-1, 100)):
        with pytest.raises(ValueError):
            await r.eco.avvia_evento(G + 2, 6, brutto[0], brutto[1], 1)
    assert await r.eco.chiudi_evento(G) == (0, 100)
    assert await r.eco.chiudi_evento(G) is None
    assert await r.eco.avvia_evento(G, 6, 10, 100, 1) is not None  # chiuso: se ne può fare un altro


@pytest.mark.asyncio
async def test_il_tetto_non_si_supera_con_messaggi_insieme(r):
    await r.eco.avvia_evento(G, 5, 30, 100, 1)  # 3 messaggi pagano 90, il 4° no (120 > 100)
    await apri_connessioni(r.pool, 8)
    dati = await asyncio.gather(*[r.eco.premia_messaggio(G, 5, u) for u in range(10, 18)])
    assert sorted(dati) == [0] * 5 + [30] * 3
    assert sum([(await r.lev.get_totals(G, u)).coins_total for u in range(10, 18)]) == 90
    assert await r.eco.premia_messaggio(G, 6, 99) == 0  # altro canale
    assert await r.eco.premia_messaggio(G + 1, 5, 99) == 0  # altro server


@pytest.mark.asyncio
async def test_si_chiude_da_solo_al_tetto(r):
    await r.eco.avvia_evento(G, 5, 50, 100, 1)
    assert [await r.eco.premia_messaggio(G, 5, 1), await r.eco.premia_messaggio(G, 5, 2)] == [50, 50]
    assert await r.eco.evento_attivo(G) is None
    assert await r.eco.premia_messaggio(G, 5, 3) == 0


def _msg(uid, canale=5, bot=False):
    m = MagicMock()
    m.guild = fake_guild(G)
    m.author = fake_member(uid, bot=bot)
    m.channel = MagicMock(id=canale)
    m.type = discord.MessageType.default
    return m


@pytest.mark.asyncio
async def test_ascolto_pausa_per_persona_bot_e_comando(monkeypatch, clean_db, r):
    await attiva_livelli(monkeypatch, clean_db, G)
    cog = EventoMoneteCog(bot=None)
    cog.cog_unload()
    i = fake_interaction(guild=fake_guild(G), user=fake_member(1))
    canale = MagicMock(id=5, mention="#c")
    await cog.avvia.callback(cog, i, canale, 10, 1000)
    i2 = fake_interaction(guild=fake_guild(G), user=fake_member(1))
    await cog.avvia.callback(cog, i2, canale, 10, 1000)  # già attivo
    assert i2.response.send_message.await_args.kwargs["ephemeral"] is True
    await cog.on_message(_msg(7))
    await cog.on_message(_msg(7))  # subito dopo: in pausa
    await cog.on_message(_msg(8, bot=True))
    await cog.on_message(_msg(9, canale=6))
    assert [(await r.lev.get_totals(G, u)).coins_total for u in (7, 8, 9)] == [10, 0, 0]
    await cog.chiudi.callback(cog, fake_interaction(guild=fake_guild(G), user=fake_member(1)))
    await cog.on_message(_msg(11))
    assert (await r.lev.get_totals(G, 11)).coins_total == 0
