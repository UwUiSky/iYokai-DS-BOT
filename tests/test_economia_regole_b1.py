"""
tests/test_economia_regole_b1.py
================================
Regole dell'economia del server (#125 B1): ECO-002 saldo di partenza, ECO-003 tetto al saldo,
ECO-008 statistiche, ECO-010 monete a un ruolo, ECO-012 azzeramento, ECO-014 saldo di chi esce,
ECO-019/024/028 attese e paghe, ECO-021/022 puntate e pausa, ECO-023 stato, ECO-025 bonus serie,
ECO-026 premi settimanale e mensile. PostgreSQL vero.
Funzioni coperte: SPEC §15 (catalogo #125)
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from core.leveling_logic import LevelingSettings, bonus_serie, controlla_puntata
from core.repositories.economia_repo import EconomiaRepository
from core.repositories.leveling_repo import LevelingRepository, TettoSaldoRaggiunto
from core.repositories.leveling_settings_repo import LevelingSettingsRepository
from tests.support.concorrenza import apri_connessioni

G = 100


@pytest.fixture
def repo(clean_db):
    return LevelingRepository(pool_provider=lambda: clean_db)


@pytest.fixture
def eco(clean_db):
    return EconomiaRepository(pool_provider=lambda: clean_db)


@pytest.fixture
def imp(clean_db):
    return LevelingSettingsRepository(pool_provider=lambda: clean_db)


def test_bonus_serie_e_puntate_pure():
    assert bonus_serie(1, 5, 30) == 0 and bonus_serie(4, 5, 30) == 15 and bonus_serie(100, 5, 10) == 50
    assert bonus_serie(5, 0, 30) == 0
    i = LevelingSettings(puntata_min=10, puntata_max=100)
    assert controlla_puntata(9, i) and controlla_puntata(101, i) and controlla_puntata(50, i) is None
    assert controlla_puntata(0, LevelingSettings()) is not None  # mai zero o negativo


@pytest.mark.asyncio
async def test_valori_fuori_limite_rifiutati(imp):
    for campi in ({"tetto_saldo": -1}, {"attesa_gioco": 3601}, {"daily_ore": 0}, {"saldo_uscita": "boh"},
                  {"puntata_min": 50, "puntata_max": 10}, {"work_attesa_min": 1441}):
        with pytest.raises(ValueError):
            await imp.set_options(G, **campi)
    await imp.set_options(G, daily_ore=12, puntata_max=500, saldo_uscita="cancella")
    i = (await imp.get_config(G, fresco=True)).impostazioni
    assert (i.daily_ore, i.puntata_max, i.saldo_uscita) == (12, 500, "cancella")


@pytest.mark.asyncio
async def test_saldo_di_partenza_una_volta_sola_anche_insieme(eco, repo, clean_db):
    conns = await apri_connessioni(clean_db, 4)
    esiti = await asyncio.gather(*[eco.accredito_iniziale(G, 1, 50) for _ in range(4)])
    assert esiti.count(True) == 1
    assert (await repo.get_totals(G, 1)).coins_total == 50
    assert await eco.accredito_iniziale(G, 1, 50) is False  # rientra: niente di nuovo
    assert await eco.accredito_iniziale(G, 2, 0) is False
    del conns


@pytest.mark.asyncio
async def test_tetto_al_saldo_su_ogni_accredito(eco, repo, imp):
    await imp.set_options(G, tetto_saldo=100)
    await repo.add_coins(G, 1, 80)
    assert await repo.add_coins(G, 1, 50) == 100  # non oltre il tetto
    assert await repo.add_coins(G, 2, 500) == 100  # riga nuova
    assert await repo.claim_daily(G, 1, 40, 60, datetime.now(timezone.utc)) is True
    assert (await repo.get_totals(G, 1)).coins_total == 100
    # gioco: la vincita si ferma al tetto, la puntata si scala sempre
    assert await repo.gioca(G, 1, 10, 200) == 100
    # tetto abbassato: chi è sopra non perde, ma non riceve
    await imp.set_options(G, tetto_saldo=50)
    assert await repo.add_coins(G, 1, 10) == 100
    await eco.accredito_iniziale(G, 9, 70)
    assert (await repo.get_totals(G, 9)).coins_total == 50


@pytest.mark.asyncio
async def test_pagamento_al_tetto_rifiutato_e_mai_a_se_stessi(repo, imp):
    await imp.set_options(G, tetto_saldo=100)
    await repo.add_coins(G, 1, 100)
    await repo.add_coins(G, 2, 90)
    with pytest.raises(TettoSaldoRaggiunto):
        await repo.transfer_coins(G, 1, 2, 20)
    assert (await repo.get_totals(G, 1)).coins_total == 100  # niente scritto
    assert await repo.transfer_coins(G, 1, 2, 10) is True
    with pytest.raises(ValueError):
        await repo.transfer_coins(G, 1, 1, 5)


@pytest.mark.asyncio
async def test_premio_settimanale_non_paga_due_volte(eco, repo, clean_db):
    await apri_connessioni(clean_db, 4)
    adesso = datetime.now(timezone.utc)
    esiti = await asyncio.gather(*[eco.riscuoti_periodico(G, 1, "settimanale", 70, 7 * 86400, adesso) for _ in range(4)])
    assert esiti.count(True) == 1
    assert (await repo.get_totals(G, 1)).coins_total == 70
    assert await eco.riscuoti_periodico(G, 1, "settimanale", 70, 7 * 86400, adesso + timedelta(days=1)) is False
    assert await eco.riscuoti_periodico(G, 1, "settimanale", 70, 7 * 86400, adesso + timedelta(days=8)) is True
    assert await eco.riscuoti_periodico(G, 1, "mensile", 300, 30 * 86400, adesso) is True  # un tipo non blocca l'altro
    with pytest.raises(ValueError):
        await eco.riscuoti_periodico(G, 1, "annuale", 5, 5, adesso)
    with pytest.raises(ValueError):
        await eco.riscuoti_periodico(G, 1, "mensile", 0, 5, adesso)


@pytest.mark.asyncio
async def test_monete_a_un_ruolo(eco, repo, imp):
    await repo.add_coins(G, 1, 30)
    assert await eco.monete_a_ruolo(G, [1, 2, 3, 3], 50, toglie=False) == 3
    assert [(await repo.get_totals(G, u)).coins_total for u in (1, 2, 3)] == [80, 50, 50]
    await eco.monete_a_ruolo(G, [1, 2], 60, toglie=True)
    assert [(await repo.get_totals(G, u)).coins_total for u in (1, 2, 3)] == [20, 0, 50]  # mai sotto zero
    await imp.set_options(G, tetto_saldo=60)
    await eco.monete_a_ruolo(G, [3, 4], 40, toglie=False)
    assert [(await repo.get_totals(G, u)).coins_total for u in (3, 4)] == [60, 40]
    with pytest.raises(ValueError):
        await eco.monete_a_ruolo(G, [1], 0, toglie=False)
    assert await eco.monete_a_ruolo(G, [], 5, toglie=False) == 0


@pytest.mark.asyncio
async def test_azzeramento_cancella_saldi_e_riscossioni_ma_non_xp(eco, repo):
    await repo.add_coins(G, 1, 40)
    await repo.add_coins(G + 1, 1, 40)  # un altro server non si tocca
    await eco.riscuoti_periodico(G, 1, "mensile", 10, 86400, datetime.now(timezone.utc))
    assert await eco.azzera_economia(G) >= 1
    assert (await repo.get_totals(G, 1)).coins_total == 0
    assert (await repo.get_totals(G + 1, 1)).coins_total == 40
    assert await eco.ultima_riscossione(G, 1, "mensile") is None


@pytest.mark.asyncio
async def test_cancella_saldo_di_chi_esce_e_statistiche(eco, repo):
    for u, c in ((1, 100), (2, 50), (3, 10)):
        await repo.add_coins(G, u, c)
    s = await eco.statistiche(G)
    assert (s.totale, s.persone, s.massimo, s.mediana, s.quota_primi_10) == (160, 3, 100, 50, 100)
    assert await eco.cancella_saldo(G, 1) == 100
    assert (await repo.get_totals(G, 1)).coins_total == 0
    assert (await eco.statistiche(G)).totale == 60
    assert (await eco.statistiche(G + 5)).totale == 0
