"""
tests/test_web_servizi.py
=========================
Catalogo #128 B2 (D69): meteo (MET Norway + Nominatim con cache), film e serie, Steam, prezzi, accorciatore.
Le chiamate esterne sono finte; si controllano gli indirizzi, le cache, i rifiuti e i limiti.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

import cogs.utility.web as cogweb
from core import web_servizi_logic as W
from core.repositories.web_repo import WebRepository
from tests.support.discord_fakes import fake_interaction
from tests.support.percorsi import comando_nel_gruppo


@pytest.fixture(autouse=True)
def _pulisci():
    W._cache.clear()
    W.INTERVALLO_NOMINATIM = 0
    yield


MET = json.dumps({"properties": {"timeseries": [
    {"time": "2026-11-09T10:00:00Z", "data": {"instant": {"details": {"air_temperature": 8.4, "wind_speed": 3.2, "relative_humidity": 80}},
                                              "next_1_hours": {"summary": {"symbol_code": "partlycloudy_day"}}}},
    *[{"time": f"2026-11-{10 + i}T12:00:00Z", "data": {"instant": {"details": {"air_temperature": 10 + i}},
                                                       "next_6_hours": {"summary": {"symbol_code": "rain"}}}} for i in range(5)],
]}})


def test_leggi_meteo_adesso_e_tre_giorni():
    m = W.leggi_meteo(MET)
    assert m["temp"] == 8.4 and len(m["giorni"]) == 3 and m["giorni"][0]["data"] == "2026-11-10"
    assert W.leggi_meteo("x") is None and W.leggi_meteo('{"properties":{"timeseries":[]}}') is None


def test_cielo_ordine_dei_pezzi():
    assert W.chiave_cielo("lightrainandthunder") == "meteo_cielo_temporale"
    assert W.chiave_cielo("partlycloudy_night") == "meteo_cielo_parziale"
    assert W.chiave_cielo("clearsky_day") == "meteo_cielo_sereno"


def test_url_meteo_ha_quattro_decimali():
    assert "lat=45.4642&lon=9.1900" in W.url_meteo(45.464211, 9.19)


@pytest.mark.asyncio
async def test_geocodifica_usa_cache_db_e_ricorda(monkeypatch):
    repo = MagicMock(luogo=AsyncMock(return_value=None), salva_luogo=AsyncMock())
    get = AsyncMock(return_value='[{"lat":"45.4","lon":"9.1","display_name":"Milano, Italia"}]')
    monkeypatch.setattr(W, "safe_get", get)
    assert await W.trova_luogo(repo, "  MILANO ") == (45.4, 9.1, "Milano, Italia")
    repo.luogo.assert_awaited_with("milano")
    repo.salva_luogo.assert_awaited_once()
    repo.luogo = AsyncMock(return_value=(1.0, 2.0, "x"))
    get.reset_mock()
    await W.trova_luogo(repo, "milano")
    get.assert_not_called()


@pytest.mark.asyncio
async def test_cache_dei_luoghi_nel_db_vero(clean_db):
    web_repo = WebRepository(pool_provider=lambda: clean_db)
    await web_repo.salva_luogo("roma", 41.9, 12.5, "Roma")
    assert await web_repo.luogo("roma") == (41.9, 12.5, "Roma")
    assert await web_repo.luogo("nessuna") is None
    await clean_db.execute("INSERT INTO web_impostazioni (guild_id, accorcia_attivo) VALUES (5, TRUE)")
    assert await web_repo.accorcia_attivo(5) and not await web_repo.accorcia_attivo(6)


@pytest.mark.asyncio
async def test_meteo_servizio_giu_non_entra_in_cache(monkeypatch):
    repo = MagicMock(luogo=AsyncMock(return_value=(1.0, 2.0, "X")))
    monkeypatch.setattr(W, "safe_get", AsyncMock(return_value=None))
    assert await W.meteo_di(repo, "x") is None and len(W._cache) == 0
    monkeypatch.setattr(W, "safe_get", AsyncMock(return_value=MET))
    nome, m = await W.meteo_di(repo, "x")
    assert nome == "X" and m["temp"] == 8.4
    monkeypatch.setattr(W, "safe_get", AsyncMock(side_effect=AssertionError))
    assert (await W.meteo_di(repo, "x"))[0] == "X"  # dalla cache


def test_serie_senza_tag_html():
    r = W.leggi_serie('{"name":"A","summary":"<p>Ciao <b>mondo</b> &amp; co</p>","rating":{"average":8.1},"premiered":"2020-01-01"}')
    assert r["testo"] == "Ciao mondo & co" and "2020" in r["dettagli"] and "8.1/10" in r["dettagli"]
    assert W.leggi_serie("{}") is None


def test_gioco_steam_prezzo_e_gratis():
    d = {"7": {"data": {"name": "G", "short_description": "d", "price_overview": {"final_formatted": "9,99€"}}}}
    assert W.leggi_gioco(json.dumps(d), 7)["prezzo"] == "9,99€"
    d["7"]["data"].pop("price_overview"); d["7"]["data"]["is_free"] = True
    assert W.leggi_gioco(json.dumps(d), 7)["prezzo"] == "Gratis"
    assert W.primo_appid('{"items":[{"id":7}]}') == 7 and W.primo_appid('{"items":[]}') is None


def test_monete_completamento_entro_25_e_prezzo():
    assert len(W.cerca_monete("")) <= 25 and W.cerca_monete("btc") == ["btc"]
    assert W.leggi_prezzo('{"bitcoin":{"eur":1.5,"eur_24h_change":-2.0}}', "bitcoin", "eur") == (1.5, -2.0)
    assert W.leggi_prezzo("{}", "bitcoin", "eur") is None


@pytest.mark.asyncio
async def test_prezzo_senza_chiave_non_chiama_nessun_servizio(monkeypatch):
    cog = cogweb.WebCog(MagicMock())
    from types import SimpleNamespace
    monkeypatch.setattr(cogweb, "config", SimpleNamespace(COINGECKO_API_KEY=""))
    it = fake_interaction()
    await cog.prezzo.callback(cog, it, "btc", "eur")
    it.response.defer.assert_not_called()
    assert "chiave" in it.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_accorcia_rifiuti(monkeypatch):
    assert await W.accorcia_link("ftp://x.it") == "non_valido"
    assert await W.accorcia_link("https://bit.ly/abc") == "gia_corto"
    monkeypatch.setattr(W, "url_e_sicuro", AsyncMock(return_value=False))
    assert await W.accorcia_link("https://esempio.it/a") == "pericoloso"
    monkeypatch.setattr(W, "url_e_sicuro", AsyncMock(return_value=True))
    monkeypatch.setattr(W, "e_phishing", lambda d, l: True)
    get = AsyncMock()
    monkeypatch.setattr(W, "safe_get", get)
    assert await W.accorcia_link("https://truffa.it/a") == "pericoloso"
    get.assert_not_called()  # il controllo viene prima della chiamata


@pytest.mark.asyncio
async def test_accorcia_ok_e_errore(monkeypatch):
    monkeypatch.setattr(W, "url_e_sicuro", AsyncMock(return_value=True))
    monkeypatch.setattr(W, "e_phishing", lambda d, l: False)
    monkeypatch.setattr(W, "safe_get", AsyncMock(return_value="https://is.gd/abc\n"))
    assert await W.accorcia_link("https://esempio.it/a") == "https://is.gd/abc"
    monkeypatch.setattr(W, "safe_get", AsyncMock(return_value="Error: Please enter a valid URL"))
    assert await W.accorcia_link("https://esempio.it/a") == "errore"


@pytest.mark.asyncio
async def test_accorcia_spento_di_base(monkeypatch):
    cog = cogweb.WebCog(MagicMock())
    monkeypatch.setattr(cogweb.web_repo, "accorcia_attivo", AsyncMock(return_value=False))
    it = fake_interaction()
    await cog.accorcia.callback(cog, it, "https://esempio.it/a")
    assert "spento" in it.response.send_message.await_args.args[0]
    it.response.defer.assert_not_called()


@pytest.mark.asyncio
async def test_limiti_dei_comandi_e_nominatim_senza_completamento():
    from discord.ext import commands as ext
    import discord

    bot = ext.Bot(command_prefix="!", intents=discord.Intents.default())
    await cogweb.setup(bot)
    for nome, massimo in (("meteo", 100), ("film", 100), ("gioco", 100), ("accorcia", 2000)):
        o = comando_nel_gruppo("web", nome).to_dict(bot.tree)["options"][0]
        assert o["max_length"] == massimo
    meteo = comando_nel_gruppo("web", "meteo").to_dict(bot.tree)["options"][0]
    assert not meteo.get("autocomplete")  # Nominatim vieta il completamento
    prezzo = comando_nel_gruppo("web", "prezzo").to_dict(bot.tree)["options"]
    assert prezzo[0]["autocomplete"] and prezzo[0]["required"] and not prezzo[1]["required"]
