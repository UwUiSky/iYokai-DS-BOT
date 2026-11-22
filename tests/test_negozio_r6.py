"""
tests/test_negozio_r6.py
========================
Negozio avanzato (#125 r6eco): rotazione (ECO-075), offerte lampo (ECO-076), ricette (ECO-078).
Il prezzo effettivo si applica dentro la scrittura dell'acquisto; due clic insieme non superano gli usi.
Funzioni coperte: catalogo #125
"""

import asyncio
from datetime import date
from types import SimpleNamespace

import pytest

from cogs.leveling.negozio_extra import leggi_ingredienti
from core.negozio_logic import prezzo_con_sconto, scelti_rotazione
from core.repositories.inventario_repo import InventarioRepository
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.negozio_repo import EsitoRicetta, NegozioRepository
from core.repositories.shop_repo import EsitoAcquisto, ShopRepository
from tests.support.concorrenza import apri_connessioni

G = 100


@pytest.fixture
def r(clean_db):
    return SimpleNamespace(
        shop=ShopRepository(pool_provider=lambda: clean_db), neg=NegozioRepository(pool_provider=lambda: clean_db),
        lev=LevelingRepository(pool_provider=lambda: clean_db), inv=InventarioRepository(pool_provider=lambda: clean_db), pool=clean_db,
    )


async def _oggetto(r, nome="Spada", prezzo=100, ruolo=None):
    n = await r.shop.add_item(G, nome, prezzo, ruolo, None)
    return await r.shop.get_item(n if isinstance(n, int) else n.id, G)


async def _saldo(r, u):
    return (await r.lev.get_totals(G, u)).coins_total


def test_prezzo_con_sconto_e_rotazione_stabile():
    assert prezzo_con_sconto(100, 25) == 75 and prezzo_con_sconto(100, None) == 100 and prezzo_con_sconto(1, 90) == 1
    assert prezzo_con_sconto(100, 500) == 10  # lo sconto non supera il 90%
    ids = list(range(1, 11))
    oggi = scelti_rotazione(ids, G, date(2026, 11, 20), 3)
    assert len(oggi) == 3 and oggi == scelti_rotazione(ids, G, date(2026, 11, 20), 3)
    assert any(scelti_rotazione(ids, G, date(2026, 11, 20 + k), 3) != oggi for k in range(1, 6))
    assert scelti_rotazione(ids, G, date(2026, 11, 20), 0) == set(ids)


@pytest.mark.asyncio
async def test_offerta_lampo_si_paga_scontata_e_gli_usi_sono_atomici(r):
    item = await _oggetto(r)
    assert await r.neg.crea_offerta(G, item.id, 50, 10, 1, 9)
    for u in (1, 2):
        await r.lev.add_coins(G, u, 500)
    prezzo, sconto = await r.neg.prezzo_oggi(G, item)
    assert (prezzo, sconto) == (50, 50)
    await apri_connessioni(r.pool, 4)
    a, b = await asyncio.gather(r.shop.buy_item(G, 1, item, prezzo_atteso=50), r.shop.buy_item(G, 2, item, prezzo_atteso=50))
    esiti = sorted([a.esito.value, b.esito.value])
    assert esiti == ["prezzo_cambiato", "riuscito"]  # il secondo trova l'offerta finita: prezzo pieno != atteso
    pagati = [await _saldo(r, 1), await _saldo(r, 2)]
    assert sorted(pagati) == [450, 500]  # chi ha comprato ha pagato 50, l'altro niente
    assert (await r.neg.offerte_attive(G)) == {}  # usi finiti


@pytest.mark.asyncio
async def test_offerta_scaduta_o_chiusa_non_vale(r):
    item = await _oggetto(r)
    await r.neg.crea_offerta(G, item.id, 50, 10, None, 9)
    await r.pool.execute("UPDATE economia_offerte SET scade_at = now() - interval '1 minute'")
    assert await r.neg.prezzo_oggi(G, item) == (100, None)
    await r.lev.add_coins(G, 1, 500)
    a = await r.shop.buy_item(G, 1, item, prezzo_atteso=100)
    assert a.esito == EsitoAcquisto.RIUSCITO and a.prezzo == 100 and await _saldo(r, 1) == 400
    await r.neg.crea_offerta(G, item.id, 20, 10, None, 9)
    assert await r.neg.togli_offerta(G, item.id) and not await r.neg.togli_offerta(G, item.id)
    assert not await r.neg.crea_offerta(G, 999999, 20, 10, None, 9)  # oggetto che non c'è


