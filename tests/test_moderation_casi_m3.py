"""
tests/test_moderation_casi_m3.py
================================
Casi di moderazione, blocco M3 (#115): durata di un caso (MOD-012), elenco e azzeramento dei warn del
server (MOD-027, 030), esportazione (MOD-043), casi nascosti (MOD-045), scadenza dei casi AutoMod (MOD-048).
Database vero.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.moderation._shared import MODULE_CASE_SYSTEM, SETTING_MOD_LOG_CHANNEL
from cogs.moderation.case_system import ModerationCaseSystemCog
from core.database import db
from core import moderation_casi_logic
from core.repositories.moderation_repo import SETTING_SCADENZA_AUTOMOD, moderation_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel

G = 100


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(G, MODULE_CASE_SYSTEM, True)
    await db.set_guild_setting(G, SETTING_MOD_LOG_CHANNEL, 7001)
    yield
    database_module.db._modules_cache.clear()


def _inter(gestione=True):
    server = fake_guild(G)
    canale_log = fake_text_channel(7001)
    canale_log.send = AsyncMock()
    server.get_channel.return_value = canale_log
    mod = fake_member(10, guild_permissions=discord.Permissions(manage_guild=gestione))
    return fake_interaction(guild=server, user=mod), canale_log


def _testo(inter):
    c = inter.response.send_message.call_args
    return c.args[0] if c.args else c.kwargs.get("content", "")


# --- logica ---

@pytest.mark.parametrize(
    "tipo,attivo,secondi,errore",
    [
        ("tempban", True, 86400 * 90, False),
        ("timeout", True, 86400 * 29, True),
        ("timeout", True, 86400 * 28, False),
        ("mute_role", True, 60, False),
        ("warn", True, 60, True),
        ("ban", True, 60, True),
        ("tempban", False, 60, True),
    ],
)
def test_errore_durata_caso(tipo, attivo, secondi, errore):
    assert (moderation_casi_logic.errore_durata_caso(tipo, attivo, secondi) is not None) is errore


async def test_testo_esportazione():
    await moderation_repo.create_case(G, 1, 10, "warn", "uno")
    await moderation_repo.add_note(G, 1, 10, "una nota")
    testo = moderation_casi_logic.testo_esportazione(
        1, await moderation_repo.list_all_cases_for_user(G, 1), await moderation_repo.list_notes_for_user(G, 1)
    )
    assert "Caso #1" in testo and "Motivo: uno" in testo and "una nota" in testo


# --- repository ---

async def test_nascosto_non_conta_in_classifiche_e_avvisi():
    for _ in range(2):
        await moderation_repo.create_case(G, 1, 10, "warn", "x")
    assert await moderation_repo.count_active_cases(G, 1, "warn") == 2
    assert await moderation_repo.set_case_hidden(G, 1, True)
    assert await moderation_repo.count_active_cases(G, 1, "warn") == 1
    assert await moderation_repo.warn_ranking(G) == [(1, 1)]
    assert await moderation_repo.count_active_warns(G) == 1
    assert [c.case_number for c in await moderation_repo.list_active_warns(G, 10)] == [2]
    assert await moderation_repo.set_case_hidden(G, 1, False)
    assert await moderation_repo.count_active_warns(G) == 2


async def test_azzera_tutti_i_warn_in_una_query():
    await moderation_repo.create_case(G, 1, 10, "warn", "x")
    await moderation_repo.create_case(G, 2, 10, "warn", "y")
    await moderation_repo.create_case(G, 2, 10, "ban", "z")
    await moderation_repo.create_case(999, 3, 10, "warn", "altro server")
    assert await moderation_repo.revoke_all_warns(G, 10) == 2
    assert await moderation_repo.count_active_warns(G) == 0
    assert await moderation_repo.count_active_warns(999) == 1
    assert await moderation_repo.count_active_cases(G, 2, "ban") == 1


async def test_casi_automod_scadono_solo_se_il_server_lo_vuole(clean_db):
    await db.set_guild_setting(G, SETTING_SCADENZA_AUTOMOD, 30)
    n = await moderation_repo.create_case(G, 1, 10, "warn", "AutoMod: spam")
    m = await moderation_repo.create_case(G, 1, 10, "warn", "a mano")
    righe = {r["case_number"]: r for r in await clean_db.fetch("SELECT * FROM moderation_cases")}
    assert righe[n]["origine"] == "automod" and righe[n]["expires_at"] is not None
    assert righe[m]["origine"] == "manuale" and righe[m]["expires_at"] is None
    await clean_db.execute("UPDATE moderation_cases SET expires_at = now() - interval '1 hour' WHERE case_number = $1", n)
    assert await moderation_repo.expire_due_cases() == 1
    assert (await moderation_repo.get_case(G, n)).active is False
    assert (await moderation_repo.get_case(G, m)).active is True


async def test_senza_scadenza_impostata_il_caso_automod_non_scade(clean_db):
    n = await moderation_repo.create_case(G, 1, 10, "warn", "AutoMod: spam")
    assert await clean_db.fetchval("SELECT expires_at FROM moderation_cases WHERE case_number = $1", n) is None


# --- comandi ---

async def test_nascondi_comando():
    await moderation_repo.create_case(G, 1, 10, "warn", "x")
    inter, _ = _inter()
    cog = ModerationCaseSystemCog(bot=None)
    await cog.case_hide.callback(cog, inter, 1, True)
    assert await moderation_repo.is_case_hidden(G, 1)
    inter2, _ = _inter()
    await cog.case_hide.callback(cog, inter2, 99, True)
    assert "Nessun caso" in _testo(inter2)


async def test_azzera_tutti_chiede_il_numero_giusto():
    for u in (1, 2, 3):
        await moderation_repo.create_case(G, u, 10, "warn", "x")
    cog = ModerationCaseSystemCog(bot=None)
    inter, _ = _inter()
    await cog.warn_reset_all.callback(cog, inter, 2)
    assert await moderation_repo.count_active_warns(G) == 3
    inter2, log = _inter()
    await cog.warn_reset_all.callback(cog, inter2, 3)
    assert await moderation_repo.count_active_warns(G) == 0
    log.send.assert_awaited()


async def test_azzera_tutti_serve_gestire_il_server():
    await moderation_repo.create_case(G, 1, 10, "warn", "x")
    cog = ModerationCaseSystemCog(bot=None)
    inter, _ = _inter(gestione=False)
    await cog.warn_reset_all.callback(cog, inter, 1)
    assert await moderation_repo.count_active_warns(G) == 1


async def test_elenco_warn_del_server():
    await moderation_repo.create_case(G, 1, 10, "warn", "primo")
    await moderation_repo.create_case(G, 2, 10, "warn", "secondo")
    inter, _ = _inter()
    cog = ModerationCaseSystemCog(bot=None)
    await cog.warn_list.callback(cog, inter)
    embed = inter.response.send_message.call_args.kwargs["embed"]
    assert "primo" in embed.description and "secondo" in embed.description


async def test_esporta_manda_un_file():
    await moderation_repo.create_case(G, 1, 10, "warn", "uno")
    inter, _ = _inter()
    cog = ModerationCaseSystemCog(bot=None)
    await cog.case_export.callback(cog, inter, MagicMock(id=1))
    file = inter.followup.send.call_args.kwargs["file"]
    assert file.filename.endswith(".txt")


async def test_durata_timeout_cambia_il_timeout():
    n = await moderation_repo.create_case(G, 1, 10, "timeout", "x", 600)
    inter, _ = _inter()
    membro = fake_member(1)
    membro.edit = AsyncMock()
    inter.guild.get_member = MagicMock(return_value=membro)
    cog = ModerationCaseSystemCog(bot=None)
    await cog.case_duration.callback(cog, inter, n, "2h")
    assert membro.edit.call_args.kwargs["timed_out_until"] > datetime.now(timezone.utc) + timedelta(hours=1, minutes=50)
    assert (await moderation_repo.get_case(G, n)).duration_seconds == 7200


async def test_durata_di_un_warn_e_rifiutata():
    n = await moderation_repo.create_case(G, 1, 10, "warn", "x")
    inter, _ = _inter()
    cog = ModerationCaseSystemCog(bot=None)
    await cog.case_duration.callback(cog, inter, n, "2h")
    assert "non ha una durata" in _testo(inter)
