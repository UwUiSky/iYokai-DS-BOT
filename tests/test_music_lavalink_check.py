"""
tests/test_music_lavalink_check.py
======================================
scripts/check_lavalink_nodes.py (issue #48): un nodo morto, con password
sbagliata o sotto la 4.2.0 e' segnalato; mai la password nel testo.
Un server HTTP finto in locale, nessuna rete vera.
"""

import importlib.util
import pathlib

import aiohttp
import pytest
from aiohttp import web

from core.music_logic import LavalinkNodeConfig

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "check_lavalink_nodes.py"
spec = importlib.util.spec_from_file_location("check_lavalink_nodes", SCRIPT)
modulo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(modulo)


async def _server(versione: str):
    async def info(request):
        if request.headers.get("Authorization") != "giusta":
            return web.Response(status=401)
        return web.json_response({"version": {"semver": versione}, "sourceManagers": ["youtube", "local"]})

    app = web.Application()
    app.router.add_get("/v4/info", info)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    porta = site._server.sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{porta}"


@pytest.mark.asyncio
async def test_nodo_valido_vecchio_con_password_sbagliata_e_morto():
    r_ok, url_ok = await _server("4.2.0")
    r_vecchio, url_vecchio = await _server("4.1.1")
    try:
        nodi = [
            LavalinkNodeConfig(url_ok, "giusta"),
            LavalinkNodeConfig(url_vecchio, "giusta"),
            LavalinkNodeConfig(url_ok, "sbagliata"),
            LavalinkNodeConfig("http://127.0.0.1:1", "giusta"),  # nessuno ascolta
        ]
        esiti = await modulo.controlla_tutti(nodi)
    finally:
        await r_ok.cleanup()
        await r_vecchio.cleanup()

    ok = [e[1] for e in esiti]
    assert ok == [True, False, False, False]
    assert "youtube" in esiti[0][2]
    assert "4.2.0" in esiti[1][2]
    assert "password" in esiti[2][2]
    assert "non risponde" in esiti[3][2]
    assert all("giusta" not in e[2] for e in esiti)  # mai la password nel testo


def test_strict_esce_con_errore_se_un_nodo_non_e_valido(monkeypatch):
    async def finto(nodi):
        return [(nodi[0], False, "non risponde")]

    monkeypatch.setattr(modulo, "controlla_tutti", finto)
    monkeypatch.setattr(modulo, "nodi_dal_ambiente", lambda: [LavalinkNodeConfig("http://x", "")])
    monkeypatch.setattr("sys.argv", ["x", "--strict"])
    assert modulo.main() == 1
    monkeypatch.setattr("sys.argv", ["x"])
    assert modulo.main() == 0


DEPLOY = SCRIPT.parent.parent / "deploy" / "lavalink"


def test_i_file_di_deploy_non_hanno_segreti_e_sono_coerenti():
    """Issue #47: solo segnaposto; porta su localhost; inediti in sola lettura."""
    yaml = pytest.importorskip("yaml")
    app = yaml.safe_load((DEPLOY / "application.yml").read_text(encoding="utf-8"))
    assert app["lavalink"]["server"]["password"].startswith("CAMBIA")
    assert app["lavalink"]["server"]["sources"]["local"] is True
    assert app["plugins"]["lavasrc"]["spotify"]["clientId"] == "${SPOTIFY_CLIENT_ID}"

    compose = yaml.safe_load((DEPLOY / "docker-compose.yml").read_text(encoding="utf-8"))
    servizio = compose["services"]["lavalink"]
    assert servizio["ports"] == ["127.0.0.1:2333:2333"]
    assert any(v.endswith("/audio/local:ro") for v in servizio["volumes"])
    assert any("${LAVALINK_PASSWORD" in e for e in servizio["environment"])
