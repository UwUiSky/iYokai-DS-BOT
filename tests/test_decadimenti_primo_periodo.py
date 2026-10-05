"""
tests/test_decadimenti_primo_periodo.py
=======================================
M 9.10: il primo decadimento arriva solo dopo un periodo intero. Una
gilda appena creata non perde il 10% della tesoreria nel giro di
un'ora, e nemmeno al primo cambio di mese; lo stesso vale per i coin
di un utente appena arrivato (settimana). Database vero.
Funzioni coperte: SPEC §15.14, §15.15
"""

from datetime import datetime, timedelta, timezone

import pytest

import core.guild_clan_treasury_decay_worker as modulo_clan
import core.weekly_personal_decay_worker as modulo_utenti
from core.guild_clan_treasury_decay_worker import GuildClanTreasuryDecayWorker
from core.leveling_logic import previous_period_start, previous_week_start
from core.repositories.guild_chest_repo import GuildChestRepository
from core.repositories.guild_clan_repo import GuildClanRepository
from core.repositories.leveling_repo import LevelingRepository
from core.weekly_personal_decay_worker import WeeklyPersonalDecayWorker

GUILD_ID = 100


def _primo_del_mese(dopo_mesi: int) -> datetime:
    """Mezz'ora dopo l'inizio del mese che viene tra `dopo_mesi` mesi."""
    adesso = datetime.now(timezone.utc)
    mese = adesso.month - 1 + dopo_mesi
    return datetime(adesso.year + mese // 12, mese % 12 + 1, 1, 0, 30, tzinfo=timezone.utc)


def _lunedi(dopo_settimane: int) -> datetime:
    """Mezz'ora dopo l'inizio (lunedì, UTC) della settimana che viene tra `dopo_settimane`."""
    adesso = datetime.now(timezone.utc)
    lunedi = (adesso - timedelta(days=adesso.weekday())).replace(
        hour=0, minute=30, second=0, microsecond=0
    )
    return lunedi + timedelta(weeks=dopo_settimane)


# ----------------------------------------------------------------------
# Tesoreria delle gilde (mensile)
# ----------------------------------------------------------------------
@pytest.fixture
async def gilda_nuova(clean_db, monkeypatch):
    """Una gilda creata adesso, ufficiale, con 100.000 coin in tesoreria."""
    clan_repo = GuildClanRepository(pool_provider=lambda: clean_db)
    chest_repo = GuildChestRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo_clan, "guild_clan_repo", clan_repo)
    monkeypatch.setattr(modulo_clan, "guild_chest_repo", chest_repo)
    clan_id = await clan_repo.create_clan(
        GUILD_ID, tag="ABC", name="Nuova", owner_id=1,
        officialize_deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    await clan_repo.donate(clan_id, user_id=1, amount=115_000)
    assert (await clan_repo.get_clan(clan_id)).officialized is True
    return clan_repo, chest_repo, clan_id


async def _tesoreria(clan_repo, clan_id) -> int:
    return (await clan_repo.get_clan(clan_id)).treasury_balance


@pytest.mark.asyncio
async def test_gilda_nuova_nessun_decadimento_dopo_un_ora(gilda_nuova):
    clan_repo, chest_repo, clan_id = gilda_nuova

    await GuildClanTreasuryDecayWorker().tick(now=datetime.now(timezone.utc) + timedelta(hours=1))

    assert await _tesoreria(clan_repo, clan_id) == 100_000
    assert await chest_repo.get_balance(GUILD_ID) == 0


@pytest.mark.asyncio
async def test_gilda_nuova_decade_solo_dopo_un_mese_intero(gilda_nuova):
    clan_repo, chest_repo, clan_id = gilda_nuova
    worker = GuildClanTreasuryDecayWorker()

    # Primo cambio di mese: la gilda non ha ancora vissuto un mese intero.
    await worker.tick(now=_primo_del_mese(1))
    assert await _tesoreria(clan_repo, clan_id) == 100_000

    # Secondo cambio di mese: ha vissuto tutto il mese precedente.
    await worker.tick(now=_primo_del_mese(2))
    assert await _tesoreria(clan_repo, clan_id) == 90_000
    assert await chest_repo.get_balance(GUILD_ID) == 10_000

    # Poi una volta al mese, come sempre.
    await worker.tick(now=_primo_del_mese(2) + timedelta(hours=5))
    assert await _tesoreria(clan_repo, clan_id) == 90_000
    await worker.tick(now=_primo_del_mese(3))
    assert await _tesoreria(clan_repo, clan_id) == 81_000


# ----------------------------------------------------------------------
# Coin personali (settimanale)
# ----------------------------------------------------------------------
@pytest.fixture
async def utente_nuovo(clean_db, monkeypatch):
    """Un utente che riceve adesso i suoi primi 500 coin."""
    leveling_repo = LevelingRepository(pool_provider=lambda: clean_db)
    chest_repo = GuildChestRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo_utenti, "leveling_repo", leveling_repo)
    monkeypatch.setattr(modulo_utenti, "guild_chest_repo", chest_repo)
    await leveling_repo.add_coins(GUILD_ID, 1, 500)
    return leveling_repo, chest_repo


