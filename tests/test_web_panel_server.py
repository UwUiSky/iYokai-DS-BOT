"""
tests/test_web_panel_server.py
==============================
Il pannello web dal browser (SPEC §24.1–24.4): login OAuth2 finto senza
rete, sessioni vere su PostgreSQL, permessi a ogni richiesta, CSRF,
origine, limite di frequenza, escape dell'HTML, wiki dei comandi.
"""

import re
import secrets
from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlparse

import aiohttp
import discord
import pytest
from aiohttp.test_utils import TestClient, TestServer
from discord import app_commands

import core.database as database_module
from core import panel_bridge, web_panel_logic as regole
from core.command_access import TipoRuolo, leggi_ruolo
from core.database import db
from core.premium import PremiumModule, registry
from core.repositories.web_panel_session_repo import WebPanelSessionRepository
from core.web_panel_server import build_app
from tests.support.discord_fakes import fake_guild, fake_member, fake_role

GUILD = 8800
ADMIN = 31
ESTRANEO = 32
URL = "http://pannello.test"


class _OAuthFinto:
    def __init__(self, utente_id=ADMIN):
        self.utente_id = utente_id
        self.scambi = []

    async def exchange_code_for_token(self, *, client_id, client_secret, redirect_uri, code):
        self.scambi.append((code, redirect_uri))
        return SimpleNamespace(access_token="finto-" + code)

    async def fetch_current_user(self, access_token):
        return self.utente_id


def _albero():
    async def _cb(interaction: discord.Interaction) -> None:  # pragma: no cover
        pass

    gruppo = app_commands.Group(name="moderazione", description="Comandi di moderazione")
    gruppo.add_command(app_commands.Command(name="ban", description="Banna un utente dal server", callback=_cb))
    gruppo.add_command(app_commands.Command(name="avviso", description="Dai un avviso", callback=_cb))
    return [gruppo]


def _bot(membri):
    guild = fake_guild(guild_id=GUILD, name="Server <b>di</b> prova", owner_id=1)
    guild.roles = []
    guild.get_member = MagicMock(side_effect=lambda uid: membri.get(uid))
    guild.get_role = MagicMock(return_value=None)
    guild.fetch_member = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404), "no"))
    bot = MagicMock()
    bot.guilds = [guild]
    bot.get_guild = MagicMock(side_effect=lambda gid: guild if gid == GUILD else None)
    bot.tree.get_commands = MagicMock(return_value=_albero())
    bot.application_id = 4242
    return bot


@pytest.fixture
def ambiente(monkeypatch, clean_db, reset_premium_registry):
    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    monkeypatch.setattr(panel_bridge, "_cache_membri", OrderedDict())
    registry.register(PremiumModule("modulo_web", "Modulo web", "Prova del pannello", category="utility"))
    membri = {ADMIN: fake_member(ADMIN, guild_permissions=discord.Permissions(manage_guild=True))}
    bot = _bot(membri)
    oauth = _OAuthFinto()
    sessioni = WebPanelSessionRepository(pool_provider=lambda: clean_db)
    chiave = secrets.token_urlsafe(48)
    app = build_app(
        bot=bot, sessioni=sessioni, oauth=oauth, client_id="1", client_secret="s" * 8,
        url_pubblico=URL, chiave=chiave,
    )
    return SimpleNamespace(app=app, bot=bot, oauth=oauth, membri=membri, chiave=chiave, pool=clean_db)


async def _client(app):
    client = TestClient(TestServer(app), cookie_jar=aiohttp.CookieJar(unsafe=True))
    await client.start_server()
    return client


async def _entra(client):
    risposta = await client.get("/accedi", allow_redirects=False)
    state = parse_qs(urlparse(risposta.headers["Location"]).query)["state"][0]
    return await client.get(f"/callback?code=abc&state={state}", allow_redirects=False)


async def _csrf(client, percorso):
    testo = await (await client.get(percorso)).text()
    return re.search(r'name="csrf" value="([^"]+)"', testo).group(1)


