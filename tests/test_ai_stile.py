"""
tests/test_ai_stile.py
======================
Messaggi «nello stile» di una persona (§25.36): propri sempre, di altri solo con il loro permesso. Database vero.
"""

from unittest.mock import AsyncMock

import pytest

from cogs.ai import personale, summaries
from core.ai_servizio import imposta_servizio_ai
from core.database import db
from core.repositories.ai_repo import ai_repo
from tests.support.ai_finto import TrasportoFinto, fornitore, servizio_finto
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

G, U, ALTRO = 9701, 9702, 9703


@pytest.fixture
def repo(clean_db, monkeypatch):
    monkeypatch.setattr(ai_repo, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(db, "_pool", clean_db, raising=False)
    s, t = servizio_finto(ai_repo, trasporto=TrasportoFinto(risposte={"alfa": "ciao ragazzi, che giornata"}))
    imposta_servizio_ai(s)
    yield t
    imposta_servizio_ai(None)


def _inter(user_id=U):
    i = fake_interaction(guild=fake_guild(G), user=fake_member(user_id))
    i.guild_id = G
    i.channel_id = i.channel.id
    return i


async def test_stile_di_un_altro_senza_permesso_e_rifiutato(repo, monkeypatch):
    letto = AsyncMock(return_value="esempio")
    monkeypatch.setattr(summaries, "testo_canale", letto)
    cog = summaries.AiRiassuntiCog(bot=None)
    i = _inter()
    altro = fake_member(ALTRO)
    altro.bot = False
    await cog.stile.callback(cog, i, "il tempo", altro)
    assert "non ha permesso" in i.response.send_message.call_args.args[0]
    letto.assert_not_awaited()
    assert not repo.chiamate


async def test_stile_di_un_altro_con_permesso_usa_i_suoi_messaggi_e_lo_dice(repo, monkeypatch):
    await ai_repo.registra_consenso(G, U, True)
    p = personale.AiPersonaleCog(bot=None)
    i_altro = _inter(ALTRO)
    await p.preferenza.callback(p, i_altro, None, True)
    assert await ai_repo.stile_consentito(ALTRO)
    letto = AsyncMock(return_value="esempio dell'altro")
    monkeypatch.setattr(summaries, "testo_canale", letto)
    cog = summaries.AiRiassuntiCog(bot=None)
    i = _inter()
    altro = fake_member(ALTRO)
    altro.bot = False
    await cog.stile.callback(cog, i, "il tempo", altro)
    assert letto.await_args.kwargs["autore_id"] == ALTRO
    assert "non l'ha scritto lui" in i.followup.send.call_args.args[0]


async def test_stile_proprio_non_chiede_permessi(repo, monkeypatch):
    await ai_repo.registra_consenso(G, U, True)
    monkeypatch.setattr(summaries, "testo_canale", AsyncMock(return_value="miei messaggi"))
    cog = summaries.AiRiassuntiCog(bot=None)
    i = _inter()
    await cog.stile.callback(cog, i, "il tempo", None)
    assert "non l'ha scritto" not in i.followup.send.call_args.args[0]


async def test_preferenza_stile_si_toglie_e_senza_scelte_avvisa(repo):
    p = personale.AiPersonaleCog(bot=None)
    await p.preferenza.callback(p, _inter(ALTRO), None, True)
    await p.preferenza.callback(p, _inter(ALTRO), None, False)
    assert not await ai_repo.stile_consentito(ALTRO)
    i = _inter()
    await p.preferenza.callback(p, i, None, None)
    assert "almeno una scelta" in i.response.send_message.call_args.args[0]
