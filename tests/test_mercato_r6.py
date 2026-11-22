"""
tests/test_mercato_r6.py
========================
Mercato tra utenti e fondo premi (#125 r6eco): ECO-074, ECO-120. Scambi atomici, mai a se stessi, blocchi rispettati.
Funzioni coperte: catalogo #125
"""

import asyncio
from types import SimpleNamespace

import pytest

from core.repositories.inventario_repo import InventarioRepository
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.mercato_repo import Esito, MercatoRepository
from core.repositories.shop_repo import ShopRepository
from tests.support.concorrenza import apri_connessioni

G = 100


@pytest.fixture
def r(clean_db):
    return SimpleNamespace(
        m=MercatoRepository(pool_provider=lambda: clean_db), shop=ShopRepository(pool_provider=lambda: clean_db),
        lev=LevelingRepository(pool_provider=lambda: clean_db), inv=InventarioRepository(pool_provider=lambda: clean_db), pool=clean_db,
    )


async def _con_oggetto(r, utenti=(1,)):
    n = await r.shop.add_item(G, "Spada", 10, None, None)
    item = await r.shop.get_item(n if isinstance(n, int) else n.id, G)
    for u in {1, *utenti}:
        await r.lev.add_coins(G, u, 1000)
    await r.shop.buy_item(G, 1, item)
    await r.shop.buy_item(G, 1, item)
    return item


async def _saldo(r, u):
    return (await r.lev.get_totals(G, u)).coins_total


async def _qta(r, u, item):
    return next((v.quantita for v in await r.inv.lista(G, u) if v.item_id == item.id), 0)


async def _annuncio(r, item, prezzo=100):
    assert await r.m.pubblica(G, 1, item.id, 1, prezzo, 3) is Esito.FATTO
    return (await r.m.elenco(G))[0].id


@pytest.mark.asyncio
async def test_pubblica_tiene_in_custodia_e_compra_scambia_in_una_volta(r):
    item = await _con_oggetto(r, (1, 2))
    assert await r.m.pubblica(G, 1, item.id, 5, 100, 3) is Esito.NON_HAI
    a = await _annuncio(r, item)
    assert await _qta(r, 1, item) == 1
    assert await r.m.compra(G, 1, a) is Esito.A_SE_STESSI
    s1, s2 = await _saldo(r, 1), await _saldo(r, 2)
    assert await r.m.compra(G, 2, a) is Esito.FATTO
    assert await _saldo(r, 2) == s2 - 100 and await _saldo(r, 1) == s1 + 100 and await _qta(r, 2, item) == 1
    assert await r.m.compra(G, 2, a) is Esito.NON_ESISTE


@pytest.mark.asyncio
async def test_due_compratori_insieme_uno_solo_e_scambi_incrociati_non_si_bloccano(r):
    item = await _con_oggetto(r, (1, 2, 3))
    a = await _annuncio(r, item)
    await apri_connessioni(r.pool, 4)
    e = await asyncio.gather(r.m.compra(G, 2, a), r.m.compra(G, 3, a))
    assert sorted(x.value for x in e) == ["fatto", "non_esiste"]
    # scambi incrociati: 1 vende a 2 mentre 2 vende a 1
    n = await r.shop.add_item(G, "Arco", 10, None, None)
    arco = await r.shop.get_item(n if isinstance(n, int) else n.id, G)
    await r.shop.buy_item(G, 2, arco)
    await r.m.pubblica(G, 2, arco.id, 1, 50, 3)
    await r.shop.buy_item(G, 1, item)
    await r.m.pubblica(G, 1, item.id, 1, 60, 3)
    ids = {x.venditore: x.id for x in await r.m.elenco(G) if x.item_id in (item.id, arco.id)}
    e = await asyncio.wait_for(asyncio.gather(r.m.compra(G, 2, ids[1]), r.m.compra(G, 1, ids[2])), 20)
    assert [x.value for x in e] == ["fatto", "fatto"]


