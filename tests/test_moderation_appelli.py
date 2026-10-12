"""
tests/test_moderation_appelli.py
================================
Appelli contro i ban manuali (NF-30, #101): regole, invio, decisione dello staff.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.moderation._shared import MODULE_ACTIONS
from cogs.moderation.ban_appeal import (
    SETTING_CANALE_APPELLI,
    decidi_appello,
    invia_appello,
    vista_appello,
)
from core.ban_appeal_logic import attesa_rimasta, lunghezza_valida
from core.database import db
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel

G, UTENTE = 100, 20
ADESSO = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


def test_regole_pure():
    assert attesa_rimasta(None, ADESSO) is None
    assert attesa_rimasta(ADESSO - timedelta(hours=25), ADESSO) is None
    assert attesa_rimasta(ADESSO - timedelta(hours=23), ADESSO) == timedelta(hours=1)
    assert not lunghezza_valida("corto") and lunghezza_valida("x" * 50) and not lunghezza_valida("x" * 1501)


@pytest.fixture
async def amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
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


async def test_senza_canale_niente_bottone(amb):
    await db.set_guild_setting(G, SETTING_CANALE_APPELLI, None)
    assert await vista_appello(G) is None


async def test_con_canale_il_bottone_e_persistente(amb):
    vista = await vista_appello(G)
    assert vista.timeout is None and vista.children[0].custom_id == f"appello:apri:{G}"


async def test_appello_senza_ban_attivo_rifiutato(amb):
    _, canale, bot = amb
    esito = await invia_appello(bot, G, fake_member(UTENTE), "x" * 30, ADESSO)
    assert "nessun ban" in esito.lower()
    canale.send.assert_not_awaited()


async def test_appello_inviato_una_volta_ogni_24_ore(amb):
    _, canale, bot = amb
    await moderation_repo.create_case(G, UTENTE, 10, "ban", "spam")

    assert "inviato" in (await invia_appello(bot, G, fake_member(UTENTE), "x" * 30, ADESSO)).lower()
    canale.send.assert_awaited_once()
    bottoni = canale.send.call_args.kwargs["view"].children
    assert [b.custom_id.split(":")[-1] for b in bottoni] == ["si", "no"]

    ancora = await invia_appello(bot, G, fake_member(UTENTE), "y" * 30, datetime.now(timezone.utc))
    assert "riprovare tra" in ancora
    assert canale.send.await_count == 1


def _inter_staff(server, ban_members=True):
    mod = fake_member(10, guild_permissions=discord.Permissions(ban_members=ban_members))
    inter = fake_interaction(guild=server, user=mod)
    inter.client = MagicMock()
    utente = MagicMock()
    utente.send = AsyncMock()
    inter.client.fetch_user = AsyncMock(return_value=utente)
    inter.message = None
    inter.edit_original_response = AsyncMock()
    return inter, utente


async def _appello(bot):
    await moderation_repo.create_case(G, UTENTE, 10, "ban", "spam")
    await invia_appello(bot, G, fake_member(UTENTE), "x" * 30, ADESSO)
    return (await moderation_repo.list_appeals(G))[0]["id"]


async def test_senza_permesso_non_decide(amb):
    server, _, bot = amb
    aid = await _appello(bot)
    inter, _ = _inter_staff(server, ban_members=False)

    await decidi_appello(inter, aid, True)

    server.unban.assert_not_awaited()
    assert (await moderation_repo.get_appeal(aid))["stato"] == "aperto"


async def test_accetta_toglie_il_ban_e_avvisa(amb):
    server, _, bot = amb
    aid = await _appello(bot)
    inter, utente = _inter_staff(server)

    await decidi_appello(inter, aid, True)

    server.unban.assert_awaited()
    utente.send.assert_awaited()
    assert (await moderation_repo.get_appeal(aid))["stato"] == "accettato"
    assert (await moderation_repo.get_latest_active_case(G, UTENTE, "ban")) is None


async def test_rifiuta_non_sbanna_e_secondo_click_non_conta(amb):
    server, _, bot = amb
    aid = await _appello(bot)
    inter, _ = _inter_staff(server)
    await decidi_appello(inter, aid, False)
    server.unban.assert_not_awaited()

    inter2, utente2 = _inter_staff(server)
    await decidi_appello(inter2, aid, True)
    server.unban.assert_not_awaited()
    assert (await moderation_repo.get_appeal(aid))["stato"] == "rifiutato"


# ----------------- correzioni del giro bug -----------------

async def test_accetta_toglie_il_ban_prima_di_segnare_accettato(amb):
    server, _, bot = amb
    aid = await _appello(bot)
    inter, _ = _inter_staff(server)
    visto = []

    async def _unban(*a, **k):
        visto.append((await moderation_repo.get_appeal(aid))["stato"])

    server.unban.side_effect = _unban
    await decidi_appello(inter, aid, True)

    assert visto == ["aperto"]
    assert (await moderation_repo.get_appeal(aid))["stato"] == "accettato"


async def test_unban_fallito_lascia_aperti_appello_e_caso(amb):
    server, _, bot = amb
    aid = await _appello(bot)
    inter, utente = _inter_staff(server)
    server.unban.side_effect = discord.HTTPException(MagicMock(status=403, reason="x"), "x")

    await decidi_appello(inter, aid, True)

    assert (await moderation_repo.get_appeal(aid))["stato"] == "aperto"
    assert await moderation_repo.get_latest_active_case(G, UTENTE, "ban") is not None
    utente.send.assert_not_awaited()


async def test_accetta_non_tocca_un_ban_piu_recente(amb):
    server, _, bot = amb
    aid = await _appello(bot)
    vecchio = (await moderation_repo.get_appeal(aid))["case_number"]
    # Il vecchio ban è stato tolto a mano e l'utente è stato bannato di nuovo.
    await moderation_repo.revoke_case(G, vecchio, 10)
    nuovo = await moderation_repo.create_case(G, UTENTE, 10, "ban", "di nuovo")
    inter, _ = _inter_staff(server)

    await decidi_appello(inter, aid, True)

    server.unban.assert_not_awaited()
    assert (await moderation_repo.get_latest_active_case(G, UTENTE, "ban")).case_number == nuovo


async def test_accetta_revoca_solo_il_caso_dell_appello(amb):
    server, _, bot = amb
    await moderation_repo.create_case(G, UTENTE, 10, "tempban", "altro", duration_seconds=60)
    aid = await _appello(bot)
    inter, _ = _inter_staff(server)

    await decidi_appello(inter, aid, True)

    # Il tempban (un altro caso) resta attivo: l'appello riguardava il ban.
    assert (await moderation_repo.get_latest_active_case(G, UTENTE, "tempban")) is not None


async def test_accetta_cancella_la_scadenza_automatica(amb):
    from core.scheduler import scheduler, in_seconds

    server, _, bot = amb
    await scheduler.schedule(
        guild_id=G, user_id=UTENTE, action_type="moderation_tempban_expire",
        execute_at=in_seconds(3600), payload={"case_number": 1, "modo": "fuori"},
    )
    aid = await _appello(bot)
    inter, _ = _inter_staff(server)

    await decidi_appello(inter, aid, True)

    assert await scheduler.list_pending_for_user(UTENTE, "moderation_tempban_expire") == []


async def test_tre_appelli_insieme_ne_creano_uno(amb):
    import asyncio

    from tests.support.concorrenza import apri_connessioni

    _, canale, bot = amb
    await moderation_repo.create_case(G, UTENTE, 10, "ban", "spam")
    await apri_connessioni(moderation_repo._pool)

    esiti = await asyncio.gather(
        *(invia_appello(bot, G, fake_member(UTENTE), "x" * 30, ADESSO) for _ in range(3))
    )

    assert len(await moderation_repo.list_appeals(G)) == 1
    assert sum("inviato" in e.lower() for e in esiti) == 1
    assert canale.send.await_count == 1


async def test_appello_non_consegnato_non_blocca_per_24_ore(amb):
    _, canale, bot = amb
    await moderation_repo.create_case(G, UTENTE, 10, "ban", "spam")
    canale.send.side_effect = discord.HTTPException(MagicMock(status=500, reason="x"), "x")

    assert "non sono riuscito" in (await invia_appello(bot, G, fake_member(UTENTE), "x" * 30, ADESSO)).lower()
    assert await moderation_repo.list_appeals(G) == []


# --------- secondo passaggio: caso non attivo, doppio clic, comandi, log ---------

async def test_appello_su_caso_gia_tolto_si_chiude_come_accettato_senza_sbannare(amb):
    server, _, bot = amb
    aid = await _appello(bot)
    numero = (await moderation_repo.get_appeal(aid))["case_number"]
    await moderation_repo.revoke_case(G, numero, 10)
    inter, utente = _inter_staff(server)

    await decidi_appello(inter, aid, True)

    server.unban.assert_not_awaited()
    assert (await moderation_repo.get_appeal(aid))["stato"] == "accettato"
    assert "già tolto" in utente.send.call_args.args[0]


async def test_appello_su_caso_eliminato_si_chiude(amb):
    server, _, bot = amb
    aid = await _appello(bot)
    numero = (await moderation_repo.get_appeal(aid))["case_number"]
    await moderation_repo.delete_case(G, numero)
    inter, utente = _inter_staff(server)

    await decidi_appello(inter, aid, True)

    assert (await moderation_repo.get_appeal(aid))["stato"] == "accettato"
    server.unban.assert_not_awaited()


async def test_appello_su_caso_sostituito_avvisa_che_ce_un_altro_ban(amb):
    server, _, bot = amb
    aid = await _appello(bot)
    await moderation_repo.revoke_case(G, (await moderation_repo.get_appeal(aid))["case_number"], 10)
    await moderation_repo.create_case(G, UTENTE, 10, "ban", "di nuovo")
    inter, utente = _inter_staff(server)

    await decidi_appello(inter, aid, True)

    server.unban.assert_not_awaited()
    assert "un altro" in utente.send.call_args.args[0]


async def test_doppio_clic_insieme_sbanna_una_volta_sola(amb):
    import asyncio

    from tests.support.concorrenza import apri_connessioni

    server, _, bot = amb
    aid = await _appello(bot)
    inter1, _ = _inter_staff(server)
    inter2, _ = _inter_staff(server)
    await apri_connessioni(moderation_repo._pool)

    await asyncio.gather(decidi_appello(inter1, aid, True), decidi_appello(inter2, aid, True))

    assert server.unban.await_count == 1
    assert (await moderation_repo.get_appeal(aid))["stato"] == "accettato"


async def test_appello_di_un_altro_server_non_si_decide(amb):
    server, _, bot = amb
    aid = await _appello(bot)
    altro = fake_guild(777)
    altro.unban = AsyncMock()
    inter, _ = _inter_staff(altro)

    await decidi_appello(inter, aid, True)

    altro.unban.assert_not_awaited()
    assert (await moderation_repo.get_appeal(aid))["stato"] == "aperto"
    assert "non trovato" in inter.response.send_message.call_args.args[0]


async def test_testo_troppo_corto_o_lungo_e_canale_mancante(amb):
    _, canale, bot = amb
    await moderation_repo.create_case(G, UTENTE, 10, "ban", "spam")

    assert "tra 10 e 1500" in await invia_appello(bot, G, fake_member(UTENTE), "corto", ADESSO)
    assert "tra 10 e 1500" in await invia_appello(bot, G, fake_member(UTENTE), "x" * 1501, ADESSO)
    await db.set_guild_setting(G, SETTING_CANALE_APPELLI, None)
    assert "non accetta appelli" in await invia_appello(bot, G, fake_member(UTENTE), "x" * 30, ADESSO)
    canale.send.assert_not_awaited()
    assert await moderation_repo.list_appeals(G) == []


async def test_un_tempban_si_puo_contestare_e_accettando_si_chiude(amb):
    server, _, bot = amb
    await moderation_repo.create_case(G, UTENTE, 10, "tempban", "spam", duration_seconds=3600)
    await invia_appello(bot, G, fake_member(UTENTE), "x" * 30, ADESSO)
    aid = (await moderation_repo.list_appeals(G))[0]["id"]
    inter, _ = _inter_staff(server)

    await decidi_appello(inter, aid, True)

    server.unban.assert_awaited()
    assert await moderation_repo.get_latest_active_case(G, UTENTE, "tempban") is None


async def test_accettare_chiude_lo_stato_del_tempban_e_scrive_nel_log(amb, monkeypatch):
    import cogs.moderation.ban_appeal as modulo

    server, _, bot = amb
    await moderation_repo.create_case(G, UTENTE, 10, "tempban", "spam", duration_seconds=3600)
    from datetime import datetime as _dt

    await moderation_repo.save_tempban_state(G, UTENTE, "rientro", [1], _dt.now(timezone.utc) + timedelta(days=1))
    await invia_appello(bot, G, fake_member(UTENTE), "x" * 30, ADESSO)
    aid = (await moderation_repo.list_appeals(G))[0]["id"]
    log = AsyncMock()
    monkeypatch.setattr(modulo, "post_to_mod_log", log)
    inter, _ = _inter_staff(server)

    await decidi_appello(inter, aid, True)

    assert (await moderation_repo.get_tempban_state(G, UTENTE))["scaduto"] is True
    assert "accettato" in log.call_args.args[1].title


async def test_comandi_appelli_canale_ed_elenco(amb):
    from cogs.moderation.ban_appeal import ModerationBanAppealCog

    server, _, bot = amb
    cog = ModerationBanAppealCog(bot)
    inter = fake_interaction(guild=server, user=fake_member(10))
    canale_nuovo = fake_text_channel(6000, "nuovo")

    await cog.canale.callback(cog, inter, canale_nuovo)
    assert await db.get_guild_setting(G, SETTING_CANALE_APPELLI) == 6000
    await cog.canale.callback(cog, inter, None)
    assert await db.get_guild_setting(G, SETTING_CANALE_APPELLI) is None

    inter2 = fake_interaction(guild=server, user=fake_member(10))
    await cog.elenco.callback(cog, inter2, None)
    assert inter2.response.send_message.call_args.args[0] == "Nessun appello."
    await moderation_repo.create_case(G, UTENTE, 10, "ban", "spam")
    await moderation_repo.create_appeal_if_allowed(G, UTENTE, 1, "x" * 30, timedelta(hours=24))
    await cog.elenco.callback(cog, inter2, None)
    assert f"<@{UTENTE}>" in inter2.response.send_message.call_args.kwargs["embed"].description


async def test_modulo_appello_risponde_con_l_esito(amb):
    from cogs.moderation.ban_appeal import ModuloAppello

    _, canale, bot = amb
    await moderation_repo.create_case(G, UTENTE, 10, "ban", "spam")
    modulo = ModuloAppello(G)
    modulo.testo._value = "x" * 30
    inter = fake_interaction(guild=None, user=fake_member(UTENTE))
    inter.client = bot

    await modulo.on_submit(inter)

    assert "inviato" in inter.followup.send.call_args.args[0].lower()
    canale.send.assert_awaited_once()
