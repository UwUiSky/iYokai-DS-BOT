"""
tests/test_panel_join.py
========================
Pagina di consenso del rientro (BKP-039, D113, SPEC §24.12): `/join/<nome>` con nome, icona e colori del server; nome breve
unico e valido (3-32 caratteri, minuscole, cifre, trattini, riservati esclusi), ID se manca; stesse risposte per «non esiste» e
«non disponibile»; il flusso OAuth del ripristino resta quello di sempre (`state` per chi l'ha chiesto, monouso, solo consenso).
Sessioni e database veri, Discord finto.
"""

import secrets
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

import discord
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from core import oauth_crypto, web_panel_backup, web_panel_join as join
from core.config_schema import ImpostazioneNonValida
from core.database import db
from core.repositories.restore_oauth_repo import RestoreOAuthRepository
from core.repositories.web_panel_pubblico_repo import web_panel_pubblico_repo as repo
from core.repositories.web_panel_session_repo import WebPanelSessionRepository
from core.restore_batch_logic import MODE_CLASSIC_INVITE, MODE_VERIFY_OAUTH
from core.restore_oauth_logic import decode_and_verify_state
from core.restore_orchestrator import ExchangedToken
from core.restore_web_server import CONSENT_ONLY_TARGET, build_app as restore_app
from core.web_panel_server import build_app
from tests.test_restore_web_server import _FakeOrchestrator, _FakeVerifyRepo
from tests.test_web_panel_server import ADMIN, ESTRANEO, GUILD, URL, _client, _csrf, _entra, ambiente  # noqa: F401

CHIAVE = oauth_crypto.generate_key()
REDIRECT = "https://bot.test/oauth/callback"
ICONA = "https://cdn.discordapp.com/icons/8800/abc.png"


