"""
tests/test_sfide_b7.py
======================
Duelli con posta (#125 B7): ECO-104, ECO-106. Posta bloccata a entrambi nella stessa transazione, solo lo
sfidato accetta, nessuna moneta creata o persa. PostgreSQL vero.
Funzioni coperte: catalogo #125
"""

import asyncio
import random
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cogs.fun.sfide import DuelloView, SfideCog
from core.duello_logic import guadagno_con_tetto, lancia_duello
from core.repositories.duelli_repo import DuelliRepository, EsitoPosta
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.leveling_settings_repo import LevelingSettingsRepository
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

G = 100


@pytest.fixture
def r(clean_db):
    return SimpleNamespace(
        d=DuelliRepository(pool_provider=lambda: clean_db), lev=LevelingRepository(pool_provider=lambda: clean_db),
        imp=LevelingSettingsRepository(pool_provider=lambda: clean_db), pool=clean_db,
    )


def test_logica_duello_equa_e_senza_parita():
    rng = random.Random(7)
    esiti = [lancia_duello(rng) for _ in range(4000)]
    assert all(sum(e.tiri_sfidante) != sum(e.tiri_sfidato) for e in esiti)
    assert 0.46 < sum(e.vince_sfidante for e in esiti) / len(esiti) < 0.54
    assert guadagno_con_tetto(100, 950, 1000) == 50 and guadagno_con_tetto(100, 1200, 1000) == 0
    assert guadagno_con_tetto(100, 5, None) == 100 and guadagno_con_tetto(100, 5, 0) == 100


@pytest.mark.asyncio
async def test_posta_passa_dal_perdente_al_vincitore_e_serve_a_entrambi(r):
    await r.lev.add_coins(G, 1, 100)
    await r.lev.add_coins(G, 2, 100)
    assert (await r.d.regola(G, 1, 2, True, 60)).importo == 60
    assert [(await r.lev.get_totals(G, u)).coins_total for u in (1, 2)] == [160, 40]
    assert (await r.d.regola(G, 1, 2, True, 60)).esito is EsitoPosta.SFIDATO_POCHE
    assert (await r.d.regola(G, 2, 1, True, 200)).esito is EsitoPosta.SFIDANTE_POCHE
    assert (await r.d.regola(G, 1, 9, True, 10)).esito is EsitoPosta.SFIDATO_POCHE  # 9 non ha righe
    with pytest.raises(ValueError):
        await r.d.regola(G, 1, 1, True, 10)
    for brutto in (0, -1, 100_001):
        with pytest.raises(ValueError):
            await r.d.regola(G, 1, 2, True, brutto)
    assert sum([(await r.lev.get_totals(G, u)).coins_total for u in (1, 2)]) == 200


@pytest.mark.asyncio
async def test_duelli_insieme_non_creano_monete_e_rispettano_il_tetto(r):
    await r.lev.add_coins(G, 1, 100)
    await r.lev.add_coins(G, 2, 100)
    await apri_connessioni(r.pool, 6)
    esiti = await asyncio.gather(*[r.d.regola(G, 1, 2, i % 2 == 0, 100) for i in range(6)], return_exceptions=True)
    assert not [e for e in esiti if isinstance(e, Exception)]
    assert sum([(await r.lev.get_totals(G, u)).coins_total for u in (1, 2)]) == 200
    assert min([(await r.lev.get_totals(G, u)).coins_total for u in (1, 2)]) >= 0
    await r.imp.set_options(G, tetto_saldo=120)
    await r.lev.modifica_monete(G, 1, "imposta", 100)
    await r.lev.modifica_monete(G, 2, "imposta", 100)
    assert (await r.d.regola(G, 1, 2, True, 100)).importo == 20  # solo fino al tetto
    assert [(await r.lev.get_totals(G, u)).coins_total for u in (1, 2)] == [120, 80]


@pytest.mark.asyncio
async def test_classifica_e_storico(r):
    await r.lev.add_coins(G, 1, 500)
    await r.lev.add_coins(G, 2, 500)
    for v in (True, True, False):
        await r.d.regola(G, 1, 2, v, 10)
    top = await r.d.classifica(G)
    assert [(x["user_id"], x["vinti"], x["persi"], x["netto"]) for x in top] == [(1, 2, 1, 10), (2, 1, 2, -10)]
    assert len(await r.d.storico(G, 1)) == 3 and await r.d.storico(G + 1, 1) == []


@pytest.mark.asyncio
async def test_solo_lo_sfidato_accetta_e_una_volta_sola(r, monkeypatch):
    await r.lev.add_coins(G, 1, 50)
    await r.lev.add_coins(G, 2, 50)
    import cogs.fun.sfide as modulo
    monkeypatch.setattr(modulo, "duelli_repo", r.d)
    a, b = fake_member(1), fake_member(2)
    view = DuelloView(G, a, b, 30, "coin")
    ladro = fake_interaction(guild=fake_guild(G), user=a)
    await view.accetta.callback(ladro)  # lo sfidante non può accettare
    assert ladro.response.send_message.await_args.kwargs["ephemeral"] is True
    assert (await r.lev.get_totals(G, 1)).coins_total == 50
    i = fake_interaction(guild=fake_guild(G), user=b)
    i.response.edit_message = AsyncMock()
    await view.accetta.callback(i)
    tot = [(await r.lev.get_totals(G, u)).coins_total for u in (1, 2)]
    assert sorted(tot) == [20, 80]
    i2 = fake_interaction(guild=fake_guild(G), user=b)
    await view.accetta.callback(i2)  # già fatto
    assert [(await r.lev.get_totals(G, u)).coins_total for u in (1, 2)] == tot


@pytest.mark.asyncio
async def test_comando_rifiuta_bot_e_se_stessi(monkeypatch, clean_db):
    from core.database import db
    async def attivo(self, g, n):
        return True
    monkeypatch.setattr(type(db), "is_module_active_for_guild", attivo)
    cog = SfideCog(bot=None)
    for bersaglio in (fake_member(1), fake_member(9, bot=True)):
        i = fake_interaction(guild=fake_guild(G), user=fake_member(1))
        await cog.duello.callback(cog, i, bersaglio, 10)
        assert i.response.send_message.await_args.kwargs["ephemeral"] is True
