"""
tests/test_panel_permessi_comandi.py
====================================
Gruppi di comandi nascosti per ruolo dal pannello (#148): stato senza mai
il token, link di autorizzazione, risincronizzazione (una al minuto per
server) e revoca, dalle funzioni di `core/command_permissions.py`.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from core import command_permissions, panel_bridge
from core.command_permissions import EsitoPermessi, TokenPermessi
from core.repositories import command_permission_token_repo as repo_modulo
from tests.support.discord_fakes import fake_guild
from tests.test_web_panel_server import GUILD, _client, _csrf, _entra, ambiente  # noqa: F401

TOKEN = TokenPermessi("segreto-accesso", "segreto-rinnovo", datetime(2026, 10, 20, tzinfo=timezone.utc), user_id=31)


@pytest.fixture
def repo_finto(monkeypatch):
    finto = AsyncMock()
    finto.get.return_value = TOKEN
    monkeypatch.setattr(repo_modulo, "command_permission_token_repo", finto)
    monkeypatch.setattr(command_permissions, "link_per_admin", lambda g, u: f"https://discord.com/oauth2/authorize?g={g}&u={u}")
    return finto


@pytest.mark.asyncio
async def test_stato_senza_token_e_con_link(repo_finto):
    stato = await panel_bridge.stato_permessi_comandi(fake_guild(guild_id=GUILD), 31)
    assert stato == {
        "link": f"https://discord.com/oauth2/authorize?g={GUILD}&u=31",
        "autorizzato": True, "da": 31, "scade": "2026-10-20",
    }
    assert "segreto" not in str(stato)


@pytest.mark.asyncio
async def test_senza_oauth_configurato_nessun_link(monkeypatch, repo_finto):
    monkeypatch.setattr(command_permissions, "link_per_admin", lambda g, u: None)
    stato = await panel_bridge.stato_permessi_comandi(fake_guild(guild_id=GUILD), 31)
    assert stato["link"] is None and not stato["autorizzato"]
    repo_finto.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_pagina_risincronizza_e_revoca(ambiente, repo_finto, monkeypatch):  # noqa: F811
    esiti = AsyncMock(return_value={"admin": EsitoPermessi(command_permissions.STATO_OK, ["admin"])})
    monkeypatch.setattr(command_permissions, "risincronizza_server", esiti)
    client = await _client(ambiente.app)
    try:
        await _entra(client)
        pagina = await (await client.get(f"/server/{GUILD}")).text()
        assert "Autorizzato da <code>31</code>" in pagina and "segreto" not in pagina
        csrf = await _csrf(client, f"/server/{GUILD}")
        primo = await client.post(f"/server/{GUILD}/permessi", data={"csrf": csrf, "azione": "sincronizza"}, allow_redirects=False)
        assert primo.headers["Location"].endswith("esito=permessi_ok")
        secondo = await client.post(f"/server/{GUILD}/permessi", data={"csrf": csrf, "azione": "sincronizza"}, allow_redirects=False)
        assert secondo.headers["Location"].endswith("esito=permessi_attendi")
        assert esiti.await_count == 1
        senza_csrf = await client.post(f"/server/{GUILD}/permessi", data={"azione": "revoca"}, allow_redirects=False)
        assert senza_csrf.status == 403
        repo_finto.cancella.assert_not_awaited()
        revoca = await client.post(f"/server/{GUILD}/permessi", data={"csrf": csrf, "azione": "revoca"}, allow_redirects=False)
        assert revoca.headers["Location"].endswith("esito=permessi_revocati")
        repo_finto.cancella.assert_awaited_once_with(GUILD)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_estraneo_non_tocca_i_permessi(ambiente, repo_finto):  # noqa: F811
    ambiente.oauth.utente_id = 32
    client = await _client(ambiente.app)
    try:
        await _entra(client)
        risposta = await client.post(f"/server/{GUILD}/permessi", data={"csrf": "x", "azione": "revoca"}, allow_redirects=False)
        assert risposta.status == 403
        repo_finto.cancella.assert_not_awaited()
    finally:
        await client.close()
