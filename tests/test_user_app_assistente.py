"""
tests/test_user_app_assistente.py
=================================
iYokai App: `/trova` (scoperta delle funzioni, senza AI) e `/assistente` (AI personale con ripiego). Discord finto.
"""

import pytest

from cogs.user_app.assistente_app import AssistenteAppCog
from core.ai_servizio import imposta_servizio_ai
from core.repositories.ai_repo import ai_repo
from core.user_app_assistente_logic import elenco_per_ai, trova
from core.user_app_bot import UserAppBot
from tests.support.ai_finto import TrasportoFinto, fornitore, servizio_finto
from tests.support.discord_fakes import fake_interaction


@pytest.fixture
async def app():
    bot = UserAppBot()
    await bot.carica_cog()
    yield bot
    await bot.close()


async def _cog(app):
    cog = AssistenteAppCog(app)

    async def senza_ids():
        return {}

    cog._ids = senza_ids
    return cog


async def test_trova_cita_comandi_e_menu_dell_app(app):
    cog = await _cog(app)
    i = fake_interaction()
    await cog.trova_funzione.callback(cog, i, "promemoria")
    assert "/promemoria" in i.followup.send.call_args.args[0]
    i2 = fake_interaction()
    await cog.trova_funzione.callback(cog, i2, "trascrivi")
    assert "Trascrivi vocale" in i2.followup.send.call_args.args[0]
    i3 = fake_interaction()
    await cog.trova_funzione.callback(cog, i3, "zzzqqq")
    assert "Non ho trovato" in i3.followup.send.call_args.args[0]


async def test_assistente_senza_ai_ricade_su_trova(app, clean_db, monkeypatch):
    monkeypatch.setattr(ai_repo, "_pool_provider", lambda: clean_db)
    servizio, _ = servizio_finto(ai_repo, fornitori=[])
    imposta_servizio_ai(servizio)
    try:
        cog = await _cog(app)
        i = fake_interaction()
        await cog.assistente.callback(cog, i, "come salvo un promemoria")
        assert "/promemoria" in i.followup.send.call_args.args[0]
    finally:
        imposta_servizio_ai(None)


async def test_assistente_con_ai_conosce_l_elenco_e_tratta_la_domanda_come_dato(app, clean_db, monkeypatch):
    monkeypatch.setattr(ai_repo, "_pool_provider", lambda: clean_db)
    servizio, trasporto = servizio_finto(ai_repo, trasporto=TrasportoFinto(risposte={"alfa": "Usa /note aggiungi."}))
    imposta_servizio_ai(servizio)
    try:
        cog = await _cog(app)
        i = fake_interaction()
        await cog.assistente.callback(cog, i, "dove scrivo una nota")
        assert i.followup.send.call_args.args[0] == "Usa /note aggiungi."
        messaggi = trasporto.chiamate[0][1]
        assert "/note aggiungi" in messaggi[0]["content"] and "<<<" in messaggi[-1]["content"]
    finally:
        imposta_servizio_ai(None)


def test_elenco_per_ai_ha_un_tetto():
    from core.command_search_logic import ComandoInfo

    tanti = [ComandoInfo(f"c{i}", "x" * 50, f"c{i}", ()) for i in range(500)]
    assert len(elenco_per_ai(tanti)) <= 3500
    assert trova("qualcosa", [], [], {}) == ""
