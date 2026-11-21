"""
tests/test_sociale_b15.py
=========================
Amici, blocchi, matrimonio, prestigio e azzeramento dei propri dati (#125 B15): ECO-148, 149, 153, 154, 155, 159.
Funzioni coperte: catalogo #125
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cogs.leveling.sociale import RichiestaView
from core.repositories.guild_chest_repo import GuildChestRepository
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.rischio_repo import RischioRepository
from core.repositories.sociale_repo import COSTO_MATRIMONIO, SocialeRepository, coppia, soglia_prestigio
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

G = 100


@pytest.fixture
def r(clean_db):
    return SimpleNamespace(
        s=SocialeRepository(pool_provider=lambda: clean_db), lev=LevelingRepository(pool_provider=lambda: clean_db),
        rk=RischioRepository(pool_provider=lambda: clean_db), cassa=GuildChestRepository(pool_provider=lambda: clean_db), pool=clean_db,
    )


def test_logica_coppie_e_soglie():
    assert coppia(5, 2) == (2, 5)
    with pytest.raises(ValueError):
        coppia(3, 3)
    assert [soglia_prestigio(n) for n in (0, 1, 4, 5, -1)] == [10_000, 20_000, 50_000, None, None]


@pytest.mark.asyncio
async def test_blocchi_amici_e_massimi(r):
    assert await r.s.blocca(1, 2) == "ok" and await r.s.blocca(1, 2) == "gia"
    assert await r.s.ha_bloccato(1, 2) and not await r.s.ha_bloccato(2, 1)  # il blocco è a senso unico
    with pytest.raises(ValueError):
        await r.s.blocca(1, 1)
    assert await r.s.elenco_blocchi(1) == [2] and await r.s.sblocca(1, 2) and not await r.s.sblocca(1, 2)
    assert await r.s.aggiungi_amico(G, 5, 2) == "ok" and await r.s.aggiungi_amico(G, 2, 5) == "gia"
    assert await r.s.sono_amici(G, 2, 5) and not await r.s.sono_amici(G + 1, 2, 5) and not await r.s.sono_amici(G, 2, 2)
    assert await r.s.amici_di(G, 5) == [2] and await r.s.togli_amico(G, 5, 2) and not await r.s.sono_amici(G, 2, 5)
    for n in range(10, 60):
        await r.s.aggiungi_amico(G, 1, n)
    assert await r.s.aggiungi_amico(G, 1, 99) == "pieno"


@pytest.mark.asyncio
async def test_matrimonio_costa_a_entrambi_o_niente_e_si_mantiene(r):
    await r.lev.add_coins(G, 1, 300)
    await r.lev.add_coins(G, 2, 100)  # non basta
    assert await r.s.sposa(G, 1, 2) == "poche"
    assert [(await r.lev.get_totals(G, u)).coins_total for u in (1, 2)] == [300, 100] and await r.s.coniuge(G, 1) is None  # annullato tutto
    await r.lev.add_coins(G, 2, 200)
    assert await r.s.sposa(G, 2, 1) == "ok"
    assert await r.cassa.get_balance(G) == 2 * COSTO_MATRIMONIO and await r.s.coniuge(G, 1) == 2
    await r.lev.add_coins(G, 3, 500)
    assert await r.s.sposa(G, 3, 1) == "gia"  # 1 è già sposato
    assert (await r.lev.get_totals(G, 3)).coins_total == 500
    await r.pool.execute("UPDATE economia_matrimoni SET mantenuto_at = now() - interval '15 days'")
    assert await r.s.coniuge(G, 1) is None and await r.s.mantieni(G, 1) is False  # scaduto
    await r.lev.add_coins(G, 1, 300)
    assert await r.s.sposa(G, 3, 1) == "ok"  # il vecchio matrimonio scaduto non blocca
    assert await r.s.mantieni(G, 3) and await r.s.divorzia(G, 3) and not await r.s.divorzia(G, 3)


@pytest.mark.asyncio
async def test_prestigio_azzera_e_sale_una_volta(r):
    await r.lev.add_coins(G, 1, 6000)
    await r.rk.deposita(G, 1, 3000)
    assert await r.s.prestigio(G, 1) == ("poche", 10_000)
    assert (await r.rk.banca(G, 1)).contanti == 3000  # niente azzerato
    await r.lev.add_coins(G, 1, 4000)
    await r.pool.execute("INSERT INTO economia_lavoro (guild_id, user_id, turni) VALUES ($1, 1, 50)", G)
    await apri_connessioni(r.pool, 3)
    esiti = await asyncio.gather(*[r.s.prestigio(G, 1) for _ in range(3)])
    assert [e for e in esiti if e[0] == "ok"] == [("ok", 1)]
    b = await r.rk.banca(G, 1)
    assert (b.contanti, b.banca) == (0, 0) and await r.s.livello_prestigio(G, 1) == 1
    assert await r.pool.fetchval("SELECT count(*) FROM economia_lavoro WHERE user_id = 1") == 0


@pytest.mark.asyncio
async def test_azzera_miei_dati_solo_i_miei_e_solo_il_server(r):
    await r.lev.add_coins(G, 1, 50)
    await r.lev.add_coins(G, 2, 70)
    await r.lev.add_coins(G + 1, 1, 90)
    await r.pool.execute("INSERT INTO economia_inventario (guild_id, user_id, item_id, quantita) VALUES ($1, 1, 5, 2), ($1, 2, 5, 1)", G)
    await r.s.aggiungi_amico(G, 1, 2)
    assert await r.s.azzera_miei_dati(G, 1) >= 3
    assert [(await r.lev.get_totals(G, u)).coins_total for u in (1, 2)] == [0, 70] and (await r.lev.get_totals(G + 1, 1)).coins_total == 90
    assert await r.pool.fetchval("SELECT count(*) FROM economia_inventario WHERE guild_id = $1", G) == 1
    assert not await r.s.sono_amici(G, 1, 2)


@pytest.mark.asyncio
async def test_richiesta_solo_il_destinatario_e_una_volta(monkeypatch):
    import core.ui_base as ui

    async def nessuno(*a, **k):
        return False

    monkeypatch.setattr(ui, "_utente_o_server_in_blacklist", nessuno)
    chiamate = []

    async def azione():
        chiamate.append(1)
        return "soc_amici_ok"

    a, b = fake_member(1), fake_member(2)
    v = RichiestaView(a, b, azione)
    assert await v.interaction_check(fake_interaction(guild=fake_guild(G), user=a)) is False
    assert await v.interaction_check(fake_interaction(guild=fake_guild(G), user=b)) is True
    for _ in range(2):
        i = fake_interaction(guild=fake_guild(G), user=b)
        i.response.edit_message = AsyncMock()
        await v.accetta.callback(i)
    assert chiamate == [1]
