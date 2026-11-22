"""
tests/test_catalogo_r2mod_quarantena.py
=======================================
Quarantena a mano (MOD-016): ruoli salvati prima, quarantena anche a tempo, rilascio che ridà solo i ruoli ridabili.
Database vero.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import discord
import pytest

from cogs.moderation import softban_mute
from cogs.moderation._shared import MODULE_ACTIONS
from cogs.moderation.softban_mute import ModerationSoftbanMuteCog
from core import moderation_quarantena as mq
from core import security_quarantine
from core.database import db
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import fake_member, fake_role
from tests.test_moderation_ordine_azione import ID_BERSAGLIO, ID_SERVER, Scena


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID_SERVER, MODULE_ACTIONS, True)
    yield
    database_module.db._modules_cache.clear()


def _scena(monkeypatch):
    s = Scena()
    s.server.me.guild_permissions = discord.Permissions(manage_roles=True)
    quarantena = fake_role(900, "Quarantined", position=2)
    ruolo_a, ruolo_b, gestito, alto = (
        fake_role(11, "a", position=5), fake_role(12, "b", position=6), fake_role(13, "boost", position=7, managed=True),
        fake_role(14, "alto", position=80),
    )
    s.server.roles = [quarantena, ruolo_a, ruolo_b, gestito, alto]
    s.server.get_role = lambda rid: next((r for r in s.server.roles if r.id == rid), None)
    s.bersaglio.roles = [fake_role(0, "@everyone", position=0), ruolo_a, ruolo_b, gestito]
    s.bersaglio.edit = AsyncMock()
    monkeypatch.setattr(security_quarantine, "ruolo_quarantena", AsyncMock(return_value=quarantena))
    monkeypatch.setattr(softban_mute.scheduler, "schedule", AsyncMock())
    monkeypatch.setattr(softban_mute.scheduler, "cancel_for_user", AsyncMock())
    return s, quarantena, ruolo_a, ruolo_b, gestito


# MOD-016
async def test_si_salvano_i_ruoli_prima_poi_si_toglie_tutto_tranne_i_gestiti(monkeypatch):
    s, quarantena, a, b, gestito = _scena(monkeypatch)
    cog = ModerationSoftbanMuteCog(bot=None)
    await cog.quarantena.callback(cog, s.interazione, s.bersaglio, "Raid sospetto")
    stato = await moderation_repo.get_quarantena(ID_SERVER, ID_BERSAGLIO)
    assert stato["ruoli"] == [11, 12] and stato["case_number"] is not None and stato["finisce_il"] is None
    nuovi = s.bersaglio.edit.await_args.kwargs["roles"]
    assert gestito in nuovi and quarantena in nuovi and a not in nuovi and b not in nuovi
    assert len(s.bersaglio.edit.await_args.kwargs["reason"]) <= 512
    caso = await moderation_repo.get_case(ID_SERVER, stato["case_number"])
    assert caso.action_type == "quarantena" and caso.active


# MOD-016
async def test_a_tempo_pianifica_la_fine_e_il_rilascio_ridà_i_ruoli_ma_non_quelli_diventati_troppo_alti(monkeypatch):
    s, quarantena, a, b, gestito = _scena(monkeypatch)
    cog = ModerationSoftbanMuteCog(bot=None)
    await cog.quarantena.callback(cog, s.interazione, s.bersaglio, "Raid sospetto", "2h")
    chiamata = softban_mute.scheduler.schedule.await_args
    assert chiamata.args[2] == mq.SCHEDULED_QUARANTENA_FINE
    assert timedelta(hours=1, minutes=59) < chiamata.args[3] - datetime.now(timezone.utc) <= timedelta(hours=2)
    b.position = 90  # nel frattempo il ruolo b è finito sopra il bot: non si può ridare
    s.bersaglio.roles = [fake_role(0, "@everyone", position=0), gestito, quarantena]
    s.bersaglio.edit.reset_mock()
    assert await mq.libera(s.server, s.bersaglio, "fine", 1) is True
    ruoli = s.bersaglio.edit.await_args.kwargs["roles"]
    assert a in ruoli and b not in ruoli and quarantena not in ruoli and gestito in ruoli
    assert await moderation_repo.get_quarantena(ID_SERVER, ID_BERSAGLIO) is None


# MOD-016
async def test_se_discord_rifiuta_lo_stato_resta_e_si_puo_riprovare(monkeypatch):
    s, quarantena, a, b, gestito = _scena(monkeypatch)
    cog = ModerationSoftbanMuteCog(bot=None)
    await cog.quarantena.callback(cog, s.interazione, s.bersaglio, "Raid sospetto")
    s.bersaglio.edit.side_effect = discord.HTTPException(AsyncMock(status=403), "no")
    assert await mq.libera(s.server, s.bersaglio, "fine", 1) is False
    assert await moderation_repo.get_quarantena(ID_SERVER, ID_BERSAGLIO) is not None
    s.bersaglio.edit.side_effect = None
    assert await mq.libera(s.server, s.bersaglio, "fine", 1) is True
    assert await mq.libera(s.server, s.bersaglio, "fine", 1) is None  # non era più in quarantena


# MOD-016
async def test_se_la_quarantena_non_parte_non_resta_niente(monkeypatch):
    s, quarantena, a, b, gestito = _scena(monkeypatch)
    s.bersaglio.edit.side_effect = discord.HTTPException(AsyncMock(status=403), "no")
    s.bersaglio.add_roles = AsyncMock(side_effect=discord.HTTPException(AsyncMock(status=403), "no"))
    cog = ModerationSoftbanMuteCog(bot=None)
    await cog.quarantena.callback(cog, s.interazione, s.bersaglio, "Raid sospetto")
    assert await moderation_repo.get_quarantena(ID_SERVER, ID_BERSAGLIO) is None
    assert await moderation_repo.list_cases_for_user(ID_SERVER, ID_BERSAGLIO) == []
    assert "Non è cambiato niente" in s.interazione.followup.send.await_args.args[0]


# MOD-016
async def test_gerarchia_e_permesso_del_bot_valgono_come_per_ogni_sanzione(monkeypatch):
    s, *_ = _scena(monkeypatch)
    s.bersaglio.roles = [fake_role(0, "@everyone", position=0), fake_role(77, "capo", position=45)]
    s.bersaglio.top_role = s.bersaglio.roles[-1]
    cog = ModerationSoftbanMuteCog(bot=None)
    await cog.quarantena.callback(cog, s.interazione, s.bersaglio, "Raid sospetto")  # pari o sopra il moderatore
    assert await moderation_repo.get_quarantena(ID_SERVER, ID_BERSAGLIO) is None
    s2, *_ = _scena(monkeypatch)
    s2.server.me.guild_permissions = discord.Permissions.none()
    await cog.quarantena.callback(cog, s2.interazione, s2.bersaglio, "Raid sospetto")
    assert await moderation_repo.get_quarantena(ID_SERVER, ID_BERSAGLIO) is None


# MOD-016
async def test_il_comando_libera_e_la_scadenza_sistemano_lo_stato(monkeypatch):
    s, quarantena, a, b, gestito = _scena(monkeypatch)
    cog = ModerationSoftbanMuteCog(bot=s.server.me)
    cog.bot = AsyncMock()
    cog.bot.get_guild = lambda gid: s.server
    cog.bot.user = fake_member(999, bot=True)
    await cog.quarantena.callback(cog, s.interazione, s.bersaglio, "Raid sospetto", "1h")
    caso = (await moderation_repo.get_quarantena(ID_SERVER, ID_BERSAGLIO))["case_number"]
    s.server.get_member.side_effect = lambda uid: s.bersaglio if uid == ID_BERSAGLIO else s.moderatore
    await cog.handle_quarantena_fine(ID_SERVER, ID_BERSAGLIO, {"caso": caso + 5})  # un job vecchio non tocca niente
    assert await moderation_repo.get_quarantena(ID_SERVER, ID_BERSAGLIO) is not None
    await cog.handle_quarantena_fine(ID_SERVER, ID_BERSAGLIO, {"caso": caso})
    assert await moderation_repo.get_quarantena(ID_SERVER, ID_BERSAGLIO) is None
    assert not (await moderation_repo.get_case(ID_SERVER, caso)).active
