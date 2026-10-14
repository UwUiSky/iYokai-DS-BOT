"""
tests/test_moderation_massa.py
==============================
Azioni su più utenti insieme (MOD-002…006): ban (anche di chi non è nel
server), unban, kick, timeout, warn. Un caso per utente, un riepilogo nel
log; chi non si può moderare è saltato con il motivo; DM prima di kick e ban,
cancellato se l'azione fallisce.
"""

from unittest.mock import MagicMock

import discord
import pytest

from cogs.moderation._shared import MODULE_ACTIONS, SETTING_MOD_LOG_CHANNEL
from cogs.moderation.actions import ModerationActionsCog
from core.database import db
from core.moderation_bulk_logic import MAX_USI_ORA, MAX_UTENTI_MASSA, azzera_usi, leggi_utenti, riepilogo
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role, fake_text_channel

SERVER = 100
MOD = 444444444444444444
LOG = 7001
A, B, C = 111111111111111111, 222222222222222222, 333333333333333333


@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    azzera_usi()
    await db.set_module_active_for_guild(SERVER, MODULE_ACTIONS, True)
    await db.set_guild_setting(SERVER, SETTING_MOD_LOG_CHANNEL, LOG)
    yield
    database_module.db._modules_cache.clear()


def _scena(membri_ids=(A, B)):
    server = fake_guild(SERVER, owner_id=1)
    server.me.top_role = fake_role(role_id=3, position=50)
    server.me.id = 999
    log = fake_text_channel(LOG, "mod-log")
    server.get_channel.return_value = log
    moderatore = fake_member(MOD, roles=[fake_role(role_id=1, position=40)])
    moderatore.guild = server
    membri = {}
    for uid in membri_ids:
        m = fake_member(uid, roles=[fake_role(role_id=2, position=5)])
        m.guild = server
        membri[uid] = m
    tutti = {MOD: moderatore, **membri}
    server.get_member.side_effect = tutti.get
    interazione = fake_interaction(guild=server, user=moderatore)
    return server, membri, interazione, log


def _cog():
    return ModerationActionsCog(bot=MagicMock())


async def _casi(uid):
    return [c.action_type for c in await moderation_repo.list_cases_for_user(SERVER, uid)]


def test_lettura_dell_elenco():
    assert leggi_utenti(f"<@{A}>, <@!{B}> {A}\n{C} 12345") == ([A, B, C], False)
    molti = " ".join(str(10**17 + i) for i in range(MAX_UTENTI_MASSA + 5))
    ids, tagliato = leggi_utenti(molti)
    assert len(ids) == MAX_UTENTI_MASSA and tagliato
    assert "2 fatti" in riepilogo(["a", "b"], []) and "1 saltati" in riepilogo([], ["x"])


async def test_ban_in_massa_anche_fuori_dal_server_e_salta_chi_non_si_tocca():
    server, membri, interazione, log = _scena(membri_ids=(A,))
    capo = fake_member(B, roles=[fake_role(role_id=9, position=45)])  # sopra il moderatore
    server.get_member.side_effect = {MOD: interazione.user, A: membri[A], B: capo}.get

    async def _bulk(utenti, **kwargs):
        return discord.guild.BulkBanResult(banned=[u for u in utenti], failed=[])

    server.bulk_ban.side_effect = _bulk
    await _cog().ban_massa.callback(_cog(), interazione, f"<@{A}> {B} {C} {MOD} 1", "raid di spam", 1)

    bannati = [u.id for u in server.bulk_ban.await_args.args[0]]
    assert bannati == [A, C]  # B è sopra il moderatore, MOD è lui stesso, 1 non è un ID
    assert server.bulk_ban.await_args.kwargs["delete_message_seconds"] == 86400
    membri[A].send.assert_awaited_once()  # DM prima del ban; C non è nel server
    assert await _casi(A) == ["ban"] and await _casi(C) == ["ban"] and await _casi(B) == []
    testo = interazione.followup.send.call_args.kwargs["embed"].description
    assert "2 fatti" in testo and "sei tu" in testo
    log.send.assert_awaited_once()


