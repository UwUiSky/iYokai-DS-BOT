"""
tests/test_verify_tempi.py
==========================
Verify, tempi e azioni (VER-008, 009, 011, 012, 013): promemoria in DM e
avviso nel canale se i DM sono chiusi, tempo massimo con kick o ban, azione
su chi non passa (captcha: solo dopo 3 errori di fila), verifica solo per gli
account sospetti.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands

from cogs.security import verify as modulo
from core import security_raid_state
from core.database import db
from core.repositories.verify_repo import verify_repo
from core.verify_logic import MOTIVO_CAPTCHA, account_sospetto, azione_dopo_fallimento, esiti_nella_finestra
from tests.support.discord_fakes import fake_interaction, fake_member, fake_text_channel
from tests.test_verify_risposta_subito import GUILD_ID, UTENTE_ID, Scenario, scenario  # noqa: F401


@pytest.fixture(autouse=True)
def _nessun_raid():
    security_raid_state._ultimo_ingresso.clear()
    yield
    security_raid_state._ultimo_ingresso.clear()


def _scelta(v):
    return app_commands.Choice(name=v, value=v)


async def _tempi(scena, **opzioni):
    interazione = fake_interaction(guild=scena.server, user=fake_member(1))
    valori = dict(promemoria_minuti=None, scadenza_minuti=None, azione_scadenza=None, azione_fallita=None, solo_sospetti=None)
    valori.update(opzioni)
    await scena.cog.tempi_cmd.callback(scena.cog, interazione, **valori)
    return interazione


async def _lavori(pool):
    return [
        (r["action_type"], r["user_id"])
        for r in await pool.fetch("SELECT action_type, user_id FROM scheduled_actions WHERE guild_id = $1 ORDER BY id", GUILD_ID)
    ]


def test_regole_pure():
    adesso = datetime.now(timezone.utc)
    assert account_sospetto(adesso - timedelta(days=2), True, adesso)
    assert account_sospetto(adesso - timedelta(days=200), False, adesso)
    assert not account_sospetto(adesso - timedelta(days=200), True, adesso)
    assert azione_dopo_fallimento("kick", "Account does not meet the minimum age requirement.", [False]) == "kick"
    assert azione_dopo_fallimento("kick", MOTIVO_CAPTCHA, [False, False]) == "niente"
    assert azione_dopo_fallimento("ban", MOTIVO_CAPTCHA, [False, False, False]) == "ban"
    assert azione_dopo_fallimento("ban", MOTIVO_CAPTCHA, [False, True, False]) == "niente"
    assert azione_dopo_fallimento("niente", "x", [False]) == "niente"
    vecchio, recente = adesso - timedelta(hours=25), adesso - timedelta(hours=1)
    assert esiti_nella_finestra([(False, "", recente), (True, "", vecchio)], adesso) == [False]


async def test_ingresso_pianifica_promemoria_e_scadenza(scenario, clean_db):
    await scenario.configura(captcha=False)
    await _tempi(scenario, promemoria_minuti=10, scadenza_minuti=30, azione_scadenza=_scelta("ban"))
    scenario.utente.guild = scenario.server
    await scenario.cog.on_member_join(scenario.utente)
    assert await _lavori(clean_db) == [(modulo.VERIFY_PROMEMORIA, UTENTE_ID), (modulo.VERIFY_SCADENZA, UTENTE_ID)]


async def test_rientro_cancella_le_scadenze_dell_ingresso_di_prima(scenario, clean_db):
    # Entra, esce e rientra: la scadenza vecchia lo caccerebbe prima del tempo.
    await scenario.configura(captcha=False)
    await _tempi(scenario, promemoria_minuti=10, scadenza_minuti=30)
    scenario.utente.guild = scenario.server
    await scenario.cog.on_member_join(scenario.utente)
    await scenario.cog.on_member_join(scenario.utente)
    assert await _lavori(clean_db) == [(modulo.VERIFY_PROMEMORIA, UTENTE_ID), (modulo.VERIFY_SCADENZA, UTENTE_ID)]


async def test_promemoria_in_dm_e_avviso_nel_canale_se_chiusi(scenario):
    await scenario.configura(captcha=False)
    scenario.utente.roles = []
    await scenario.cog.handle_promemoria(GUILD_ID, UTENTE_ID, {})
    scenario.utente.send.assert_awaited_once()

    canale = fake_text_channel(channel_id=77)
    scenario.server.get_channel.side_effect = {77: canale}.get
    await verify_repo.set_panel_message(GUILD_ID, 77, 1234)
    scenario.utente.send.side_effect = discord.Forbidden(MagicMock(status=403), "chiusi")
    await scenario.cog.handle_promemoria(GUILD_ID, UTENTE_ID, {})
    assert canale.send.await_args.kwargs["delete_after"] == modulo.SECONDI_AVVISO_CANALE
    assert scenario.utente.mention in canale.send.await_args.args[0]


async def test_promemoria_tace_per_chi_e_gia_verificato_o_durante_un_raid(scenario):
    await scenario.configura(captcha=False)
    scenario.utente.roles = [scenario.ruolo]
    await scenario.cog.handle_promemoria(GUILD_ID, UTENTE_ID, {})
    scenario.utente.roles = []
    security_raid_state.segna_raid(GUILD_ID)
    await scenario.cog.handle_promemoria(GUILD_ID, UTENTE_ID, {})
    scenario.utente.send.assert_not_awaited()


async def test_scadenza_caccia_chi_non_si_e_verificato(scenario):
    await scenario.configura(captcha=False)
    await _tempi(scenario, azione_scadenza=_scelta("ban"))
    scenario.utente.roles = []
    await scenario.cog.handle_scadenza(GUILD_ID, UTENTE_ID, {})
    scenario.server.ban.assert_awaited_once()
    assert "scaduto" in (await verify_repo.get_recent_attempts(GUILD_ID, UTENTE_ID, 1))[0][1]

    scenario.server.ban.reset_mock()
    scenario.utente.roles = [scenario.ruolo]
    await scenario.cog.handle_scadenza(GUILD_ID, UTENTE_ID, {})
    scenario.server.ban.assert_not_awaited()


async def test_chi_non_passa_il_captcha_tre_volte_viene_espulso(scenario):
    await scenario.configura(captcha=True)
    await _tempi(scenario, azione_fallita=_scelta("kick"))
    scenario.utente.roles = []
    for _ in range(2):
        await scenario.cog.run_checks_and_finalize(scenario.server, scenario.utente, False)
    scenario.utente.kick.assert_not_awaited()
    await scenario.cog.run_checks_and_finalize(scenario.server, scenario.utente, False)
    scenario.utente.kick.assert_awaited_once()


async def test_errori_di_captcha_vecchi_non_contano(scenario, clean_db):
    # Due errori di due giorni fa e uno oggi non sono «3 di fila».
    await scenario.configura(captcha=True)
    await _tempi(scenario, azione_fallita=_scelta("kick"))
    scenario.utente.roles = []
    for _ in range(2):
        await clean_db.execute(
            "INSERT INTO verify_attempts (guild_id, user_id, success, reason, attempted_at) "
            "VALUES ($1, $2, FALSE, $3, now() - interval '2 days')",
            GUILD_ID, UTENTE_ID, MOTIVO_CAPTCHA,
        )
    await scenario.cog.run_checks_and_finalize(scenario.server, scenario.utente, False)
    scenario.utente.kick.assert_not_awaited()


async def test_solo_sospetti_gli_altri_entrano_subito(scenario):
    await scenario.configura(captcha=True)
    await _tempi(scenario, solo_sospetti=True)
    scenario.utente.guild = scenario.server
    scenario.utente.avatar = MagicMock()
    scenario.utente.roles = []
    scenario.utente.add_roles = AsyncMock()
    await scenario.cog.on_member_join(scenario.utente)
    assert scenario.utente.add_roles.await_args.args[0].id == scenario.ruolo.id

    giovane = fake_member(user_id=UTENTE_ID + 1)
    giovane.guild = scenario.server
    giovane.created_at = datetime.now(timezone.utc) - timedelta(days=1)
    giovane.add_roles = AsyncMock()
    await scenario.cog.on_member_join(giovane)
    giovane.add_roles.assert_not_awaited()
    assert await db.get_guild_setting(GUILD_ID, modulo.SETTING_SOLO_SOSPETTI) is True


async def test_comando_verifica_per_il_membro_anche_durante_il_panico(scenario, monkeypatch):
    from core import lockdown_service

    await scenario.configura(captcha=False)
    monkeypatch.setattr(lockdown_service, "panico_riservato", lambda _gid: True)
    scenario.utente.roles = []
    interazione = scenario.clic()
    await scenario.cog.verifica_cmd.callback(scenario.cog, interazione)
    assert "ruolo" in scenario.ordine
    assert interazione.followup.send.await_args.args[0] == "All checks passed."
