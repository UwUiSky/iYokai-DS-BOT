"""
tests/test_automod_contatori.py
===============================
Contatori delle regole (X violazioni in Y minuti, scadenza, azzera), riepilogo e comando azzera.
Funzioni coperte: SPEC §6 (AMD-058, 059, 060, 061, 063, 064, 066)
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from core import automod_contatori as C
from core.automod_regole_logic import Condizioni, Contatore, Regola, Soglia, azione_da_json, azioni_dai_nomi_vecchi
from core.repositories.automod_advanced_repo import automod_advanced_repo
from tests.test_automod_regole_filtri import GUILD_ID, _caps_attivo, _msg, cog  # noqa: F401  (fixture)
from core import automod_regole_service as servizio

ADESSO = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def _soglia(n, minuti, secondi=600):
    return Soglia(n, minuti, (azione_da_json({"t": "timeout", "secondi": secondi}),))


def test_la_scadenza_in_giorni_accorcia_la_finestra():
    c = Contatore("link", scadenza_giorni=1, soglie=(_soglia(3, 60 * 24 * 7),))
    assert C.inizio_finestra(c, c.soglie[0], ADESSO) == ADESSO - timedelta(days=1)
    c2 = Contatore("link", scadenza_giorni=None, soglie=(_soglia(3, 10),))
    assert C.inizio_finestra(c2, c2.soglie[0], ADESSO) == ADESSO - timedelta(minutes=10)


async def _riga(clean_db, user, contatore, minuti_fa, violazione="anti_link"):
    await clean_db.execute(
        "INSERT INTO automod_action_log (guild_id, user_id, channel_id, violation, contatore, created_at) "
        "VALUES ($1, $2, 1, $3, $4, now() - make_interval(mins => $5))", GUILD_ID, user, violazione, contatore, minuti_fa)


@pytest.fixture
def repo(clean_db, monkeypatch):
    monkeypatch.setattr(automod_advanced_repo, "_pool_provider", lambda: clean_db)
    return clean_db


async def test_soglia_scatta_solo_dentro_la_finestra_e_per_l_utente(repo):
    c = Contatore("link", soglie=(_soglia(3, 10),))
    now = datetime.now(timezone.utc)
    for minuti in (1, 2, 30):  # la terza è fuori dai 10 minuti
        await _riga(repo, 5, "link", minuti)
    await _riga(repo, 6, "link", 1)
    await _riga(repo, 5, "altro", 1)
    assert await C.soglia_scattata(GUILD_ID, 5, c, now) is None
    await _riga(repo, 5, "link", 3)
    assert await C.soglia_scattata(GUILD_ID, 5, c, now) == c.soglie[0]
    assert await C.soglia_scattata(GUILD_ID, 6, c, now) is None


async def test_si_sceglie_la_soglia_piu_alta_raggiunta(repo):
    c = Contatore("link", soglie=(_soglia(2, 10, 60), _soglia(4, 10, 3600)))
    for _ in range(4):
        await _riga(repo, 5, "link", 1)
    assert (await C.soglia_scattata(GUILD_ID, 5, c)).azioni[0].get("secondi") == 3600


async def test_consuma_azzera_il_contatore_ma_il_registro_resta(repo):
    c = Contatore("link", soglie=(_soglia(2, 10),))
    for _ in range(2):
        await _riga(repo, 5, "link", 1)
    assert await C.consuma(GUILD_ID, 5, c) == 2
    assert await C.soglia_scattata(GUILD_ID, 5, c) is None
    assert await repo.fetchval("SELECT count(*) FROM automod_action_log WHERE user_id = 5") == 2


async def test_azzera_a_lotti_con_filtri_giorni_e_utente(repo):
    for utente in (1, 2, 3):
        for minuti in (5, 60 * 24 * 3):
            await _riga(repo, utente, "link", minuti)
    dal = datetime.now(timezone.utc) - timedelta(days=1)
    assert await automod_advanced_repo.conta_da_azzerare(GUILD_ID, "link", dal, None) == 3
    assert await automod_advanced_repo.conta_da_azzerare(GUILD_ID, "link", None, 2) == 2
    assert await automod_advanced_repo.azzera_a_lotti(GUILD_ID, "link", dal, None, lotto=2) == 3  # due lotti
    assert await automod_advanced_repo.conta_da_azzerare(GUILD_ID, "link", None, None) == 3  # restano i vecchi
    assert await automod_advanced_repo.azzera_a_lotti(GUILD_ID, "link", None, 2) == 1
    assert await repo.fetchval("SELECT count(*) FROM automod_action_log") == 6


async def test_riepilogo_per_tipo_e_ultime_a_pagine(repo):
    for utente in (1, 2):
        await _riga(repo, utente, None, 5, "anti_link")
    await _riga(repo, 1, None, 5, "anti_caps")
    await _riga(repo, 1, None, 60 * 24 * 30, "anti_zalgo")  # fuori dai 7 giorni
    righe, gruppi = await automod_advanced_repo.riepilogo_violazioni(
        GUILD_ID, datetime.now(timezone.utc) - timedelta(days=7), 10, 0)
    assert [(r["violation"], r["totale"], r["utenti"]) for r in righe] == [("anti_link", 2, 2), ("anti_caps", 1, 1)]
    assert gruppi == 2
    ultime, totale = await automod_advanced_repo.recenti_pagina(GUILD_ID, 2, 0)
    assert len(ultime) == 2 and totale == 4
    ultime2, _ = await automod_advanced_repo.recenti_pagina(GUILD_ID, 2, 2)
    assert len(ultime2) == 2


async def test_regola_con_contatore_dopo_due_violazioni_scatta_il_timeout(cog, clean_db, monkeypatch):
    import core.automod_azioni as azioni

    await _caps_attivo(cog)
    isola = AsyncMock()
    monkeypatch.setattr(azioni.bot_roles, "isola", isola)
    contatore = Contatore("urla", soglie=(_soglia(2, 10, 900),))
    await servizio.salva(GUILD_ID, Regola(chiave="anti_caps", tipo="filtro", nome="anti_caps", contatore=contatore,
                                          azioni=azioni_dai_nomi_vecchi(("delete",), 600)), 1)
    primo, secondo, terzo = _msg(), _msg(), _msg()
    await cog.on_message(primo)
    isola.assert_not_awaited()
    await cog.on_message(secondo)
    isola.assert_awaited_once()
    assert isola.await_args.args[1] == timedelta(seconds=900)
    await cog.on_message(terzo)
    isola.assert_awaited_once()  # il contatore è ripartito: una sola violazione dopo il timeout
    # il registro ha tre righe; le prime due sono state consumate dalla soglia, la terza ricomincia il conteggio
    assert await clean_db.fetchval("SELECT count(*) FROM automod_action_log") == 3
    assert await clean_db.fetchval("SELECT count(*) FROM automod_action_log WHERE contatore = 'urla'") == 1


async def test_comando_riepilogo_e_azzera(repo, monkeypatch):
    import cogs.automod.regole as modulo
    import cogs.moderation._shared as condiviso
    from core.database import Database
    from unittest.mock import create_autospec
    from tests.support.discord_fakes import fake_guild, fake_interaction
    from discord import app_commands

    db_finto = create_autospec(Database, instance=True)
    db_finto.is_module_active_for_guild.return_value = True
    db_finto.get_guild_setting.return_value = None
    monkeypatch.setattr(condiviso, "db", db_finto)
    monkeypatch.setattr(servizio.automod_regole_repo, "_pool_provider", lambda: repo)
    servizio.svuota_cache()
    cog = modulo.RegoleCog(bot=None)
    for utente in (1, 2):
        await _riga(repo, utente, "urla", 5, "anti_caps")

    inter = fake_interaction(guild=fake_guild(guild_id=GUILD_ID))
    scelta = app_commands.Choice(name="violazioni", value="violazioni")
    await cog.riepilogo.callback(cog, inter, scelta, 7, 1)
    embed = inter.followup.send.await_args.kwargs["embed"]
    assert "anti_caps" in embed.description and "2" in embed.description

    inter = fake_interaction(guild=fake_guild(guild_id=GUILD_ID))
    await cog.azzera.callback(cog, inter, "urla", None, None)
    vista = inter.followup.send.await_args.kwargs["view"]
    assert await repo.fetchval("SELECT count(*) FROM automod_action_log WHERE contatore = 'urla'") == 2  # prima serve il sì
    assert vista.interaction_check(fake_interaction(user=inter.user)) is not None
    conferma = fake_interaction(guild=fake_guild(guild_id=GUILD_ID), user=inter.user)
    conferma.edit_original_response = AsyncMock()
    await vista.conferma.callback(conferma)
    assert await repo.fetchval("SELECT count(*) FROM automod_action_log WHERE contatore = 'urla'") == 0
    assert await repo.fetchval("SELECT count(*) FROM automod_action_log") == 2

    inter = fake_interaction(guild=fake_guild(guild_id=GUILD_ID))
    await cog.azzera.callback(cog, inter, "urla", None, None)
    assert "view" not in inter.followup.send.await_args.kwargs  # niente da azzerare: nessun bottone


async def test_due_messaggi_insieme_fanno_scattare_la_soglia_una_volta_sola(cog, clean_db, monkeypatch):
    import asyncio

    import core.automod_azioni as azioni

    await _caps_attivo(cog)
    isola = AsyncMock()
    monkeypatch.setattr(azioni.bot_roles, "isola", isola)
    await servizio.salva(GUILD_ID, Regola(chiave="anti_caps", tipo="filtro", nome="anti_caps",
                                          contatore=Contatore("urla", soglie=(_soglia(2, 10, 900),)),
                                          azioni=azioni_dai_nomi_vecchi(("delete",), 600)), 1)
    if hasattr(clean_db, "acquire"):
        from tests.support.concorrenza import apri_connessioni
        await apri_connessioni(clean_db)
    await asyncio.gather(*(cog.on_message(_msg()) for _ in range(3)))
    isola.assert_awaited_once()  # una sola soglia: il contatore si consuma una volta
