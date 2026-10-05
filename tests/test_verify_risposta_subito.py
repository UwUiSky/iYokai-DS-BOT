"""
tests/test_verify_risposta_subito.py
====================================
Verify (LIM-9, LC-3): Discord concede 3 secondi per la prima risposta a
un clic. Il bottone faceva quattro letture, dava il ruolo e scriveva il
log PRIMA di rispondere: in un'ondata di ingressi l'utente vedeva
"interazione non riuscita" anche se il ruolo arrivava.

Ora la prima chiamata è `defer` (o il modulo del captcha, che deve
essere per forza la prima risposta) e il lavoro lento viene dopo.

Il Verify è configurato con `/verify setup` (database vero).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, create_autospec

import discord
import pytest
from discord import app_commands
from discord.ext import commands

import core.ui_base as modulo_ui_base
from cogs.security.verify import MODULE_VERIFY, CaptchaModal, VerifyCog, VerifyPanelView
from core.repositories.verify_repo import verify_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role

GUILD_ID = 100
UTENTE_ID = 42


class Scenario:
    def __init__(self) -> None:
        self.ordine: list[str] = []

        bot_member = fake_member(user_id=999, name="Yokai Bot", bot=True)
        bot_member.top_role = fake_role(role_id=900, name="Yokai Bot", position=50)
        self.server = fake_guild(GUILD_ID, owner_id=1, me=bot_member)
        self.ruolo = fake_role(role_id=500, name="Verificato", position=1)
        self.server.get_role.side_effect = lambda role_id: (
            self.ruolo if role_id == self.ruolo.id else None
        )

        self.bot = create_autospec(commands.Bot, instance=True)
        self.bot.guilds = [self.server]
        self.bot.get_guild.side_effect = lambda guild_id: (
            self.server if guild_id == GUILD_ID else None
        )
        self.cog = VerifyCog(self.bot)
        self.bot.get_cog.return_value = self.cog

        self.utente = fake_member(user_id=UTENTE_ID, name="nuovo")
        self.utente.created_at = datetime.now(timezone.utc) - timedelta(days=400)
        self.utente.add_roles.side_effect = self._annota("ruolo")
        self.server.get_member.side_effect = lambda user_id: (
            self.utente if user_id == UTENTE_ID else None
        )

    def _annota(self, nome: str):
        async def _chiamata(*_args, **_kwargs):
            self.ordine.append(nome)

        return _chiamata

    async def configura(self, *, captcha: bool) -> None:
        admin = fake_member(user_id=1, name="owner")
        interazione = fake_interaction(guild=self.server, user=admin)
        await self.cog.setup_cmd.callback(
            self.cog,
            interazione,
            app_commands.Choice(name="Button", value="button"),
            self.ruolo,
            0,
            0,
            captcha,
            None,
        )

    def clic(self) -> MagicMock:
        interazione = fake_interaction(guild=self.server, user=self.utente)
        interazione.client = self.bot
        interazione.response.defer.side_effect = self._annota("defer")
        interazione.response.send_modal.side_effect = self._annota("modulo")
        interazione.response.send_message.side_effect = self._annota("send_message")
        interazione.followup.send.side_effect = self._annota("followup")
        return interazione


@pytest.fixture
async def scenario(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    monkeypatch.setattr(verify_repo, "_pool_provider", lambda: clean_db)

    async def mai_bloccato(*_args):
        return False

    monkeypatch.setattr(modulo_ui_base.blacklist_repo, "is_user_blacklisted", mai_bloccato)
    monkeypatch.setattr(modulo_ui_base.blacklist_repo, "is_guild_blacklisted", mai_bloccato)

    await database_module.db.set_module_active_for_guild(GUILD_ID, MODULE_VERIFY, True)
    yield Scenario()
    database_module.db._modules_cache.clear()


async def _tentativi(pool) -> int:
    return await pool.fetchval("SELECT count(*) FROM verify_attempts WHERE guild_id = $1", GUILD_ID)


async def test_bottone_senza_captcha_chiama_defer_per_primo(scenario, clean_db):
    await scenario.configura(captcha=False)
    interazione = scenario.clic()
    vista = VerifyPanelView()

    await vista.verify_click.callback(interazione)

    assert scenario.ordine == ["defer", "ruolo", "followup"]
    assert interazione.response.defer.call_args.kwargs == {"ephemeral": True}
    assert interazione.followup.send.call_args.kwargs["ephemeral"] is True
    assert await _tentativi(clean_db) == 1


async def test_bottone_con_captcha_il_modulo_e_la_prima_risposta(scenario, clean_db):
    await scenario.configura(captcha=True)
    interazione = scenario.clic()

    await VerifyPanelView().verify_click.callback(interazione)

    assert scenario.ordine == ["modulo"]
    assert isinstance(interazione.response.send_modal.call_args.args[0], CaptchaModal)
    # Niente lavoro lento prima del modulo: nessun tentativo scritto, nessun ruolo.
    assert await _tentativi(clean_db) == 0


async def test_modulo_del_captcha_chiama_defer_prima_di_dare_il_ruolo(scenario, clean_db):
    await scenario.configura(captcha=True)
    modulo_captcha = CaptchaModal(scenario.cog, GUILD_ID, UTENTE_ID)
    modulo_captcha.answer_input._value = modulo_captcha._expected_answer
    interazione = scenario.clic()

    await modulo_captcha.on_submit(interazione)

    assert scenario.ordine == ["defer", "ruolo", "followup"]
    assert interazione.response.defer.call_args.kwargs == {"ephemeral": True}
    assert await _tentativi(clean_db) == 1


async def test_captcha_sbagliato_risponde_senza_dare_il_ruolo(scenario):
    await scenario.configura(captcha=True)
    modulo_captcha = CaptchaModal(scenario.cog, GUILD_ID, UTENTE_ID)
    modulo_captcha.answer_input._value = "999"
    interazione = scenario.clic()

    await modulo_captcha.on_submit(interazione)

    assert scenario.ordine == ["defer", "followup"]


async def test_modulo_spento_risponde_subito_senza_defer(scenario):
    import core.database as database_module

    await scenario.configura(captcha=False)
    await database_module.db.set_module_active_for_guild(GUILD_ID, MODULE_VERIFY, False)
    interazione = scenario.clic()

    await VerifyPanelView().verify_click.callback(interazione)

    assert scenario.ordine == ["send_message"]


async def test_ruolo_che_discord_rifiuta_non_lascia_l_utente_senza_risposta(scenario):
    await scenario.configura(captcha=False)
    risposta = MagicMock()
    risposta.status = 500
    risposta.reason = "Internal Server Error"
    scenario.utente.add_roles.side_effect = discord.HTTPException(risposta, "errore finto")
    interazione = scenario.clic()

    await VerifyPanelView().verify_click.callback(interazione)

    assert scenario.ordine == ["defer", "followup"]
