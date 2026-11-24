"""
tests/test_panel_ruoli_collegati_invito.py
==========================================
Invito dalle connessioni del profilo (ALR-049, D127, SPEC §24.9): il permesso OAuth `connections` è facoltativo e si
chiede solo con un clic; si leggono i tipi (due sì/no), il token si revoca subito, nessun nome né ID resta; `state`
monouso e legato alla sessione; «Dimentica» cancella; la pagina propone Twitch e mostra i ruoli dei server in comune.
Rete finta.
"""

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from core import oauth_crypto, ruoli_collegati_logic as logica, web_panel_ruoli_collegati as pagina_rc
from core.repositories.ruoli_collegati_connessioni_repo import ruoli_collegati_connessioni_repo as repo
from core.repositories.ruoli_collegati_repo import ruoli_collegati_repo
from tests.test_panel_ruoli_collegati import ReteFinta as ReteBase
from tests.test_web_panel_server import ADMIN, ESTRANEO, _client, _csrf, _entra, ambiente  # noqa: F401

BASE = "/ruoli-collegati"
CHIAVE = oauth_crypto.generate_key()


class Rete(ReteBase):
    def __init__(self):
        super().__init__()
        self.tipi = ["twitch", "steam"]
        self.revocati = []
        self.letture = 0

    async def discord_connessioni(self, access):
        self.letture += 1
        return self.tipi

    async def discord_revoca(self, access):
        self.revocati.append(access)
        return True


@pytest.fixture
def cn(ambiente, clean_db, monkeypatch):  # noqa: F811
    for r in (ruoli_collegati_repo, repo):
        monkeypatch.setattr(r, "_pool_provider", lambda: clean_db)
    rete = Rete()
    cfg = logica.Configurazione("twitch-client", "segreto-twitch", CHIAVE, "token-bot")
    monkeypatch.setattr(pagina_rc, "leggi_configurazione", lambda: cfg)
    monkeypatch.setattr(pagina_rc, "crea_rete", lambda *a, **k: rete)
    monkeypatch.setattr(logica, "_USATI", {})
    ambiente.rete = rete
    return ambiente


def _state(location):
    return parse_qs(urlparse(location).query)["state"][0]


async def _avvia(client):
    csrf = await _csrf(client, BASE)
    return await client.post(f"{BASE}/connessioni/avvia", data={"csrf": csrf}, allow_redirects=False), csrf


