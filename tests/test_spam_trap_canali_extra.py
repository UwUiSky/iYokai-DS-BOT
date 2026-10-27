"""
tests/test_spam_trap_canali_extra.py
====================================
SIC-039: piu' canali trappola nello stesso server (fino a 5 in tutto: quello
principale e 4 in piu'). Chi scrive in uno qualunque cade nella trappola.
Database vero.
"""

import pytest

from core.database import db
from core.spam_trap_logic import (
    MAX_CANALI_TRAPPOLA,
    SETTING_CANALI_EXTRA,
    canali_trappola,
    controlla_canale_extra,
)
from tests.support.discord_fakes import fake_interaction
from tests.test_spam_trap_ban_e_appello import GUILD_ID, scenario  # noqa: F401


def test_regole_pure():
    assert MAX_CANALI_TRAPPOLA == 5
    assert canali_trappola(1, [2, 3]) == {1, 2, 3}
    assert canali_trappola(None, [2]) == {2}
    assert controlla_canale_extra([], 5, trap_id=1, log_id=2) is None
    assert "trappola" in controlla_canale_extra([], 1, trap_id=1, log_id=2)
    assert "log" in controlla_canale_extra([], 2, trap_id=1, log_id=2)
    assert "già" in controlla_canale_extra([5], 5, trap_id=1, log_id=2)
    # Principale + 4 extra = 5: il quinto extra non entra.
    assert "al massimo" in controlla_canale_extra([10, 11, 12, 13], 14, trap_id=1, log_id=2)


async def _setup(scenario, **opzioni):
    interazione = fake_interaction(guild=scenario.server)
    await scenario.cog.spamtrap_setup.callback(scenario.cog, interazione, **opzioni)
    return interazione


async def test_canale_extra_si_aggiunge_e_fa_cadere_nella_trappola(scenario):
    await scenario.configura()
    extra = scenario.aggiungi_canale("trappola-2")
    interazione = await _setup(scenario, canale_extra_aggiungi=extra)
    assert await db.get_guild_setting(GUILD_ID, SETTING_CANALI_EXTRA) == [extra.id]
    assert extra.mention in interazione.followup.send.call_args.args[0]
    extra.send.assert_awaited()  # embed di presidio nel nuovo canale
    scenario.server.ban.assert_not_awaited()
    adesso = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    await scenario.cog.on_message(scenario.messaggio(extra, 910_000, adesso))
    scenario.server.ban.assert_awaited_once()


async def test_un_canale_normale_non_e_una_trappola(scenario):
    await scenario.configura()
    normale = scenario.aggiungi_canale("chiacchiere")
    adesso = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    await scenario.cog.on_message(scenario.messaggio(normale, 920_000, adesso))
    scenario.server.ban.assert_not_awaited()


async def test_canale_extra_si_toglie(scenario):
    await scenario.configura()
    extra = scenario.aggiungi_canale("trappola-2")
    await _setup(scenario, canale_extra_aggiungi=extra)
    await _setup(scenario, canale_extra_togli=extra)
    assert not await db.get_guild_setting(GUILD_ID, SETTING_CANALI_EXTRA)
    adesso = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    await scenario.cog.on_message(scenario.messaggio(extra, 930_000, adesso))
    scenario.server.ban.assert_not_awaited()


async def test_il_canale_dei_log_non_diventa_trappola(scenario):
    await scenario.configura()
    interazione = await _setup(scenario, canale_extra_aggiungi=scenario.log)
    assert not await db.get_guild_setting(GUILD_ID, SETTING_CANALI_EXTRA)
    assert "log" in interazione.followup.send.call_args.args[0]


async def test_oltre_il_tetto_si_rifiuta(scenario):
    await scenario.configura()
    for n in range(4):
        await _setup(scenario, canale_extra_aggiungi=scenario.aggiungi_canale(f"t{n}"))
    quinto = scenario.aggiungi_canale("t5")
    interazione = await _setup(scenario, canale_extra_aggiungi=quinto)
    assert len(await db.get_guild_setting(GUILD_ID, SETTING_CANALI_EXTRA)) == 4
    assert "al massimo" in interazione.followup.send.call_args.args[0]


def test_l_indice_dei_messaggi_della_trappola_ha_la_pulizia_dei_30_giorni():
    # PERF-3: prima la pulizia esisteva ma nessuno la chiamava.
    from core.data_registry import REGISTRO

    tabella = next(t for t in REGISTRO if t.nome == "spam_trap_message_index")
    assert tabella.scadenza is not None and tabella.scadenza.giorni == 30
    assert tabella.scadenza.colonna == "created_at"
