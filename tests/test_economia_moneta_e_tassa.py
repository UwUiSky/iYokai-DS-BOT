"""
tests/test_economia_moneta_e_tassa.py
=====================================
ECO-001 (nome della moneta scelto dal server) ed ECO-015 (tetto e tassa sui
trasferimenti tra utenti, la tassa va alla cassa del server).
Archivio su PostgreSQL vero e comandi.
Funzioni coperte: SPEC §15.3 (catalogo #125)
"""

from types import SimpleNamespace

import pytest

import cogs.leveling.leveling as modulo
from core.leveling_logic import nome_moneta_valido, tassa_su_pagamento
from core.repositories.guild_chest_repo import GuildChestRepository
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.leveling_settings_repo import LevelingSettingsRepository
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.moduli import attiva_livelli

GUILD = 100


# ---------------------------------------------------------------- logica pura
def test_tassa_arrotondata_per_eccesso():
    """Per difetto, nove pagamenti da 9 con il 10% non pagherebbero mai la tassa."""
    assert tassa_su_pagamento(100, 10) == 10
    assert tassa_su_pagamento(15, 10) == 2
    assert tassa_su_pagamento(9, 10) == 1
    assert tassa_su_pagamento(100, 0) == 0


def test_nome_moneta_ripulito_e_con_limiti():
    assert nome_moneta_valido("  gemme   blu ") == "gemme blu"
    for brutto in ("", "   ", "x" * 21, "@everyone", "a\n@b", "**x**", "<@1>"):
        with pytest.raises(ValueError):
            nome_moneta_valido(brutto)


# ---------------------------------------------------------------- impostazioni
@pytest.fixture
def impostazioni(clean_db):
    return LevelingSettingsRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_valori_di_base_e_modifica(impostazioni):
    i = (await impostazioni.get_config(GUILD)).impostazioni
    assert (i.currency_name, i.pay_tax_pct, i.pay_max) == ("coin", 0, 0)
    await impostazioni.set_options(GUILD, currency_name=" Gemme ", pay_tax_pct=10, pay_max=500)
    i = (await impostazioni.get_config(GUILD)).impostazioni
    assert (i.currency_name, i.pay_tax_pct, i.pay_max) == ("Gemme", 10, 500)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "campi",
    [{"pay_tax_pct": 51}, {"pay_tax_pct": -1}, {"pay_max": 1_000_001}, {"currency_name": "@here"},
     {"currency_name": ""}, {"pay_min": -1}, {"pay_min": 1_000_001}, {"pay_min": 50, "pay_max": 10}],
)
async def test_valori_fuori_dai_limiti_rifiutati(impostazioni, campi):
    with pytest.raises(ValueError):
        await impostazioni.set_options(GUILD, **campi)


# ---------------------------------------------------------------- archivio
@pytest.fixture
def repo(clean_db):
    return LevelingRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_la_tassa_va_alla_cassa_nella_stessa_scrittura(repo, clean_db):
    cassa = GuildChestRepository(pool_provider=lambda: clean_db)
    await repo.add_coins(GUILD, 1, 1000)
    assert await repo.transfer_coins(GUILD, 1, 2, 200, tassa=20) is True
    assert (await repo.get_totals(GUILD, 1)).coins_total == 800
    assert (await repo.get_totals(GUILD, 2)).coins_total == 180
    assert await cassa.get_balance(GUILD) == 20
    assert [m.reason for m in await cassa.list_ledger(GUILD)] == ["pay_tax"]


@pytest.mark.asyncio
async def test_senza_saldo_non_si_muove_nulla_nemmeno_la_tassa(repo, clean_db):
    cassa = GuildChestRepository(pool_provider=lambda: clean_db)
    await repo.add_coins(GUILD, 1, 50)
    assert await repo.transfer_coins(GUILD, 1, 2, 200, tassa=20) is False
    assert await cassa.get_balance(GUILD) == 0
    assert (await repo.get_totals(GUILD, 1)).coins_total == 50


@pytest.mark.asyncio
async def test_senza_tassa_funziona_come_prima(repo, clean_db):
    await repo.add_coins(GUILD, 1, 100)
    assert await repo.transfer_coins(GUILD, 1, 2, 60) is True
    assert (await repo.get_totals(GUILD, 2)).coins_total == 60


@pytest.mark.asyncio
@pytest.mark.parametrize("tassa", [-1, 100, 150])
async def test_tassa_non_valida_rifiutata(repo, tassa):
    await repo.add_coins(GUILD, 1, 500)
    with pytest.raises(ValueError):
        await repo.transfer_coins(GUILD, 1, 2, 100, tassa=tassa)


# ---------------------------------------------------------------- comandi
@pytest.fixture
async def scena(monkeypatch, clean_db):
    from core.command_groups import costruisci_gruppi, registra_comandi_del_cog
    from core.repositories.leveling_settings_repo import leveling_settings_repo

    await apri_connessioni(clean_db)
    await attiva_livelli(monkeypatch, clean_db, GUILD)
    monkeypatch.setattr(leveling_settings_repo, "_pool_provider", lambda: clean_db)
    leveling_settings_repo._cache = type(leveling_settings_repo._cache)(max_size=100)
    monete = LevelingRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "leveling_repo", monete)
    cog = modulo.LevelingCog(bot=None)
    cog.cog_unload()
    comandi = {
        c.qualified_name: c
        for c in registra_comandi_del_cog(cog, gruppi=costruisci_gruppi(), tree=None)
    }
    yield SimpleNamespace(cog=cog, comandi=comandi, monete=monete, impostazioni=leveling_settings_repo)
    leveling_settings_repo._cache = type(leveling_settings_repo._cache)(max_size=100)