@pytest.mark.asyncio
async def test_senza_clic_il_bot_non_legge_niente(cn, clean_db):
    client = await _client(cn.app)
    try:
        await _entra(client)
        pagina = await (await client.get(BASE)).text()
        assert "Controlla i miei collegamenti" in pagina
        assert cn.rete.letture == 0 and await repo.leggi(ADMIN) is None
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_flusso_salva_solo_due_si_no_e_revoca_il_token(cn, clean_db):
    client = await _client(cn.app)
    try:
        await _entra(client)
        r, _ = await _avvia(client)
        q = parse_qs(urlparse(r.headers["Location"]).query)
        assert r.status == 302 and q["scope"] == ["identify connections"]
        assert q["redirect_uri"][0].endswith("/ruoli-collegati/discord")  # nessun nuovo indirizzo da registrare
        stato = _state(r.headers["Location"])
        d = await client.get(f"{BASE}/discord?code=buono&state={stato}", allow_redirects=False)
        assert d.status == 302 and "esito=rc_connessioni_ok" in d.headers["Location"]
        c = await repo.leggi(ADMIN)
        assert (c.ha_twitch, c.ha_kick) == (True, False)
        assert cn.rete.revocati == ["discord-access-1"] and cn.rete.scritti == []
        colonne = await clean_db.fetchval("SELECT string_agg(column_name, ',') FROM information_schema.columns WHERE table_name = 'ruoli_collegati_connessioni'")
        assert set(colonne.split(",")) == {"user_id", "ha_twitch", "ha_kick", "controllato_il"}
        # lo `state` vale una volta sola
        assert (await client.get(f"{BASE}/discord?code=buono&state={stato}", allow_redirects=False)).status == 400
        assert cn.rete.letture == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_state_altrui_o_token_di_un_altra_persona_non_salvano(cn, clean_db):
    client = await _client(cn.app)
    try:
        await _entra(client)
        altrui = logica.crea_state(CHIAVE, ESTRANEO, logica.SCOPO_CONNESSIONI)
        assert (await client.get(f"{BASE}/discord?code=buono&state={altrui}", allow_redirects=False)).status == 400
        cn.rete.discord_utente_id = ESTRANEO  # il token è di un'altra persona
        mio = logica.crea_state(CHIAVE, ADMIN, logica.SCOPO_CONNESSIONI)
        assert (await client.get(f"{BASE}/discord?code=buono&state={mio}", allow_redirects=False)).status == 400
        assert cn.rete.letture == 0 and await repo.leggi(ADMIN) is None and cn.rete.revocati == ["discord-access-1"]
        # lo `state` delle connessioni non vale per Twitch
        buono = logica.crea_state(CHIAVE, ADMIN, logica.SCOPO_CONNESSIONI)
        assert (await client.get(f"{BASE}/twitch?code=buono&state={buono}", allow_redirects=False)).status == 400
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_avvio_serve_csrf_e_sessione(cn):
    client = await _client(cn.app)
    try:
        assert (await client.post(f"{BASE}/connessioni/avvia", data={}, allow_redirects=False)).headers["Location"] == "/accedi"
        await _entra(client)
        r = await client.post(f"{BASE}/connessioni/avvia", data={"csrf": "sbagliato"}, allow_redirects=False)
        assert r.status in (400, 403)
        r = await client.post(f"{BASE}/connessioni/dimentica", data={"csrf": "sbagliato"}, allow_redirects=False)
        assert r.status in (400, 403)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_la_pagina_propone_twitch_e_kick_e_dimentica_cancella(cn, clean_db):
    await repo.salva(ADMIN, True, True)
    client = await _client(cn.app)
    try:
        await _entra(client)
        pagina = await (await client.get(BASE)).text()
        assert "ha Twitch collegato" in pagina and "Kick" in pagina and "Dimentica" in pagina
        csrf = await _csrf(client, BASE)
        r = await client.post(f"{BASE}/connessioni/dimentica", data={"csrf": csrf}, allow_redirects=False)
        assert "esito=rc_connessioni_dimenticate" in r.headers["Location"] and await repo.leggi(ADMIN) is None
        assert "ha Twitch collegato" not in await (await client.get(BASE)).text()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_kick_si_riconosce_e_i_tipi_strani_no(cn):
    assert logica.piattaforme_collegate(["Kick", "steam"]) == (False, True)
    assert logica.piattaforme_collegate(["twitch", 5, None]) == (True, False)
    assert logica.piattaforme_collegate("twitch") == (False, False) and logica.piattaforme_collegate(None) == (False, False)


def _guild(nome, membri, ruoli):
    return SimpleNamespace(
        name=nome, get_member=lambda u: object() if u in membri else None,
        roles=[SimpleNamespace(name=n, tags=SimpleNamespace(is_guild_connection=lambda c=c: c) if c is not None else None) for n, c in ruoli],
    )


def test_server_in_comune_con_ruoli_collegati():
    guilds = [
        _guild("Uno", {5}, [("Twitch sub", True), ("Admin", False), ("Senza tag", None)]),
        _guild("Due", {6}, [("Twitch", True)]),   # la persona non c'è
        _guild("Tre", {5}, [("Admin", False)]),    # nessun ruolo collegato
    ]
    assert logica.server_con_ruoli_collegati(guilds, 5) == [("Uno", ["Twitch sub"])]
    assert logica.server_con_ruoli_collegati(None, 5) == []