async def test_ban_rifiutato_cancella_il_dm_e_non_crea_il_caso():
    server, membri, interazione, _ = _scena(membri_ids=(A,))
    dm = MagicMock(spec=discord.Message)
    membri[A].send.return_value = dm

    async def _bulk(utenti, **kwargs):
        return discord.guild.BulkBanResult(banned=[], failed=list(utenti))

    server.bulk_ban.side_effect = _bulk
    await _cog().ban_massa.callback(_cog(), interazione, str(A), "motivo valido", 0)
    dm.delete.assert_awaited_once()
    assert await _casi(A) == []


async def test_ban_senza_gestisci_server_passa_ai_ban_singoli():
    # Il ban in blocco di Discord vuole anche «Gestisci server»: senza, Forbidden.
    server, membri, interazione, _ = _scena(membri_ids=(A,))
    server.bulk_ban.side_effect = discord.Forbidden(MagicMock(status=403, reason="x"), "Missing Permissions")
    await _cog().ban_massa.callback(_cog(), interazione, f"{A} {C}", "raid di spam", 0)
    assert sorted(c.args[0].id for c in server.ban.await_args_list) == [A, C]
    assert await _casi(A) == ["ban"] and await _casi(C) == ["ban"]


async def test_ban_e_kick_in_massa_hanno_un_tetto_di_usi_all_ora():
    cog = _cog()
    for _ in range(MAX_USI_ORA):
        server, membri, interazione, _ = _scena()
        await cog.kick_massa.callback(cog, interazione, f"{A}", "pulizia")
        membri[A].kick.assert_awaited_once()
    server, membri, interazione, _ = _scena()
    await cog.kick_massa.callback(cog, interazione, f"{A}", "pulizia")
    membri[A].kick.assert_not_awaited()
    assert "nell'ultima ora" in interazione.response.send_message.call_args.args[0]
    # Il proprietario del server non ha tetto.
    server.owner_id = MOD
    await cog.kick_massa.callback(cog, interazione, f"{A}", "pulizia")
    membri[A].kick.assert_awaited_once()


async def test_kick_timeout_warn_in_massa():
    server, membri, interazione, _ = _scena()
    cog = _cog()
    await cog.kick_massa.callback(cog, interazione, f"{A} {B} {C}", "pulizia")
    membri[A].kick.assert_awaited_once()
    membri[B].kick.assert_awaited_once()
    assert "non è nel server" in interazione.followup.send.call_args.kwargs["embed"].description

    server, membri, interazione, _ = _scena()
    await cog.timeout_massa.callback(cog, interazione, f"{A} {B}", "2h", "flood")
    assert membri[A].timeout.await_args.args[0].total_seconds() == 7200
    await cog.warn_massa.callback(cog, interazione, f"{A}", "linguaggio")
    assert sorted(await _casi(A)) == ["kick", "timeout", "warn"]


async def test_timeout_oltre_28_giorni_rifiutato_prima_di_toccare_qualcuno():
    server, membri, interazione, _ = _scena()
    await _cog().timeout_massa.callback(_cog(), interazione, f"{A}", "30d", "troppo")
    membri[A].timeout.assert_not_awaited()
    interazione.response.defer.assert_not_awaited()


async def test_unban_in_massa_chiude_i_casi_di_ban():
    server, _, interazione, _ = _scena(membri_ids=())
    await moderation_repo.create_case(SERVER, A, MOD, "ban", "vecchio")

    async def _unban(utente, **kwargs):
        if utente.id == B:
            raise discord.NotFound(MagicMock(status=404, reason="x"), "Unknown Ban")

    server.unban.side_effect = _unban
    await _cog().unban_massa.callback(_cog(), interazione, f"{A} {B}", "perdonati")
    casi = await moderation_repo.list_cases_for_user(SERVER, A)
    assert all(not c.active for c in casi if c.action_type == "ban")
    assert "non è bannato" in interazione.followup.send.call_args.kwargs["embed"].description