def _interazione(user_id=1):
    return fake_interaction(guild=fake_guild(GUILD), user=fake_member(user_id, name=f"u{user_id}"))


def _testo(interazione):
    chiamata = interazione.response.send_message.await_args
    return chiamata.args[0] if chiamata.args else str(chiamata.kwargs)


@pytest.mark.asyncio
async def test_pay_con_tassa_e_tetto(scena, clean_db):
    await scena.impostazioni.set_options(GUILD, pay_tax_pct=10, pay_max=300, currency_name="gemme")
    await scena.monete.add_coins(GUILD, 1, 1000)

    troppo = _interazione()
    await scena.comandi["level pay"].callback(scena.cog, troppo, member=fake_member(2), amount=301)
    assert "al massimo **300** gemme" in _testo(troppo)
    assert (await scena.monete.get_totals(GUILD, 1)).coins_total == 1000

    ok = _interazione()
    await scena.comandi["level pay"].callback(scena.cog, ok, member=fake_member(2), amount=200)
    testo = _testo(ok)
    assert "**200** gemme" in testo and "Tassa" in testo and "**20**" in testo and "**180**" in testo
    assert (await scena.monete.get_totals(GUILD, 2)).coins_total == 180


@pytest.mark.asyncio
async def test_pay_senza_impostazioni_resta_com_era(scena):
    await scena.monete.add_coins(GUILD, 1, 100)
    interazione = _interazione()
    await scena.comandi["level pay"].callback(scena.cog, interazione, member=fake_member(2), amount=60)
    assert "**60** coin" in _testo(interazione) and "Tassa" not in _testo(interazione)
    assert (await scena.monete.get_totals(GUILD, 2)).coins_total == 60


@pytest.mark.asyncio
async def test_saldo_daily_e_classifica_usano_il_nome_scelto(scena):
    await scena.impostazioni.set_options(GUILD, currency_name="gemme")
    await scena.monete.add_coins(GUILD, 1, 70)

    saldo = _interazione()
    await scena.comandi["level balance"].callback(scena.cog, saldo, member=None)
    assert "**70** gemme" in _testo(saldo)

    daily = _interazione(user_id=5)
    await scena.comandi["level daily"].callback(scena.cog, daily)
    assert "gemme" in _testo(daily) and "coin" not in _testo(daily)

    classifica = _interazione()
    await scena.comandi["level leaderboard"].callback(
        scena.cog, classifica,
        metric=SimpleNamespace(value="coins", name="Coin"),
        period=SimpleNamespace(value="alltime", name="Di sempre"),
    )
    assert "gemme" in classifica.response.send_message.await_args.kwargs["embed"].description


@pytest.mark.asyncio
async def test_il_comando_delle_impostazioni_salva_nome_tassa_e_tetto(scena):
    interazione = _interazione()
    await scena.comandi["level impostazioni xp"].callback(
        scena.cog, interazione, nome_moneta="stelle", tassa_pay=5, massimo_pay=100
    )
    i = (await scena.impostazioni.get_config(GUILD)).impostazioni
    assert (i.currency_name, i.pay_tax_pct, i.pay_max) == ("stelle", 5, 100)


@pytest.mark.asyncio
async def test_pagamenti_piccoli_non_evitano_la_tassa(scena, clean_db):
    cassa = GuildChestRepository(pool_provider=lambda: clean_db)
    await scena.impostazioni.set_options(GUILD, pay_tax_pct=10)
    await scena.monete.add_coins(GUILD, 1, 100)

    piccolo = _interazione()
    await scena.comandi["level pay"].callback(scena.cog, piccolo, member=fake_member(2), amount=9)
    assert (await scena.monete.get_totals(GUILD, 2)).coins_total == 8
    assert await cassa.get_balance(GUILD) == 1

    # 1 solo: la tassa sarebbe tutto l'importo, quindi si rifiuta e non si muove nulla.
    uno = _interazione()
    await scena.comandi["level pay"].callback(scena.cog, uno, member=fake_member(2), amount=1)
    assert "almeno **2**" in _testo(uno)
    assert (await scena.monete.get_totals(GUILD, 1)).coins_total == 91


@pytest.mark.asyncio
async def test_pay_sotto_il_minimo_rifiutato(scena):
    """ECO-015 chiede anche il minimo."""
    await scena.impostazioni.set_options(GUILD, pay_min=50)
    await scena.monete.add_coins(GUILD, 1, 100)
    poco = _interazione()
    await scena.comandi["level pay"].callback(scena.cog, poco, member=fake_member(2), amount=49)
    assert "almeno **50**" in _testo(poco)
    assert (await scena.monete.get_totals(GUILD, 1)).coins_total == 100

    interazione = _interazione()
    await scena.comandi["level impostazioni xp"].callback(scena.cog, interazione, minimo_pay=10)
    assert (await scena.impostazioni.get_config(GUILD)).impostazioni.pay_min == 10
