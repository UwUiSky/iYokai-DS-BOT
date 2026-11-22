"""
tests/test_panel_ruoli_collegati.py
===================================
Ruoli collegati per affiliati e partner Twitch (ALR-049, SPEC §24.9): flusso in due passi (Twitch, poi Discord) con
`state` firmato e monouso, token cifrati, metadati registrati, configurazione mancante. La rete è finta: la prova dal
vivo è in VERIFICA_LIVE. Sessioni e database veri.
"""

from urllib.parse import parse_qs, urlparse

import pytest

from core import oauth_crypto, ruoli_collegati_logic as logica, web_panel_ruoli_collegati as pagina_rc
from core.repositories.ruoli_collegati_repo import ruoli_collegati_repo
from tests.test_web_panel_server import ADMIN, ESTRANEO, GUILD, _client, _csrf, _entra, ambiente  # noqa: F401

BASE = "/ruoli-collegati"
CHIAVE = oauth_crypto.generate_key()
SEGRETO_TWITCH = "SEGRETO-TWITCH-NON-MOSTRARE"


class ReteFinta:
    def __init__(self):
        self.tipo = "affiliate"
        self.discord_utente_id = ADMIN
        self.scrittura_ok = True
        self.scritti = []
        self.metadati = 0

    async def twitch_scambia(self, code, redirect_uri):
        return logica.TokenOAuth("twitch-access-1", "twitch-refresh-1", None) if code == "buono" else None

    async def twitch_utente(self, access):
        return {"data": [{"id": "123", "login": "mario_tv", "broadcaster_type": self.tipo}]}

    async def discord_scambia(self, code, redirect_uri):
        return logica.TokenOAuth("discord-access-1", "discord-refresh-1", None) if code == "buono" else None

    async def discord_utente(self, access):
        return self.discord_utente_id

    async def discord_scrivi_collegamento(self, access, corpo):
        self.scritti.append(corpo)
        return self.scrittura_ok

    async def registra_metadati(self, metadati):
        self.metadati += 1
        return True


