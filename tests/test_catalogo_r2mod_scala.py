"""
tests/test_catalogo_r2mod_scala.py
==================================
Scala di escalation sui warn a mano (#115, r2mod): conteggio in una finestra di giorni (MOD-033), durata per gradino
(MOD-034), conteggio azzerato dopo la sanzione (MOD-035). Database vero.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

import cogs.automod.escalation as esc
from core.escalation_ladder_logic import LadderStep, get_ladder_action
from core.repositories.escalation_repo import escalation_repo
from core.repositories.moderation_repo import moderation_repo
from tests.test_escalation_warn_manuali import A, SERVER, _ambiente, _cog, _scena, _tipi, _warn  # noqa: F401

ADESSO = datetime(2026, 11, 1, tzinfo=timezone.utc)


# MOD-033
def test_un_gradino_a_finestra_conta_solo_gli_ultimi_giorni():
    scala = [LadderStep(1, "warn"), LadderStep(3, "timeout", 600, finestra_giorni=7)]
    assert get_ladder_action(5, scala, conteggi_finestra={7: 2}).action_type == "warn"
    assert get_ladder_action(5, scala, conteggi_finestra={7: 3}).action_type == "timeout"
    assert get_ladder_action(5, scala, conteggi_finestra={7: 0}).action_type == "warn"


# MOD-033
def test_senza_finestre_la_scala_resta_quella_di_prima():
    scala = [LadderStep(1, "warn"), LadderStep(2, "timeout", 600)]
    assert get_ladder_action(2, scala).duration_seconds == 600
    assert get_ladder_action(9, scala).action_type == "timeout"


# MOD-033
async def test_il_repo_conta_le_infrazioni_nella_finestra(clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    for giorni in (20, 3, 1):
        await escalation_repo.record_violation(SERVER, A, ADESSO - timedelta(days=giorni), 365)
    assert await escalation_repo.conta_in_finestre(SERVER, A, {7, 30}, ADESSO) == {7: 2, 30: 3}
    await escalation_repo.reset_violations(SERVER, A)
    assert await escalation_repo.conta_in_finestre(SERVER, A, {30}, ADESSO) == {30: 0}


# MOD-033
async def test_tre_warn_in_poco_tempo_fanno_scattare_il_timeout_ma_vecchi_no(monkeypatch):
    isola = AsyncMock()
    monkeypatch.setattr(esc.bot_roles, "isola", isola)
    await escalation_repo.set_enabled(SERVER, True)
    await escalation_repo.set_conta_warn_manuali(SERVER, True)
    await escalation_repo.set_step(SERVER, 1, "warn", None)
    await escalation_repo.set_step(SERVER, 3, "timeout", 1800, 7)
    # Due infrazioni vecchie di 30 giorni: fuori dalla finestra di 7 giorni.
    for giorni in (31, 30):
        await escalation_repo.record_violation(SERVER, A, datetime.now(timezone.utc) - timedelta(days=giorni), 365)
    cog = _cog()
    membro, interazione = _scena()
    await _warn(cog, membro, interazione)  # terza in tutto, ma una sola negli ultimi 7 giorni
    isola.assert_not_awaited()
    await _warn(cog, membro, interazione)
    await _warn(cog, membro, interazione)  # tre negli ultimi 7 giorni
    isola.assert_awaited_once()
    assert isola.await_args.args[1].total_seconds() == 1800  # MOD-034: durata del gradino


# MOD-035
async def test_dopo_la_sanzione_il_conteggio_riparte_e_i_casi_restano(monkeypatch):
    isola = AsyncMock()
    monkeypatch.setattr(esc.bot_roles, "isola", isola)
    await escalation_repo.set_enabled(SERVER, True)
    await escalation_repo.set_conta_warn_manuali(SERVER, True)
    await escalation_repo.set_azzera_dopo_scatto(SERVER, True)
    cog = _cog()
    membro, interazione = _scena()
    for _ in range(2):  # base: 1 warn, 2 timeout 10 minuti
        await _warn(cog, membro, interazione)
    isola.assert_awaited_once()
    assert await db_conteggio() == 0
    assert await _tipi(A) == ["automod_escalation", "warn", "warn"]  # i casi restano
    await _warn(cog, membro, interazione)  # riparte dal livello 1
    assert isola.await_count == 1


# MOD-035
async def test_di_base_il_conteggio_non_si_azzera(monkeypatch):
    monkeypatch.setattr(esc.bot_roles, "isola", AsyncMock())
    await escalation_repo.set_enabled(SERVER, True)
    await escalation_repo.set_conta_warn_manuali(SERVER, True)
    cog = _cog()
    membro, interazione = _scena()
    for _ in range(2):
        await _warn(cog, membro, interazione)
    assert await db_conteggio() == 2


async def db_conteggio() -> int:
    from core.database import db

    return await db.pool.fetchval("SELECT COALESCE(MAX(violation_count), 0) FROM automod_violations WHERE guild_id = $1 AND user_id = $2", SERVER, A)


# MOD-034
async def test_un_gradino_tempban_banna_e_pianifica_la_fine(monkeypatch, clean_db):
    from cogs.moderation.actions import SCHEDULED_TEMPBAN_EXPIRE

    banna = AsyncMock()
    monkeypatch.setattr(esc.bot_roles, "banna", banna)
    await escalation_repo.set_enabled(SERVER, True)
    await escalation_repo.set_conta_warn_manuali(SERVER, True)
    await escalation_repo.set_step(SERVER, 1, "warn", None)
    await escalation_repo.set_step(SERVER, 2, "tempban", 7200)
    cog = _cog()
    membro, interazione = _scena()
    await _warn(cog, membro, interazione)
    banna.assert_not_awaited()
    await _warn(cog, membro, interazione)
    banna.assert_awaited_once()
    assert len(banna.await_args.kwargs["reason"]) <= 512
    riga = await clean_db.fetchrow(
        "SELECT payload, execute_at - now() AS tra FROM scheduled_actions WHERE guild_id = $1 AND action_type = $2",
        SERVER, SCHEDULED_TEMPBAN_EXPIRE,
    )
    assert timedelta(hours=1, minutes=55) < riga["tra"] <= timedelta(hours=2)
    caso = (await moderation_repo.list_cases_for_user(SERVER, A))[0]
    assert caso.duration_seconds == 7200 and '"modo"' in riga["payload"]


# MOD-034
async def test_il_gradino_tempban_parte_solo_se_il_moderatore_potrebbe_bannare(monkeypatch):
    banna = AsyncMock()
    monkeypatch.setattr(esc.bot_roles, "banna", banna)
    await escalation_repo.set_enabled(SERVER, True)
    await escalation_repo.set_conta_warn_manuali(SERVER, True)
    await escalation_repo.set_step(SERVER, 1, "tempban", 3600)
    import discord

    cog = _cog()
    membro, interazione = _scena(permessi=discord.Permissions(moderate_members=True, kick_members=True))
    await _warn(cog, membro, interazione)
    banna.assert_not_awaited()
    assert "non l'ho applicato" in interazione.followup.send.await_args.args[0]
