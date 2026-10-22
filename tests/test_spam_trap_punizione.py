"""
tests/test_spam_trap_punizione.py
=================================
SIC-040: la trappola punisce come sceglie il server. Di base il ban
(sequenza completa); kick, timeout, solo cancellazione o «decide lo
staff» cancellano il messaggio e fanno solo quello. Database vero.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.security.spam_trap import StaffDecisionButton, StaffDecisionView
from core.database import db
from core.repositories.moderation_repo import moderation_repo
from core.spam_trap_logic import SETTING_PUNIZIONE
from tests.support.discord_fakes import fake_interaction, fake_member, fake_role
from tests.test_spam_trap_ban_e_appello import GUILD_ID, UTENTE_ID, scenario  # noqa: F401


def _scelta(valore):
    return discord.app_commands.Choice(name=valore, value=valore)


async def _tipi():
    return [c.action_type for c in await moderation_repo.list_cases_for_user(GUILD_ID, UTENTE_ID)]


async def _con_punizione(scenario, valore):
    interazione = fake_interaction(guild=scenario.server)
    await scenario.cog.spamtrap_setup.callback(
        scenario.cog, interazione, None, None, None, None, _scelta(valore)
    )
    scenario.log.send.reset_mock()
    return interazione


async def test_di_base_resta_il_ban(scenario):
    assert await db.get_guild_setting(GUILD_ID, SETTING_PUNIZIONE) is None
    await scenario.scrive_nella_trappola()
    scenario.server.ban.assert_awaited_once()


async def test_kick_cancella_avvisa_prima_ed_espelle(scenario):
    interazione = await _con_punizione(scenario, "kick")
    assert "kick" in interazione.followup.send.call_args.args[0]
    await scenario.scrive_nella_trappola()

    scenario.server.ban.assert_not_awaited()
    scenario.utente.send.assert_awaited_once()
    scenario.utente.kick.assert_awaited_once()
    assert await _tipi() == ["spam_trap_kick"]
    assert scenario.embed_del_log().title == "🚨 Spam Trap Triggered"


async def test_kick_fallito_cancella_il_dm_e_non_apre_casi(scenario):
    await _con_punizione(scenario, "kick")
    dm = MagicMock()
    dm.delete = AsyncMock()
    scenario.utente.send = AsyncMock(return_value=dm)
    scenario.utente.kick = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403, reason="x"), "no"))
    await scenario.scrive_nella_trappola()

    dm.delete.assert_awaited_once()
    assert await _tipi() == []
    assert "non riuscito" in str(scenario.embed_del_log().fields)


async def test_timeout_di_un_giorno(scenario):
    await _con_punizione(scenario, "timeout")
    await scenario.scrive_nella_trappola()
    scenario.utente.timeout.assert_awaited_once()
    assert await _tipi() == ["spam_trap_timeout"]


async def test_solo_cancellare_anche_i_messaggi_dopo(scenario):
    await _con_punizione(scenario, "cancella")
    await scenario.scrive_nella_trappola()
    await scenario.scrive_nella_trappola()
    assert await _tipi() == []
    scenario.server.ban.assert_not_awaited()
    scenario.log.send.assert_awaited_once()  # un solo avviso


async def test_decide_lo_staff_con_bottoni_persistenti(scenario):
    await _con_punizione(scenario, "staff")
    await scenario.scrive_nella_trappola()
    vista = scenario.log.send.call_args.kwargs["view"]
    assert isinstance(vista, StaffDecisionView) and vista.timeout is None
    ids = {b.item.custom_id for b in vista.children}
    assert ids == {f"spamtrap_staff:ban:{GUILD_ID}:{UTENTE_ID}", f"spamtrap_staff:kick:{GUILD_ID}:{UTENTE_ID}"}
    assert await _tipi() == []

    # Un moderatore senza «Bannare» non banna; chi ce l'ha sì, e nasce il caso.
    scenario.server.me.top_role = fake_role(role_id=3, position=50)
    scenario.server.get_member.side_effect = {UTENTE_ID: scenario.utente}.get
    scenario.utente.top_role = fake_role(role_id=4, position=1)
    senza = fake_member(7, roles=[fake_role(role_id=5, position=40)])
    senza.guild = scenario.server
    interazione = fake_interaction(guild=scenario.server, user=senza)
    await StaffDecisionView(GUILD_ID, UTENTE_ID).decidi(interazione, "ban")
    scenario.server.ban.assert_not_awaited()

    capo = fake_member(8, roles=[fake_role(role_id=6, position=40)], guild_permissions=discord.Permissions(ban_members=True))
    capo.guild = scenario.server
    interazione = fake_interaction(guild=scenario.server, user=capo)
    await StaffDecisionView(GUILD_ID, UTENTE_ID).decidi(interazione, "ban")
    assert await _tipi() == ["ban"]
    assert "Deciso da" in interazione.edit_original_response.call_args.kwargs["content"]


async def test_il_bottone_si_ricostruisce_dal_custom_id():
    import re

    from cogs.security.spam_trap import MODELLO_ID_STAFF

    match = re.fullmatch(MODELLO_ID_STAFF, f"spamtrap_staff:kick:{GUILD_ID}:{UTENTE_ID}")
    bottone = await StaffDecisionButton.from_custom_id(MagicMock(), MagicMock(), match)
    assert (bottone.azione, bottone.guild_id, bottone.user_id) == ("kick", GUILD_ID, UTENTE_ID)


def _prepara_bottoni(scenario):
    scenario.server.me.top_role = fake_role(role_id=3, position=50)
    scenario.server.get_member.side_effect = {UTENTE_ID: scenario.utente}.get
    scenario.utente.top_role = fake_role(role_id=4, position=1)


def _capo(scenario, uid=8):
    capo = fake_member(
        uid, roles=[fake_role(role_id=6, position=40)],
        guild_permissions=discord.Permissions(ban_members=True, kick_members=True),
    )
    capo.guild = scenario.server
    interazione = fake_interaction(guild=scenario.server, user=capo)
    interazione.message = MagicMock(created_at=discord.utils.utcnow() - __import__("datetime").timedelta(minutes=5))
    return interazione


async def test_bottone_staff_dopo_la_decisione_non_rifa_l_azione(scenario):
    """Il secondo clic (altro moderatore, o lo stesso dopo un'edit fallita) non banna/espelle di nuovo."""
    await _con_punizione(scenario, "staff")
    _prepara_bottoni(scenario)
    await StaffDecisionView(GUILD_ID, UTENTE_ID).decidi(_capo(scenario), "kick")
    secondo = _capo(scenario, uid=9)
    await StaffDecisionView(GUILD_ID, UTENTE_ID).decidi(secondo, "ban")

    scenario.utente.kick.assert_awaited_once()
    scenario.server.ban.assert_not_awaited()
    assert await _tipi() == ["kick"]
    assert "Già deciso" in secondo.followup.send.call_args.args[0]


async def test_bottone_staff_due_clic_insieme_una_sola_azione(scenario):
    import asyncio

    await _con_punizione(scenario, "staff")
    _prepara_bottoni(scenario)
    via = asyncio.Event()

    async def _ban_lento(*a, **k):
        await via.wait()

    scenario.utente.ban = AsyncMock(side_effect=_ban_lento)
    scenario.server.ban = AsyncMock(side_effect=_ban_lento)
    primo = asyncio.ensure_future(StaffDecisionView(GUILD_ID, UTENTE_ID).decidi(_capo(scenario), "ban"))
    for _ in range(20):
        await asyncio.sleep(0)
    secondo = asyncio.ensure_future(StaffDecisionView(GUILD_ID, UTENTE_ID).decidi(_capo(scenario, uid=9), "ban"))
    for _ in range(20):
        await asyncio.sleep(0)
    via.set()
    await asyncio.wait_for(asyncio.gather(primo, secondo), 10)
    assert await _tipi() == ["ban"]


async def test_bottone_staff_rispetta_i_ruoli_immuni(scenario):
    from core import moderation_opzioni

    await _con_punizione(scenario, "staff")
    _prepara_bottoni(scenario)
    immune = fake_role(role_id=77, position=1)
    scenario.utente.roles = [immune]
    await moderation_opzioni.cambia_ruolo_immune(GUILD_ID, 77, True, 1)
    interazione = _capo(scenario)
    await StaffDecisionView(GUILD_ID, UTENTE_ID).decidi(interazione, "kick")

    scenario.utente.kick.assert_not_awaited()
    assert await _tipi() == []
    assert "immune" in interazione.followup.send.call_args.args[0]
