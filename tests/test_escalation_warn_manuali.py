"""
tests/test_escalation_warn_manuali.py
=====================================
M 1.10 (#57): i warn dati a mano con /mod warn salgono la scala di
escalation, se il server l'ha scelto. Spento di base. Database vero.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

import cogs.automod.escalation as modulo_escalation
from cogs.moderation._shared import MODULE_ACTIONS
from cogs.moderation.actions import ModerationActionsCog
from core.database import db
from core.repositories.escalation_repo import escalation_repo
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role

SERVER = 100
MOD = 444444444444444444
A = 111111111111111111


@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(SERVER, MODULE_ACTIONS, True)
    yield
    database_module.db._modules_cache.clear()


def _scena():
    server = fake_guild(SERVER, owner_id=1)
    server.me.top_role = fake_role(role_id=3, position=50)
    server.me.id = 999
    server.get_channel.return_value = None
    moderatore = fake_member(MOD, roles=[fake_role(role_id=1, position=40)])
    moderatore.guild = server
    membro = fake_member(A, roles=[fake_role(role_id=2, position=5)])
    membro.guild = server
    server.get_member.side_effect = {MOD: moderatore, A: membro}.get
    return membro, fake_interaction(guild=server, user=moderatore)


def _cog():
    bot = MagicMock()
    bot.user = fake_member(999, bot=True)
    return ModerationActionsCog(bot=bot)


async def _warn(cog, membro, interazione):
    await cog.warn.callback(cog, interazione, membro, "linguaggio")


async def _tipi(uid):
    return sorted(c.action_type for c in await moderation_repo.list_cases_for_user(SERVER, uid))


async def test_di_base_i_warn_manuali_non_contano(monkeypatch):
    isola = AsyncMock()
    monkeypatch.setattr(modulo_escalation.bot_roles, "isola", isola)
    await escalation_repo.set_enabled(SERVER, True)
    cog = _cog()
    membro, interazione = _scena()
    for _ in range(3):
        await _warn(cog, membro, interazione)

    isola.assert_not_awaited()
    assert await _tipi(A) == ["warn"] * 3


async def test_tre_warn_manuali_fanno_scattare_il_gradino(monkeypatch):
    isola = AsyncMock()
    monkeypatch.setattr(modulo_escalation.bot_roles, "isola", isola)
    await escalation_repo.set_enabled(SERVER, True)
    await escalation_repo.set_conta_warn_manuali(SERVER, True)
    cog = _cog()
    membro, interazione = _scena()

    # Scala di base: 1 warn (nessun warn in più), 2 timeout 10 min, 3 timeout 1 ora.
    await _warn(cog, membro, interazione)
    isola.assert_not_awaited()
    interazione.followup.send.assert_not_awaited()
    assert await _tipi(A) == ["warn"]

    await _warn(cog, membro, interazione)
    await _warn(cog, membro, interazione)

    assert isola.await_count == 2
    assert isola.await_args.args[1].total_seconds() == 3600
    assert "infrazione #3" in interazione.followup.send.await_args.args[0]
    assert await _tipi(A) == ["automod_escalation"] * 2 + ["warn"] * 3


async def test_azione_fallita_lo_dice_e_non_apre_casi(monkeypatch):
    import discord

    isola = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403, reason="x"), "no"))
    monkeypatch.setattr(modulo_escalation.bot_roles, "isola", isola)
    await escalation_repo.set_enabled(SERVER, True)
    await escalation_repo.set_conta_warn_manuali(SERVER, True)
    cog = _cog()
    membro, interazione = _scena()
    await _warn(cog, membro, interazione)
    await _warn(cog, membro, interazione)

    assert "non ci sono riuscito" in interazione.followup.send.await_args.args[0]
    assert await _tipi(A) == ["warn"] * 2


async def test_il_comando_enable_accende_e_tiene_la_scelta():
    from cogs.automod.escalation import EscalationCog

    cog = EscalationCog(MagicMock())
    server = fake_guild(SERVER, owner_id=1)
    await cog.enable.callback(cog, fake_interaction(guild=server), True)
    assert (await escalation_repo.get_config(SERVER)).conta_warn_manuali

    interazione = fake_interaction(guild=server)
    await cog.enable.callback(cog, interazione)
    assert (await escalation_repo.get_config(SERVER)).conta_warn_manuali
    assert "contano." in interazione.response.send_message.call_args.args[0]
