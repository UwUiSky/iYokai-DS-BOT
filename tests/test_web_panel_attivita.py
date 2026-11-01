"""
tests/test_web_panel_attivita.py
================================
Activity «radio iYokai» (SPEC B.8): stato della radio, intestazioni per il riquadro di Discord,
apertura su `/?frame_id=…&instance_id=…`, file statici ammessi, nessuna fuga dei dati interni.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from core import web_panel_attivita as attivita
from core.repositories.main_radio_repo import MainRadioState, MainRadioTrack
from core.web_panel_server import build_app

ADESSO = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


def _traccia(i, durata_ms, etichetta):
    return MainRadioTrack(
        id=i, position=i, identifier=f"local:/segreto/{i}.mp3", duration_ms=durata_ms, label=etichetta,
        added_by=1, added_at=ADESSO,
    )


TRACCE = [_traccia(0, 60_000, "Uno"), _traccia(1, 30_000, "Due")]


def test_stato_dice_brano_e_punto():
    stato = MainRadioState(track_index=0, track_started_at=ADESSO - timedelta(seconds=70), is_active=True)
    r = attivita.stato_radio(TRACCE, stato, ADESSO)
    assert r == {"attiva": True, "titolo": "Due", "durata_ms": 30_000, "trascorso_ms": 10_000, "numero": 2, "totale": 2}


@pytest.mark.parametrize("stato", [None, MainRadioState(0, ADESSO, False)])
def test_stato_spenta_o_assente(stato):
    assert attivita.stato_radio(TRACCE, stato, ADESSO) == {"attiva": False}


def test_stato_senza_tracce_o_indice_incoerente():
    assert attivita.stato_radio([], MainRadioState(0, ADESSO, True), ADESSO) == {"attiva": False}
    assert attivita.stato_radio(TRACCE, MainRadioState(9, ADESSO, True), ADESSO) == {"attiva": False}


def test_stato_non_mostra_percorsi_e_taglia_il_titolo():
    lunga = [_traccia(0, 1000, "x" * 500)]
    r = attivita.stato_radio(lunga, MainRadioState(0, ADESSO, True), ADESSO)
    assert len(r["titolo"]) == attivita.MAX_TITOLO
    assert "segreto" not in str(r)


def test_apertura_attivita_riconosciuta():
    assert attivita.e_apertura_attivita("/", {"frame_id": "1", "instance_id": "2"})
    assert attivita.e_apertura_attivita("/attivita/radio", {})
    assert not attivita.e_apertura_attivita("/", {"frame_id": "1"})
    assert not attivita.e_apertura_attivita("/server/1", {"frame_id": "1", "instance_id": "2"})


def test_intestazioni_solo_discord_nel_riquadro():
    h = attivita.intestazioni_attivita(True)
    assert "frame-ancestors https://discord.com" in h["Content-Security-Policy"]
    assert "'unsafe-inline'" not in h["Content-Security-Policy"]
    assert "X-Frame-Options" not in h


@pytest.mark.parametrize("url,atteso", [("https://radio.example/live", "https://radio.example/live"), ("http://x/y", ""),
                                        ("javascript:alert(1)", ""), ("https://a\"b", ""), ("", "")])
def test_flusso_solo_https(url, atteso):
    assert attivita.flusso_valido(url) == atteso


@pytest.fixture
async def client(monkeypatch):
    finto = SimpleNamespace(
        list_tracks=AsyncMock(return_value=TRACCE),
        get_state=AsyncMock(return_value=MainRadioState(0, datetime.now(timezone.utc), True)),
    )
    monkeypatch.setattr(attivita, "main_radio_repo", finto)
    sessioni = SimpleNamespace(utente_della_sessione=AsyncMock(return_value=None))
    bot = MagicMock()
    bot.guilds = []
    app = build_app(
        bot=bot, sessioni=sessioni, oauth=MagicMock(), client_id="4242", client_secret="s" * 8,
        url_pubblico="https://pannello.test", chiave="k" * 48, radio_flusso="https://radio.example/live",
    )
    async with TestClient(TestServer(app)) as c:
        yield c


async def test_apertura_dentro_discord_serve_la_pagina_radio(client):
    r = await client.get("/?frame_id=1&instance_id=2")
    corpo = await r.text()
    assert r.status == 200
    assert 'data-client="4242"' in corpo and 'data-flusso="https://radio.example/live"' in corpo
    assert "X-Frame-Options" not in r.headers
    assert "frame-ancestors https://discord.com" in r.headers["Content-Security-Policy"]


async def test_home_normale_resta_chiusa_ai_riquadri(client):
    r = await client.get("/")
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert "Radio iYokai" not in await r.text()


async def test_stato_json_pubblico(client):
    r = await client.get("/attivita/radio/stato")
    dati = await r.json()
    assert dati["attiva"] is True and dati["titolo"] == "Uno"
    assert "X-Frame-Options" not in r.headers


async def test_statici_ammessi_e_solo_quelli(client):
    assert (await client.get("/static/radio.js")).status == 200
    sdk = await client.get("/static/discord-sdk.js")
    assert sdk.status == 200 and sdk.content_type == "text/javascript"
    assert (await client.get("/static/SDK_LICENZA.md")).status == 404
    assert (await client.get("/static/../../core/config.py")).status == 404
