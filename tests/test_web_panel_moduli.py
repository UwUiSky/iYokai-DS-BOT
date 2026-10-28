"""
tests/test_web_panel_moduli.py
==============================
SPEC §24.2 (#91): una pagina per modulo nel pannello, con interruttore e impostazioni dal punto unico.
"""

import pytest

from core import config_impostazioni as ci
from core.database import db
from tests.test_web_panel_server import ADMIN, GUILD, _client, _csrf, _entra, ambiente  # noqa: F401


@pytest.fixture
def con_scheda(monkeypatch, ambiente):  # noqa: F811
    monkeypatch.setitem(ci.SCHEDE, "modulo_web", (
        ci.Campo("music_max_volume", "Volume massimo", ci.NUMERO),
        ci.Campo("music_known_sites_only", "Solo siti conosciuti", ci.BOOL),
        ci.Campo("report_channel_id", "Canale", ci.CANALE),
    ))
    ambiente.bot.guilds[0].text_channels = []
    return ambiente


@pytest.mark.asyncio
async def test_pagina_del_modulo_e_salvataggio_con_csrf(con_scheda):
    client = await _client(con_scheda.app)
    try:
        await _entra(client)
        pagina = await (await client.get(f"/server/{GUILD}")).text()
        assert f'href="/server/{GUILD}/modulo/modulo_web"' in pagina
        csrf = await _csrf(client, f"/server/{GUILD}/modulo/modulo_web")
        corpo = await (await client.get(f"/server/{GUILD}/modulo/modulo_web")).text()
        assert "Volume massimo" in corpo and "Accendi" in corpo

        senza = await client.post(f"/server/{GUILD}/modulo/modulo_web", data={"chiave": "music_max_volume", "valore": "10"})
        assert senza.status == 403 and await db.get_guild_setting(GUILD, "music_max_volume") is None

        ok = await client.post(
            f"/server/{GUILD}/modulo/modulo_web", data={"csrf": csrf, "chiave": "music_max_volume", "valore": "120"}, allow_redirects=False
        )
        assert ok.headers["Location"] == f"/server/{GUILD}/modulo/modulo_web?esito=salvato"
        assert await db.get_guild_setting(GUILD, "music_max_volume") == 120
        uguale = await client.post(
            f"/server/{GUILD}/modulo/modulo_web", data={"csrf": csrf, "chiave": "music_max_volume", "valore": "120"}, allow_redirects=False
        )
        assert uguale.headers["Location"].endswith("esito=invariato")
        storico = await (await client.get(f"/server/{GUILD}/storico")).text()
        assert "music_max_volume" in storico and str(ADMIN) in storico
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_valori_storti_e_chiavi_altrui_rifiutati(con_scheda):
    client = await _client(con_scheda.app)
    try:
        await _entra(client)
        csrf = await _csrf(client, f"/server/{GUILD}")
        for chiave, valore in (("music_max_volume", "999"), ("report_channel_id", "5"), ("verify_captcha_tipo", "testo"), ("", "x")):
            r = await client.post(
                f"/server/{GUILD}/modulo/modulo_web", data={"csrf": csrf, "chiave": chiave, "valore": valore}, allow_redirects=False
            )
            assert r.headers["Location"].endswith("esito=non_valido"), (chiave, valore)
        assert await db.get_guild_setting(GUILD, "music_max_volume") is None
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_modulo_senza_impostazioni_o_sconosciuto_404_e_serve_il_permesso(ambiente):
    client = await _client(ambiente.app)
    try:
        await _entra(client)
        assert (await client.get(f"/server/{GUILD}/modulo/modulo_web")).status == 404  # esiste ma senza scheda
        assert (await client.get(f"/server/{GUILD}/modulo/inesistente")).status == 404
    finally:
        await client.close()
    anonimo = await _client(ambiente.app)
    try:
        r = await anonimo.get(f"/server/{GUILD}/modulo/modulo_web", allow_redirects=False)
        assert r.status in (302, 401, 403)
    finally:
        await anonimo.close()
