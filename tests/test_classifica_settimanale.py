"""
tests/test_classifica_settimanale.py
====================================
LIV-058: classifica della settimana (XP e coin), accanto a mese e di sempre.
Archivio su PostgreSQL vero e comando.
Funzioni coperte: SPEC §15.7 (catalogo #124)
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import cogs.leveling.leveling as modulo
from core.leveling_logic import period_key, week_key
from core.repositories.leveling_repo import LevelingRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.moduli import attiva_livelli

GUILD = 100


@pytest.fixture
def repo(clean_db):
    return LevelingRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_xp_e_coin_contano_nel_mese_e_nella_settimana(repo):
    await repo.add_text_xp(GUILD, 1, amount=15, cooldown_seconds=0)
    await repo.add_coins(GUILD, 1, 40)
    mese_xp = await repo.top_xp_period(GUILD, 10)
    settimana_xp = await repo.top_xp_period(GUILD, 10, week_key())
    assert [(v.user_id, v.amount) for v in mese_xp] == [(1, 15)]
    assert [(v.user_id, v.amount) for v in settimana_xp] == [(1, 15)]
    assert [(v.user_id, v.amount) for v in await repo.top_coins_period(GUILD, 10, week_key())] == [(1, 40)]
    assert [(v.user_id, v.amount) for v in await repo.top_coins_period(GUILD, 10)] == [(1, 40)]


@pytest.mark.asyncio
async def test_una_settimana_nuova_riparte_da_zero(repo, clean_db):
    await repo.add_coins(GUILD, 1, 40)
    scorsa = week_key(datetime.now(timezone.utc) - timedelta(weeks=1))
    await clean_db.execute(
        "UPDATE leveling_activity SET period_key = $1 WHERE period_key = $2", scorsa, week_key()
    )
    assert await repo.top_coins_period(GUILD, 10, week_key()) == []
    assert len(await repo.top_coins_period(GUILD, 10, scorsa)) == 1
    assert len(await repo.top_coins_period(GUILD, 10)) == 1  # il mese non cambia


@pytest.mark.asyncio
async def test_il_decadimento_cancella_solo_le_settimane_vecchie(repo, clean_db):
    vecchia = week_key(datetime.now(timezone.utc) - timedelta(weeks=12))
    recente = week_key(datetime.now(timezone.utc) - timedelta(weeks=3))
    for chiave in (vecchia, recente, "2020-01"):
        await clean_db.execute(
            "INSERT INTO leveling_activity (guild_id, user_id, period_key, xp) VALUES ($1, 1, $2, 5)",
            GUILD, chiave,
        )
    await repo.add_coins(GUILD, 2, 500)  # un saldo da far decadere
    await clean_db.execute("UPDATE leveling_totals SET last_weekly_decay_period = NULL")
    await repo.apply_weekly_decay_guild(
        GUILD, week_key(), datetime.now(timezone.utc) + timedelta(days=1)
    )
    chiavi = {r["period_key"] for r in await clean_db.fetch(
        "SELECT period_key FROM leveling_activity WHERE user_id = 1")}
    assert chiavi == {recente, "2020-01"}


@pytest.fixture
async def scena(monkeypatch, clean_db):
    from core.command_groups import costruisci_gruppi, registra_comandi_del_cog

    await attiva_livelli(monkeypatch, clean_db, GUILD)
    monete = LevelingRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "leveling_repo", monete)
    cog = modulo.LevelingCog(bot=None)
    cog.cog_unload()
    comandi = {
        c.qualified_name: c
        for c in registra_comandi_del_cog(cog, gruppi=costruisci_gruppi(), tree=None)
    }
    return SimpleNamespace(cog=cog, comandi=comandi, monete=monete)


@pytest.mark.asyncio
@pytest.mark.parametrize("metrica", ["xp", "coins"])
async def test_il_comando_mostra_la_classifica_della_settimana(scena, metrica):
    await scena.monete.add_text_xp(GUILD, 7, amount=15, cooldown_seconds=0)
    await scena.monete.add_coins(GUILD, 7, 50)
    interazione = fake_interaction(guild=fake_guild(GUILD), user=fake_member(1))
    await scena.comandi["level leaderboard"].callback(
        scena.cog, interazione,
        metric=SimpleNamespace(value=metrica, name=metrica),
        period=SimpleNamespace(value="week", name="Questa settimana"),
    )
    embed = interazione.response.send_message.await_args.kwargs["embed"]
    assert "<@7>" in embed.description and "Questa settimana" in embed.title
