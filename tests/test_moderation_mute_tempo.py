"""
tests/test_moderation_mute_tempo.py
===================================
Mute con ruolo a tempo (MOD-014), hardmute (MOD-015) e mute che resta
al rientro (MOD-021). Database vero, scheduler vero, Discord finto.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from cogs.moderation import softban_mute
from cogs.moderation._shared import MODULE_ACTIONS
from cogs.moderation.case_system import righe_sanzioni_attive
from cogs.moderation.softban_mute import (
    MUTE_ROLE_ACTION_TYPE,
    SCHEDULED_MUTE_EXPIRE,
    SETTING_MUTE_ROLE_ID,
    ModerationSoftbanMuteCog,
)
from core.database import db
from core.moderation_mute_logic import (
    MAX_MUTE_SECONDI,
    mute_finito,
    ruoli_dopo_nuovo_mute,
    ruoli_hardmute,
)
from core.repositories.moderation_repo import moderation_repo
from core.scheduler import scheduler
from core.tempban_logic import RuoloInfo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role

SERVER = 100
MUTO = 900
STAFF = 7


# ---------------------------------------------------------------- logica pura
def test_hardmute_toglie_solo_i_ruoli_che_il_bot_puo_toccare():
    ruoli = [
        RuoloInfo(0, 0, is_default=True),
        RuoloInfo(10, 5),
        RuoloInfo(11, 8, managed=True),  # integrazione
        RuoloInfo(12, 60),  # sopra il bot
        RuoloInfo(13, 3),
        RuoloInfo(99, 1),  # il ruolo mute
    ]
    assert ruoli_hardmute(ruoli, 50, 99) == [10, 13]


def test_nuovo_mute_su_chi_e_gia_in_hardmute_non_perde_i_ruoli_salvati():
    assert ruoli_dopo_nuovo_mute(True, [10, 13], [], False) == [10, 13]
    assert ruoli_dopo_nuovo_mute(True, [10], [13], True) == [10, 13]
    assert ruoli_dopo_nuovo_mute(False, [], [10], True) == [10]
    assert ruoli_dopo_nuovo_mute(False, [], [10], False) == []


def test_mute_finito():
    ora = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert mute_finito(None, ora) is False
    assert mute_finito(ora - timedelta(seconds=1), ora) is True
    assert mute_finito(ora + timedelta(seconds=1), ora) is False


# -------------------------------------------------------------------- scena
@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    database_module.db._settings_cache.clear()
    await db.set_module_active_for_guild(SERVER, MODULE_ACTIONS, True)
    monkeypatch.setattr(softban_mute, "check_can_moderate", AsyncMock(return_value=True))
    monkeypatch.setattr(softban_mute, "try_dm", AsyncMock(return_value=None))
    monkeypatch.setattr(softban_mute, "post_to_mod_log", AsyncMock())

    async def _copri(guild, role):
        return None

    monkeypatch.setattr(softban_mute, "_cover_all_channels", _copri)
    yield
    database_module.db._modules_cache.clear()
    database_module.db._settings_cache.clear()


def _scena(ruoli_membro=()):
    ruolo_mute = fake_role(99, "Muted", position=2)
    r10 = fake_role(10, "Giocatore", position=5)
    r11 = fake_role(11, "Booster", position=8, managed=True)
    r13 = fake_role(13, "Fan", position=3)
    server = fake_guild(SERVER, owner_id=1)
    server.me.top_role = fake_role(500, "Yokai", position=50)
    tutti = {r.id: r for r in (ruolo_mute, r10, r11, r13)}
    server.roles = list(tutti.values())
    server.get_role = MagicMock(side_effect=tutti.get)
    base = fake_role(0, "@everyone", position=0)
    membro = fake_member(MUTO, roles=[base] + [tutti[i] for i in ruoli_membro])
    membro.guild = server

    async def _add(*ruoli, reason=None):
        for r in ruoli:
            if r not in membro.roles:
                membro.roles.append(r)

    async def _rm(*ruoli, reason=None):
        for r in ruoli:
            if r in membro.roles:
                membro.roles.remove(r)

    membro.add_roles = AsyncMock(side_effect=_add)
    membro.remove_roles = AsyncMock(side_effect=_rm)
    server.get_member = MagicMock(return_value=membro)
    bot = MagicMock()
    bot.get_guild.return_value = server
    bot.user.id = 999
    cog = ModerationSoftbanMuteCog(bot)
    interazione = fake_interaction(guild=server, user=fake_member(STAFF))
    return server, membro, cog, interazione, tutti


async def _imposta_ruolo_mute():
    await db.set_guild_setting(SERVER, SETTING_MUTE_ROLE_ID, 99)


def _ids(membro):
    return {r.id for r in membro.roles}


# --------------------------------------------------------------------- mute
async def test_mute_a_tempo_pianifica_la_fine_e_la_scadenza_toglie_il_ruolo():
    await _imposta_ruolo_mute()
    server, membro, cog, inter, _ = _scena([10])
    await cog.mute_role.callback(cog, inter, membro, "spam", "2h", False)

    assert 99 in _ids(membro) and 10 in _ids(membro)  # mute semplice: gli altri ruoli restano
    stato = await moderation_repo.get_mute_state(SERVER, MUTO)
    assert stato["hard"] is False and stato["finisce_il"] is not None
    [attesa] = await scheduler.list_pending_for_guild(SERVER, SCHEDULED_MUTE_EXPIRE)
    assert attesa["user_id"] == MUTO and attesa["payload"] == {"caso": stato["case_number"]}
    caso = await moderation_repo.get_case(SERVER, stato["case_number"])
    assert caso.duration_seconds == 7200 and caso.active

    await cog.handle_mute_expire(SERVER, MUTO, attesa["payload"])
    assert 99 not in _ids(membro)
    assert await moderation_repo.get_mute_state(SERVER, MUTO) is None
    assert (await moderation_repo.get_case(SERVER, stato["case_number"])).active is False


async def test_mute_senza_durata_non_pianifica_nulla_ma_ricorda_il_mute():
    await _imposta_ruolo_mute()
    server, membro, cog, inter, _ = _scena()
    await cog.mute_role.callback(cog, inter, membro, "spam", None, False)
    assert await scheduler.list_pending_for_guild(SERVER, SCHEDULED_MUTE_EXPIRE) == []
    assert (await moderation_repo.get_mute_state(SERVER, MUTO))["finisce_il"] is None


async def test_durata_non_valida_o_oltre_un_anno_rifiutata():
    await _imposta_ruolo_mute()
    server, membro, cog, inter, _ = _scena()
    await cog.mute_role.callback(cog, inter, membro, "spam", "2anni", False)
    await cog.mute_role.callback(cog, inter, membro, "spam", f"{MAX_MUTE_SECONDI // 86400 + 1}d", False)
    assert inter.response.send_message.await_count == 2
    membro.add_roles.assert_not_awaited()
    assert await moderation_repo.get_mute_state(SERVER, MUTO) is None


async def test_scadenza_vecchia_non_tocca_un_mute_piu_nuovo():
    await _imposta_ruolo_mute()
    server, membro, cog, inter, _ = _scena()
    await cog.mute_role.callback(cog, inter, membro, "uno", "1h", False)
    [vecchia] = await scheduler.list_pending_for_guild(SERVER, SCHEDULED_MUTE_EXPIRE)
    await cog.mute_role.callback(cog, inter, membro, "due", "5h", False)
    [nuova] = await scheduler.list_pending_for_guild(SERVER, SCHEDULED_MUTE_EXPIRE)  # la vecchia è annullata
    assert nuova["payload"] != vecchia["payload"]

    await cog.handle_mute_expire(SERVER, MUTO, vecchia["payload"])
    assert 99 in _ids(membro)


# ----------------------------------------------------------------- hardmute
async def test_unmute_lascia_una_riga_nel_log_di_moderazione():
    """§18.7: anche togliere il ruolo mute si registra."""
    await _imposta_ruolo_mute()
    server, membro, cog, inter, _ = _scena([10])
    await cog.mute_role.callback(cog, inter, membro, "raid", None, False)
    softban_mute.post_to_mod_log.reset_mock()

    await cog.unmute_role.callback(cog, inter, membro, "tutto a posto")

    softban_mute.post_to_mod_log.assert_awaited_once()
    assert softban_mute.post_to_mod_log.await_args.args[1].title == "🔊 Mute (ruolo) tolto"


async def test_hardmute_toglie_i_ruoli_e_il_unmute_li_ridà():
    await _imposta_ruolo_mute()
    server, membro, cog, inter, _ = _scena([10, 11, 13])
    await cog.mute_role.callback(cog, inter, membro, "raid", None, True)

    assert _ids(membro) == {0, 11, 99}  # il Booster è gestito da Discord: resta
    stato = await moderation_repo.get_mute_state(SERVER, MUTO)
    assert stato["hard"] is True and sorted(stato["ruoli"]) == [10, 13]

    await cog.unmute_role.callback(cog, inter, membro, "tutto a posto")
    assert _ids(membro) == {0, 10, 11, 13}
    assert await moderation_repo.get_mute_state(SERVER, MUTO) is None


async def test_hardmute_a_tempo_ridà_i_ruoli_alla_scadenza():
    await _imposta_ruolo_mute()
    server, membro, cog, inter, _ = _scena([10, 13])
    await cog.mute_role.callback(cog, inter, membro, "raid", "1h", True)
    [attesa] = await scheduler.list_pending_for_guild(SERVER, SCHEDULED_MUTE_EXPIRE)
    await cog.handle_mute_expire(SERVER, MUTO, attesa["payload"])
    assert _ids(membro) == {0, 10, 13}


async def test_secondo_mute_su_un_hardmute_non_perde_i_ruoli():
    await _imposta_ruolo_mute()
    server, membro, cog, inter, _ = _scena([10, 13])
    await cog.mute_role.callback(cog, inter, membro, "raid", None, True)
    await cog.mute_role.callback(cog, inter, membro, "ancora", "1h", False)
    stato = await moderation_repo.get_mute_state(SERVER, MUTO)
    assert stato["hard"] is True and sorted(stato["ruoli"]) == [10, 13]


async def test_hardmute_che_fallisce_rimette_i_ruoli_e_non_lascia_stato():
    import discord

    await _imposta_ruolo_mute()
    server, membro, cog, inter, _ = _scena([10, 13])
    originale = membro.add_roles.side_effect
    chiamate = []

    async def _add(*ruoli, reason=None):
        chiamate.append(ruoli)
        if len(chiamate) == 1:  # il ruolo mute: Discord rifiuta
            raise discord.HTTPException(MagicMock(status=403, reason="x"), "no")
        await originale(*ruoli, reason=reason)

    membro.add_roles = AsyncMock(side_effect=_add)
    await cog.mute_role.callback(cog, inter, membro, "raid", None, True)
    assert _ids(membro) == {0, 10, 13}
    assert await moderation_repo.get_mute_state(SERVER, MUTO) is None
    assert await moderation_repo.get_latest_active_case(SERVER, MUTO, MUTE_ROLE_ACTION_TYPE) is None


# ------------------------------------------------------------------- rientro
async def test_chi_rientra_resta_silenziato():
    await _imposta_ruolo_mute()
    server, membro, cog, inter, _ = _scena()
    await cog.mute_role.callback(cog, inter, membro, "spam", "1h", False)
    membro.roles[:] = [r for r in membro.roles if r.id != 99]  # è uscito: ruoli persi

    await cog.on_member_join(membro)
    assert 99 in _ids(membro)


async def test_rientro_dopo_la_fine_chiude_il_mute():
    await _imposta_ruolo_mute()
    server, membro, cog, inter, _ = _scena([10])
    await cog.mute_role.callback(cog, inter, membro, "raid", "1h", True)
    await moderation_repo.save_mute_state(
        SERVER, MUTO, True, [10], (await moderation_repo.get_mute_state(SERVER, MUTO))["case_number"],
        datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    membro.roles[:] = [r for r in membro.roles if r.id == 0]

    await cog.on_member_join(membro)
    assert _ids(membro) == {0, 10}
    assert await moderation_repo.get_mute_state(SERVER, MUTO) is None


async def test_mute_di_chi_e_uscito_prima_della_fine_non_si_perde():
    await _imposta_ruolo_mute()
    server, membro, cog, inter, _ = _scena()
    await cog.mute_role.callback(cog, inter, membro, "spam", "1h", False)
    [attesa] = await scheduler.list_pending_for_guild(SERVER, SCHEDULED_MUTE_EXPIRE)
    server.get_member = MagicMock(return_value=None)
    server.fetch_member = AsyncMock(side_effect=_non_trovato())
    await cog.handle_mute_expire(SERVER, MUTO, attesa["payload"])
    assert await moderation_repo.get_mute_state(SERVER, MUTO) is not None  # lo chiude il rientro


def _non_trovato():
    import discord

    return discord.NotFound(MagicMock(status=404, reason="x"), "no")


async def test_scadenza_con_membro_fuori_cache_toglie_il_ruolo():
    await _imposta_ruolo_mute()
    server, membro, cog, inter, _ = _scena()
    await cog.mute_role.callback(cog, inter, membro, "spam", "1h", False)
    [attesa] = await scheduler.list_pending_for_guild(SERVER, SCHEDULED_MUTE_EXPIRE)
    server.get_member = MagicMock(return_value=None)  # cache fredda: è ancora nel server
    server.fetch_member = AsyncMock(return_value=membro)
    await cog.handle_mute_expire(SERVER, MUTO, attesa["payload"])
    assert 99 not in _ids(membro)
    assert await moderation_repo.get_mute_state(SERVER, MUTO) is None


# --------------------------------------------------------------- sanzioni attive
async def test_i_mute_compaiono_tra_le_sanzioni_attive():
    await _imposta_ruolo_mute()
    server, membro, cog, inter, _ = _scena([10])
    server.members = []
    await cog.mute_role.callback(cog, inter, membro, "raid", "1h", True)
    righe = await righe_sanzioni_attive(server)
    assert any("Hardmute" in r and str(MUTO) in r for r in righe)
