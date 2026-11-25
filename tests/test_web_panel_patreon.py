"""
tests/test_web_panel_patreon.py
===============================
Pagina personale «Premium» del pannello con «Collega Patreon» e «Scollega» (CFG-036, #122): CSRF sui POST, stato monouso,
rotte spente (stessa 404) senza le chiavi di Patreon. Sessioni e database veri.
"""

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from core import patreon_service, piani
from tests.test_web_panel_server import _client, _csrf, _entra, ADMIN, ambiente  # noqa: F401

CFG = SimpleNamespace(PATREON_CLIENT_ID="cid", PATREON_CLIENT_SECRET="csecret-1234", PATREON_WEBHOOK_SECRET="segreto-webhook-1234",
                      OAUTH_ENCRYPTION_KEY="A" * 43 + "=", WEB_PANEL_PUBLIC_URL="http://pannello.test")
SPENTA = SimpleNamespace(PATREON_CLIENT_ID="", PATREON_CLIENT_SECRET="", PATREON_WEBHOOK_SECRET="")


@pytest.fixture
def con_patreon(ambiente, monkeypatch):
    """L'ambiente di prova è costruito prima delle chiavi: lo si ricostruisce con Patreon acceso."""
    from core.web_panel_server import build_app
    from core.repositories.web_panel_session_repo import WebPanelSessionRepository

    monkeypatch.setattr(patreon_service, "_config", lambda: CFG)
    app = build_app(
        bot=ambiente.bot, sessioni=WebPanelSessionRepository(pool_provider=lambda: ambiente.pool), oauth=ambiente.oauth,
        client_id="1", client_secret="s" * 8, url_pubblico="http://pannello.test", chiave=ambiente.chiave,
    )
    return SimpleNamespace(app=app, pool=ambiente.pool)


async def test_senza_chiavi_le_rotte_non_esistono_e_danno_la_stessa_404(ambiente, monkeypatch):
    monkeypatch.setattr(patreon_service, "_config", lambda: SPENTA)
    client = await _client(ambiente.app)
    try:
        await _entra(client)
        inventata = await client.get("/non-esiste-davvero")
        for percorso in ("/premium",):
            r = await client.get(percorso)
            assert r.status == 404 and await r.text() == await inventata.text()
        for percorso in ("/premium/patreon/collega", "/premium/patreon/scollega"):
            assert (await client.post(percorso, data={})).status in (404, 405)
        assert "/premium" not in await (await client.get("/")).text()
    finally:
        await client.close()


async def test_collega_ha_csrf_e_manda_a_patreon_con_stato_monouso(con_patreon):
    client = await _client(con_patreon.app)
    try:
        assert (await client.get("/premium", allow_redirects=False)).status == 302  # senza accesso
        await _entra(client)
        csrf = await _csrf(client, "/premium")
        assert (await client.post("/premium/patreon/collega", data={}, allow_redirects=False)).status == 403
        r = await client.post("/premium/patreon/collega", data={"csrf": csrf}, allow_redirects=False)
        assert r.status == 302
        url = urlparse(r.headers["Location"])
        assert url.netloc == "www.patreon.com"
        stato = parse_qs(url.query)["state"][0]
        impronta = await con_patreon.pool.fetchval("SELECT sessione_impronta FROM patreon_stati")
        assert impronta and len(impronta) == 64  # legato alla sessione del pannello
        with pytest.raises(patreon_service.CollegamentoFallito):  # un'altra sessione non lo usa (e lo brucia)
            await patreon_service._consuma_stato(stato, "b" * 64)
        stato2 = parse_qs(urlparse((await client.post("/premium/patreon/collega", data={"csrf": csrf}, allow_redirects=False)).headers["Location"]).query)["state"][0]
        assert await patreon_service._consuma_stato(stato2, impronta) == ADMIN  # lo stato è di chi ha cominciato
        with pytest.raises(patreon_service.CollegamentoFallito):  # e vale una volta sola
            await patreon_service._consuma_stato(stato2, impronta)
    finally:
        await client.close()


async def test_scollega_toglie_il_collegamento_e_il_livello(con_patreon):
    await con_patreon.pool.execute("INSERT INTO patreon_collegamenti (discord_user_id, patreon_id, token_cifrato) VALUES ($1, 'p1', 'x')", ADMIN)
    await piani.concedi("utente", ADMIN, piani.VIP, "patreon", giorni=30, riferimento="patreon")
    client = await _client(con_patreon.app)
    try:
        await _entra(client)
        testo = await (await client.get("/premium")).text()
        assert "Scollega" in testo and "Collega Patreon" not in testo
        csrf = await _csrf(client, "/premium")
        assert (await client.post("/premium/patreon/scollega", data={}, allow_redirects=False)).status == 403
        r = await client.post("/premium/patreon/scollega", data={"csrf": csrf}, allow_redirects=False)
        assert r.status == 302 and r.headers["Location"] == "/premium?patreon=scollegato"
        assert await piani.livello_utente(ADMIN) == piani.GRATUITO
        testo = await (await client.get("/premium?patreon=ok")).text()
        assert "Collega Patreon" in testo and "Account Patreon collegato." in testo
    finally:
        await client.close()


async def test_conferma_dello_spostamento_dal_pannello(con_patreon):
    await con_patreon.pool.execute("INSERT INTO patreon_collegamenti (discord_user_id, patreon_id, token_cifrato) VALUES (999, 'p1', 'x')")
    await con_patreon.pool.execute(
        "INSERT INTO patreon_spostamenti (discord_user_id, patreon_id, token_cifrato, attivo, tiers, scade_il) "
        "VALUES ($1, 'p1', 'y', false, '{}', now() + interval '5 minutes')", ADMIN,
    )
    client = await _client(con_patreon.app)
    try:
        await _entra(client)
        testo = await (await client.get("/premium")).text()
        assert "già collegato a un'altra persona" in testo and "Sì, sposta qui" in testo
        csrf = await _csrf(client, "/premium")
        assert (await client.post("/premium/patreon/sposta", data={"azione": "conferma"}, allow_redirects=False)).status == 403  # senza CSRF
        assert await con_patreon.pool.fetchval("SELECT discord_user_id FROM patreon_collegamenti") == 999
        r = await client.post("/premium/patreon/sposta", data={"csrf": csrf, "azione": "conferma"}, allow_redirects=False)
        assert r.status == 302 and "patreon=spostato" in r.headers["Location"]
        assert await con_patreon.pool.fetchval("SELECT discord_user_id FROM patreon_collegamenti") == ADMIN
        r = await client.post("/premium/patreon/sposta", data={"csrf": csrf, "azione": "conferma"}, allow_redirects=False)
        assert "patreon=scaduto" in r.headers["Location"]  # non c'è più niente da confermare
    finally:
        await client.close()