@pytest.mark.asyncio
async def test_poche_monete_blocco_e_oggetto_non_regalabile(r):
    item = await _con_oggetto(r, (2,))
    a = await _annuncio(r, item, 5000)
    assert await r.m.compra(G, 2, a) is Esito.POCHE_MONETE and await _qta(r, 1, item) == 1
    await r.pool.execute("INSERT INTO economia_blocchi (user_id, bloccato_id) VALUES (1, 2)")
    assert await r.m.compra(G, 2, a) is Esito.BLOCCATO and await r.m.offri(G, 2, a, 10) is Esito.BLOCCATO
    await r.pool.execute("UPDATE shop_items SET regalabile = FALSE")
    assert await r.m.pubblica(G, 1, item.id, 1, 5, 3) is Esito.NON_COMMERCIABILE


@pytest.mark.asyncio
async def test_offerta_in_custodia_accettata_ritirata_e_scadenza(r):
    item = await _con_oggetto(r, (2, 3))
    a = await _annuncio(r, item, 500)
    assert await r.m.offri(G, 2, a, 500) is Esito.OFFERTA_NO and await r.m.offri(G, 1, a, 10) is Esito.A_SE_STESSI
    s2 = await _saldo(r, 2)
    assert await r.m.offri(G, 2, a, 100) is Esito.FATTO and await _saldo(r, 2) == s2 - 100
    assert await r.m.offri(G, 2, a, 150) is Esito.FATTO and await _saldo(r, 2) == s2 - 150  # sostituisce la vecchia
    assert await r.m.offri(G, 3, a, 200) is Esito.FATTO
    assert await r.m.ritira_offerta(G, 3, a) is Esito.FATTO and await _saldo(r, 3) == 1000
    assert await r.m.offri(G, 3, a, 200) is Esito.FATTO
    s1 = await _saldo(r, 1)
    assert await r.m.accetta(G, 2, a, 3) is Esito.NON_TUO
    assert await r.m.accetta(G, 1, a, 3) is Esito.FATTO
    assert await _saldo(r, 1) == s1 + 200 and await _qta(r, 3, item) == 1 and await _saldo(r, 3) == 800
    assert await _saldo(r, 2) == s2  # l'offerta non accettata è tornata
    assert await r.pool.fetchval("SELECT count(*) FROM economia_mercato_offerte") == 0
    b = await _annuncio(r, item, 500)
    await r.m.offri(G, 2, b, 100)
    await r.pool.execute("UPDATE economia_mercato SET scade_at = now() - interval '1 minute'")
    assert await r.m.compra(G, 3, b) is Esito.SCADUTO
    assert await r.m.scadenze() == 1
    assert await _saldo(r, 2) == s2 and await _qta(r, 1, item) == 1  # oggetto al venditore, monete all'offerente


@pytest.mark.asyncio
async def test_ritira_solo_il_proprio_e_dono_al_fondo(r):
    item = await _con_oggetto(r, (2,))
    a = await _annuncio(r, item)
    assert await r.m.ritira(G, 2, a) is Esito.NON_TUO and await r.m.ritira(G, 1, a) is Esito.FATTO and await _qta(r, 1, item) == 2
    assert await r.m.dona_oggetto(G, 1, item.id) is Esito.FATTO and await _qta(r, 1, item) == 1
    assert await r.m.dona_oggetto(G, 2, item.id) is Esito.NON_HAI
    assert [x[2] for x in await r.m.fondo(G)] == [1]
    assert await r.m.dai_dal_fondo(G, 2, item.id) and not await r.m.dai_dal_fondo(G, 2, item.id) and await _qta(r, 2, item) == 1
    s = await _saldo(r, 2)
    assert await r.m.dona_monete(G, 2, 100) and not await r.m.dona_monete(G, 2, 10_000)
    assert await _saldo(r, 2) == s - 100
    assert await r.pool.fetchval("SELECT balance FROM guild_chest WHERE guild_id = $1", G) == 100
