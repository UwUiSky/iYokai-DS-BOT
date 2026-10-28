"""
tests/test_verify_r10.py
========================
Verify, giro r10 (#118): VER-017 (lo staff rimanda l'invito), VER-019 (account
troppo giovane: attesa o espulsione), VER-020 (modalità cieca), VER-030
(statistiche complete), VER-031 (ricerca per utente ed esportazione in CSV).
"""

import csv
import io
from datetime import datetime, timedelta, timezone

import discord
import pytest
from discord import app_commands

from cogs.security import verify as modulo
from core import security_raid_state
from core.repositories.verify_repo import verify_repo
from core.verify_logic import MOTIVO_CAPTCHA, quando_maggiorenne, sospesa_adesso
from tests.support.discord_fakes import fake_interaction, fake_member, fake_text_channel
from tests.test_verify_risposta_subito import GUILD_ID, UTENTE_ID, Scenario, scenario  # noqa: F401
from tests.test_verify_tempi import _lavori, _scelta, _tempi


@pytest.fixture(autouse=True)
def _nessun_raid():
    security_raid_state._ultimo_ingresso.clear()
    modulo._ultimo_csv.clear()
    yield
    security_raid_state._ultimo_ingresso.clear()
    modulo._ultimo_csv.clear()


async def _setup_con_eta(scena, giorni):
    interazione = fake_interaction(guild=scena.server, user=fake_member(1))
    await scena.cog.setup_cmd.callback(
        scena.cog,
        interazione,
        method=app_commands.Choice(name="Button", value="button"),
        verified_role=scena.ruolo,
        min_account_age_days=giorni,
    )


def test_regole_pure():
    adesso = datetime.now(timezone.utc)
    assert quando_maggiorenne(adesso - timedelta(days=2), 5) == adesso - timedelta(days=2) + timedelta(days=5)
    assert sospesa_adesso(int((adesso + timedelta(hours=1)).timestamp()), adesso)
    assert not sospesa_adesso(int((adesso - timedelta(hours=1)).timestamp()), adesso)
    assert not sospesa_adesso(None, adesso)
    assert not sospesa_adesso(0, adesso)


# ------------------------------------------------------------ VER-020
async def test_modalita_cieca_da_il_ruolo_subito_e_lo_scrive_nel_log(scenario):
    await scenario.configura(captcha=True)
    await _tempi(scenario, sospendi_ore=2)
    scenario.utente.guild = scenario.server
    scenario.utente.roles = []
    await scenario.cog.on_member_join(scenario.utente)
    scenario.utente.add_roles.assert_awaited_once()
    assert "cieca" in (await verify_repo.get_recent_attempts(GUILD_ID, UTENTE_ID, 1))[0][1]


async def test_modalita_cieca_scaduta_o_spenta_non_da_il_ruolo(scenario):
    await scenario.configura(captcha=True)
    scenario.utente.guild = scenario.server
    scenario.utente.roles = []
    await _tempi(scenario, sospendi_ore=1)
    await _tempi(scenario, sospendi_ore=0)
    await scenario.cog.on_member_join(scenario.utente)
    scenario.utente.add_roles.assert_not_awaited()


async def test_modalita_cieca_non_vale_per_chi_e_in_blacklist(scenario):
    await scenario.configura(captcha=True)
    await verify_repo.add_blacklist(GUILD_ID, UTENTE_ID)
    await _tempi(scenario, sospendi_ore=2)
    scenario.utente.guild = scenario.server
    scenario.utente.roles = []
    await scenario.cog.on_member_join(scenario.utente)
    scenario.utente.add_roles.assert_not_awaited()


# ------------------------------------------------------------ VER-019
async def test_account_giovane_con_attesa_pianifica_il_via_libera(scenario, clean_db):
    await _setup_con_eta(scenario, 10)
    await _tempi(scenario, scadenza_minuti=30)
    scenario.utente.created_at = datetime.now(timezone.utc) - timedelta(days=4)
    scenario.utente.guild = scenario.server
    scenario.utente.roles = []
    await scenario.cog.on_member_join(scenario.utente)
    assert (modulo.VERIFY_ETA, UTENTE_ID) in await _lavori(clean_db)
    scenario.utente.kick.assert_not_awaited()
    # La scadenza parte dopo l'attesa, non subito: tra 6 giorni + 30 minuti.
    riga = await clean_db.fetchrow(
        "SELECT execute_at FROM scheduled_actions WHERE guild_id = $1 AND action_type = $2",
        GUILD_ID, modulo.VERIFY_SCADENZA,
    )
    assert riga["execute_at"] > datetime.now(timezone.utc) + timedelta(days=6)


