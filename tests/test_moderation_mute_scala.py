"""
tests/test_moderation_mute_scala.py
===================================
Mute a ruolo a tempo come gradino della scala delle sanzioni (D127): il gradino dà il ruolo, apre il caso e prepara
la scadenza; dopo un riavvio la scadenza vale ancora (stato e coda stanno nel database). Database vero, scheduler vero.
"""

from datetime import timedelta
from unittest.mock import MagicMock

import cogs.automod.escalation as esc
from cogs.moderation.softban_mute import MUTE_ROLE_ACTION_TYPE, SCHEDULED_MUTE_EXPIRE, ModerationSoftbanMuteCog
from core.escalation_ladder_logic import LadderStep, get_ladder_action
from core.repositories.escalation_repo import escalation_repo
from core.repositories.moderation_repo import moderation_repo
from core.scheduler import scheduler
from tests.test_moderation_mute_tempo import (  # noqa: F401
    MUTO,
    SERVER,
    _ambiente,
    _ids,
    _imposta_ruolo_mute,
    _scena,
)


def test_il_mute_e_un_gradino_valido_della_scala():
    scala = [LadderStep(1, "warn"), LadderStep(2, "mute", 3600)]
    assert get_ladder_action(2, scala).action_type == "mute"
    assert get_ladder_action(2, scala).duration_seconds == 3600


async def test_il_gradino_mute_si_salva_e_si_rilegge_dal_database(clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    await escalation_repo.set_step(SERVER, 2, "mute", 3600)
    config = await escalation_repo.get_config(SERVER)
    assert any(s.action_type == "mute" and s.duration_seconds == 3600 for s in config.ladder)


async def test_il_gradino_mute_da_il_ruolo_apre_il_caso_e_prepara_la_scadenza():
    await _imposta_ruolo_mute()
    server, membro, cog, inter, _ = _scena([10])
    bot = MagicMock()
    bot.user.id = 999
    step = LadderStep(2, "mute", 7200)
    caso = await esc._applica_passo(bot, SERVER, membro, step, "Scala dei warn")
    assert caso is not None and 99 in _ids(membro) and 10 in _ids(membro)
    stato = await moderation_repo.get_mute_state(SERVER, MUTO)
    assert stato["case_number"] == caso and stato["finisce_il"] is not None
    assert (await moderation_repo.get_case(SERVER, caso)).action_type == MUTE_ROLE_ACTION_TYPE
    [attesa] = await scheduler.list_pending_for_guild(SERVER, SCHEDULED_MUTE_EXPIRE)
    assert attesa["payload"]["caso"] == caso
    assert timedelta(hours=1, minutes=59) < attesa["execute_at"] - stato["finisce_il"] + timedelta(hours=2) <= timedelta(hours=2, seconds=5)


async def test_dopo_un_riavvio_la_scadenza_del_mute_della_scala_toglie_il_ruolo():
    await _imposta_ruolo_mute()
    server, membro, _cog, _inter, _ = _scena([10])
    bot = MagicMock()
    bot.user.id = 999
    caso = await esc._applica_passo(bot, SERVER, membro, LadderStep(2, "mute", 7200), "Scala dei warn")
    [attesa] = await scheduler.list_pending_for_guild(SERVER, SCHEDULED_MUTE_EXPIRE)
    # «riavvio»: un cog nuovo, senza memoria; resta solo quello che c'è nel database
    nuovo_bot = MagicMock()
    nuovo_bot.user.id = 999
    nuovo_bot.get_guild.return_value = server
    nuovo = ModerationSoftbanMuteCog(nuovo_bot)
    await nuovo.handle_mute_expire(SERVER, MUTO, attesa["payload"])
    assert 99 not in _ids(membro) and 10 in _ids(membro)
    assert await moderation_repo.get_mute_state(SERVER, MUTO) is None
    assert not (await moderation_repo.get_case(SERVER, caso)).active


async def test_un_mute_nuovo_della_scala_sostituisce_la_scadenza_vecchia():
    await _imposta_ruolo_mute()
    server, membro, _cog, _inter, _ = _scena([10])
    bot = MagicMock()
    bot.user.id = 999
    await esc._applica_passo(bot, SERVER, membro, LadderStep(1, "mute", 600), "uno")
    caso2 = await esc._applica_passo(bot, SERVER, membro, LadderStep(2, "mute", 7200), "due")
    [attesa] = await scheduler.list_pending_for_guild(SERVER, SCHEDULED_MUTE_EXPIRE)
    assert attesa["payload"]["caso"] == caso2
