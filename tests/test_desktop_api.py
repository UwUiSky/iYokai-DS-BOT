"""
tests/test_desktop_api.py
=========================
SPEC D.1, D.5-D.10 (#108): l'interfaccia di iYokai Desktop. Token personale (solo impronta), permessi veri,
limiti, corpo piccolo, nessun evento di canali che la persona non vede più.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

import core.desktop_api as api
import core.desktop_staff as staff
from core import desktop_logic as dl
from core.repositories.desktop_repo import DesktopRepository
from core.repositories.user_app_repo import UserAppRepository
from core.web_panel_server import build_app

ME, G = 10, 500


def _guild(gid=G, nome="Casa", vede=True, membri=(ME,)):
    g = MagicMock()
    g.id, g.name, g.icon = gid, nome, None
    g.get_member = MagicMock(side_effect=lambda u: SimpleNamespace(id=u) if u in membri else None)
    canale = MagicMock()
    canale.permissions_for = MagicMock(return_value=SimpleNamespace(view_channel=vede))
    g.get_channel = MagicMock(return_value=canale)
    return g


@pytest.fixture
async def mondo(monkeypatch, clean_db):
    repo = DesktopRepository(pool_provider=lambda: clean_db)
    app_repo = UserAppRepository(pool_provider=lambda: clean_db)
    for modulo in (api, staff):
        monkeypatch.setattr(modulo, "desktop_repo", repo)
    monkeypatch.setattr(api, "user_app_repo", app_repo)
    token = dl.nuovo_token()
    await repo.imposta_token(ME, dl.impronta(token))
    guild = _guild()
    bot = MagicMock()
    bot.guilds = [guild, _guild(gid=2, nome="Altro", membri=())]
    bot.get_guild = MagicMock(side_effect=lambda g: guild if g == G else None)
    ponte = SimpleNamespace(
        server_gestibili=AsyncMock(return_value=[guild]),
        server_gestibile=AsyncMock(side_effect=lambda b, g, u: guild if g == G and u == ME else None),
        e_proprietario=lambda u: False,
    )
    sessioni = SimpleNamespace(utente_della_sessione=AsyncMock(return_value=None))
    app = build_app(
        bot=bot, sessioni=sessioni, oauth=MagicMock(), client_id="1", client_secret="s" * 8,
        url_pubblico="https://pannello.test", chiave="k" * 48, ponte=ponte,
    )
    async with TestClient(TestServer(app)) as client:
        yield SimpleNamespace(client=client, repo=repo, app_repo=app_repo, token=token, guild=guild, bot=bot, ponte=ponte)


def _auth(m, token=None):
    return {"Authorization": f"Bearer {token or m.token}"}


async def test_senza_token_o_con_token_sbagliato_401(mondo):
    for intestazioni in ({}, {"Authorization": "Bearer dsk_" + "a" * 43}, {"Authorization": "Bearer corto"}, {"Authorization": "Basic x"}):
        r = await mondo.client.get("/api/desktop/io", headers=intestazioni)
        assert r.status == 401 and (await r.json())["errore"] == "token_non_valido"


async def test_tentativi_con_token_sbagliato_si_fermano(mondo):
    stati = [(await mondo.client.get("/api/desktop/io")).status for _ in range(12)]
    assert stati[:10] == [401] * 10 and stati[10:] == [429, 429]


async def test_io_mostra_chi_sei_e_gli_avvisi(mondo):
    await mondo.repo.imposta_menzioni(ME, True)
    await mondo.repo.imposta_parole(ME, ["ciao"])
    dati = await (await mondo.client.get("/api/desktop/io", headers=_auth(mondo))).json()
    assert dati == {"utente": "10", "avvisi": True, "parole": ["ciao"], "api": 1}


async def test_revoca_chiude_subito(mondo):
    assert (await mondo.client.get("/api/desktop/io", headers=_auth(mondo))).status == 200
    await mondo.repo.revoca_token(ME)
    assert (await mondo.client.get("/api/desktop/io", headers=_auth(mondo))).status == 401


async def test_server_solo_dove_sei_con_staff_e_pannello(mondo):
    dati = await (await mondo.client.get("/api/desktop/server", headers=_auth(mondo))).json()
    assert dati["server"] == [
        {"id": "500", "nome": "Casa", "icona": None, "iyokai": True, "staff": True, "pannello": "https://pannello.test/server/500"}
    ]


async def test_eventi_dopo_id_con_link_e_filtro_tipo(mondo):
    await mondo.repo.aggiungi_evento(ME, "menzione", guild_id=G, channel_id=7, message_id=70, autore_nome="Ann", canale_nome="gen", testo="ciao")
    await mondo.repo.aggiungi_evento(ME, "promemoria", testo="bevi")
    tutti = (await (await mondo.client.get("/api/desktop/eventi", headers=_auth(mondo))).json())["eventi"]
    assert [e["tipo"] for e in tutti] == ["menzione", "promemoria"]
    assert tutti[0]["link"] == "https://discord.com/channels/500/7/70" and tutti[1]["link"] is None
    dopo = (await (await mondo.client.get(f"/api/desktop/eventi?dopo={tutti[0]['id']}", headers=_auth(mondo))).json())["eventi"]
    assert [e["tipo"] for e in dopo] == ["promemoria"]
    r = await mondo.client.get("/api/desktop/eventi?tipo=inventato", headers=_auth(mondo))
    assert r.status == 400


async def test_eventi_di_canali_che_non_vedi_piu_non_escono(mondo):
    await mondo.repo.aggiungi_evento(ME, "menzione", guild_id=G, channel_id=7, message_id=70, testo="segreto")
    mondo.guild.get_channel.return_value.permissions_for.return_value = SimpleNamespace(view_channel=False)
    assert (await (await mondo.client.get("/api/desktop/eventi", headers=_auth(mondo))).json())["eventi"] == []
    mondo.guild.get_channel.return_value.permissions_for.return_value = SimpleNamespace(view_channel=True)
    mondo.guild.get_member.side_effect = lambda u: None  # uscito dal server
    assert (await (await mondo.client.get("/api/desktop/eventi", headers=_auth(mondo))).json())["eventi"] == []


async def test_attesa_lunga_aspetta_poi_risponde_vuoto(mondo, monkeypatch):
    sono = []

    async def finto_sleep(secondi):
        sono.append(secondi)
        await mondo.repo.aggiungi_evento(ME, "promemoria", testo="arrivato durante l'attesa")

    monkeypatch.setattr(api.asyncio, "sleep", finto_sleep)
    r = await mondo.client.get("/api/desktop/eventi?attesa=5", headers=_auth(mondo))
    dati = (await r.json())["eventi"]
    assert len(sono) == 1 and [e["testo"] for e in dati] == ["arrivato durante l'attesa"]


async def test_storico_comandi_e_azioni(mondo):
    await mondo.app_repo.registra_comando(ME, "promemoria crea", None)
    await mondo.repo.registra_azione(ME, G, "blocca_canale", "channel_id=7", "ok")
    dati = await (await mondo.client.get("/api/desktop/storico", headers=_auth(mondo))).json()
    assert dati["comandi"][0]["comando"] == "promemoria crea"
    assert dati["azioni"][0]["azione"] == "blocca_canale" and dati["azioni"][0]["server"] == "500"


async def test_risposte_con_testo(mondo):
    await mondo.app_repo.salva_risposta(ME, "ciao", "Ciao a tutti!", None, None, None)
    dati = await (await mondo.client.get("/api/desktop/risposte", headers=_auth(mondo))).json()
    assert dati["risposte"] == [{"nome": "ciao", "testo": "Ciao a tutti!"}]


async def test_traduci_passa_dallo_snodo_dell_app(mondo, monkeypatch):
    finto = AsyncMock(return_value=("Hello", None))
    monkeypatch.setattr(api, "chiedi_ai_app", finto)
    r = await mondo.client.post("/api/desktop/traduci", json={"testo": "Ciao", "lingua": "en"}, headers=_auth(mondo))
    assert (await r.json()) == {"testo": "Hello"}
    assert finto.await_args.args[:3] == (ME, "traduci", "traduzione") and finto.await_args.args[5] == "en"
    finto.return_value = (None, "AI ferma")
    r = await mondo.client.post("/api/desktop/traduci", json={"testo": "Ciao"}, headers=_auth(mondo))
    assert r.status == 503 and (await r.json())["motivo"] == "AI ferma"
    for brutto in ({"testo": ""}, {"testo": "x", "lingua": "klingon"}, {"testo": "x" * 3001}):
        r = await mondo.client.post("/api/desktop/traduci", json=brutto, headers=_auth(mondo))
        assert r.status == 400


async def test_corpo_troppo_grande_o_storto(mondo):
    r = await mondo.client.post("/api/desktop/traduci", data=b"x" * 9000, headers=_auth(mondo))
    assert r.status == 413
    r = await mondo.client.post("/api/desktop/traduci", data=b"non json", headers=_auth(mondo))
    assert r.status == 413
    r = await mondo.client.post("/api/desktop/traduci", data=b"[1,2]", headers=_auth(mondo))
    assert r.status == 413


async def test_staff_azione_e_registro(mondo, monkeypatch):
    finto = AsyncMock(return_value=staff.OK)
    monkeypatch.setattr(api.staff, "esegui", finto)
    r = await mondo.client.post("/api/desktop/staff/azione", json={"server": G, "azione": "blocca_canale", "channel_id": 7}, headers=_auth(mondo))
    assert r.status == 200 and (await r.json()) == {"esito": "ok"}
    assert finto.await_args.args[:4] == (mondo.bot, ME, G, "blocca_canale")
    finto.return_value = staff.NESSUN_PERMESSO
    r = await mondo.client.post("/api/desktop/staff/azione", json={"server": G, "azione": "timeout"}, headers=_auth(mondo))
    assert r.status == 403
    finto.return_value = staff.DATI_NON_VALIDI
    r = await mondo.client.post("/api/desktop/staff/azione", json={}, headers=_auth(mondo))
    assert r.status == 400


async def test_staff_azioni_del_server_solo_se_gestisci(mondo):
    await mondo.repo.registra_azione(99, G, "timeout", "target_id=1", "ok")
    r = await mondo.client.get(f"/api/desktop/staff/azioni?server={G}", headers=_auth(mondo))
    assert [a["azione"] for a in (await r.json())["azioni"]] == ["timeout"]
    assert (await mondo.client.get("/api/desktop/staff/azioni?server=2", headers=_auth(mondo))).status == 403
    assert (await mondo.client.get("/api/desktop/staff/azioni?server=x", headers=_auth(mondo))).status == 400


async def test_staff_limite_di_azioni_al_minuto(mondo, monkeypatch):
    monkeypatch.setattr(api.staff, "esegui", AsyncMock(return_value=staff.OK))
    stati = [
        (await mondo.client.post("/api/desktop/staff/azione", json={"server": G, "azione": "annuncio"}, headers=_auth(mondo))).status
        for _ in range(21)
    ]
    assert stati[:20] == [200] * 20 and stati[20] == 429


async def test_radio(mondo, monkeypatch):
    monkeypatch.setattr(api, "main_radio_repo", SimpleNamespace(list_tracks=AsyncMock(return_value=[]), get_state=AsyncMock(return_value=None)))
    assert await (await mondo.client.get("/api/desktop/radio", headers=_auth(mondo))).json() == {"attiva": False}


async def test_la_pagina_della_api_resta_chiusa_ai_riquadri(mondo):
    r = await mondo.client.get("/api/desktop/io", headers=_auth(mondo))
    assert r.headers["X-Frame-Options"] == "DENY" and r.headers["Cache-Control"] == "no-store"
