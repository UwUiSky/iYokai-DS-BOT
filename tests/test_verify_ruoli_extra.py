"""
tests/test_verify_ruoli_extra.py
================================
Verify: ruolo «non verificato» all'ingresso, ruoli extra alla verifica,
verifica a mano, ricerca tentativi e statistiche (VER-014, 015, 016, 030, 031).
"""

from unittest.mock import AsyncMock


from cogs.security.verify import (
    SETTING_RUOLI_EXTRA,
    SETTING_RUOLO_NON_VERIFICATO,
)
from core.database import db
from core.repositories.verify_repo import verify_repo
from tests.support.discord_fakes import fake_interaction, fake_member, fake_role
from tests.test_verify_risposta_subito import GUILD_ID, UTENTE_ID, Scenario, scenario  # noqa: F401


def _ruoli(scena):
    scena.extra = fake_role(role_id=501, name="Extra", position=1)
    scena.non_ver = fake_role(role_id=502, name="Non verificato", position=1)
    mappa = {r.id: r for r in (scena.ruolo, scena.extra, scena.non_ver)}
    scena.server.get_role.side_effect = lambda i: mappa.get(i)


async def test_all_ingresso_arriva_il_ruolo_non_verificato(scenario):
    _ruoli(scenario)
    await db.set_guild_setting(GUILD_ID, SETTING_RUOLO_NON_VERIFICATO, scenario.non_ver.id)
    nuovo = fake_member(UTENTE_ID)
    nuovo.guild = scenario.server
    nuovo.add_roles = AsyncMock()

    await scenario.cog.on_member_join(nuovo)

    assert nuovo.add_roles.call_args.args[0].id == 502


async def test_senza_impostazione_nessun_ruolo_all_ingresso(scenario):
    _ruoli(scenario)
    nuovo = fake_member(UTENTE_ID)
    nuovo.guild = scenario.server
    nuovo.add_roles = AsyncMock()
    await scenario.cog.on_member_join(nuovo)
    nuovo.add_roles.assert_not_awaited()


async def test_verifica_dona_ruoli_extra_e_toglie_non_verificato(scenario):
    _ruoli(scenario)
    await scenario.configura(captcha=False)
    await db.set_guild_setting(GUILD_ID, SETTING_RUOLI_EXTRA, [501])
    await db.set_guild_setting(GUILD_ID, SETTING_RUOLO_NON_VERIFICATO, 502)
    scenario.utente.roles = [scenario.non_ver]
    scenario.utente.remove_roles = AsyncMock()
    scenario.utente.add_roles = AsyncMock()

    esito = await scenario.cog.run_checks_and_finalize(scenario.server, scenario.utente, True)

    assert esito.success
    assert [r.id for r in scenario.utente.add_roles.call_args.args] == [500, 501]
    assert scenario.utente.remove_roles.call_args.args[0].id == 502


async def test_verifica_a_mano_senza_controlli_e_registrata(scenario, clean_db):
    _ruoli(scenario)
    await scenario.configura(captcha=True)
    scenario.utente.add_roles = AsyncMock()
    staff = fake_interaction(guild=scenario.server, user=fake_member(1))

    await scenario.cog.manual_cmd.callback(scenario.cog, staff, scenario.utente)

    scenario.utente.add_roles.assert_awaited()
    tentativi = await verify_repo.get_recent_attempts(GUILD_ID, UTENTE_ID)
    assert tentativi[0][0] is True and "a mano" in tentativi[0][1]


async def test_tentativi_e_statistiche(scenario):
    await verify_repo.log_attempt(GUILD_ID, UTENTE_ID, False, "Captcha verification failed.")
    await verify_repo.log_attempt(GUILD_ID, UTENTE_ID, True, "All checks passed.")
    await verify_repo.log_attempt(GUILD_ID, 77, True, "All checks passed.")

    assert await verify_repo.attempt_stats(GUILD_ID, 7) == (2, 1, 2)
    assert await verify_repo.attempt_stats(999, 7) == (0, 0, 0)

    staff = fake_interaction(guild=scenario.server, user=fake_member(1))
    await scenario.cog.attempts_cmd.callback(scenario.cog, staff, scenario.utente)
    assert "Captcha" in staff.response.send_message.call_args.kwargs["embed"].description
    await scenario.cog.stats_cmd.callback(scenario.cog, staff, 7)
    assert "2" in staff.response.send_message.call_args.args[0]


async def test_non_verificato_uguale_al_ruolo_di_verifica_non_viene_tolto(scenario):
    _ruoli(scenario)
    await scenario.configura(captcha=False)
    await db.set_guild_setting(GUILD_ID, SETTING_RUOLO_NON_VERIFICATO, scenario.ruolo.id)
    scenario.utente.roles = [scenario.ruolo]
    scenario.utente.remove_roles = AsyncMock()
    scenario.utente.add_roles = AsyncMock()

    assert await scenario.cog.dai_ruoli_di_verifica(scenario.server, scenario.utente, scenario.ruolo.id)

    scenario.utente.remove_roles.assert_not_awaited()


