"""
tests/test_verify_117.py
========================
Difetti di verify trovati leggendo:
- whitelist/blacklist chiedevano un `Member`: non si poteva mettere in
  blacklist chi era appena uscito (e poi tornava);
- clic sul pannello fuori da un server, o senza il cog caricato, senza
  risposta ("interazione non riuscita");
- chi ha gia' il ruolo rifaceva tutto il giro e riempiva il log;
- il pannello si pubblicava anche col modulo spento;
- reazione del pannello rifiutata da Discord: errore non gestito.
"""

import typing
from unittest.mock import AsyncMock, MagicMock

import discord

from cogs.security.verify import MODULE_VERIFY, VerifyCog, VerifyPanelView
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.test_verify_risposta_subito import Scenario, scenario  # noqa: F401


def test_liste_accettano_un_utente_anche_fuori_dal_server():
    for nome in ("whitelist_add", "whitelist_remove", "blacklist_add", "blacklist_remove"):
        comando = getattr(VerifyCog, nome)
        assert typing.get_type_hints(comando.callback)["member"] is discord.User, nome


async def test_clic_senza_server_riceve_una_risposta():
    interazione = fake_interaction()
    interazione.guild = None
    await VerifyPanelView().verify_click.callback(interazione)
    interazione.response.send_message.assert_awaited_once()


async def test_clic_senza_cog_riceve_una_risposta(scenario):
    scenario.bot.get_cog.return_value = None
    interazione = scenario.clic()
    await VerifyPanelView().verify_click.callback(interazione)
    interazione.response.send_message.assert_awaited_once()


async def test_chi_ha_gia_il_ruolo_non_rifa_il_giro(scenario, clean_db):
    await scenario.configura(captcha=False)
    scenario.utente.roles = [scenario.ruolo]
    esito = await scenario.cog.run_checks_and_finalize(scenario.server, scenario.utente, True)
    assert esito.success and "already" in esito.reason
    scenario.utente.add_roles.assert_not_called()
    assert await clean_db.fetchval("SELECT count(*) FROM verify_attempts") == 0


async def test_pannello_con_modulo_spento_viene_rifiutato(scenario, monkeypatch):
    import core.database as database_module
    await database_module.db.set_module_active_for_guild(100, MODULE_VERIFY, False)
    database_module.db._modules_cache.clear()
    interazione = fake_interaction(guild=scenario.server)
    await scenario.cog.panel_cmd.callback(scenario.cog, interazione)
    assert "non è attivo" in interazione.response.send_message.call_args.args[0]


async def test_reazione_rifiutata_non_rompe_il_pannello(scenario):
    from discord import app_commands
    admin = fake_member(user_id=1, name="owner")
    setup = fake_interaction(guild=scenario.server, user=admin)
    await scenario.cog.setup_cmd.callback(
        scenario.cog, setup, app_commands.Choice(name="Reaction", value="reaction"),
        scenario.ruolo, 0, 0, False, None,
    )
    interazione = fake_interaction(guild=scenario.server, user=admin)
    messaggio = MagicMock()
    messaggio.channel.id, messaggio.id = 5, 6
    messaggio.add_reaction = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=403), "no"))
    interazione.original_response = AsyncMock(return_value=messaggio)
    await scenario.cog.panel_cmd.callback(scenario.cog, interazione)
    interazione.followup.send.assert_awaited_once()
    assert "reazione" in interazione.followup.send.call_args.args[0]
