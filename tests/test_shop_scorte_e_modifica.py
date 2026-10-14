"""
tests/test_shop_scorte_e_modifica.py
====================================
ECO-062 (scorte limitate), ECO-064 (modificare un oggetto in vendita) e
ECO-061 (ruolo richiesto per comprare). Archivio su PostgreSQL vero e comandi.
Funzioni coperte: SPEC §15.4 (catalogo #125)
"""

import asyncio
from types import SimpleNamespace

import pytest

import cogs.leveling.leveling as modulo
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.shop_repo import EsitoAcquisto, ShopRepository
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role
from tests.support.moduli import attiva_livelli

GUILD = 100


@pytest.fixture
def repo(clean_db):
    return ShopRepository(pool_provider=lambda: clean_db)


@pytest.fixture
def monete(clean_db):
    return LevelingRepository(pool_provider=lambda: clean_db)


async def _con_coin(monete, utente, quante=1000):
    await monete.add_coins(GUILD, utente, quante)


# ----------------------------------------------------------------------
# Scorte
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_senza_scorte_l_oggetto_non_finisce_mai(repo, monete):
    item_id = await repo.add_item(GUILD, name="Adesivo", price=10)
    oggetto = await repo.get_item(item_id, GUILD)
    assert oggetto.stock is None
    await _con_coin(monete, 1)
    for _ in range(3):
        assert (await repo.buy_item(GUILD, 1, oggetto)).esito == EsitoAcquisto.RIUSCITO


@pytest.mark.asyncio
async def test_le_scorte_scendono_e_alla_fine_non_si_compra(repo, monete):
    item_id = await repo.add_item(GUILD, name="Raro", price=100, stock=2)
    oggetto = await repo.get_item(item_id, GUILD)
    await _con_coin(monete, 1)
    assert (await repo.buy_item(GUILD, 1, oggetto)).esito == EsitoAcquisto.RIUSCITO
    assert (await repo.get_item(item_id, GUILD)).stock == 1
    assert (await repo.buy_item(GUILD, 1, oggetto)).esito == EsitoAcquisto.RIUSCITO
    assert (await repo.get_item(item_id, GUILD)).stock == 0

    assert (await repo.buy_item(GUILD, 1, oggetto)).esito == EsitoAcquisto.ESAURITO
    assert (await monete.get_totals(GUILD, 1)).coins_total == 800  # nessun terzo addebito


@pytest.mark.asyncio
async def test_senza_saldo_le_scorte_non_scendono(repo, monete):
    item_id = await repo.add_item(GUILD, name="Raro", price=100, stock=3)
    oggetto = await repo.get_item(item_id, GUILD)
    await _con_coin(monete, 1, 50)
    assert (await repo.buy_item(GUILD, 1, oggetto)).esito == EsitoAcquisto.SALDO_INSUFFICIENTE
    assert (await repo.get_item(item_id, GUILD)).stock == 3


@pytest.mark.asyncio
async def test_acquisti_insieme_non_vendono_piu_delle_scorte(repo, monete, clean_db):
    await apri_connessioni(clean_db)
    item_id = await repo.add_item(GUILD, name="Raro", price=10, stock=2)
    oggetto = await repo.get_item(item_id, GUILD)
    for utente in range(1, 7):
        await _con_coin(monete, utente, 100)
    esiti = await asyncio.gather(*(repo.buy_item(GUILD, u, oggetto) for u in range(1, 7)))
    assert [e.esito for e in esiti].count(EsitoAcquisto.RIUSCITO) == 2
    assert [e.esito for e in esiti].count(EsitoAcquisto.ESAURITO) == 4
    assert (await repo.get_item(item_id, GUILD)).stock == 0
    spesi = 0
    for utente in range(1, 7):
        spesi += 100 - (await monete.get_totals(GUILD, utente)).coins_total
    assert spesi == 20


@pytest.mark.asyncio
async def test_il_rimborso_rimette_l_oggetto_in_scorta(repo, monete):
    item_id = await repo.add_item(GUILD, name="Raro", price=100, stock=1, role_id=5)
    oggetto = await repo.get_item(item_id, GUILD)
    await _con_coin(monete, 1)
    acquisto = await repo.buy_item(GUILD, 1, oggetto)
    assert (await repo.get_item(item_id, GUILD)).stock == 0

    assert await repo.refund_purchase(acquisto.purchase_id, GUILD, 1, 100) is True
    assert (await repo.get_item(item_id, GUILD)).stock == 1
    assert await repo.refund_purchase(acquisto.purchase_id, GUILD, 1, 100) is False
    assert (await repo.get_item(item_id, GUILD)).stock == 1  # il secondo rimborso non rimette altro


# ----------------------------------------------------------------------
# Modifica
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_item_cambia_solo_i_campi_dati(repo):
    item_id = await repo.add_item(GUILD, name="Vecchio", price=10, description="d", stock=5)
    nuovo = await repo.update_item(item_id, GUILD, name="Nuovo", price=20)
    assert (nuovo.name, nuovo.price, nuovo.description, nuovo.stock) == ("Nuovo", 20, "d", 5)

    nuovo = await repo.update_item(item_id, GUILD, stock=None)  # tolte le scorte: illimitato
    assert nuovo.stock is None
    nuovo = await repo.update_item(item_id, GUILD, required_role_id=77, description=None)
    assert (nuovo.required_role_id, nuovo.description) == (77, None)