async def test_account_giovane_con_espulsione_manda_il_dm_e_caccia(scenario, clean_db):
    await _setup_con_eta(scenario, 10)
    await _tempi(scenario, azione_eta=_scelta("kick"))
    scenario.utente.created_at = datetime.now(timezone.utc) - timedelta(days=4)
    scenario.utente.guild = scenario.server
    scenario.utente.roles = []
    ordine = []

    async def dm(*a, **k):
        ordine.append("dm")

    async def kick(*a, **k):
        ordine.append("kick")

    scenario.utente.send.side_effect = dm
    scenario.utente.kick.side_effect = kick
    await scenario.cog.on_member_join(scenario.utente)
    assert ordine == ["dm", "kick"]
    assert (modulo.VERIFY_ETA, UTENTE_ID) not in await _lavori(clean_db)


async def test_account_maggiorenne_o_in_whitelist_entra_normalmente(scenario, clean_db):
    await _setup_con_eta(scenario, 10)
    await _tempi(scenario, azione_eta=_scelta("kick"))
    scenario.utente.guild = scenario.server
    scenario.utente.roles = []
    await scenario.cog.on_member_join(scenario.utente)  # 400 giorni
    scenario.utente.kick.assert_not_awaited()
    scenario.utente.created_at = datetime.now(timezone.utc) - timedelta(days=1)
    await verify_repo.add_whitelist(GUILD_ID, UTENTE_ID)
    await scenario.cog.on_member_join(scenario.utente)
    scenario.utente.kick.assert_not_awaited()


async def test_via_libera_manda_dm_solo_a_chi_e_ancora_da_verificare(scenario):
    await _setup_con_eta(scenario, 10)
    scenario.utente.roles = []
    await scenario.cog.handle_eta(GUILD_ID, UTENTE_ID, {})
    scenario.utente.send.assert_awaited_once()
    scenario.utente.send.reset_mock()
    scenario.utente.roles = [scenario.ruolo]
    await scenario.cog.handle_eta(GUILD_ID, UTENTE_ID, {})
    scenario.utente.send.assert_not_awaited()


async def test_l_esito_per_account_giovane_dice_da_quando_ci_si_puo_verificare(scenario):
    await _setup_con_eta(scenario, 10)
    scenario.utente.created_at = datetime.now(timezone.utc) - timedelta(days=4)
    scenario.utente.roles = []
    esito = await scenario.cog.run_checks_and_finalize(scenario.server, scenario.utente, captcha_ok=True)
    assert not esito.success
    assert "<t:" in esito.reason


# ------------------------------------------------------------ VER-017
async def test_invia_rimanda_l_invito_al_membro(scenario):
    await scenario.configura(captcha=False)
    scenario.utente.roles = []
    interazione = fake_interaction(guild=scenario.server, user=fake_member(1))
    await scenario.cog.send_cmd.callback(scenario.cog, interazione, scenario.utente)
    scenario.utente.send.assert_awaited_once()
    assert "inviato" in interazione.response.send_message.call_args.args[0].lower()


async def test_invia_con_dm_chiusi_lo_dice_e_non_scrive_nel_canale(scenario):
    await scenario.configura(captcha=False)
    scenario.utente.roles = []
    scenario.utente.send.side_effect = discord.Forbidden(
        type("R", (), {"status": 403, "reason": "x"})(), "chiusi"
    )
    interazione = fake_interaction(guild=scenario.server, user=fake_member(1))
    await scenario.cog.send_cmd.callback(scenario.cog, interazione, scenario.utente)
    assert "chius" in interazione.response.send_message.call_args.args[0]


async def test_invia_a_chi_e_gia_verificato_non_manda_niente(scenario):
    await scenario.configura(captcha=False)
    scenario.utente.roles = [scenario.ruolo]
    interazione = fake_interaction(guild=scenario.server, user=fake_member(1))
    await scenario.cog.send_cmd.callback(scenario.cog, interazione, scenario.utente)
    scenario.utente.send.assert_not_awaited()


# ------------------------------------------------------------ VER-030
async def test_statistiche_complete(scenario):
    await scenario.configura(captcha=False)
    scenario.utente.guild = scenario.server
    scenario.utente.roles = []
    await scenario.cog.on_member_join(scenario.utente)
    await scenario.cog.on_member_remove(scenario.utente)
    await verify_repo.registra_evento(GUILD_ID, UTENTE_ID, "captcha_inviato")
    await verify_repo.log_attempt(GUILD_ID, UTENTE_ID, False, MOTIVO_CAPTCHA)
    await verify_repo.log_attempt(GUILD_ID, UTENTE_ID, True, "All checks passed.")
    await verify_repo.log_attempt(GUILD_ID, 7, False, "Tempo per la verifica scaduto: kick")
    s = await verify_repo.statistiche(GUILD_ID, 7)
    assert s == {
        "ingressi": 1, "uscite": 1, "captcha_inviati": 1, "captcha_falliti": 1,
        "completate": 1, "scaduti": 1,
    }
    interazione = fake_interaction(guild=scenario.server, user=fake_member(1))
    await scenario.cog.stats_cmd.callback(scenario.cog, interazione, 7)
    testo = interazione.response.send_message.call_args.args[0]
    for parola in ("Ingressi", "uscite", "Captcha inviati", "falliti", "completate", "scaduto"):
        assert parola in testo


