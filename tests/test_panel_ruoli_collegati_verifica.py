"""
tests/test_panel_ruoli_collegati_verifica.py
============================================
Verifica con i ruoli collegati di Discord (VER-027, D111, SPEC §24.10): un solo passo su Discord con `state` firmato e
monouso (scopo diverso da Twitch), token cifrati, valori «verifica superata», «età in giorni» e «avatar presente»,
corpo unico con Twitch, aggiornamento quando la verifica riesce. La rete è finta: la prova dal vivo è in VERIFICA_LIVE.
"""

import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from core import oauth_crypto, ruoli_collegati_logic as logica, ruoli_collegati_verifica as servizio, web_panel_ruoli_collegati as pagina_rc
from core.repositories.ruoli_collegati_repo import ruoli_collegati_repo
from core.repositories.ruoli_collegati_verifica_repo import ruoli_collegati_verifica_repo as repo
from tests.test_panel_ruoli_collegati import ReteFinta as ReteTwitch
from tests.test_web_panel_server import ADMIN, ESTRANEO, _client, _csrf, _entra, ambiente  # noqa: F401

BASE = "/ruoli-collegati"
CHIAVE = oauth_crypto.generate_key()


class ReteFinta(ReteTwitch):
    def __init__(self):
        super().__init__()
        self.avatar = True
        self.profilo_id = ADMIN
        self.rinnovi = 0
        self.rinnovo_ok = True

    async def discord_profilo(self, access):
        return (self.profilo_id, self.avatar)

    async def discord_rinnova(self, refresh):
        self.rinnovi += 1
        return logica.TokenOAuth("discord-access-2", "discord-refresh-2", None) if self.rinnovo_ok else None


@pytest.fixture
def vf(ambiente, clean_db, monkeypatch):  # noqa: F811
    for r in (ruoli_collegati_repo, repo):
        monkeypatch.setattr(r, "_pool_provider", lambda: clean_db)
    rete = ReteFinta()
    cfg = logica.Configurazione("twitch-client", "segreto-twitch", CHIAVE, "token-bot")
    monkeypatch.setattr(pagina_rc, "leggi_configurazione", lambda: cfg)
    monkeypatch.setattr(pagina_rc, "crea_rete", lambda *a, **k: rete)
    monkeypatch.setattr(servizio, "crea_rete_da_config", lambda: (cfg, rete))
    monkeypatch.setattr(logica, "_USATI", {})
    ambiente.rete, ambiente.cfg = rete, cfg
    return ambiente


def _state(location):
    return parse_qs(urlparse(location).query)["state"][0]


async def _avvia(client):
    csrf = await _csrf(client, BASE)
    return await client.post(f"{BASE}/verifica/avvia", data={"csrf": csrf}, allow_redirects=False), csrf


async def _successo(pool, user_id=ADMIN, guild_id=1):
    await pool.execute("INSERT INTO verify_attempts (guild_id, user_id, success, reason) VALUES ($1, $2, TRUE, 'ok')", guild_id, user_id)