@pytest.mark.asyncio
async def test_rotazione_nasconde_e_blocca_chi_non_e_in_vetrina_ma_l_offerta_lo_riapre(r):
    oggetti = [await _oggetto(r, f"O{i}", 10) for i in range(6)]
    for o in oggetti:
        assert await r.neg.imposta_a_rotazione(G, o.id, True)
    await r.neg.imposta_rotazione(G, 2)
    visibili = await r.neg.in_vetrina(G)
    assert len(visibili) == 2
    fuori = next(o for o in oggetti if o.id not in visibili)
    dentro = next(o for o in oggetti if o.id in visibili)
    await r.lev.add_coins(G, 1, 100)
    a = await r.shop.buy_item(G, 1, fuori)
    assert a.esito == EsitoAcquisto.NON_IN_VENDITA and await _saldo(r, 1) == 100
    assert (await r.shop.buy_item(G, 1, dentro)).esito == EsitoAcquisto.RIUSCITO
    await r.neg.crea_offerta(G, fuori.id, 50, 10, None, 9)
    b = await r.shop.buy_item(G, 1, fuori, prezzo_atteso=5)
    assert b.esito == EsitoAcquisto.RIUSCITO and b.prezzo == 5
    await r.neg.imposta_rotazione(G, 0)
    assert await r.neg.in_vetrina(G) is None


def test_lettura_degli_ingredienti():
    assert leggi_ingredienti("3:2, 5:1") == {3: 2, 5: 1}
    for brutto in ("3", "a:1", "3:0", "3:1,3:2", "3:101", "1:1,2:1,3:1,4:1,5:1,6:1", "-1:2", ""):
        assert leggi_ingredienti(brutto) is None


@pytest.mark.asyncio
async def test_ricetta_toglie_ingredienti_e_da_il_risultato_in_una_volta(r):
    legno, ferro, spada = await _oggetto(r, "Legno", 5), await _oggetto(r, "Ferro", 5), await _oggetto(r, "Spada", 50)
    ruolo = await _oggetto(r, "Ruolo", 5, ruolo=777)
    assert await r.neg.crea_ricetta(G, "forgia", spada.id, 1, 10, {legno.id: 2, ferro.id: 1}) == "ok"
    assert await r.neg.crea_ricetta(G, "forgia", spada.id, 1, 0, {legno.id: 1}) == "esiste"
    assert await r.neg.crea_ricetta(G, "x", ruolo.id, 1, 0, {legno.id: 1}) == "oggetto"
    assert await r.neg.crea_ricetta(G, "y", spada.id, 1, 0, {spada.id: 1}) == "oggetto"
    assert await r.neg.crea_ricetta(G, "z", spada.id, 1, 0, {}) == "ingredienti"
    await r.lev.add_coins(G, 1, 100)
    for _ in range(2):
        await r.shop.buy_item(G, 1, legno)
    assert await r.neg.crea_oggetto(G, 1, "forgia") == EsitoRicetta.MANCANO  # manca il ferro
    assert {v.nome: v.quantita for v in await r.inv.lista(G, 1)} == {"Legno": 2}  # il legno non è stato tolto
    await r.shop.buy_item(G, 1, ferro)
    saldo = await _saldo(r, 1)
    assert await r.neg.crea_oggetto(G, 1, "FORGIA") == EsitoRicetta.FATTO
    assert {v.nome: v.quantita for v in await r.inv.lista(G, 1)} == {"Spada": 1}
    assert await _saldo(r, 1) == saldo - 10
    assert await r.neg.crea_oggetto(G, 1, "nulla") == EsitoRicetta.NON_ESISTE
    assert [x.nome for x in await r.neg.ricette(G)] == ["forgia"]


@pytest.mark.asyncio
async def test_ricetta_costo_non_pagabile_annulla_tutto_e_due_clic_ne_creano_uno(r):
    a, b = await _oggetto(r, "A", 1), await _oggetto(r, "B", 1)
    await r.neg.crea_ricetta(G, "m", b.id, 1, 50, {a.id: 1})
    await r.lev.add_coins(G, 1, 60)
    await r.shop.buy_item(G, 1, a)  # saldo 59, un solo A
    await r.pool.execute("UPDATE leveling_totals SET coins_total = 10 WHERE user_id = 1")
    assert await r.neg.crea_oggetto(G, 1, "m") == EsitoRicetta.POCHE_MONETE
    assert {v.nome: v.quantita for v in await r.inv.lista(G, 1)} == {"A": 1}  # l'ingrediente è tornato
    await r.pool.execute("UPDATE leveling_totals SET coins_total = 500 WHERE user_id = 1")
    await apri_connessioni(r.pool, 4)
    esiti = await asyncio.gather(r.neg.crea_oggetto(G, 1, "m"), r.neg.crea_oggetto(G, 1, "m"))
    assert sorted(e.value for e in esiti) == ["fatto", "mancano"]
    assert {v.nome: v.quantita for v in await r.inv.lista(G, 1)} == {"B": 1} and await _saldo(r, 1) == 450


@pytest.mark.asyncio
async def test_togliere_un_oggetto_toglie_ricette_e_offerte(r):
    a, b = await _oggetto(r, "A", 1), await _oggetto(r, "B", 1)
    await r.neg.crea_ricetta(G, "m", b.id, 1, 0, {a.id: 1})
    await r.neg.crea_offerta(G, a.id, 10, 5, None, 1)
    assert await r.shop.remove_item(a.id, G)
    assert await r.neg.ricette(G) == [] and await r.neg.offerte_attive(G) == {}
    assert await r.pool.fetchval("SELECT count(*) FROM economia_ricette_ingredienti") == 0
