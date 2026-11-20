"""
tests/test_inventario_b3.py
===========================
Inventario del negozio (#125 B3): ECO-058 elenco, ECO-059 uso, ECO-070/071 regalo, ECO-072 rivendita,
ECO-073 scheda, ECO-086 azzeramento. Scritture atomiche provate con richieste insieme.
Funzioni coperte: SPEC §15.4, catalogo #125
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cogs.leveling.inventario import InventarioCog
from core.leveling_logic import prezzo_rivendita
from core.repositories.inventario_repo import Esito, InventarioRepository
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.shop_repo import ShopRepository
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.moduli import attiva_livelli

G = 100


@pytest.fixture
def r(clean_db):
    return SimpleNamespace(
        shop=ShopRepository(pool_provider=lambda: clean_db),
        inv=InventarioRepository(pool_provider=lambda: clean_db),
        lev=LevelingRepository(pool_provider=lambda: clean_db),
        pool=clean_db,
    )


async def _nuovo(r, nome, prezzo, ruolo, descrizione):
    nuovo = await r.shop.add_item(G, nome, prezzo, ruolo, descrizione)
    return await r.shop.get_item(nuovo if isinstance(nuovo, int) else nuovo.id, G)


async def _compra(r, utente=1, prezzo=100):
    item = await _nuovo(r, "Spada", prezzo, None, "affilata")
    await r.lev.add_coins(G, utente, 1000)
    a = await r.shop.buy_item(G, utente, item)
    assert a.esito.value == "riuscito"
    return item


def test_rivendita_sempre_meno_del_prezzo():
    assert prezzo_rivendita(100) == 50 and prezzo_rivendita(1) == 0 and prezzo_rivendita(-5) == 0


@pytest.mark.asyncio
async def test_l_acquisto_riempie_l_inventario_e_il_ruolo_no(r):
    item = await _compra(r)
    await r.shop.buy_item(G, 1, item)
    assert [(v.nome, v.quantita) for v in await r.inv.lista(G, 1)] == [("Spada", 2)]
    ruolo = await _nuovo(r, "Ruolo", 10, 555, None)
    await r.shop.buy_item(G, 1, ruolo)
    assert len(await r.inv.lista(G, 1)) == 1  # il ruolo non è un oggetto da tenere


@pytest.mark.asyncio
async def test_uso_consuma_un_pezzo_anche_insieme(r):
    item = await _compra(r)
    await apri_connessioni(r.pool, 4)
    esiti = await asyncio.gather(*[r.inv.usa(G, 1, item.id) for _ in range(4)])
    assert esiti.count(True) == 1 and await r.inv.lista(G, 1) == []


@pytest.mark.asyncio
async def test_regalo_atomico_non_regalabile_e_mai_a_se_stessi(r):
    item = await _compra(r)
    assert await r.inv.regala(G, 1, 2, item.id) is Esito.FATTO
    assert await r.inv.lista(G, 1) == [] and (await r.inv.lista(G, 2))[0].quantita == 1
    assert await r.inv.regala(G, 1, 2, item.id) is Esito.NON_HAI
    with pytest.raises(ValueError):
        await r.inv.regala(G, 2, 2, item.id)
    await r.shop.update_item(item.id, G, regalabile=False)
    assert await r.inv.regala(G, 2, 3, item.id) is Esito.NON_REGALABILE
    assert (await r.inv.lista(G, 2))[0].quantita == 1


@pytest.mark.asyncio
async def test_regali_incrociati_insieme_non_si_bloccano(r):
    item = await _compra(r)
    await r.shop.buy_item(G, 1, item)
    await r.lev.add_coins(G, 2, 1000)
    await r.shop.buy_item(G, 2, item)
    await apri_connessioni(r.pool, 4)
    esiti = await asyncio.gather(
        *[r.inv.regala(G, 1, 2, item.id), r.inv.regala(G, 2, 1, item.id)] * 2, return_exceptions=True
    )
    assert not [e for e in esiti if isinstance(e, Exception)]
    totale = sum(v.quantita for v in (await r.inv.lista(G, 1)) + (await r.inv.lista(G, 2)))
    assert totale == 3  # niente creato né perso: 1+2 pezzi comprati in tutto


@pytest.mark.asyncio
async def test_rivendita_metà_prezzo_una_volta_per_pezzo(r):
    item = await _compra(r, prezzo=100)
    saldo0 = (await r.lev.get_totals(G, 1)).coins_total
    await apri_connessioni(r.pool, 4)
    esiti = await asyncio.gather(*[r.inv.vendi(G, 1, item.id) for _ in range(4)])
    assert [e.esito for e in esiti].count(Esito.FATTO) == 1
    from datetime import datetime, timezone
    from core.leveling_logic import tasso_del_giorno
    assert (await r.lev.get_totals(G, 1)).coins_total == saldo0 + tasso_del_giorno(G, datetime.now(timezone.utc).date())  # 100 * tasso%
    gratis = await _nuovo(r, "Sassolino", 1, None, None)
    await r.lev.add_coins(G, 1, 5)
    await r.shop.buy_item(G, 1, gratis)
    assert (await r.inv.vendi(G, 1, gratis.id)).esito is Esito.NIENTE_DA_PAGARE
    assert (await r.inv.lista(G, 1))[0].nome == "Sassolino"  # non è stato tolto


@pytest.mark.asyncio
async def test_oggetto_rimosso_toglie_l_inventario_e_azzera_server(r):
    item = await _compra(r)
    await r.shop.remove_item(item.id, G)
    assert await r.inv.lista(G, 1) == []
    item2 = await _compra(r)
    assert await r.inv.azzera_server(G + 1) == 0
    assert await r.inv.azzera_server(G) == 1 and await r.inv.lista(G, 1) == []
    del item2


@pytest.fixture
async def cog(monkeypatch, clean_db):
    await attiva_livelli(monkeypatch, clean_db, G)
    return InventarioCog(bot=None)


def _i(uid=1, nome="Casa"):
    i = fake_interaction(guild=fake_guild(G, nome), user=fake_member(uid))
    i.permissions.manage_guild = True
    return i


@pytest.mark.asyncio
async def test_comandi_regala_rifiuta_bot_e_se_stessi_poi_usa_e_azzera(cog, r):
    item = await _compra(r)
    i = _i()
    await cog.regala.callback(cog, i, fake_member(1), item.id)
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True
    i = _i()
    await cog.regala.callback(cog, i, fake_member(9, bot=True), item.id)
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True
    assert (await r.inv.lista(G, 1))[0].quantita == 1
    i = _i()
    await cog.usa.callback(cog, i, item.id)
    assert "affilata" not in str(i.response.send_message.await_args)  # nessuna risposta personalizzata: testo base
    assert await r.inv.lista(G, 1) == []
    await cog.azzera_inventari.callback(cog, _i(), "sbagliato")
    assert i.response.send_message.await_count == 1
