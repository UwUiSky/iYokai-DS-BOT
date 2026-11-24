"""
tests/test_panel_ticket_live.py
===============================
Risposta dal sito, parte nuova (TKT-085, D127, SPEC §24.14): tempo reale con ETag (200, poi 304), stessa 404 per «non
esiste» e «non puoi», CSP con il solo script del sito; risposta con webhook del bot (nome e avatar di chi risponde, oppure
«Staff» e icona del server), menzioni spente, ripiego sul messaggio del bot senza il permesso. Discord finto.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core import web_panel_ticket as wt
from core.repositories.ticket_repo import ticket_repo
from tests.support.discord_fakes import fake_member
from tests.test_panel_ticket import BASE, CANALE, tk  # noqa: F401
from tests.test_web_panel_server import ADMIN, GUILD, _client, _csrf, _entra, ambiente  # noqa: F401

UTENTE_BOT = 999


def _webhook(nome=wt.NOME_WEBHOOK, proprio=True):
    w = MagicMock(spec=discord.Webhook)
    w.token, w.name, w.id = "tok", nome, 7
    w.user = SimpleNamespace(id=UTENTE_BOT if proprio else 5)
    w.send = AsyncMock()
    return w


@pytest.fixture(autouse=True)
def _pulisci():
    wt._webhook_per_canale.clear()
    yield
    wt._webhook_per_canale.clear()


@pytest.fixture
def con_webhook(tk):  # noqa: F811
    tk.bot.user.id = UTENTE_BOT
    tk.bot.guilds[0].icon = SimpleNamespace(url="https://cdn.discordapp.com/icons/1/x.png")
    tk.membri[ADMIN].display_avatar = SimpleNamespace(url="https://cdn.discordapp.com/avatars/1/y.png")
    tk.canale.permissions_for = MagicMock(return_value=discord.Permissions(send_messages=True, manage_webhooks=True))
    tk.webhook = _webhook()
    tk.canale.webhooks = AsyncMock(return_value=[_webhook(proprio=False), tk.webhook])
    tk.canale.create_webhook = AsyncMock(return_value=_webhook())
    return tk


async def _rispondi(client, tk, **dati):
    csrf = await _csrf(client, f"{BASE}/{tk.ticket.id}")
    return await client.post(f"{BASE}/{tk.ticket.id}/rispondi", data={"csrf": csrf, **dati}, allow_redirects=False)


@pytest.mark.asyncio
async def test_stato_etag_poi_304_e_cambia_quando_cambia(tk, clean_db):
    client = await _client(tk.app)
    try:
        await _entra(client)
        r = await client.get(f"{BASE}/{tk.ticket.id}/stato")
        corpo = await r.json()
        assert r.status == 200 and corpo["stato"] == "open" and corpo["presa_da"] is None
        assert set(corpo) == {"stato", "presa_da", "utente_scritto", "attivita", "prima_risposta"}  # mai il testo
        etag = r.headers["ETag"]
        r2 = await client.get(f"{BASE}/{tk.ticket.id}/stato", headers={"If-None-Match": etag})
        assert r2.status == 304 and r2.headers["ETag"] == etag and await r2.text() == ""
        await clean_db.execute("UPDATE tickets SET utente_scritto_at = now() WHERE id = $1", tk.ticket.id)
        r3 = await client.get(f"{BASE}/{tk.ticket.id}/stato", headers={"If-None-Match": etag})
        assert r3.status == 200 and r3.headers["ETag"] != etag and (await r3.json())["utente_scritto"]
        await clean_db.execute("UPDATE tickets SET status = 'closed' WHERE id = $1", tk.ticket.id)
        assert (await (await client.get(f"{BASE}/{tk.ticket.id}/stato")).json())["stato"] == "closed"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_stato_per_chi_non_e_staff_o_ticket_inesistente_ha_la_stessa_risposta(tk, clean_db):
    client = await _client(tk.app)
    try:
        assert (await client.get(f"{BASE}/{tk.ticket.id}/stato", allow_redirects=False)).status == 302  # senza sessione: accesso
        await _entra(client)
        inesistente = await client.get(f"{BASE}/999999/stato")
        await clean_db.execute("UPDATE tickets SET guild_id = 1 WHERE id = $1", tk.ticket.id)  # di un altro server
        non_puoi = await client.get(f"{BASE}/{tk.ticket.id}/stato")
        assert inesistente.status == non_puoi.status == 404 and await inesistente.text() == await non_puoi.text()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_pagina_con_script_del_sito_e_csp_stretta(tk):
    client = await _client(tk.app)
    try:
        await _entra(client)
        r = await client.get(f"{BASE}/{tk.ticket.id}")
        csp = r.headers["Content-Security-Policy"]
        assert "script-src 'self'" in csp and "connect-src 'self'" in csp and "unsafe" not in csp
        testo = await r.text()
        assert "/static/ticket_live.js" in testo and 'name="anonimo"' in testo and "<script>" not in testo
        titolo = testo.split("<title>")[1].split("</title>")[0]
        assert "<script" not in titolo and testo.count("ticket_live.js") == 1  # lo script sta solo in fondo, non nel titolo
        assert "script-src" not in (await client.get(BASE)).headers["Content-Security-Policy"]  # solo la scheda
        js = await client.get("/static/ticket_live.js")
        assert js.status == 200 and "If-None-Match" in await js.text()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_risposta_con_webhook_nome_e_avatar_di_chi_risponde(con_webhook):
    tk = con_webhook
    client = await _client(tk.app)
    try:
        await _entra(client)
        r = await _rispondi(client, tk, testo="Ciao @everyone <@1>")
        assert r.status == 302 and "esito=ticket_inviato" in r.headers["Location"]
        tk.canale.send.assert_not_called()
        args, kw = tk.webhook.send.await_args
        assert args[0] == "Ciao @everyone <@1>"  # il testo è solo il testo: nome e avatar stanno nel webhook
        assert kw["username"].endswith("(dal sito)") and "Mario" in kw["username"] and "<b>" not in kw["username"]
        assert kw["avatar_url"].endswith("y.png")
        m = kw["allowed_mentions"]
        assert not m.everyone and m.users is False and m.roles is False
        assert (await ticket_repo.get_ticket_by_channel(CANALE)).first_response_at is not None
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_risposta_anonima_staff_e_avatar_del_server(con_webhook):
    tk = con_webhook
    client = await _client(tk.app)
    try:
        await _entra(client)
        await _rispondi(client, tk, testo="Salve", anonimo="1")
        _, kw = tk.webhook.send.await_args
        assert kw["username"] == "Staff" and kw["avatar_url"].endswith("x.png")
        assert "Mario" not in str(tk.webhook.send.await_args)
        assert not kw["allowed_mentions"].everyone
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_senza_webhook_del_bot_se_ne_crea_uno_e_si_riusa(con_webhook):
    tk = con_webhook
    tk.canale.webhooks = AsyncMock(return_value=[_webhook(proprio=False)])  # nessuno nostro (l'altro è di un'altra persona)
    client = await _client(tk.app)
    try:
        await _entra(client)
        await _rispondi(client, tk, testo="uno")
        await _rispondi(client, tk, testo="due")
        tk.canale.create_webhook.assert_awaited_once()
        assert tk.canale.create_webhook.await_args.kwargs["name"] == wt.NOME_WEBHOOK
        assert tk.canale.webhooks.await_count == 1  # la seconda volta il webhook è in memoria
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_senza_permesso_sui_webhook_risponde_il_bot_e_anonimo_non_dice_il_nome(tk):
    client = await _client(tk.app)
    try:
        await _entra(client)
        await _rispondi(client, tk, testo="Salve", anonimo="1")
        _, kw = tk.canale.send.await_args
        assert "Staff" in kw["content"] and "Mario" not in kw["content"] and not kw["allowed_mentions"].everyone
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_nome_rifiutato_da_discord_ripiega_sul_messaggio(con_webhook):
    tk = con_webhook
    tk.webhook.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=400), "username non valido"))
    client = await _client(tk.app)
    try:
        await _entra(client)
        r = await _rispondi(client, tk, testo="ciao")
        assert "esito=ticket_inviato" in r.headers["Location"]
        tk.canale.send.assert_awaited_once()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_webhook_cancellato_si_ricrea(con_webhook):
    tk = con_webhook
    nuovo = _webhook()
    tk.canale.webhooks = AsyncMock(return_value=[])
    tk.canale.create_webhook = AsyncMock(side_effect=[tk.webhook, nuovo])
    tk.webhook.send = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404), "sparito"))
    client = await _client(tk.app)
    try:
        await _entra(client)
        r = await _rispondi(client, tk, testo="ciao")
        assert "esito=ticket_inviato" in r.headers["Location"] and nuovo.send.await_count == 1
    finally:
        await client.close()


def test_nome_webhook_e_stato_di_un_ticket_di_prova():
    assert wt.nome_webhook("@everyone **x**", False).endswith("(dal sito)") and len(wt.nome_webhook("a" * 200, False)) <= 80
    assert "@" not in wt.nome_webhook("@everyone", False) and wt.nome_webhook("Mario", True) == "Staff"
