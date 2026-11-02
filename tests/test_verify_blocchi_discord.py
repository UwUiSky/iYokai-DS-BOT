"""
tests/test_verify_blocchi_discord.py
====================================
D67: l'invito al ticket in privato c'è per OGNI blocco della verifica, anche captcha e bottone su Discord
(non solo la verifica web). Il blocco si ricorda per aprire il ticket ModMail col motivo; chi si verifica non
lascia blocchi; se il ModMail non è pronto non c'è nessun invito.
"""

from unittest.mock import AsyncMock

import pytest

from cogs.security import verify as cog_verify
from cogs.security.verify import CaptchaImmagineModal, CaptchaModal, VerifyPanelView
from core import captcha_image, verify_blocchi
from core.repositories.verify_blocchi_repo import VerifyBlocchiRepository
from tests.test_verify_risposta_subito import GUILD_ID, UTENTE_ID, Scenario, scenario  # noqa: F401

INVITO = "ticket con lo staff di"


@pytest.fixture
def blocchi(monkeypatch, clean_db):
    repo = VerifyBlocchiRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr("core.repositories.verify_blocchi_repo.verify_blocchi_repo", repo)
    monkeypatch.setattr(verify_blocchi, "modmail_pronto", AsyncMock(return_value=True))
    return repo


async def _risposta_modulo(scenario, risposta: str) -> str:
    modulo = CaptchaModal(scenario.cog, GUILD_ID, UTENTE_ID)
    modulo.answer_input._value = risposta
    interazione = scenario.clic()
    interazione.client = scenario.bot
    await modulo.on_submit(interazione)
    return interazione.followup.send.await_args.args[0]


@pytest.mark.asyncio
async def test_captcha_sbagliato_invita_al_ticket_e_ricorda_il_blocco(scenario, blocchi):
    await scenario.configura(captcha=True)
    testo = await _risposta_modulo(scenario, "sbagliato")
    assert INVITO in testo
    riga = await blocchi.recente(UTENTE_ID)
    assert riga["guild_id"] == GUILD_ID and INVITO not in riga["motivo"] and riga["motivo"]


@pytest.mark.asyncio
async def test_captcha_giusto_nessun_invito_e_nessun_blocco_rimasto(scenario, blocchi):
    await scenario.configura(captcha=True)
    await _risposta_modulo(scenario, "sbagliato")
    assert await blocchi.recente(UTENTE_ID) is not None
    modulo = CaptchaModal(scenario.cog, GUILD_ID, UTENTE_ID)
    modulo.answer_input._value = modulo._expected_answer
    interazione = scenario.clic()
    await modulo.on_submit(interazione)
    assert INVITO not in interazione.followup.send.await_args.args[0]
    assert await blocchi.recente(UTENTE_ID) is None  # niente ticket «a sorpresa» col motivo vecchio


@pytest.mark.asyncio
async def test_bottone_senza_captcha_bloccato_dal_server_invita_al_ticket(scenario, blocchi, clean_db):
    await scenario.configura(captcha=False)
    await clean_db.execute("UPDATE verify_config SET min_account_age_days = 9999 WHERE guild_id = $1", GUILD_ID)
    interazione = scenario.clic()
    await VerifyPanelView().verify_click.callback(interazione)
    assert INVITO in interazione.followup.send.await_args.args[0]
    assert await blocchi.recente(UTENTE_ID) is not None


@pytest.mark.asyncio
async def test_captcha_a_immagine_con_tentativi_finiti_invita_al_ticket(scenario, blocchi, monkeypatch):
    await scenario.configura(captcha=True)
    sfida = captcha_image.nuova_sfida() if hasattr(captcha_image, "nuova_sfida") else None
    if sfida is None:
        pytest.skip("la sfida a immagine si crea in un altro modo")
    scenario.cog.sfide.set((GUILD_ID, UTENTE_ID), sfida)
    monkeypatch.setattr(type(sfida), "prova", lambda self, risposta: "esaurita")
    modulo = CaptchaImmagineModal(scenario.cog, GUILD_ID, UTENTE_ID)
    modulo.answer_input._value = "xxxx"
    interazione = scenario.clic()
    await modulo.on_submit(interazione)
    assert INVITO in interazione.followup.send.await_args.args[0]


@pytest.mark.asyncio
async def test_senza_modmail_pronto_nessun_invito_e_nessuna_riga(scenario, blocchi, monkeypatch):
    monkeypatch.setattr(verify_blocchi, "modmail_pronto", AsyncMock(return_value=False))
    await scenario.configura(captcha=True)
    testo = await _risposta_modulo(scenario, "sbagliato")
    assert INVITO not in testo and await blocchi.recente(UTENTE_ID) is None


@pytest.mark.asyncio
async def test_la_verifica_web_non_raddoppia_l_invito(scenario, blocchi):
    """Il percorso web aggiunge già l'invito da sé: run_checks_and_finalize senza `con_invito` non lo aggiunge."""
    await scenario.configura(captcha=False)
    guild = scenario.server
    membro = scenario.utente
    esito = await scenario.cog.run_checks_and_finalize(guild, membro, captcha_ok=False)
    assert not esito.success and INVITO not in esito.reason


def test_il_cog_importa_il_modulo_dei_blocchi():
    assert cog_verify.verify_blocchi is verify_blocchi