async def test_il_captcha_mostrato_viene_contato(scenario):
    await scenario.configura(captcha=True)
    scenario.utente.roles = []
    clic = scenario.clic()
    await modulo.avvia_verifica(clic)
    assert (await verify_repo.statistiche(GUILD_ID, 1))["captcha_inviati"] == 1


# ------------------------------------------------------------ VER-031
async def test_tentativi_senza_utente_ne_csv_chiede_un_utente(scenario):
    await scenario.configura(captcha=False)
    interazione = fake_interaction(guild=scenario.server, user=fake_member(1))
    await scenario.cog.attempts_cmd.callback(scenario.cog, interazione, None, False)
    assert "utente" in interazione.response.send_message.call_args.args[0].lower()


async def test_csv_di_un_utente_ha_intestazione_e_righe(scenario):
    await scenario.configura(captcha=False)
    await verify_repo.log_attempt(GUILD_ID, UTENTE_ID, True, "ok")
    await verify_repo.log_attempt(GUILD_ID, 8, False, "no")
    interazione = fake_interaction(guild=scenario.server, user=fake_member(1))
    utente = fake_member(UTENTE_ID)
    await scenario.cog.attempts_cmd.callback(scenario.cog, interazione, utente, True)
    file = (interazione.followup.send.call_args or interazione.response.send_message.call_args).kwargs["file"]
    righe = list(csv.reader(io.StringIO(file.fp.read().decode("utf-8"))))
    assert righe[0] == ["utente", "esito", "motivo", "data"]
    assert [r[0] for r in righe[1:]] == [str(UTENTE_ID)]


async def test_csv_di_tutto_il_server_una_volta_all_ora_e_senza_formule(scenario):
    await scenario.configura(captcha=False)
    await verify_repo.log_attempt(GUILD_ID, 9, False, "=HYPERLINK(\"http://x\")")
    interazione = fake_interaction(guild=scenario.server, user=fake_member(1))
    await scenario.cog.attempts_cmd.callback(scenario.cog, interazione, None, True)
    file = (interazione.followup.send.call_args or interazione.response.send_message.call_args).kwargs["file"]
    contenuto = file.fp.read().decode("utf-8")
    assert "'=HYPERLINK" in contenuto and ",=HYPERLINK" not in contenuto
    seconda = fake_interaction(guild=scenario.server, user=fake_member(1))
    await scenario.cog.attempts_cmd.callback(scenario.cog, seconda, None, True)
    testo = (seconda.followup.send.call_args or seconda.response.send_message.call_args).args[0]
    assert "ora" in testo.lower()
    assert "file" not in (seconda.followup.send.call_args or seconda.response.send_message.call_args).kwargs


# ------------------------------------------------------------ revisione r10
async def test_modalita_cieca_non_vale_durante_un_raid(scenario):
    # Il ruolo di verifica può aprire canali che la quarantena chiude: durante
    # un raid nessuno lo riceve senza passare la verifica.
    await scenario.configura(captcha=True)
    await _tempi(scenario, sospendi_ore=2)
    security_raid_state.segna_raid(GUILD_ID)
    scenario.utente.guild = scenario.server
    scenario.utente.roles = []
    await scenario.cog.on_member_join(scenario.utente)
    scenario.utente.add_roles.assert_not_awaited()


async def test_solo_sospetti_non_salta_l_eta_minima(scenario, clean_db):
    # Account di 10 giorni con avatar: non «sospetto», ma sotto i 30 giorni richiesti.
    from unittest.mock import MagicMock

    await _setup_con_eta(scenario, 30)
    await _tempi(scenario, solo_sospetti=True)
    scenario.utente.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    scenario.utente.avatar = MagicMock()
    scenario.utente.guild = scenario.server
    scenario.utente.roles = []
    await scenario.cog.on_member_join(scenario.utente)
    scenario.utente.add_roles.assert_not_awaited()
    assert (modulo.VERIFY_ETA, UTENTE_ID) in await _lavori(clean_db)


async def test_in_attesa_dell_eta_il_clic_non_fa_scattare_l_azione_di_chi_non_passa(scenario):
    # VER-019 «attendi»: chi preme il bottone troppo presto non viene bannato.
    await _setup_con_eta(scenario, 10)
    await _tempi(scenario, azione_fallita=_scelta("ban"))
    scenario.utente.created_at = datetime.now(timezone.utc) - timedelta(days=4)
    scenario.utente.roles = []
    esito = await scenario.cog.run_checks_and_finalize(scenario.server, scenario.utente, captcha_ok=True)
    assert not esito.success
    scenario.server.ban.assert_not_awaited()
    scenario.utente.kick.assert_not_awaited()