async def test_ruolo_di_verifica_sopra_il_bot_non_completa_e_tiene_il_non_verificato(scenario):
    _ruoli(scenario)
    await scenario.configura(captcha=False)
    scenario.ruolo.position = 99  # sopra il bot (50)
    await db.set_guild_setting(GUILD_ID, SETTING_RUOLO_NON_VERIFICATO, scenario.non_ver.id)
    scenario.utente.roles = [scenario.non_ver]
    scenario.utente.remove_roles = AsyncMock()
    scenario.utente.add_roles = AsyncMock()

    assert not await scenario.cog.dai_ruoli_di_verifica(scenario.server, scenario.utente, scenario.ruolo.id)

    scenario.utente.add_roles.assert_not_awaited()
    scenario.utente.remove_roles.assert_not_awaited()
    esito = await scenario.cog.run_checks_and_finalize(scenario.server, scenario.utente, True)
    assert "couldn't give you the role" in esito.reason


async def test_non_verificato_sopra_il_bot_non_si_prova_a_togliere(scenario):
    _ruoli(scenario)
    await scenario.configura(captcha=False)
    scenario.non_ver.position = 99
    await db.set_guild_setting(GUILD_ID, SETTING_RUOLO_NON_VERIFICATO, scenario.non_ver.id)
    scenario.utente.roles = [scenario.non_ver]
    scenario.utente.remove_roles = AsyncMock()
    scenario.utente.add_roles = AsyncMock()

    assert await scenario.cog.dai_ruoli_di_verifica(scenario.server, scenario.utente, scenario.ruolo.id)

    scenario.utente.remove_roles.assert_not_awaited()


async def test_opzioni_salva_non_verificato_e_massimo_tre_extra(scenario):
    _ruoli(scenario)
    extra = [fake_role(role_id=600 + i, name=f"E{i}", position=1) for i in range(3)]
    scenario.server.get_role.side_effect = None
    admin = fake_member(1)
    inter = fake_interaction(guild=scenario.server, user=admin)
    admin.top_role = fake_role(role_id=7, position=40)

    await scenario.cog.options_cmd.callback(
        scenario.cog, inter, scenario.non_ver, extra[0], extra[1], extra[2], False
    )

    assert await db.get_guild_setting(GUILD_ID, SETTING_RUOLO_NON_VERIFICATO) == 502
    assert await db.get_guild_setting(GUILD_ID, SETTING_RUOLI_EXTRA) == [600, 601, 602]


async def test_opzioni_rifiuta_un_ruolo_non_assegnabile(scenario):
    _ruoli(scenario)
    alto = fake_role(role_id=700, name="Alto", position=99)  # sopra il bot
    admin = fake_member(1)
    admin.top_role = fake_role(role_id=7, position=120)
    inter = fake_interaction(guild=scenario.server, user=admin)

    await scenario.cog.options_cmd.callback(scenario.cog, inter, alto, None, None, None, False)

    assert await db.get_guild_setting(GUILD_ID, SETTING_RUOLO_NON_VERIFICATO) is None
    assert "sopra" in inter.response.send_message.call_args.args[0]


async def test_opzioni_azzera_toglie_le_impostazioni(scenario):
    await db.set_guild_setting(GUILD_ID, SETTING_RUOLO_NON_VERIFICATO, 502)
    await db.set_guild_setting(GUILD_ID, SETTING_RUOLI_EXTRA, [501])
    inter = fake_interaction(guild=scenario.server, user=fake_member(1))

    await scenario.cog.options_cmd.callback(scenario.cog, inter, None, None, None, None, True)

    assert await db.get_guild_setting(GUILD_ID, SETTING_RUOLO_NON_VERIFICATO) is None
    assert not await db.get_guild_setting(GUILD_ID, SETTING_RUOLI_EXTRA)


async def test_ingresso_di_un_bot_o_a_modulo_spento_non_da_il_ruolo(scenario):
    from cogs.security.verify import MODULE_VERIFY

    _ruoli(scenario)
    await db.set_guild_setting(GUILD_ID, SETTING_RUOLO_NON_VERIFICATO, scenario.non_ver.id)
    robot = fake_member(UTENTE_ID, bot=True)
    robot.guild = scenario.server
    robot.add_roles = AsyncMock()
    await scenario.cog.on_member_join(robot)
    robot.add_roles.assert_not_awaited()

    await db.set_module_active_for_guild(GUILD_ID, MODULE_VERIFY, False)
    persona = fake_member(UTENTE_ID)
    persona.guild = scenario.server
    persona.add_roles = AsyncMock()
    await scenario.cog.on_member_join(persona)
    persona.add_roles.assert_not_awaited()


async def test_extra_non_assegnabili_sono_saltati_ma_la_verifica_riesce(scenario):
    _ruoli(scenario)
    scenario.extra.position = 99  # sopra il bot: non assegnabile
    await db.set_guild_setting(GUILD_ID, SETTING_RUOLI_EXTRA, [501])
    scenario.utente.roles = []
    scenario.utente.add_roles = AsyncMock()

    assert await scenario.cog.dai_ruoli_di_verifica(scenario.server, scenario.utente, scenario.ruolo.id)

    assert [r.id for r in scenario.utente.add_roles.call_args.args] == [500]


async def test_verifica_a_mano_senza_configurazione_non_fa_niente(scenario):
    scenario.utente.add_roles = AsyncMock()
    inter = fake_interaction(guild=scenario.server, user=fake_member(1))

    await scenario.cog.manual_cmd.callback(scenario.cog, inter, scenario.utente)

    scenario.utente.add_roles.assert_not_awaited()
    assert "Configura" in inter.response.send_message.call_args.args[0]
