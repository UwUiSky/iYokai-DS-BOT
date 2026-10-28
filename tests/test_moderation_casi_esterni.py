"""
tests/test_moderation_casi_esterni.py
=====================================
Casi creati anche per ban, kick e timeout fatti fuori da iYokai (MOD-047):
dal registro di controllo di Discord, solo se il server lo ha acceso.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.moderation import case_system
from cogs.moderation._shared import MODULE_CASE_SYSTEM
from cogs.moderation.case_system import ModerationCaseSystemCog
from core import moderation_opzioni
from core.database import db
from core.moderation_casi_esterni_logic import MOTIVO_PREDEFINITO, caso_da_voce
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import fake_guild

G = 100
BOT = 999
STAFF = 10
VITTIMA = 55
ORA = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_logica_ban_kick_e_timeout():
    assert caso_da_voce("ban", " spam ").motivo == "spam"
    assert caso_da_voce("kick", None).motivo == MOTIVO_PREDEFINITO
    assert caso_da_voce("ban", "x" * 900).motivo == "x" * 512
    t = caso_da_voce("member_update", None, timeout_fino=ORA + timedelta(hours=1), ora=ORA)
    assert (t.tipo, t.durata_secondi) == ("timeout", 3600)


def test_logica_ignora_il_resto():
    assert caso_da_voce("member_update", None, timeout_fino=None, ora=ORA) is None  # timeout tolto o altra modifica
    assert caso_da_voce("member_update", None, timeout_fino=ORA - timedelta(minutes=1), ora=ORA) is None
    assert caso_da_voce("channel_create", None) is None


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    database_module.db._settings_cache.clear()
    await db.set_module_active_for_guild(G, MODULE_CASE_SYSTEM, True)
    monkeypatch.setattr(case_system, "post_to_mod_log", AsyncMock())
    yield
    database_module.db._modules_cache.clear()
    database_module.db._settings_cache.clear()


def _cog():
    bot = MagicMock()
    bot.user.id = BOT
    return ModerationCaseSystemCog(bot)


def _voce(azione, *, autore=STAFF, bersaglio=VITTIMA, motivo="motivo", after=None):
    return SimpleNamespace(
        action=azione, user_id=autore, target=SimpleNamespace(id=bersaglio), reason=motivo,
        guild=fake_guild(G), after=after or SimpleNamespace(),
    )


async def _casi():
    return await moderation_repo.list_cases_for_user(G, VITTIMA)


async def test_spento_di_default_non_crea_casi():
    await _cog().on_audit_log_entry_create(_voce(discord.AuditLogAction.ban))
    assert await _casi() == []


async def test_ban_kick_e_timeout_esterni_diventano_casi():
    await moderation_opzioni.imposta_casi_esterni(G, True, STAFF)
    cog = _cog()
    await cog.on_audit_log_entry_create(_voce(discord.AuditLogAction.ban, motivo="raid"))
    await cog.on_audit_log_entry_create(_voce(discord.AuditLogAction.kick))
    fino = discord.utils.utcnow() + timedelta(minutes=30)
    await cog.on_audit_log_entry_create(
        _voce(discord.AuditLogAction.member_update, after=SimpleNamespace(timed_out_until=fino))
    )
    tipi = {c.action_type: c for c in await _casi()}
    assert set(tipi) == {"ban", "kick", "timeout"}
    assert tipi["ban"].reason == "raid" and tipi["ban"].moderator_id == STAFF
    assert 1700 < tipi["timeout"].duration_seconds <= 1800
    case_system.post_to_mod_log.assert_awaited()


async def test_azioni_di_iyokai_e_automoderazione_non_si_contano_due_volte():
    await moderation_opzioni.imposta_casi_esterni(G, True, STAFF)
    cog = _cog()
    await cog.on_audit_log_entry_create(_voce(discord.AuditLogAction.ban, autore=BOT))
    await cog.on_audit_log_entry_create(_voce(discord.AuditLogAction.kick, autore=VITTIMA))  # esce da solo
    await cog.on_audit_log_entry_create(_voce(discord.AuditLogAction.member_update))  # non è un timeout
    assert await _casi() == []


async def test_unban_esterno_chiude_il_ban_attivo():
    await moderation_opzioni.imposta_casi_esterni(G, True, STAFF)
    n = await moderation_repo.create_case(G, VITTIMA, STAFF, "ban", "uno")
    await _cog().on_audit_log_entry_create(_voce(discord.AuditLogAction.unban))
    assert (await moderation_repo.get_case(G, n)).active is False
    assert len(await _casi()) == 1  # nessun caso nuovo


async def test_modulo_spento_non_crea_casi():
    await moderation_opzioni.imposta_casi_esterni(G, True, STAFF)
    await db.set_module_active_for_guild(G, MODULE_CASE_SYSTEM, False)
    await _cog().on_audit_log_entry_create(_voce(discord.AuditLogAction.ban))
    assert await _casi() == []


# ------------------------------------------------------- rientro (MOD-064)
def _membro_rientrato(uid=VITTIMA, bot=False):
    return SimpleNamespace(id=uid, mention=f"<@{uid}>", bot=bot, guild=fake_guild(G))


async def test_rientro_con_casi_avvisa_lo_staff_solo_se_acceso():
    await moderation_repo.create_case(G, VITTIMA, STAFF, "warn", "insulti")
    cog = _cog()
    await cog.on_member_join(_membro_rientrato())
    case_system.post_to_mod_log.assert_not_awaited()  # spento di default

    await moderation_opzioni.imposta_avviso_rientro(G, True, STAFF)
    await cog.on_member_join(_membro_rientrato())
    embed = case_system.post_to_mod_log.await_args.args[1]
    assert "Rientra" in embed.title and "insulti" in embed.description


async def test_rientro_senza_casi_o_di_un_bot_non_avvisa():
    await moderation_opzioni.imposta_avviso_rientro(G, True, STAFF)
    cog = _cog()
    await cog.on_member_join(_membro_rientrato(uid=777))
    await moderation_repo.create_case(G, 778, STAFF, "warn", "x" * 5)
    await cog.on_member_join(_membro_rientrato(uid=778, bot=True))
    case_system.post_to_mod_log.assert_not_awaited()