@pytest.fixture
def jn(ambiente, clean_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(repo, "_pool_provider", lambda: clean_db)
    permessi = {ADMIN: True}

    async def puo(guild, user_id):
        return permessi.get(user_id, False)

    monkeypatch.setattr(web_panel_backup, "puo_gestire_backup", puo)
    guild = ambiente.bot.get_guild(GUILD)
    guild.icon = SimpleNamespace(url=ICONA)
    app = build_app(
        bot=ambiente.bot, sessioni=WebPanelSessionRepository(pool_provider=lambda: clean_db), oauth=ambiente.oauth,
        client_id="1234", client_secret="s" * 8, url_pubblico=URL, chiave=secrets.token_urlsafe(48),
        restore_redirect_uri=REDIRECT, chiave_ripristino=CHIAVE,
    )
    ambiente.app, ambiente.permessi, ambiente.guild = app, permessi, guild
    return ambiente


async def _accendi(nome="il-mio-server", accento="#c24a3a", sfondo="#07070b", attiva=True):
    return await join.imposta_pagina(GUILD, attiva, nome, accento, sfondo, ADMIN)


# --- nome breve e colori -----------------------------------------------------
@pytest.mark.parametrize("storto", [
    "ab", "x" * 33, "con spazi", "-inizio", "fine-", "dop--pio", "àccento", "123456", "slash/no", "<b>", "a.b",
    "admin", "api", "iyokai-mio", "discord-x", "join", "restore", "oauth", "static", "ripristino",
])
def test_nomi_non_validi_o_riservati(storto):
    with pytest.raises(ImpostazioneNonValida):
        join.valida_nome(storto)


@pytest.mark.parametrize("buono", ["abc", "il-mio-server", "a1b", "x" * 32, "server-2026"])
def test_nomi_validi(buono):
    assert join.valida_nome(buono) == buono


def test_il_nome_si_porta_in_minuscolo():
    assert join.valida_nome("  Il-Mio-Server ") == "il-mio-server"


@pytest.mark.parametrize("storto", ["rosso", "#fff", "#gggggg", "#12345", "#1234567", "red;}", "#aabbcc;x", "url(x)", "#ａａｂｂｃｃ"])
def test_colori_non_validi(storto):
    with pytest.raises(ImpostazioneNonValida):
        join.valida_colore(storto)


def test_colori_validi_e_vuoto():
    assert join.valida_colore("#C24A3A") == "#c24a3a" and join.valida_colore("  ") is None


def test_il_foglio_dei_colori_ignora_valori_non_esadecimali():
    assert join.foglio_colori("red;}body{x:y", "#07070b") .count("red") == 0
    assert join.foglio_colori(None, None) == ""
    css = join.foglio_colori("#c24a3a", "#07070b")
    assert css.startswith(":root{") and "--accento:#c24a3a" in css and "--sfondo:#07070b" in css and "--testo:#ececf2" in css
    assert "--testo:#1d1d24" in join.foglio_colori(None, "#f0f0f0")  # sfondo chiaro: testo scuro


@pytest.mark.asyncio
async def test_nome_unico_tra_i_server(jn, clean_db):
    await _accendi("nome-unico")
    await clean_db.execute("INSERT INTO web_panel_pubblico (guild_id) VALUES (999)")
    with pytest.raises(ImpostazioneNonValida):
        await join.imposta_pagina(999, True, "nome-unico", "", "", 1)
    assert (await repo.leggi(999)).join_slug is None
    await _accendi("nome-unico")  # lo stesso server può risalvarlo


@pytest.mark.asyncio
async def test_pagina_sul_nome_o_sull_id(jn):
    await _accendi("")  # senza nome: vale l'ID
    assert await repo.guild_da_join(str(GUILD)) == GUILD
    await _accendi("scelto")
    assert await repo.guild_da_join("scelto") == GUILD
    assert await repo.guild_da_join(str(GUILD)) is None  # con un nome scelto l'ID non vale più
    await _accendi("scelto", attiva=False)
    assert await repo.guild_da_join("scelto") is None
    assert await repo.guild_da_join("9" * 30) is None and await repo.guild_da_join(str(2**63)) is None


# --- la pagina pubblica ------------------------------------------------------
@pytest.mark.asyncio
async def test_pagina_mostra_nome_icona_e_colori_con_escape(jn):
    await _accendi()
    client = await _client(jn.app)
    try:
        r = await client.get("/join/il-mio-server")
        testo = await r.text()
        assert r.status == 200
        assert "Server &lt;b&gt;di&lt;/b&gt; prova" in testo and "<b>di</b>" not in testo  # il nome del server è escapato
        assert ICONA in testo and "/join/il-mio-server/colori.css" in testo
        assert "Accedi con Discord per continuare" in testo  # non è entrato: nessun pulsante di consenso
        css = await client.get("/join/il-mio-server/colori.css")
        assert css.status == 200 and css.content_type == "text/css" and "--accento:#c24a3a" in await css.text()
        assert "style-src 'self'" in r.headers["Content-Security-Policy"] and "unsafe-inline" not in r.headers["Content-Security-Policy"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_icona_fuori_dal_cdn_di_discord_non_si_mostra(jn):
    jn.guild.icon = SimpleNamespace(url="https://evil.test/x.png")
    await _accendi()
    client = await _client(jn.app)
    try:
        assert "evil.test" not in await (await client.get("/join/il-mio-server")).text()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_stessa_risposta_per_ogni_motivo_di_non_disponibilita(jn, clean_db, monkeypatch):
    client = await _client(jn.app)
    try:
        async def corpo(percorso):
            r = await client.get(percorso)
            return r.status, await r.text()

        inesistente = await corpo("/join/non-esiste")
        spenta = None
        await _accendi("spenta", attiva=False)
        spenta = await corpo("/join/spenta")
        await _accendi("viva")
        await db.set_guild_setting(GUILD, "backup_restore_mode", MODE_CLASSIC_INVITE)
        classico = await corpo("/join/viva")
        await db.set_guild_setting(GUILD, "backup_restore_mode", MODE_VERIFY_OAUTH)
        assert (await corpo("/join/viva"))[0] == 200
        jn.bot.get_guild.side_effect = lambda gid: None  # il bot non è più nel server
        senza_bot = await corpo("/join/viva")
        id_numerico = await corpo(f"/join/{GUILD}")
        fuori_misura = await corpo("/join/" + "9" * 40)
        colori = [(await client.get(p)).status for p in ("/join/non-esiste/colori.css", "/join/viva/colori.css")]
        assert inesistente[0] == 404 and inesistente == spenta == classico == senza_bot == id_numerico
        assert fuori_misura[0] == 404 and colori == [404, 404]
        assert "viva" not in inesistente[1] and "Server" not in inesistente[1]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_senza_chiavi_del_ripristino_la_pagina_non_c_e(jn, clean_db):
    await _accendi()
    app = build_app(
        bot=jn.bot, sessioni=WebPanelSessionRepository(pool_provider=lambda: clean_db), oauth=jn.oauth, client_id="1234",
        client_secret="s" * 8, url_pubblico=URL, chiave=secrets.token_urlsafe(48),
    )
    client = await _client(app)
    try:
        assert (await client.get("/join/il-mio-server")).status == 404
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_limite_per_ip_sulle_pagine_pubbliche(jn):
    client = await _client(jn.app)
    try:
        codici = {(await client.get("/join/non-esiste")).status for _ in range(40)}
        assert 429 in codici and 404 in codici
    finally:
        await client.close()


# --- dal consenso al ripristino ----------------------------------------------
@pytest.mark.asyncio
async def test_accesso_e_ritorno_solo_alla_pagina_di_consenso(jn):
    await _accendi()
    client = await _client(jn.app)
    try:
        r = await client.get("/join/il-mio-server/accedi", allow_redirects=False)
        assert r.status == 302 and r.headers["Location"] == "/accedi"
        assert "iyokai_ritorno=" in r.headers["Set-Cookie"] and "/join/il-mio-server" in r.headers["Set-Cookie"]
        fine = await _entra(client)
        assert fine.headers["Location"] == "/join/il-mio-server"
        pagina = await (await client.get("/join/il-mio-server")).text()
        assert "Autorizzo il rientro" in pagina
        # una destinazione non ammessa nel cookie non porta da nessuna parte
        client.session.cookie_jar.update_cookies({"iyokai_ritorno": "https://evil.test/"})
        fine = await _entra(client)
        assert fine.headers["Location"] == "/"
        assert (await client.get("/join/non-esiste/accedi", allow_redirects=False)).status == 404
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_avvio_usa_lo_stesso_state_del_ripristino(jn):
    await _accendi()
    client = await _client(jn.app)
    try:
        assert (await client.post("/join/il-mio-server/avvia", data={}, allow_redirects=False)).headers["Location"] == "/accedi"
        await _entra(client)
        assert (await client.post("/join/il-mio-server/avvia", data={"csrf": "no"}, allow_redirects=False)).status == 403
        csrf = await _csrf(client, "/join/il-mio-server")
        r = await client.post("/join/il-mio-server/avvia", data={"csrf": csrf}, allow_redirects=False)
        assert r.status == 302
        u = urlparse(r.headers["Location"])
        q = parse_qs(u.query)
        assert (u.netloc, u.path) == ("discord.com", "/oauth2/authorize")
        assert q["client_id"] == ["1234"] and q["redirect_uri"] == [REDIRECT] and q["scope"] == ["identify guilds.join"]
        stato = decode_and_verify_state(q["state"][0], CHIAVE)
        assert (stato.source_guild_id, stato.target_guild_id, stato.user_id) == (GUILD, CONSENT_ONLY_TARGET, ADMIN)
        assert CHIAVE not in r.headers["Location"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_il_link_della_pagina_passa_dalla_callback_del_ripristino_senza_cambiarla(jn):
    await _accendi()
    client = await _client(jn.app)
    try:
        await _entra(client)
        csrf = await _csrf(client, "/join/il-mio-server")
        r = await client.post("/join/il-mio-server/avvia", data={"csrf": csrf}, allow_redirects=False)
        stato = parse_qs(urlparse(r.headers["Location"]).query)["state"][0]
    finally:
        await client.close()

    salvati = []

    class Repo:
        async def save_token(self, source, user, access, refresh, scade):
            salvati.append((source, user))
            return True

    def callback(utente_autenticato):
        orch = _FakeOrchestrator(token=ExchangedToken(access_token="a", refresh_token="r", expires_at=None), utente_autenticato=utente_autenticato)
        return restore_app(
            orchestrator=orch, oauth_repo=Repo(), verify_repo_=_FakeVerifyRepo(), client_id="1234", client_secret="x" * 8,
            redirect_uri=REDIRECT, bot_token="t", oauth_encryption_key=CHIAVE, get_guild=lambda g: None,
        ), orch

    # un altro account non entra (SEC-19), lo stesso account sì, una volta sola
    app_x, _ = callback(ESTRANEO)
    cx = TestClient(TestServer(app_x))
    await cx.start_server()
    try:
        assert (await cx.get(f"/oauth/callback?code=c&state={stato}")).status == 403
    finally:
        await cx.close()
    app_ok, orch = callback(ADMIN)
    cok = TestClient(TestServer(app_ok))
    await cok.start_server()
    try:
        assert (await cok.get(f"/oauth/callback?code=c&state={stato}")).status == 200
        assert salvati == [(GUILD, ADMIN)] and orch.chiamate_join == []  # solo consenso: nessuno viene aggiunto adesso
        assert (await cok.get(f"/oauth/callback?code=c&state={stato}")).status == 400  # già usato
    finally:
        await cok.close()


@pytest.mark.asyncio
async def test_avvio_a_pagina_spenta_non_crea_link(jn):
    await _accendi()
    client = await _client(jn.app)
    try:
        await _entra(client)
        csrf = await _csrf(client, "/join/il-mio-server")
        await _accendi(attiva=False)
        r = await client.post("/join/il-mio-server/avvia", data={"csrf": csrf}, allow_redirects=False)
        assert r.status == 404 and "Location" not in r.headers
    finally:
        await client.close()


# --- impostazioni del server -------------------------------------------------
@pytest.mark.asyncio
async def test_impostazioni_solo_per_chi_gestisce_il_ripristino(jn):
    client = await _client(jn.app)
    try:
        assert (await client.get(f"/server/{GUILD}/join", allow_redirects=False)).headers["Location"] == "/accedi"
        await _entra(client)
        assert (await client.get(f"/server/{GUILD}/join")).status == 200
        jn.permessi[ADMIN] = False  # riletto a ogni richiesta
        assert (await client.get(f"/server/{GUILD}/join")).status == 403
        csrf = await _csrf(client, "/")
        r = await client.post(f"/server/{GUILD}/join", data={"csrf": csrf, "attiva": "1", "nome": "x-y-z"}, allow_redirects=False)
        assert r.status == 403 and (await repo.leggi(GUILD)).join_attiva is False
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_salvataggio_dal_pannello_con_csrf_e_errori(jn):
    client = await _client(jn.app)
    try:
        await _entra(client)
        csrf = await _csrf(client, f"/server/{GUILD}/join")
        dati = {"csrf": csrf, "attiva": "1", "nome": "mio-server", "accento": "#c24a3a", "sfondo": "#07070b"}
        assert (await client.post(f"/server/{GUILD}/join", data={**dati, "csrf": "no"}, allow_redirects=False)).status == 403
        r = await client.post(f"/server/{GUILD}/join", data=dati, allow_redirects=False)
        assert r.status == 302 and "esito=join_salvata" in r.headers["Location"]
        p = await repo.leggi(GUILD)
        assert (p.join_attiva, p.join_slug, p.join_accento, p.join_sfondo) == (True, "mio-server", "#c24a3a", "#07070b")
        assert "mio-server" in await (await client.get(f"/server/{GUILD}/join")).text()
        for storto in ({"nome": "admin"}, {"nome": "ab"}, {"accento": "red"}, {"sfondo": "#12"}):
            r = await client.post(f"/server/{GUILD}/join", data={**dati, **storto}, allow_redirects=False)
            assert r.status == 400, storto
            assert (await repo.leggi(GUILD)).join_slug == "mio-server"  # niente è cambiato
        r = await client.post(f"/server/{GUILD}/join", data={"csrf": csrf}, allow_redirects=False)  # senza «accesa» = spenta
        assert "esito=join_spenta" in r.headers["Location"] and (await repo.leggi(GUILD)).join_attiva is False
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_nome_nei_form_con_html_resta_escapato(jn, clean_db):
    await clean_db.execute("INSERT INTO web_panel_pubblico (guild_id, join_attiva) VALUES ($1, TRUE) ON CONFLICT (guild_id) DO UPDATE SET join_attiva = TRUE", GUILD)
    client = await _client(jn.app)
    try:
        await _entra(client)
        csrf = await _csrf(client, f"/server/{GUILD}/join")
        r = await client.post(f"/server/{GUILD}/join", data={"csrf": csrf, "nome": '"><script>x</script>'})
        testo = await r.text()
        assert r.status == 400 and "<script>x" not in testo
    finally:
        await client.close()
