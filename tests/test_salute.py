"""
tests/test_salute.py
====================
Endpoint /salute, misura del ritardo del ciclo, servizio di sistema e script di installazione.
Funzioni coperte: consiglio 25/11/2026, critico 11 (blocco C)
"""

from __future__ import annotations

import asyncio
import configparser
import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer

from core import giro_periodico as gp
from core import salute

RADICE = Path(__file__).resolve().parent.parent
UNITA = RADICE / "deploy" / "systemd" / "iyokai-bot.service"


def _bot(pronto=True):
    return SimpleNamespace(is_ready=lambda: pronto)


@pytest.fixture(autouse=True)
def _giri_puliti(monkeypatch):
    monkeypatch.setattr(gp, "GIRI", {})


async def _chiedi(bot, pool):
    async with TestClient(TestServer(salute.build_app(bot, lambda: pool))) as client:
        risposta = await client.get("/salute")
        return risposta.status, await risposta.json()


async def test_tutto_a_posto_200(clean_db):
    stato, dati = await _chiedi(_bot(), clean_db)
    assert stato == 200 and dati["stato"] == "ok"
    assert dati["pronto"] is True and dati["database"]["ok"] is True
    assert {"totale", "vivi", "in_difficolta"} <= set(dati["giri"])
    assert "ultimo" in dati["ritardo_ciclo_ms"]


async def test_bot_non_pronto_503(clean_db):
    stato, dati = await _chiedi(_bot(pronto=False), clean_db)
    assert stato == 503 and dati["stato"] == "giu"


async def test_database_lento_503_entro_due_secondi(monkeypatch):
    class PoolLento:
        async def fetchval(self, *a):
            await asyncio.sleep(30)

    monkeypatch.setattr(salute, "TIMEOUT_DATABASE_SECONDI", 0.2)
    inizio = asyncio.get_running_loop().time()
    stato, dati = await _chiedi(_bot(), PoolLento())
    assert stato == 503 and dati["database"]["ok"] is False
    assert asyncio.get_running_loop().time() - inizio < 3


def test_il_limite_del_database_e_di_due_secondi():
    assert salute.TIMEOUT_DATABASE_SECONDI == 2.0


async def test_senza_pool_503():
    stato, dati = await _chiedi(_bot(), None)
    assert stato == 503 and dati["database"]["ok"] is False


async def test_giro_in_difficolta_e_degradato_ma_200(clean_db):
    @gp.giro_periodico(seconds=60, subito=True)
    async def lavoro():
        await asyncio.sleep(3600)  # resta dentro il giro: gli errori contati non si azzerano

    lavoro.start()
    await asyncio.sleep(0.05)
    lavoro.errori_consecutivi = gp.ERRORI_PER_AVVISO
    try:
        stato, dati = await _chiedi(_bot(), clean_db)
    finally:
        lavoro.cancel()
    assert stato == 200 and dati["stato"] == "degradato"
    assert dati["giri"]["in_difficolta"] == [lavoro.nome]


async def test_nessun_segreto_nella_risposta(clean_db):
    _, dati = await _chiedi(_bot(), clean_db)
    testo = json.dumps(dati)
    assert os.environ["DATABASE_URL"] not in testo and "postgresql://" not in testo


def test_misura_del_ritardo_del_ciclo():
    m = salute.MisuraCiclo()
    assert m.registra(100.0) == 0.0  # il primo giro non ha un prima
    assert m.registra(101.0) == 0.0
    assert m.registra(103.5) == pytest.approx(1.5)
    assert m.ultimo_ms == pytest.approx(1500)
    assert m.massimo_ms(104.0) == pytest.approx(1500)
    assert m.massimo_ms(1000.0) == 0.0  # fuori dalla finestra di 5 minuti


# ---------------------------------------------------------------- servizio di sistema


def _unita() -> dict[str, list[str]]:
    letto: dict[str, list[str]] = {}
    for riga in UNITA.read_text(encoding="utf-8").splitlines():
        if "=" in riga and not riga.lstrip().startswith(("#", "[")):
            chiave, valore = riga.split("=", 1)
            letto.setdefault(chiave.strip(), []).append(valore.strip())
    return letto


def test_servizio_si_rialza_e_parte_al_boot():
    u = _unita()
    assert u["Restart"] == ["always"]
    assert int(u["RestartSec"][0]) >= 1
    assert "StartLimitIntervalSec" in u and "StartLimitBurst" in u
    assert "TimeoutStopSec" in u and "MemoryMax" in u
    assert u["WantedBy"] == ["multi-user.target"]
    assert "postgresql.service" in u["After"][0] and "postgresql.service" in u["Wants"][0]


def test_lavalink_e_facoltativo_nel_servizio():
    """Nessuna dipendenza forte da Lavalink o da Docker: il bot parte anche senza."""
    u = _unita()
    for chiave in ("Requires", "BindsTo", "Requisite", "PartOf"):
        assert not any("lavalink" in v.lower() or "docker" in v.lower() for v in u.get(chiave, []))
    for chiave in ("After", "Wants"):
        assert not any("lavalink" in v.lower() for v in u.get(chiave, []))


def test_unita_con_systemd_analyze():
    if not shutil.which("systemd-analyze"):
        pytest.skip("systemd-analyze non c'è")  # solo l'ambiente, mai per far passare un test
    esito = subprocess.run(["systemd-analyze", "verify", str(UNITA)], capture_output=True, text=True)
    errori = [r for r in esito.stderr.splitlines() if r and "is not executable" not in r and "No such file" not in r]
    assert not errori, errori


def test_script_di_installazione_in_prova_non_cambia_niente(tmp_path):
    cartella = tmp_path / "iyokai"
    (cartella / "scripts").mkdir(parents=True)
    (cartella / "deploy" / "systemd").mkdir(parents=True)
    (cartella / ".venv" / "bin").mkdir(parents=True)
    shutil.copy(RADICE / "scripts" / "installa_servizio.sh", cartella / "scripts")
    shutil.copy(UNITA, cartella / "deploy" / "systemd")
    (cartella / ".env").write_text("X=1\n")
    python = cartella / ".venv" / "bin" / "python"
    python.write_text("#!/bin/sh\n")
    python.chmod(0o755)
    esito = subprocess.run(["bash", str(cartella / "scripts" / "installa_servizio.sh"), "--prova"], capture_output=True, text=True)
    assert esito.returncode == 0, esito.stderr
    assert "(prova)" in esito.stdout
    assert not (cartella / "logs").exists()  # in prova non si crea niente
    assert "ERRORE" not in esito.stderr