@pytest.fixture
def rc(ambiente, clean_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(ruoli_collegati_repo, "_pool_provider", lambda: clean_db)
    rete = ReteFinta()
    cfg = logica.Configurazione("twitch-client", SEGRETO_TWITCH, CHIAVE, "token-bot")
    monkeypatch.setattr(pagina_rc, "leggi_configurazione", lambda: cfg)
    monkeypatch.setattr(pagina_rc, "crea_rete", lambda *a, **k: rete)
    monkeypatch.setattr(logica, "_USATI", {})
    ambiente.rete, ambiente.cfg = rete, cfg
    return ambiente


def _state(location):
    return parse_qs(urlparse(location).query)["state"][0]


async def _avvia(client):
    csrf = await _csrf(client, BASE)
    return await client.post(f"{BASE}/avvia", data={"csrf": csrf}, allow_redirects=False), csrf


async def _fino_a_discord(client):
    r, csrf = await _avvia(client)
    t = await client.get(f"{BASE}/twitch?code=buono&state={_state(r.headers['Location'])}", allow_redirects=False)
    return r, t, csrf


@pytest.mark.asyncio
async def test_flusso_completo_token_cifrati_e_metadati(rc):
    client = await _client(rc.app)
    try:
        assert (await client.get(BASE, allow_redirects=False)).headers["Location"] == "/accedi"
        await _entra(client)
        pagina = await (await client.get(BASE)).text()
        assert "Collega Twitch" in pagina and SEGRETO_TWITCH not in pagina
        assert rc.rete.metadati == 1
        await client.get(BASE)
        assert rc.rete.metadati == 1  # registrati una volta sola per processo

        r, t, csrf = await _fino_a_discord(client)
        assert r.status == 302 and r.headers["Location"].startswith("https://id.twitch.tv/oauth2/authorize?")
        q = parse_qs(urlparse(r.headers["Location"]).query)
        assert q["client_id"] == ["twitch-client"] and q["redirect_uri"][0].endswith("/ruoli-collegati/twitch")
        assert SEGRETO_TWITCH not in r.headers["Location"]
        assert t.status == 302 and t.headers["Location"].startswith("https://discord.com/oauth2/authorize?")
        qd = parse_qs(urlparse(t.headers["Location"]).query)
        assert "role_connections.write" in qd["scope"][0] and qd["redirect_uri"][0].endswith("/ruoli-collegati/discord")
        assert await ruoli_collegati_repo.stato(ADMIN) is None  # a metà: ancora non collegato

        d = await client.get(f"{BASE}/discord?code=buono&state={_state(t.headers['Location'])}", allow_redirects=False)
        assert d.status == 302 and "esito=rc_collegato" in d.headers["Location"]
        assert rc.rete.scritti == [{
            "platform_name": "Twitch", "platform_username": "mario_tv",
            "metadata": {"twitch_affiliato": True, "twitch_partner": False},
        }]
        stato = await ruoli_collegati_repo.stato(ADMIN)
        assert (stato.twitch_login, stato.tipo) == ("mario_tv", "affiliate")
        righe = await rc.pool.fetch("SELECT * FROM ruoli_collegati_twitch")
        riga = dict(righe[0])
        for campo, chiaro in (("twitch_token", "twitch-access-1"), ("twitch_refresh", "twitch-refresh-1"),
                              ("discord_token", "discord-access-1"), ("discord_refresh", "discord-refresh-1")):
            assert chiaro not in riga[campo] and riga[campo].startswith("v2.")
            assert logica.decifra(CHIAVE, ADMIN, campo, riga[campo]) == chiaro
        finale = await (await client.get(BASE)).text()
        assert "mario_tv" in finale and "affiliato" in finale.lower()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_partner_e_nessun_tipo(rc):
    for tipo, atteso in (("partner", (False, True)), ("", (False, False)), ("<script>", (False, False))):
        rc.rete.tipo, rc.rete.scritti = tipo, []
        client = await _client(rc.app)
        try:
            await _entra(client)
            _, t, _ = await _fino_a_discord(client)
            await client.get(f"{BASE}/discord?code=buono&state={_state(t.headers['Location'])}", allow_redirects=False)
            meta = rc.rete.scritti[0]["metadata"]
            assert (meta["twitch_affiliato"], meta["twitch_partner"]) == atteso
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_senza_configurazione_la_pagina_lo_dice_e_niente_si_rompe(rc, monkeypatch):
    monkeypatch.setattr(pagina_rc, "leggi_configurazione", lambda: logica.Configurazione())
    client = await _client(rc.app)
    try:
        await _entra(client)
        pagina = await (await client.get(BASE)).text()
        assert "non è configurato" in pagina and "TWITCH_CLIENT_ID" in pagina and "Collega Twitch" not in pagina
        r = await client.post(f"{BASE}/avvia", data={"csrf": "x"}, allow_redirects=False)
        assert r.status in (403, 200, 302) and "twitch.tv" not in r.headers.get("Location", "")
        for percorso in ("twitch", "discord"):
            r = await client.get(f"{BASE}/{percorso}?code=buono&state=x", allow_redirects=False)
            assert r.status == 400
        assert rc.rete.metadati == 0
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_state_non_valido_scaduto_riusato_o_di_un_altro(rc, monkeypatch):
    client = await _client(rc.app)
    try:
        await _entra(client)
        r, csrf = await _avvia(client)
        buono = _state(r.headers["Location"])
        casi = ["", "x", buono + "x", buono[:-3], logica.crea_state(CHIAVE + "A", ADMIN, "tw"),
                logica.crea_state(CHIAVE, ADMIN, "dc"),  # scopo sbagliato
                logica.crea_state(CHIAVE, ESTRANEO, "tw"),  # di un altro utente
                logica.crea_state(CHIAVE, ADMIN, "tw", ora=1.0)]  # scaduto
        for st in casi:
            x = await client.get(f"{BASE}/twitch?code=buono&state={st}", allow_redirects=False)
            assert x.status == 400, st
        assert await rc.pool.fetchval("SELECT count(*) FROM ruoli_collegati_twitch") == 0
        ok = await client.get(f"{BASE}/twitch?code=buono&state={buono}", allow_redirects=False)
        assert ok.status == 302
        riuso = await client.get(f"{BASE}/twitch?code=buono&state={buono}", allow_redirects=False)
        assert riuso.status == 400
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_codice_rifiutato_o_discord_di_un_altro_utente_non_collega(rc):
    client = await _client(rc.app)
    try:
        await _entra(client)
        r, csrf = await _avvia(client)
        x = await client.get(f"{BASE}/twitch?code=cattivo&state={_state(r.headers['Location'])}", allow_redirects=False)
        assert x.status == 400 and "cattivo" not in await x.text()
        assert await rc.pool.fetchval("SELECT count(*) FROM ruoli_collegati_twitch") == 0

        _, t, _ = await _fino_a_discord(client)
        rc.rete.discord_utente_id = ESTRANEO  # il token Discord è di un'altra persona
        d = await client.get(f"{BASE}/discord?code=buono&state={_state(t.headers['Location'])}", allow_redirects=False)
        assert d.status == 400 and rc.rete.scritti == []
        assert await ruoli_collegati_repo.stato(ADMIN) is None

        rc.rete.discord_utente_id = ADMIN
        _, t, _ = await _fino_a_discord(client)
        rc.rete.scrittura_ok = False  # Discord non accetta il collegamento
        d = await client.get(f"{BASE}/discord?code=buono&state={_state(t.headers['Location'])}", allow_redirects=False)
        assert "esito=rc_non_riuscito" in d.headers["Location"]
        assert await ruoli_collegati_repo.stato(ADMIN) is None
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_csrf_sulle_scritture_e_scollega(rc):
    client = await _client(rc.app)
    try:
        await _entra(client)
        assert (await client.post(f"{BASE}/avvia", data={})).status == 403
        assert (await client.post(f"{BASE}/scollega", data={})).status == 403
        _, t, csrf = await _fino_a_discord(client)
        await client.get(f"{BASE}/discord?code=buono&state={_state(t.headers['Location'])}", allow_redirects=False)
        assert await ruoli_collegati_repo.stato(ADMIN) is not None
        r = await client.post(f"{BASE}/scollega", data={"csrf": csrf}, allow_redirects=False)
        assert r.status == 302 and "esito=rc_scollegato" in r.headers["Location"]
        assert await rc.pool.fetchval("SELECT count(*) FROM ruoli_collegati_twitch") == 0
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_senza_accesso_i_callback_e_le_scritture_non_fanno_niente(rc):
    client = await _client(rc.app)
    try:
        for metodo, percorso in ((client.get, f"{BASE}/twitch?code=buono&state=x"), (client.get, f"{BASE}/discord?code=buono&state=x"),
                                 (client.post, f"{BASE}/avvia"), (client.post, f"{BASE}/scollega")):
            r = await metodo(percorso, allow_redirects=False)
            assert r.status in (302, 403) and (r.status == 403 or r.headers["Location"] == "/accedi")
    finally:
        await client.close()


def test_la_tabella_e_nel_registro_dei_dati_senza_esportare_i_token():
    from core.data_registry import REGISTRO

    t = next(x for x in REGISTRO if x.nome == "ruoli_collegati_twitch")
    assert {"twitch_token", "discord_token"} <= set(t.escludi_dall_esportazione)
