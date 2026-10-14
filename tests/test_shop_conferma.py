"""
tests/test_shop_conferma.py
===========================
ECO-069 (#125): conferma prima dell'acquisto nel negozio, che l'admin può
accendere o spegnere (`/level impostazioni negozio`). Di base è spenta: il
comportamento di prima non cambia.
Funzioni coperte: SPEC §15.4 (catalogo #125)
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import cogs.leveling.leveling as modulo
from core.leveling_logic import LevelingSettings
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.leveling_settings_repo import LevelingSettingsRepository
from core.repositories.shop_repo import ShopRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.moduli import attiva_livelli

GUILD = 100


def test_la_conferma_e_spenta_di_base():
    assert LevelingSettings().shop_confirm is False


@pytest.mark.asyncio
async def test_il_valore_si_salva(clean_db):
    repo = LevelingSettingsRepository(pool_provider=lambda: clean_db)
    await repo.set_options(GUILD, shop_confirm=True)
    assert (await repo.get_config(GUILD)).impostazioni.shop_confirm is True


@pytest.fixture
async def scena(monkeypatch, clean_db):
    from core.command_groups import costruisci_gruppi, registra_comandi_del_cog
    from core.repositories.leveling_settings_repo import leveling_settings_repo

    await attiva_livelli(monkeypatch, clean_db, GUILD)
    monkeypatch.setattr(leveling_settings_repo, "_pool_provider", lambda: clean_db)
    leveling_settings_repo._cache = type(leveling_settings_repo._cache)(max_size=100)
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
    item_id = await negozio.add_item(GUILD, name="Adesivo", price=100)
    await monete.add_coins(GUILD, 1, 500)
    return SimpleNamespace(
        cog=cog, comandi=comandi, negozio=negozio, monete=monete, item_id=item_id,
        impostazioni=leveling_settings_repo,
    )


def _interazione(user_id=1):
    i = fake_interaction(guild=fake_guild(GUILD), user=fake_member(user_id))
    i.edit_original_response = AsyncMock()
    return i


async def _saldo(scena, utente=1):
    return (await scena.monete.get_totals(GUILD, utente)).coins_total


@pytest.mark.asyncio
async def test_spenta_si_compra_subito(scena):
    interazione = _interazione()
    await scena.comandi["level shop buy"].callback(scena.cog, interazione, item_id=scena.item_id)
    assert await _saldo(scena) == 400
    assert "view" not in interazione.response.send_message.await_args.kwargs


@pytest.mark.asyncio
async def test_accesa_prima_chiede_e_non_addebita(scena):
    await scena.impostazioni.set_options(GUILD, shop_confirm=True)
    interazione = _interazione()
    await scena.comandi["level shop buy"].callback(scena.cog, interazione, item_id=scena.item_id)

    chiamata = interazione.response.send_message.await_args
    assert "Adesivo" in chiamata.args[0] and "100" in chiamata.args[0]
    assert chiamata.kwargs["ephemeral"] is True and chiamata.kwargs["view"] is not None
    assert await _saldo(scena) == 500


@pytest.mark.asyncio
async def test_conferma_compra_una_volta_e_toglie_i_bottoni(scena):
    await scena.impostazioni.set_options(GUILD, shop_confirm=True)
    comando = _interazione()
    await scena.comandi["level shop buy"].callback(scena.cog, comando, item_id=scena.item_id)
    vista = comando.response.send_message.await_args.kwargs["view"]
    conferma = [b for b in vista.children if b.label == "Conferma"][0]

    click = _interazione()
    await conferma.callback(click)

    assert await _saldo(scena) == 400
    comando.edit_original_response.assert_awaited()
    assert comando.edit_original_response.await_args.kwargs["view"] is None
    assert "acquistato" in click.response.send_message.await_args.args[0]

    secondo = _interazione()
    await conferma.callback(secondo)  # un secondo clic sulla stessa finestra
    assert await _saldo(scena) == 400


@pytest.mark.asyncio
async def test_annulla_non_compra(scena):
    await scena.impostazioni.set_options(GUILD, shop_confirm=True)
    comando = _interazione()
    await scena.comandi["level shop buy"].callback(scena.cog, comando, item_id=scena.item_id)
    vista = comando.response.send_message.await_args.kwargs["view"]
    annulla = [b for b in vista.children if b.label == "Annulla"][0]

    click = _interazione()
    await annulla.callback(click)

    assert await _saldo(scena) == 500
    click.response.edit_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_il_clic_di_un_altro_utente_e_rifiutato(scena):
    await scena.impostazioni.set_options(GUILD, shop_confirm=True)
    comando = _interazione()
    await scena.comandi["level shop buy"].callback(scena.cog, comando, item_id=scena.item_id)
    vista = comando.response.send_message.await_args.kwargs["view"]

    estraneo = _interazione(user_id=2)
    assert await vista.interaction_check(estraneo) is False
    assert await _saldo(scena) == 500


@pytest.mark.asyncio
async def test_comando_negozio_accende_e_spegne(scena):
    comando = scena.comandi["level impostazioni negozio"]
    await comando.callback(scena.cog, _interazione(), conferma=True)
    assert (await scena.impostazioni.get_config(GUILD)).impostazioni.shop_confirm is True
    await comando.callback(scena.cog, _interazione(), conferma=False)
    assert (await scena.impostazioni.get_config(GUILD)).impostazioni.shop_confirm is False


@pytest.mark.asyncio
async def test_prezzo_cambiato_dopo_la_finestra_rifiuta_e_non_addebita(scena):
    await scena.impostazioni.set_options(GUILD, shop_confirm=True)
    comando = _interazione()
    await scena.comandi["level shop buy"].callback(scena.cog, comando, item_id=scena.item_id)
    vista = comando.response.send_message.await_args.kwargs["view"]
    conferma = [b for b in vista.children if b.label == "Conferma"][0]

    await scena.negozio.update_item(scena.item_id, GUILD, price=400)  # lo staff rialza il prezzo
    click = _interazione()
    await conferma.callback(click)

    assert await _saldo(scena) == 500
    assert "prezzo è cambiato" in click.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_il_repo_rifiuta_il_prezzo_diverso_da_quello_atteso(scena):
    from core.repositories.shop_repo import EsitoAcquisto

    oggetto = await scena.negozio.get_item(scena.item_id, GUILD)
    esito = await scena.negozio.buy_item(GUILD, 1, oggetto, prezzo_atteso=99)
    assert esito.esito is EsitoAcquisto.PREZZO_CAMBIATO
    assert await _saldo(scena) == 500
    esito = await scena.negozio.buy_item(GUILD, 1, oggetto, prezzo_atteso=100)
    assert esito.esito is EsitoAcquisto.RIUSCITO
    assert await _saldo(scena) == 400


@pytest.mark.asyncio
async def test_senza_conferma_il_prezzo_cambiato_tra_lettura_e_acquisto_non_addebita(scena, monkeypatch):
    """Conferma spenta: addebito, messaggio e rimborso devono coincidere con il prezzo letto."""
    originale = scena.negozio.buy_item

    async def buy_dopo_modifica(guild_id, user_id, item, **kw):
        await scena.negozio.update_item(scena.item_id, GUILD, price=400)  # staff, dopo la lettura
        return await originale(guild_id, user_id, item, **kw)

    monkeypatch.setattr(scena.negozio, "buy_item", buy_dopo_modifica)
    interazione = _interazione()
    await scena.comandi["level shop buy"].callback(scena.cog, interazione, item_id=scena.item_id)

    assert await _saldo(scena) == 500
    assert "prezzo è cambiato" in interazione.response.send_message.await_args.args[0]