@pytest.mark.asyncio
async def test_intestazioni_e_pagina_iniziale(ambiente):
    client = await _client(ambiente.app)
    try:
        risposta = await client.get("/")
        assert risposta.status == 200
        assert "default-src 'none'" in risposta.headers["Content-Security-Policy"]
        assert risposta.headers["X-Frame-Options"] == "DENY"
        assert "Accedi con Discord" in await risposta.text()
        assert (await client.get("/non-esiste")).headers["X-Content-Type-Options"] == "nosniff"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_login_completo_salva_solo_l_impronta(ambiente):
    client = await _client(ambiente.app)
    try:
        accedi = await client.get("/accedi", allow_redirects=False)
        assert accedi.status == 302
        cookie_state = accedi.headers["Set-Cookie"]
        assert "HttpOnly" in cookie_state and "SameSite=Lax" in cookie_state
        query = parse_qs(urlparse(accedi.headers["Location"]).query)
        assert query["scope"] == ["identify"] and query["redirect_uri"] == [URL + "/callback"]

        risposta = await client.get(f"/callback?code=abc&state={query['state'][0]}", allow_redirects=False)
        assert risposta.status == 302 and risposta.headers["Location"] == "/"
        cookie = risposta.cookies["iyokai_sessione"]
        righe = await ambiente.pool.fetch("SELECT token_hash, user_id FROM web_panel_sessions")
        assert [(r["token_hash"], r["user_id"]) for r in righe] == [(regole.impronta(cookie.value), ADMIN)]
        assert "Server &lt;b&gt;di&lt;/b&gt; prova" in await (await client.get("/")).text()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_callback_senza_il_suo_state_rifiutata(ambiente):
    client = await _client(ambiente.app)
    try:
        await client.get("/accedi", allow_redirects=False)
        risposta = await client.get("/callback?code=abc&state=inventato", allow_redirects=False)
        assert risposta.status == 400
        assert ambiente.oauth.scambi == []
        altro = await _client(ambiente.app)  # browser diverso: niente cookie dello state
        try:
            state = parse_qs(urlparse((await client.get("/accedi", allow_redirects=False)).headers["Location"]).query)
            assert (await altro.get(f"/callback?code=x&state={state['state'][0]}")).status == 400
        finally:
            await altro.close()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_configura_modulo_con_csrf_e_storico(ambiente):
    client = await _client(ambiente.app)
    try:
        await _entra(client)
        csrf = await _csrf(client, f"/server/{GUILD}")
        senza = await client.post(f"/server/{GUILD}/modulo", data={"nome": "modulo_web", "attivo": "1"})
        assert senza.status == 403
        assert not await db.is_module_active_for_guild(GUILD, "modulo_web")

        risposta = await client.post(
            f"/server/{GUILD}/modulo", data={"csrf": csrf, "nome": "modulo_web", "attivo": "1"}, allow_redirects=False
        )
        assert risposta.headers["Location"] == f"/server/{GUILD}?esito=salvato"
        assert await db.is_module_active_for_guild(GUILD, "modulo_web")
        ambiente.bot.dispatch.assert_called_once_with("modules_updated", GUILD, "modulo_web", True, ADMIN)
        storico = await (await client.get(f"/server/{GUILD}/storico")).text()
        assert "modulo_web" in storico and str(ADMIN) in storico

        await client.post(f"/server/{GUILD}/lingua", data={"csrf": csrf, "lingua": "en"})
        assert await db.get_guild_language(GUILD) == "en"
        sbagliata = await client.post(f"/server/{GUILD}/lingua", data={"csrf": csrf, "lingua": "<x>"}, allow_redirects=False)
        assert sbagliata.headers["Location"].endswith("esito=non_valido")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_permessi_ricontrollati_a_ogni_richiesta(ambiente):
    client = await _client(ambiente.app)
    try:
        await _entra(client)
        csrf = await _csrf(client, f"/server/{GUILD}")
        ambiente.membri[ADMIN].guild_permissions = discord.Permissions.none()
        assert (await client.get(f"/server/{GUILD}")).status == 403
        risposta = await client.post(f"/server/{GUILD}/modulo", data={"csrf": csrf, "nome": "modulo_web", "attivo": "1"})
        assert risposta.status == 403
        assert not await db.is_module_active_for_guild(GUILD, "modulo_web")
        assert (await client.get("/server/123")).status == 403
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_estraneo_e_anonimo_non_entrano(ambiente):
    ambiente.oauth.utente_id = ESTRANEO
    client = await _client(ambiente.app)
    try:
        anonimo = await client.get(f"/server/{GUILD}", allow_redirects=False)
        assert anonimo.status == 302 and anonimo.headers["Location"] == "/accedi"
        await _entra(client)
        assert (await client.get(f"/server/{GUILD}")).status == 403
        assert "Nessun server da gestire" in await (await client.get("/")).text()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_origine_estranea_rifiutata_e_uscita(ambiente):
    client = await _client(ambiente.app)
    try:
        await _entra(client)
        csrf = await _csrf(client, f"/server/{GUILD}")
        estranea = await client.post(
            f"/server/{GUILD}/modulo", data={"csrf": csrf, "nome": "modulo_web", "attivo": "1"},
            headers={"Origin": "https://cattivo.example"},
        )
        assert estranea.status == 403
        await client.post("/esci", data={"csrf": csrf})
        assert await ambiente.pool.fetchval("SELECT count(*) FROM web_panel_sessions") == 0
        assert (await client.get(f"/server/{GUILD}", allow_redirects=False)).status == 302
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_limite_sui_tentativi_di_accesso(ambiente):
    client = await _client(ambiente.app)
    try:
        stati = [(await client.get("/accedi", allow_redirects=False)).status for _ in range(11)]
        assert stati[:10] == [302] * 10 and stati[10] == 429
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_wiki_cerca_ed_escape(ambiente):
    client = await _client(ambiente.app)
    try:
        tutti = await (await client.get("/wiki")).text()
        assert "/moderazione ban" in tutti and "/moderazione avviso" in tutti
        cercati = await (await client.get("/wiki?q=banna")).text()
        assert "/moderazione ban" in cercati and "/moderazione avviso" not in cercati
        assert "<script>" not in await (await client.get("/wiki?q=<script>")).text()
        dettaglio = await client.get("/wiki/moderazione/ban")
        assert dettaglio.status == 200 and "Banna un utente" in await dettaglio.text()
        assert (await client.get("/wiki/moderazione/inventato")).status == 404
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_cookie_secure_su_https(clean_db):
    app = build_app(
        bot=_bot({}), sessioni=WebPanelSessionRepository(lambda: clean_db), oauth=_OAuthFinto(),
        client_id="1", client_secret="s", url_pubblico="https://pannello.example", chiave=secrets.token_urlsafe(48),
    )
    client = await _client(app)
    try:
        risposta = await client.get("/accedi", allow_redirects=False)
        assert risposta.headers["Set-Cookie"].startswith("__Host-iyokai_state=")
        assert "Secure" in risposta.headers["Set-Cookie"]
        assert "Strict-Transport-Security" in risposta.headers
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_post_con_la_politica_referrer_del_pannello_passa(ambiente):
    """Il browser segue la Referrer-Policy della pagina: con "no-referrer" l'Origin del POST è "null"."""
    client = await _client(ambiente.app)
    try:
        await _entra(client)
        pagina = await client.get(f"/server/{GUILD}")
        politica = pagina.headers["Referrer-Policy"]
        csrf = re.search(r'name="csrf" value="([^"]+)"', await pagina.text()).group(1)
        origine = "null" if politica == "no-referrer" else URL
        risposta = await client.post(
            f"/server/{GUILD}/modulo", data={"csrf": csrf, "nome": "modulo_web", "attivo": "1"},
            headers={"Origin": origine}, allow_redirects=False,
        )
        assert risposta.status == 302 and "esito=salvato" in risposta.headers["Location"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_cookie_host_cancellati_con_secure(clean_db):
    """Un cookie `__Host-` senza Secure è scartato dal browser: anche la cancellazione deve averlo."""
    app = build_app(
        bot=_bot({}), sessioni=WebPanelSessionRepository(lambda: clean_db), oauth=_OAuthFinto(),
        client_id="1", client_secret="s", url_pubblico="https://pannello.example", chiave=secrets.token_urlsafe(48),
    )
    client = await _client(app)
    try:
        uscita = await client.post("/esci", allow_redirects=False)
        cookie = uscita.headers["Set-Cookie"]
        assert cookie.startswith("__Host-iyokai_sessione=") and "Secure" in cookie
        errore = await client.get("/callback?code=x&state=y", allow_redirects=False)
        cookie = errore.headers["Set-Cookie"]
        assert cookie.startswith("__Host-iyokai_state=") and "Secure" in cookie
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_ruolo_admin_dal_pannello_serve_amministratore(ambiente):
    """D27: il ruolo admin apre anche i comandi di sicurezza («Amministratore»)."""
    ruolo = fake_role(role_id=500, name="Staff")
    ambiente.bot.get_guild(GUILD).get_role = MagicMock(side_effect=lambda rid: ruolo if rid == 500 else None)
    client = await _client(ambiente.app)
    try:
        await _entra(client)
        csrf = await _csrf(client, f"/server/{GUILD}")
        dati = {"csrf": csrf, "tipo": "admin", "ruolo_id": "500"}
        negato = await client.post(f"/server/{GUILD}/ruolo", data=dati, allow_redirects=False)
        assert negato.headers["Location"].endswith("esito=serve_amministratore")
        assert await leggi_ruolo(GUILD, TipoRuolo.ADMIN) is None
        assert "Amministratore" in await (await client.get(negato.headers["Location"])).text()

        # Come Member.guild_permissions vero: con «Amministratore» ci sono tutti i permessi.
        ambiente.membri[ADMIN].guild_permissions = discord.Permissions.all()
        ok = await client.post(f"/server/{GUILD}/ruolo", data=dati, allow_redirects=False)
        assert ok.headers["Location"].endswith("esito=salvato")
        assert await leggi_ruolo(GUILD, TipoRuolo.ADMIN) == 500
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("fidati, bloccato", [(frozenset(), True), (frozenset({"127.0.0.1"}), False)])
async def test_x_forwarded_for_solo_dal_proxy_fidato(clean_db, fidati, bloccato):
    """Senza proxy fidato un X-Forwarded-For inventato non aggira il limite per IP."""
    app = build_app(
        bot=_bot({}), sessioni=WebPanelSessionRepository(pool_provider=lambda: clean_db), oauth=_OAuthFinto(),
        client_id="1", client_secret="s" * 8, url_pubblico=URL, chiave=secrets.token_urlsafe(48),
        proxy_fidati=fidati,
    )
    client = await _client(app)
    try:
        stati = [
            (await client.get("/accedi", allow_redirects=False, headers={"X-Forwarded-For": f"10.0.0.{i}"})).status
            for i in range(11)
        ]
        assert (stati[10] == 429) is bloccato
    finally:
        await client.close()
