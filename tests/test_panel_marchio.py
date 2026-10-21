"""
tests/test_panel_marchio.py
===========================
Pagina del bot con marchio proprio nel pannello (NF-38, #109): stato senza
mai il token, collegamento, testo di stato, accendi/spegni, scollega.
Tutto dalle funzioni di `core/whitelabel_bot.py` usate anche dal comando.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import core.premium as premium_module
from core import whitelabel_bot as wl
from core.oauth_crypto import generate_key
from core.repositories import whitelabel_repo as repo_modulo
from core.repositories.whitelabel_repo import WhitelabelRepository
from tests.test_web_panel_server import GUILD, _client, _csrf, _entra, ambiente  # noqa: F401

TOKEN = ".".join(["MTIzNDU2Nzg5MDEyMzQ1Njc4", "abcdef", "ghijklmnopqrstuvwxyz0123456"])
CHIAVE = generate_key()
PAGINA = f"/server/{GUILD}/marchio"


class _ConfigPremium:
    PREMIUM_ALPHA_UNLOCK_ALL = True
    MAIN_GUILD_ID = 999


@pytest.fixture
def marchio(ambiente, monkeypatch):  # noqa: F811
    repo = WhitelabelRepository(pool_provider=lambda: ambiente.pool, chiave_provider=lambda: CHIAVE)
    monkeypatch.setattr(repo_modulo, "whitelabel_repo", repo)
    monkeypatch.setattr(wl, "whitelabel_repo", repo)
    monkeypatch.setattr(premium_module, "config", _ConfigPremium())
    monkeypatch.setattr(wl, "verifica_token", AsyncMock(return_value=wl.InfoApplicazione(4343, 9000, "Mio Bot")))
    gestore = SimpleNamespace(avvia=AsyncMock(return_value=True), ferma=AsyncMock(), aggiorna_testo=AsyncMock())
    ambiente.bot.get_cog = lambda nome: SimpleNamespace(gestore=gestore) if nome == "MarchioCog" else None
    ambiente.bot.get_guild(GUILD).me = SimpleNamespace(id=1)
    return SimpleNamespace(repo=repo, gestore=gestore, ambiente=ambiente)


async def _invia(client, dati):
    csrf = await _csrf(client, PAGINA)
    risposta = await client.post(PAGINA, data={"csrf": csrf, **dati}, allow_redirects=False)
    assert risposta.status == 302
    return risposta.headers["Location"].split("esito=")[1]


@pytest.mark.asyncio
async def test_collega_testo_spegni_e_scollega(marchio):
    client = await _client(marchio.ambiente.app)
    try:
        await _entra(client)
        pagina = await (await client.get(PAGINA)).text()
        assert "Nessun bot con marchio collegato" in pagina and 'type="password"' in pagina

        assert await _invia(client, {"azione": "collega", "token": TOKEN}) == "marchio_collegato"
        marchio.gestore.ferma.assert_awaited_with(GUILD)
        marchio.gestore.avvia.assert_awaited_with(GUILD)
        pagina = await (await client.get(PAGINA + "?esito=marchio_collegato")).text()
        assert "Mio Bot" in pagina and "Bot collegato" in pagina and "client_id=9000" in pagina
        assert TOKEN not in pagina

        assert await _invia(client, {"azione": "testo", "testo": "  Server di prova "}) == "mar_testo_ok"
        assert (await marchio.repo.get(GUILD)).status_text == "Server di prova"
        marchio.gestore.aggiorna_testo.assert_awaited_with(GUILD, "Server di prova")
        assert await _invia(client, {"azione": "testo", "testo": "x" * 101}) == "non_valido"

        assert await _invia(client, {"azione": "ferma"}) == "mar_fermato"
        assert (await marchio.repo.get(GUILD)).enabled is False
        pagina = await (await client.get(PAGINA + "?esito=mar_fermato")).text()
        assert "Il bot con marchio è spento." in pagina and "Accendi" in pagina

        assert await _invia(client, {"azione": "rimuovi"}) == "mar_rimosso"
        assert await marchio.repo.get(GUILD) is None
        # Discord non revoca i token dei bot via API: la pagina dice di rigenerarlo nel Developer Portal.
        pagina = await (await client.get(PAGINA + "?esito=mar_rimosso")).text()
        assert "rigeneralo nel Developer Portal" in pagina
        assert await _invia(client, {"azione": "avvia"}) == "mar_nessun_marchio"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_controlli_del_modulo(marchio, monkeypatch):
    client = await _client(marchio.ambiente.app)
    try:
        await _entra(client)
        senza_csrf = await client.post(PAGINA, data={"azione": "rimuovi"}, allow_redirects=False)
        assert senza_csrf.status == 403
        assert await _invia(client, {"azione": "collega", "token": "corto"}) == "non_valido"
        assert await _invia(client, {"azione": "boh"}) == "non_valido"
        esiti = [await _invia(client, {"azione": "collega", "token": TOKEN}) for _ in range(4)]
        assert esiti[-1] == "marchio_attendi"
        # Solo i codici dell'elenco: un testo con segnaposto non si mostra dall'URL.
        pagina = await (await client.get(PAGINA + "?esito=mar_invita")).text()
        assert "{url}" not in pagina and "avviso" not in pagina.split("<main>")[1].split("<h1>")[0]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_senza_premium_e_senza_cog(marchio, monkeypatch):
    class _SenzaPremium(_ConfigPremium):
        PREMIUM_ALPHA_UNLOCK_ALL = False

    monkeypatch.setattr(premium_module, "config", _SenzaPremium())
    client = await _client(marchio.ambiente.app)
    try:
        await _entra(client)
        assert "funzione premium" in await (await client.get(PAGINA)).text()
        assert await _invia(client, {"azione": "collega", "token": TOKEN}) == "mar_richiede_premium"
        assert await marchio.repo.get(GUILD) is None
        marchio.ambiente.bot.get_cog = lambda nome: None
        assert await _invia(client, {"azione": "testo", "testo": "x"}) == "marchio_non_disponibile"
    finally:
        await client.close()
