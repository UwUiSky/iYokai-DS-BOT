"""
tests/test_patreon.py
=====================
CFG-036: Patreon. Spento senza chiavi (nessuna rotta), firma a tempo costante, evento doppio, collegamento OAuth con
stato monouso e token cifrati, livelli Patreon associati ai livelli del bot.
"""

import hashlib
import hmac
import json
from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer

from core import patreon_logic as logica
from core import patreon_server, patreon_service, piani

SEGRETO = "segreto-webhook-1234"
CHIAVE_CIFRATURA = "A" * 43 + "="


def _firma(corpo: bytes, segreto: str = SEGRETO) -> str:
    return hmac.new(segreto.encode(), corpo, hashlib.md5).hexdigest()


def _corpo(utente="u1", stato="active_patron", tiers=("t1",), member="m1") -> bytes:
    return json.dumps({"data": {"id": member, "attributes": {"patron_status": stato}, "relationships": {
        "user": {"data": {"id": utente}}, "currently_entitled_tiers": {"data": [{"id": t} for t in tiers]}}}}).encode()


@pytest.fixture
async def pronto(clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    cfg = SimpleNamespace(PATREON_CLIENT_ID="cid", PATREON_CLIENT_SECRET="csecret-1234", PATREON_WEBHOOK_SECRET=SEGRETO,
                          OAUTH_ENCRYPTION_KEY=CHIAVE_CIFRATURA, WEB_PANEL_PUBLIC_URL="https://pannello.example")
    monkeypatch.setattr(patreon_service, "_config", lambda: cfg)
    return clean_db


class _Cliente:
    def __init__(self, patreon_id="u1", attivo=True, tiers=("t1",)):
        self.dati = (patreon_id, attivo, tiers)

    async def scambia_codice(self, codice):
        assert codice == "codice-ok"
        return {"access_token": "token-di-accesso-segreto", "refresh_token": "refresh-segreto"}

    async def identita(self, token):
        patreon_id, attivo, tiers = self.dati
        return {"data": {"id": patreon_id}, "included": [{"type": "member", "attributes": {"patron_status": "active_patron" if attivo else "former_patron"},
                "relationships": {"currently_entitled_tiers": {"data": [{"id": t} for t in tiers]}}}]}


# ---------------------------------------------------------------- logica pura
def test_firma_valida_solo_con_il_segreto_giusto():
    corpo = b'{"a": 1}'
    assert logica.firma_valida(SEGRETO, corpo, _firma(corpo))
    assert logica.firma_valida(SEGRETO, corpo, _firma(corpo).upper())
    assert not logica.firma_valida(SEGRETO, corpo, _firma(corpo, "altro-segreto-99"))
    assert not logica.firma_valida(SEGRETO, corpo + b" ", _firma(corpo))
    assert not logica.firma_valida(SEGRETO, corpo, None) and not logica.firma_valida(SEGRETO, corpo, "")
    assert not logica.firma_valida("", corpo, _firma(corpo, ""))  # senza segreto mai
    assert not logica.firma_valida("corto", corpo, _firma(corpo, "corto"))


def test_la_firma_si_confronta_a_tempo_costante():
    import inspect

    assert "compare_digest" in inspect.getsource(logica.firma_valida)


def test_chiavi_tutte_necessarie():
    assert logica.chiavi_presenti("a", "12345678", "12345678")
    for argomenti in (("", "12345678", "12345678"), ("a", "", "12345678"), ("a", "12345678", ""), ("a", "123", "12345678")):
        assert not logica.chiavi_presenti(*argomenti)


def test_leggi_evento():
    e = logica.leggi_evento("members:pledge:create", _corpo())
    assert (e.patreon_id, e.attivo, e.tiers, e.member_id) == ("u1", True, ("t1",), "m1")
    assert logica.leggi_evento("members:pledge:delete", _corpo()).attivo is False
    assert logica.leggi_evento("members:update", _corpo(stato="declined_patron")).attivo is False
    assert logica.leggi_evento("campaigns:update", _corpo()) is None
    assert logica.leggi_evento("members:create", b"non json") is None
    assert logica.leggi_evento("members:create", b'{"data": {}}') is None
    assert logica.leggi_evento("members:create", b"x" * (logica.MAX_BYTE_CORPO + 1)) is None


# ---------------------------------------------------------------- server web
@pytest.fixture(autouse=True)
def _tracker_pulito():
    from core.webhook_rate_tracker import webhook_rate_tracker

    webhook_rate_tracker._data.clear()


async def _client(applica=None, completa=None, **chiavi):
    async def _niente(*a, **k):
        return True

    valori = dict(client_id="cid", client_secret="csecret-1234", webhook_secret=SEGRETO)
    valori.update(chiavi)
    app = patreon_server.build_app(applica_evento=applica or _niente, completa_collegamento=completa or _niente, **valori)
    cliente = TestClient(TestServer(app))
    await cliente.start_server()
    return cliente


async def test_senza_chiavi_nessuna_rotta_e_nessun_errore():
    for vuote in ({"client_id": ""}, {"client_secret": ""}, {"webhook_secret": ""}):
        c = await _client(**vuote)
        try:
            assert [r for r in c.server.app.router.routes() if r.resource and r.resource.canonical.startswith("/patreon")] == []
            assert (await c.post("/patreon/webhook", data=b"{}")).status == 404
            assert (await c.get("/patreon/callback?state=a&code=b")).status == 404
        finally:
            await c.close()


async def test_webhook_rifiuta_firma_sbagliata_e_accetta_quella_giusta():
    visti = []

    async def applica(evento, corpo):
        visti.append(evento)
        return True

    c = await _client(applica=applica)
    try:
        corpo = _corpo()
        sbagliata = await c.post("/patreon/webhook", data=corpo, headers={"X-Patreon-Signature": "0" * 32, "X-Patreon-Event": "members:create"})
        assert sbagliata.status == 401 and visti == []
        senza = await c.post("/patreon/webhook", data=corpo, headers={"X-Patreon-Event": "members:create"})
        assert senza.status == 401
        giusta = await c.post("/patreon/webhook", data=corpo, headers={"X-Patreon-Signature": _firma(corpo), "X-Patreon-Event": "members:create"})
        assert giusta.status == 200 and len(visti) == 1
    finally:
        await c.close()


async def test_troppe_firme_sbagliate_bloccano_l_indirizzo():
    c = await _client()
    try:
        stati = [(await c.post("/patreon/webhook", data=b"{}", headers={"X-Patreon-Signature": "x"})).status for _ in range(patreon_server.MAX_TENTATIVI_SBAGLIATI + 2)]
        assert stati[0] == 401 and stati[-1] == 429
    finally:
        await c.close()


async def test_callback_non_rivela_il_motivo_del_rifiuto():
    async def completa(stato, codice):
        raise patreon_service.CollegamentoFallito("stato scaduto")

    c = await _client(completa=completa)
    try:
        r = await c.get("/patreon/callback?state=a&code=b")
        assert r.status == 400 and "scaduto" not in await r.text()
        assert (await c.get("/patreon/callback?code=b")).status == 400
    finally:
        await c.close()


# ---------------------------------------------------------------- servizio
async def test_evento_doppio_si_applica_una_volta(pronto):
    await patreon_service.imposta_livello_tier("t1", "ultra")
    await pronto.execute("INSERT INTO patreon_collegamenti (discord_user_id, patreon_id, token_cifrato) VALUES (5, 'u1', 'x')")
    corpo = _corpo()
    evento = logica.leggi_evento("members:pledge:create", corpo)
    assert await patreon_service.applica_evento(evento, corpo) is True
    assert await piani.livello_utente(5) == piani.ULTRA
    await pronto.execute("DELETE FROM piani_concessioni")  # se il doppione si riapplicasse, tornerebbe la concessione
    assert await patreon_service.applica_evento(evento, corpo) is False
    assert await pronto.fetchval("SELECT count(*) FROM piani_concessioni") == 0
    assert await pronto.fetchval("SELECT count(*) FROM patreon_eventi") == 1


async def test_disdetta_toglie_il_livello_e_livello_non_associato_non_da_niente(pronto):
    await patreon_service.imposta_livello_tier("t1", "premium")
    await pronto.execute("INSERT INTO patreon_collegamenti (discord_user_id, patreon_id, token_cifrato) VALUES (5, 'u1', 'x')")
    for tipo, corpo in (("members:pledge:create", _corpo()), ):
        await patreon_service.applica_evento(logica.leggi_evento(tipo, corpo), corpo)
    assert await piani.livello_utente(5) == piani.PREMIUM
    corpo = _corpo(stato="former_patron", tiers=())
    await patreon_service.applica_evento(logica.leggi_evento("members:pledge:delete", corpo), corpo)
    assert await piani.livello_utente(5) == piani.GRATUITO
    corpo = _corpo(tiers=("sconosciuto",), member="m2")
    await patreon_service.applica_evento(logica.leggi_evento("members:update", corpo), corpo)
    assert await piani.livello_utente(5) == piani.GRATUITO


async def test_collegamento_oauth_stato_monouso_e_token_cifrati(pronto):
    await patreon_service.imposta_livello_tier("t1", "vip")
    stato = await patreon_service.crea_stato(5)
    assert "state=" + stato in patreon_service.url_collegamento(stato)
    assert await patreon_service.completa_collegamento(stato, "codice-ok", _Cliente()) == 5
    assert await piani.livello_utente(5) == piani.VIP
    riga = await pronto.fetchrow("SELECT token_cifrato, refresh_cifrato FROM patreon_collegamenti WHERE discord_user_id = 5")
    assert "token-di-accesso-segreto" not in riga["token_cifrato"] and "refresh-segreto" not in riga["refresh_cifrato"]
    from core.oauth_crypto import decrypt_token

    assert decrypt_token(riga["token_cifrato"], CHIAVE_CIFRATURA, aad=b"patreon:5") == "token-di-accesso-segreto"
    with pytest.raises(patreon_service.CollegamentoFallito):  # lo stato vale una volta sola
        await patreon_service.completa_collegamento(stato, "codice-ok", _Cliente())
    with pytest.raises(patreon_service.CollegamentoFallito):  # uno stato inventato
        await patreon_service.completa_collegamento("inventato", "codice-ok", _Cliente())


async def test_stato_scaduto_non_vale(pronto):
    stato = await patreon_service.crea_stato(5)
    await pronto.execute("UPDATE patreon_stati SET scade_il = now() - interval '1 second'")
    with pytest.raises(patreon_service.CollegamentoFallito):
        await patreon_service.completa_collegamento(stato, "codice-ok", _Cliente())


async def test_account_patreon_gia_di_un_altro_passa_al_nuovo_e_scollega_toglie_tutto(pronto):
    await patreon_service.imposta_livello_tier("t1", "ultra")
    for utente in (5, 6):
        await patreon_service.completa_collegamento(await patreon_service.crea_stato(utente), "codice-ok", _Cliente())
    assert await piani.livello_utente(6) == piani.ULTRA
    assert await pronto.fetchval("SELECT count(*) FROM patreon_collegamenti") == 1  # un account Patreon, una persona
    assert await patreon_service.scollega(6) is True
    assert await piani.livello_utente(6) == piani.GRATUITO
    assert await pronto.fetchval("SELECT count(*) FROM patreon_collegamenti") == 0


async def test_account_patreon_ricollegato_piu_volte_lascia_il_livello_solo_all_ultimo(pronto):
    await patreon_service.imposta_livello_tier("t1", "vip")
    for utente in (11, 22, 33):
        await patreon_service.completa_collegamento(await patreon_service.crea_stato(utente), "codice-ok", _Cliente())
    assert await piani.livello_utente(11) == piani.GRATUITO
    assert await piani.livello_utente(22) == piani.GRATUITO
    assert await piani.livello_utente(33) == piani.VIP
    assert await pronto.fetchval("SELECT count(*) FROM piani_concessioni WHERE fonte = 'patreon'") == 1


async def test_sostenitore_non_ancora_collegato_prende_il_livello_al_collegamento(pronto):
    await patreon_service.imposta_livello_tier("t1", "premium")
    corpo = _corpo()
    await patreon_service.applica_evento(logica.leggi_evento("members:create", corpo), corpo)  # prima del collegamento
    assert await pronto.fetchval("SELECT count(*) FROM piani_concessioni") == 0
    await patreon_service.completa_collegamento(await patreon_service.crea_stato(5), "codice-ok", _Cliente())
    assert await piani.livello_utente(5) == piani.PREMIUM


async def test_spento_senza_chiavi(pronto, monkeypatch):
    monkeypatch.setattr(patreon_service, "_config", lambda: SimpleNamespace(PATREON_CLIENT_ID="", PATREON_CLIENT_SECRET="", PATREON_WEBHOOK_SECRET=""))
    assert patreon_service.acceso() is False
    with pytest.raises(patreon_service.PatreonSpento):
        await patreon_service.crea_stato(5)
    with pytest.raises(patreon_service.PatreonSpento):
        await patreon_service.completa_collegamento("a", "b", _Cliente())


async def test_cog_senza_chiavi_non_apre_porte(monkeypatch):
    from cogs.utility import patreon as cog_patreon

    monkeypatch.setattr(patreon_service, "_config", lambda: SimpleNamespace(PATREON_CLIENT_ID="", PATREON_CLIENT_SECRET="", PATREON_WEBHOOK_SECRET=""))
    cog = cog_patreon.PatreonCog(object())
    await cog.cog_load()
    assert cog._runner is None
    await cog.cog_unload()