@pytest.mark.asyncio
async def test_update_item_di_un_altro_server_o_inesistente_non_fa_nulla(repo):
    item_id = await repo.add_item(GUILD, name="X", price=10)
    assert await repo.update_item(item_id, GUILD + 1, price=99) is None
    assert await repo.update_item(item_id + 999, GUILD, price=99) is None
    assert (await repo.get_item(item_id, GUILD)).price == 10


@pytest.mark.asyncio
@pytest.mark.parametrize("campi", [{"price": 0}, {"stock": -1}, {"name": ""}, {"colore": 1}])
async def test_update_item_rifiuta_valori_non_validi(repo, campi):
    item_id = await repo.add_item(GUILD, name="X", price=10)
    with pytest.raises(ValueError):
        await repo.update_item(item_id, GUILD, **campi)


# ----------------------------------------------------------------------
# Comandi
# ----------------------------------------------------------------------
@pytest.fixture
async def scena(monkeypatch, clean_db):
    from core.command_groups import costruisci_gruppi, registra_comandi_del_cog

    await attiva_livelli(monkeypatch, clean_db, GUILD)
    negozio = ShopRepository(pool_provider=lambda: clean_db)
    monete = LevelingRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "shop_repo", negozio)
    monkeypatch.setattr(modulo, "leveling_repo", monete)
    cog = modulo.LevelingCog(bot=None)
    cog.cog_unload()
    comandi = {
        c.qualified_name: c
        for c in registra_comandi_del_cog(cog, gruppi=costruisci_gruppi(), tree=None)
    }
    return SimpleNamespace(cog=cog, comandi=comandi, negozio=negozio, monete=monete)


def _interazione(user_id=1, ruoli=()):
    utente = fake_member(user_id, roles=list(ruoli))
    return fake_interaction(guild=fake_guild(GUILD), user=utente)


def _testo(interazione):
    chiamata = interazione.response.send_message.await_args
    return chiamata.args[0] if chiamata.args else str(chiamata.kwargs)


@pytest.mark.asyncio
async def test_shop_add_con_scorte_e_ruolo_richiesto(scena):
    richiesto = fake_role(role_id=42)
    interazione = _interazione()
    await scena.comandi["economia shop-add"].callback(
        scena.cog, interazione, name="Raro", price=50, role=None, description=None,
        scorte=3, ruolo_richiesto=richiesto,
    )
    oggetto = (await scena.negozio.list_items(GUILD))[0]
    assert (oggetto.stock, oggetto.required_role_id) == (3, 42)


@pytest.mark.asyncio
async def test_shop_edit_modifica_e_rifiuta_un_id_sbagliato(scena):
    item_id = await scena.negozio.add_item(GUILD, name="Vecchio", price=10, stock=2)
    interazione = _interazione()
    await scena.comandi["economia shop-edit"].callback(
        scena.cog, interazione, item_id=item_id, name="Nuovo", price=30, scorte=None,
        scorte_illimitate=True, description=None, ruolo_richiesto=None,
    )
    oggetto = await scena.negozio.get_item(item_id, GUILD)
    assert (oggetto.name, oggetto.price, oggetto.stock) == ("Nuovo", 30, None)

    interazione = _interazione()
    await scena.comandi["economia shop-edit"].callback(
        scena.cog, interazione, item_id=item_id + 50, name="Boh", price=None, scorte=None,
        scorte_illimitate=None, description=None, ruolo_richiesto=None,
    )
    assert "Nessun oggetto" in _testo(interazione)


@pytest.mark.asyncio
async def test_shop_edit_senza_nessun_valore_non_scrive(scena):
    item_id = await scena.negozio.add_item(GUILD, name="X", price=10)
    interazione = _interazione()
    await scena.comandi["economia shop-edit"].callback(
        scena.cog, interazione, item_id=item_id, name=None, price=None, scorte=None,
        scorte_illimitate=None, description=None, ruolo_richiesto=None,
    )
    assert "almeno un valore" in _testo(interazione)


@pytest.mark.asyncio
async def test_buy_esaurito_non_addebita(scena):
    item_id = await scena.negozio.add_item(GUILD, name="Raro", price=100, stock=0)
    await scena.monete.add_coins(GUILD, 1, 500)
    interazione = _interazione()
    await scena.comandi["level shop buy"].callback(scena.cog, interazione, item_id=item_id)
    assert "esaurito" in _testo(interazione).lower()
    assert (await scena.monete.get_totals(GUILD, 1)).coins_total == 500


@pytest.mark.asyncio
async def test_buy_senza_il_ruolo_richiesto_e_rifiutato_prima_di_pagare(scena):
    item_id = await scena.negozio.add_item(GUILD, name="Vip", price=100, required_role_id=42)
    await scena.monete.add_coins(GUILD, 1, 500)

    senza = _interazione()
    await scena.comandi["level shop buy"].callback(scena.cog, senza, item_id=item_id)
    assert "<@&42>" in _testo(senza)
    assert (await scena.monete.get_totals(GUILD, 1)).coins_total == 500

    con = _interazione(ruoli=[fake_role(role_id=42)])
    await scena.comandi["level shop buy"].callback(scena.cog, con, item_id=item_id)
    assert (await scena.monete.get_totals(GUILD, 1)).coins_total == 400


@pytest.mark.asyncio
async def test_la_lista_mostra_scorte_e_ruolo_richiesto(scena):
    await scena.negozio.add_item(GUILD, name="Raro", price=100, stock=3, required_role_id=42)
    interazione = _interazione()
    await scena.comandi["level shop list"].callback(scena.cog, interazione)
    testo = interazione.response.send_message.await_args.kwargs["embed"].description
    assert "3" in testo and "<@&42>" in testo
