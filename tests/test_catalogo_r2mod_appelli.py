"""
tests/test_catalogo_r2mod_appelli.py
====================================
Controllo delle aree chiuse (#115, r2mod): ban senza appello (MOD-008), testo e bottone di appello nel DM del ban (MOD-061),
canale degli appelli (MOD-062), appello anche per i timeout (MOD-063). Database vero.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.moderation.ban_appeal as ban_appeal_module
from cogs.moderation._shared import MODULE_ACTIONS
from cogs.moderation.actions import ModerationActionsCog
from cogs.moderation.ban_appeal import (
    SETTING_APPELLI_TIMEOUT,
    SETTING_CANALE_APPELLI,
    ModerationBanAppealCog,
    decidi_appello,
    invia_appello,
    offri_appello_in_dm,
)
from core.database import db
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role, fake_text_channel
from tests.test_moderation_ordine_azione import ID_SERVER, Scena

G, UTENTE = 100, 20
ADESSO = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
async def amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    ban_appeal_module._offerte_dm.clear()
    await db.set_module_active_for_guild(G, MODULE_ACTIONS, True)
    await db.set_guild_setting(G, SETTING_CANALE_APPELLI, 5000)
    server = fake_guild(G)
    server.name = "Server"
    canale = fake_text_channel(5000, "appelli")
    canale.send = AsyncMock()
    server.get_channel.return_value = canale
    server.unban = AsyncMock()
    bot = MagicMock()
    bot.get_guild.return_value = server
    yield server, canale, bot
    database_module.db._modules_cache.clear()


def _stile_scena(s: Scena) -> Scena:
    s.moderatore.guild_permissions = discord.Permissions(ban_members=True, moderate_members=True)
    s.server.me.guild_permissions = discord.Permissions(ban_members=True)
    return s


@pytest.fixture
async def scena(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID_SERVER, MODULE_ACTIONS, True)
    await db.set_guild_setting(ID_SERVER, SETTING_CANALE_APPELLI, 5000)
    yield _stile_scena(Scena())
    database_module.db._modules_cache.clear()


# MOD-061, MOD-062
async def test_il_dm_del_ban_porta_il_bottone_di_appello_quando_il_server_ha_il_canale(scena):
    cog = ModerationActionsCog(bot=None)
    await cog.ban.callback(cog, scena.interazione, scena.bersaglio, "Spam ripetuto")
    vista = scena.bersaglio.send.call_args.kwargs["view"]
    assert vista.children[0].custom_id == f"appello:apri:{ID_SERVER}"
    assert await db.get_guild_setting(ID_SERVER, SETTING_CANALE_APPELLI) == 5000


# MOD-008
async def test_ban_senza_appello_niente_bottone_e_il_caso_e_segnato(scena):
    cog = ModerationActionsCog(bot=None)
    await cog.ban.callback(cog, scena.interazione, scena.bersaglio, "Spam ripetuto", None, None, False)
    assert scena.bersaglio.send.call_args.kwargs.get("view") is None
    caso = await moderation_repo.get_latest_active_case(ID_SERVER, scena.bersaglio.id, "ban")
    assert await moderation_repo.caso_senza_appello(ID_SERVER, caso.case_number) is True


# MOD-008
async def test_un_ban_normale_non_e_segnato_senza_appello(scena):
    cog = ModerationActionsCog(bot=None)
    await cog.ban.callback(cog, scena.interazione, scena.bersaglio, "Spam ripetuto")
    caso = await moderation_repo.get_latest_active_case(ID_SERVER, scena.bersaglio.id, "ban")
    assert await moderation_repo.caso_senza_appello(ID_SERVER, caso.case_number) is False


# MOD-008
async def test_chi_ha_un_ban_senza_appello_non_puo_fare_appello_ne_riceve_il_bottone_in_dm(amb):
    _, canale, bot = amb
    numero = await moderation_repo.create_case(G, UTENTE, 10, "ban", "spam")
    await moderation_repo.segna_senza_appello(G, numero)
    esito = await invia_appello(bot, G, fake_member(UTENTE), "x" * 30, ADESSO)
    assert "senza possibilità di appello" in esito
    canale.send.assert_not_awaited()
    assert await moderation_repo.list_appeals(G) == []
    dm = MagicMock()
    dm.send = AsyncMock()
    assert await offri_appello_in_dm(bot, fake_member(UTENTE), dm) is False
    dm.send.assert_not_awaited()


# MOD-063
async def test_il_timeout_non_si_contesta_se_il_server_non_lo_ha_acceso(amb):
    _, canale, bot = amb
    await moderation_repo.create_case(G, UTENTE, 10, "timeout", "spam", 3600)
    esito = await invia_appello(bot, G, fake_member(UTENTE), "x" * 30, ADESSO)
    assert "nessun ban" in esito.lower()
    canale.send.assert_not_awaited()


# MOD-063
async def test_il_timeout_acceso_si_contesta_e_accettando_si_toglie(amb):
    server, canale, bot = amb
    await db.set_guild_setting(G, SETTING_APPELLI_TIMEOUT, True)
    await moderation_repo.create_case(G, UTENTE, 10, "timeout", "spam", 3600)
    assert "inviato" in (await invia_appello(bot, G, fake_member(UTENTE), "x" * 30, ADESSO)).lower()
    aid = (await moderation_repo.list_appeals(G))[0]["id"]

    bersaglio = fake_member(UTENTE, roles=[fake_role(2, position=5)])
    bersaglio.is_timed_out.return_value = True
    bersaglio.timeout = AsyncMock()
    server.get_member.return_value = bersaglio
    server.owner_id = 1
    mod = fake_member(10, roles=[fake_role(1, position=40)], guild_permissions=discord.Permissions(moderate_members=True))
    inter = fake_interaction(guild=server, user=mod)
    inter.client = MagicMock()
    utente = MagicMock()
    utente.send = AsyncMock()
    inter.client.fetch_user = AsyncMock(return_value=utente)
    inter.message = None
    inter.edit_original_response = AsyncMock()

    await decidi_appello(inter, aid, True)

    bersaglio.timeout.assert_awaited_once()
    assert bersaglio.timeout.call_args.args[0] is None
    assert len(bersaglio.timeout.call_args.kwargs["reason"]) <= 512
    assert (await moderation_repo.get_appeal(aid))["stato"] == "accettato"
    assert await moderation_repo.get_latest_active_case(G, UTENTE, "timeout") is None


# MOD-063
async def test_chi_ha_solo_moderare_i_membri_non_decide_l_appello_di_un_ban(amb):
    server, _, bot = amb
    await moderation_repo.create_case(G, UTENTE, 10, "ban", "spam")
    await invia_appello(bot, G, fake_member(UTENTE), "x" * 30, ADESSO)
    aid = (await moderation_repo.list_appeals(G))[0]["id"]
    mod = fake_member(10, guild_permissions=discord.Permissions(moderate_members=True))
    inter = fake_interaction(guild=server, user=mod)
    await decidi_appello(inter, aid, True)
    server.unban.assert_not_awaited()
    assert (await moderation_repo.get_appeal(aid))["stato"] == "aperto"


# MOD-063
async def test_un_timeout_non_si_toglie_a_chi_sta_sopra_chi_decide(amb):
    server, _, bot = amb
    await db.set_guild_setting(G, SETTING_APPELLI_TIMEOUT, True)
    await moderation_repo.create_case(G, UTENTE, 10, "timeout", "spam", 3600)
    await invia_appello(bot, G, fake_member(UTENTE), "x" * 30, ADESSO)
    aid = (await moderation_repo.list_appeals(G))[0]["id"]
    bersaglio = fake_member(UTENTE, roles=[fake_role(2, position=45)])
    bersaglio.is_timed_out.return_value = True
    bersaglio.timeout = AsyncMock()
    server.get_member.return_value = bersaglio
    server.owner_id = 1
    mod = fake_member(10, roles=[fake_role(1, position=40)], guild_permissions=discord.Permissions(moderate_members=True))
    inter = fake_interaction(guild=server, user=mod)
    inter.client = MagicMock()
    inter.message = None
    await decidi_appello(inter, aid, True)
    bersaglio.timeout.assert_not_awaited()
    assert (await moderation_repo.get_appeal(aid))["stato"] == "aperto"


# MOD-063
async def test_il_comando_accende_e_spegne_gli_appelli_per_i_timeout(amb):
    server, _, _ = amb
    cog = ModerationBanAppealCog(bot=MagicMock())
    inter = fake_interaction(guild=server, user=fake_member(10))
    await cog.timeout_appelli.callback(cog, inter, True)
    assert await db.get_guild_setting(G, SETTING_APPELLI_TIMEOUT) is True
    inter2 = fake_interaction(guild=server, user=fake_member(10))
    await cog.timeout_appelli.callback(cog, inter2, False)
    assert await db.get_guild_setting(G, SETTING_APPELLI_TIMEOUT) is False


# MOD-063
async def test_il_dm_del_timeout_porta_il_bottone_solo_se_acceso(scena):
    cog = ModerationActionsCog(bot=None)
    await cog.timeout.callback(cog, scena.interazione, scena.bersaglio, "Spam ripetuto", "1h")
    assert scena.bersaglio.send.call_args.kwargs.get("view") is None
    await db.set_guild_setting(ID_SERVER, SETTING_APPELLI_TIMEOUT, True)
    scena.bersaglio.send.reset_mock()
    await cog.timeout.callback(cog, scena.interazione, scena.bersaglio, "Spam ripetuto", "1h")
    assert scena.bersaglio.send.call_args.kwargs["view"].children[0].custom_id == f"appello:apri:{ID_SERVER}"
    scena.bersaglio.send.reset_mock()
    await cog.timeout.callback(cog, scena.interazione, scena.bersaglio, "Spam ripetuto", "1h", None, False)
    assert scena.bersaglio.send.call_args.kwargs.get("view") is None