async def _saldo(leveling_repo) -> int:
    return (await leveling_repo.get_totals(GUILD_ID, 1)).coins_total


@pytest.mark.asyncio
async def test_utente_nuovo_nessun_decadimento_dopo_un_ora(utente_nuovo):
    leveling_repo, chest_repo = utente_nuovo

    await WeeklyPersonalDecayWorker().tick(now=datetime.now(timezone.utc) + timedelta(hours=1))

    assert await _saldo(leveling_repo) == 500
    assert await chest_repo.get_balance(GUILD_ID) == 0


@pytest.mark.asyncio
async def test_utente_nuovo_decade_solo_dopo_una_settimana_intera(utente_nuovo):
    leveling_repo, chest_repo = utente_nuovo
    worker = WeeklyPersonalDecayWorker()

    await worker.tick(now=_lunedi(1))  # non ha ancora vissuto una settimana intera
    assert await _saldo(leveling_repo) == 500

    await worker.tick(now=_lunedi(2))
    assert await _saldo(leveling_repo) == 450
    assert await chest_repo.get_balance(GUILD_ID) == 50

    await worker.tick(now=_lunedi(3))
    assert await _saldo(leveling_repo) == 405


@pytest.mark.asyncio
async def test_utente_arrivato_prima_della_migrazione_decade_come_sempre(utente_nuovo, clean_db):
    """Le righe già presenti non hanno una data di creazione: valgono come vecchie."""
    leveling_repo, _ = utente_nuovo
    await clean_db.execute("UPDATE leveling_totals SET created_at = NULL")

    await WeeklyPersonalDecayWorker().tick(now=datetime.now(timezone.utc) + timedelta(hours=1))

    assert await _saldo(leveling_repo) == 450


# ----------------------------------------------------------------------
# Le due date di confronto
# ----------------------------------------------------------------------
def test_inizio_del_mese_precedente():
    assert previous_period_start(datetime(2026, 3, 15, 10, tzinfo=timezone.utc)) == datetime(
        2026, 2, 1, tzinfo=timezone.utc
    )
    assert previous_period_start(datetime(2026, 1, 1, tzinfo=timezone.utc)) == datetime(
        2025, 12, 1, tzinfo=timezone.utc
    )


def test_inizio_della_settimana_precedente():
    # Giovedì 24/09/2026: la settimana prima comincia lunedì 14/09.
    assert previous_week_start(datetime(2026, 9, 24, 12, tzinfo=timezone.utc)) == datetime(
        2026, 9, 14, tzinfo=timezone.utc
    )
    # Di lunedì conta la settimana appena finita.
    assert previous_week_start(datetime(2026, 9, 21, 0, 5, tzinfo=timezone.utc)) == datetime(
        2026, 9, 14, tzinfo=timezone.utc
    )