@pytest.mark.asyncio
async def test_flusso_completo_valori_token_cifrati_e_state(vf, clean_db):
    await _successo(clean_db)
    client = await _client(vf.app)
    try:
        await _entra(client)
        pagina = await (await client.get(BASE)).text()
        assert "Collega la verifica" in pagina
        r, _ = await _avvia(client)
        assert r.status == 302 and r.headers["Location"].startswith("https://discord.com/oauth2/authorize?")
        q = parse_qs(urlparse(r.headers["Location"]).query)
        assert q["redirect_uri"][0].endswith("/ruoli-collegati/discord") and "role_connections.write" in q["scope"][0]
        stato = _state(r.headers["Location"])
        assert logica.verifica_state(CHIAVE, stato, logica.SCOPO_VERIFICA, consuma=False) == ADMIN

        d = await client.get(f"{BASE}/discord?code=buono&state={stato}", allow_redirects=False)
        assert d.status == 302 and "esito=rc_verifica_collegata" in d.headers["Location"]
        (corpo,) = vf.rete.scritti
        assert corpo["metadata"] == {"verifica_superata": True, "eta_account_giorni": logica.eta_giorni(ADMIN), "avatar_presente": True}
        assert "twitch_affiliato" not in corpo["metadata"]  # Twitch non è collegato: nessuna chiave sua
        riga = dict((await clean_db.fetch("SELECT * FROM ruoli_collegati_verifica"))[0])
        assert riga["verificato"] is True and riga["avatar_presente"] is True
        for campo, chiaro in (("discord_token", "discord-access-1"), ("discord_refresh", "discord-refresh-1")):
            assert chiaro not in riga[campo] and riga[campo].startswith("v2.")
        assert logica.decifra(CHIAVE, ADMIN, "verifica_token", riga["discord_token"]) == "discord-access-1"
        finale = await (await client.get(BASE)).text()
        assert "Verifica superata:" in finale and "discord-access-1" not in finale

        # il `state` vale una volta sola
        again = await client.get(f"{BASE}/discord?code=buono&state={stato}", allow_redirects=False)
        assert again.status == 400 and len(vf.rete.scritti) == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_senza_verifica_passata_il_valore_e_falso(vf, clean_db):
    vf.rete.avatar = False
    client = await _client(vf.app)
    try:
        await _entra(client)
        r, _ = await _avvia(client)
        await client.get(f"{BASE}/discord?code=buono&state={_state(r.headers['Location'])}", allow_redirects=False)
        meta = vf.rete.scritti[0]["metadata"]
        assert meta["verifica_superata"] is False and meta["avatar_presente"] is False
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_state_di_un_altro_utente_o_manomesso_o_scaduto_o_di_twitch(vf, clean_db):
    client = await _client(vf.app)
    try:
        await _entra(client)
        cattivi = {
            "altro utente": logica.crea_state(CHIAVE, ESTRANEO, logica.SCOPO_VERIFICA),
            "scaduto": logica.crea_state(CHIAVE, ADMIN, logica.SCOPO_VERIFICA, ora=time.time() - 3600),
            "chiave diversa": logica.crea_state(oauth_crypto.generate_key(), ADMIN, logica.SCOPO_VERIFICA),
            "manomesso": logica.crea_state(CHIAVE, ADMIN, logica.SCOPO_VERIFICA)[:-3] + "abc",
            "assente": "",
        }
        for nome, stato in cattivi.items():
            r = await client.get(f"{BASE}/discord?code=buono&state={stato}", allow_redirects=False)
            assert r.status == 400, nome
        # uno `state` di verifica non vale sul passo di Twitch
        buono = logica.crea_state(CHIAVE, ADMIN, logica.SCOPO_VERIFICA)
        assert (await client.get(f"{BASE}/twitch?code=buono&state={buono}", allow_redirects=False)).status == 400
        assert vf.rete.scritti == [] and await repo.leggi(ADMIN) is None
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_token_di_un_altro_account_non_si_salva(vf, clean_db):
    vf.rete.profilo_id = ESTRANEO
    client = await _client(vf.app)
    try:
        await _entra(client)
        r, _ = await _avvia(client)
        d = await client.get(f"{BASE}/discord?code=buono&state={_state(r.headers['Location'])}", allow_redirects=False)
        assert d.status == 400 and vf.rete.scritti == [] and await repo.leggi(ADMIN) is None and await repo.leggi(ESTRANEO) is None
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_codice_rifiutato_e_discord_che_non_accetta(vf, clean_db):
    client = await _client(vf.app)
    try:
        await _entra(client)
        r, _ = await _avvia(client)
        assert (await client.get(f"{BASE}/discord?code=sbagliato&state={_state(r.headers['Location'])}", allow_redirects=False)).status == 400
        vf.rete.scrittura_ok = False
        r, _ = await _avvia(client)
        d = await client.get(f"{BASE}/discord?code=buono&state={_state(r.headers['Location'])}", allow_redirects=False)
        assert "esito=rc_non_riuscito" in d.headers["Location"] and await repo.leggi(ADMIN) is None
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_avvio_richiede_sessione_csrf_e_configurazione(vf, clean_db, monkeypatch):
    client = await _client(vf.app)
    try:
        assert (await client.post(f"{BASE}/verifica/avvia", data={}, allow_redirects=False)).headers["Location"] == "/accedi"
        await _entra(client)
        assert (await client.post(f"{BASE}/verifica/avvia", data={"csrf": "sbagliato"}, allow_redirects=False)).status == 403
        assert (await client.post(f"{BASE}/verifica/scollega", data={"csrf": "sbagliato"}, allow_redirects=False)).status == 403
        assert (await client.get(f"{BASE}/verifica/avvia", allow_redirects=False)).status == 405
        csrf = await _csrf(client, BASE)
        monkeypatch.setattr(pagina_rc, "leggi_configurazione", lambda: logica.Configurazione())
        r = await client.post(f"{BASE}/verifica/avvia", data={"csrf": csrf}, allow_redirects=False)
        assert "esito=rc_verifica_non_configurata" in r.headers["Location"]
        assert "Collega la verifica" not in await (await client.get(BASE)).text()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_verifica_senza_twitch_configurato(vf, clean_db, monkeypatch):
    cfg = logica.Configurazione("", "", CHIAVE, "token-bot")  # solo la chiave: la verifica funziona lo stesso
    monkeypatch.setattr(pagina_rc, "leggi_configurazione", lambda: cfg)
    client = await _client(vf.app)
    try:
        await _entra(client)
        pagina = await (await client.get(BASE)).text()
        assert "Collega la verifica" in pagina and vf.rete.metadati == 1
        r, _ = await _avvia(client)
        d = await client.get(f"{BASE}/discord?code=buono&state={_state(r.headers['Location'])}", allow_redirects=False)
        assert "rc_verifica_collegata" in d.headers["Location"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_twitch_e_verifica_stanno_nello_stesso_corpo(vf, clean_db):
    await _successo(clean_db)
    client = await _client(vf.app)
    try:
        await _entra(client)
        r, _ = await _avvia(client)
        await client.get(f"{BASE}/discord?code=buono&state={_state(r.headers['Location'])}", allow_redirects=False)
        # ora collega Twitch: la scrittura deve portare anche i valori della verifica
        csrf = await _csrf(client, BASE)
        a = await client.post(f"{BASE}/avvia", data={"csrf": csrf}, allow_redirects=False)
        t = await client.get(f"{BASE}/twitch?code=buono&state={_state(a.headers['Location'])}", allow_redirects=False)
        await client.get(f"{BASE}/discord?code=buono&state={_state(t.headers['Location'])}", allow_redirects=False)
        meta = vf.rete.scritti[-1]["metadata"]
        assert meta["twitch_affiliato"] is True and meta["verifica_superata"] is True and meta["avatar_presente"] is True
        # scollegare Twitch non toglie la verifica
        csrf = await _csrf(client, BASE)
        await client.post(f"{BASE}/scollega", data={"csrf": csrf}, allow_redirects=False)
        meta = vf.rete.scritti[-1]["metadata"]
        assert meta["twitch_affiliato"] is False and meta["verifica_superata"] is True
        # scollegare la verifica toglie i suoi valori e tiene Twitch (che è già stato scollegato: corpo vuoto di Twitch)
        csrf = await _csrf(client, BASE)
        r = await client.post(f"{BASE}/verifica/scollega", data={"csrf": csrf}, allow_redirects=False)
        assert "rc_verifica_scollegata" in r.headers["Location"] and await repo.leggi(ADMIN) is None
        assert "verifica_superata" not in vf.rete.scritti[-1]["metadata"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_scollega_verifica_con_token_illeggibile_cancella_lo_stesso(vf, clean_db):
    await repo.salva(ADMIN, "v2.rotto", None, None, True, True)
    client = await _client(vf.app)
    try:
        await _entra(client)
        csrf = await _csrf(client, BASE)
        r = await client.post(f"{BASE}/verifica/scollega", data={"csrf": csrf}, allow_redirects=False)
        assert "rc_verifica_scollegata" in r.headers["Location"] and await repo.leggi(ADMIN) is None
    finally:
        await client.close()


# --- aggiornamento quando la verifica del server riesce -----------------------
async def _collegato(clean_db, scade=None, refresh=True):
    await repo.salva(
        ADMIN, logica.cifra(CHIAVE, ADMIN, "verifica_token", "vecchio"),
        logica.cifra(CHIAVE, ADMIN, "verifica_refresh", "refresh-1") if refresh else None, scade, False, False,
    )


@pytest.mark.asyncio
async def test_dopo_la_verifica_i_valori_si_aggiornano(vf, clean_db):
    await _collegato(clean_db)
    assert await servizio.aggiorna_dopo_verifica(ADMIN, avatar_presente=True) is True
    (corpo,) = vf.rete.scritti
    assert corpo["metadata"]["verifica_superata"] is True and corpo["metadata"]["avatar_presente"] is True
    riga = await repo.leggi(ADMIN)
    assert riga.verificato is True and riga.avatar_presente is True


@pytest.mark.asyncio
async def test_dopo_la_verifica_chi_non_ha_collegato_non_cambia_niente(vf, clean_db):
    assert await servizio.aggiorna_dopo_verifica(ESTRANEO, avatar_presente=True) is False
    assert vf.rete.scritti == [] and await repo.leggi(ESTRANEO) is None


@pytest.mark.asyncio
async def test_token_scaduto_si_rinnova_e_si_salva_cifrato(vf, clean_db):
    await _collegato(clean_db, scade=datetime.now(timezone.utc) - timedelta(hours=1))
    assert await servizio.aggiorna_dopo_verifica(ADMIN, avatar_presente=False) is True
    assert vf.rete.rinnovi == 1
    riga = await repo.leggi(ADMIN)
    assert "discord-access-2" not in riga.token and logica.decifra(CHIAVE, ADMIN, "verifica_token", riga.token) == "discord-access-2"


@pytest.mark.asyncio
async def test_token_scaduto_senza_rinnovo_non_scrive_e_non_solleva(vf, clean_db):
    await _collegato(clean_db, scade=datetime.now(timezone.utc) - timedelta(hours=1))
    vf.rete.rinnovo_ok = False
    assert await servizio.aggiorna_dopo_verifica(ADMIN, avatar_presente=True) is False
    assert vf.rete.scritti == []
    await _collegato(clean_db, scade=datetime.now(timezone.utc) - timedelta(hours=1), refresh=False)
    assert await servizio.aggiorna_dopo_verifica(ADMIN, avatar_presente=True) is False


@pytest.mark.asyncio
async def test_errori_di_rete_o_chiave_sbagliata_non_si_propagano(vf, clean_db, monkeypatch):
    await _collegato(clean_db)

    async def esplode(*a, **k):
        raise RuntimeError("rete giù")

    monkeypatch.setattr(vf.rete, "discord_scrivi_collegamento", esplode)
    assert await servizio.aggiorna_dopo_verifica(ADMIN, avatar_presente=True) is False
    # chiave di cifratura cambiata: il token non si legge, niente scritture
    monkeypatch.setattr(servizio, "crea_rete_da_config", lambda: (logica.Configurazione("", "", oauth_crypto.generate_key(), ""), vf.rete))
    assert await servizio.aggiorna_dopo_verifica(ADMIN, avatar_presente=True, cfg=None, rete=None) is False


@pytest.mark.asyncio
async def test_senza_chiavi_del_bot_non_si_fa_niente(vf, clean_db, monkeypatch):
    await _collegato(clean_db)
    monkeypatch.setattr(servizio, "crea_rete_da_config", lambda: (logica.Configurazione(), None))
    assert await servizio.aggiorna_dopo_verifica(ADMIN, avatar_presente=True) is False


@pytest.mark.asyncio
async def test_la_verifica_del_server_chiama_l_aggiornamento(monkeypatch):
    chiamate = []

    async def finta(user_id, *, avatar_presente, **k):
        chiamate.append((user_id, avatar_presente))

    monkeypatch.setattr(servizio, "aggiorna_dopo_verifica", finta)
    servizio.programma_aggiornamento(77, avatar_presente=True)
    import asyncio

    await asyncio.gather(*list(servizio._in_corso))
    assert chiamate == [(77, True)]


# --- metadati, corpo ed età --------------------------------------------------
def test_metadati_dentro_i_limiti_di_discord():
    for con_twitch, attesi in ((True, 5), (False, 3)):
        campi = logica.metadati_applicazione(con_twitch)
        assert len(campi) == attesi <= 5
        for c in campi:
            assert re.fullmatch(r"[a-z0-9_]{1,50}", c["key"]) and len(c["name"]) <= 100 and len(c["description"]) <= 200
            assert c["type"] in (logica.TIPO_BOOLEANO, logica.TIPO_INTERO_MINIMO)
            assert c["name_localizations"]["en-US"] and c["description_localizations"]["en-US"]
        assert len({c["key"] for c in campi}) == len(campi)


def test_eta_giorni_dall_id():
    ora = 1_800_000_000.0
    id_dieci_giorni_fa = (int((ora - 10 * 86400) * 1000) - 1420070400000) << 22
    assert logica.eta_giorni(id_dieci_giorni_fa, ora=ora) == 10
    assert logica.eta_giorni(id_dieci_giorni_fa, ora=ora - 99 * 86400) == 0  # mai negativa
    assert logica.eta_giorni(0) > 0


def test_corpo_solo_twitch_e_come_prima():
    assert logica.corpo_collegamento("mario", "partner") == {
        "platform_name": "Twitch", "platform_username": "mario", "metadata": {"twitch_affiliato": False, "twitch_partner": True},
    }
    solo_verifica = logica.corpo_collegamento("", "", verifica=(True, 400, False), con_twitch=False)
    assert solo_verifica == {"platform_name": "iYokai", "metadata": {"verifica_superata": True, "eta_account_giorni": 400, "avatar_presente": False}}
