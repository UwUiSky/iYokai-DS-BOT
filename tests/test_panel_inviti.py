"""
tests/test_panel_inviti.py
==========================
Pannello web: `/invito/<slug>` (redirect all'invito Discord dedicato, limite per IP, nessun nome),
«I miei inviti» (accesso, CSRF) e pagina dell'admin (permessi a ogni richiesta, CSRF, escape,
opzioni dallo stesso punto dei comandi).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core import invite_links_logic as l, invite_service as svc
from core.bounded_cache import BoundedCache
from core.invite_tracker import InviteTracker
from core.repositories.invite_links_repo import invite_links_repo
from tests.support.discord_fakes import fake_member, fake_role, fake_text_channel
from tests.test_web_panel_server import ADMIN, GUILD, _client, _csrf, _entra, ambiente  # noqa: F401


@pytest.fixture
def inviti(ambiente, monkeypatch):  # noqa: F811
    guild = ambiente.bot.get_guild(GUILD)
    canale = fake_text_channel(GUILD + 1, "bene<b>venuto")
    canale.position = 0
    canale.permissions_for = MagicMock(return_value=discord.Permissions(create_instant_invite=True))
    canale.create_invite = AsyncMock(return_value=SimpleNamespace(code="Abc123"))
    guild.text_channels = [canale]
    guild.system_channel = guild.rules_channel = guild.public_updates_channel = None
    guild.features = []
    guild.vanity_url_code = None
    guild.get_channel = MagicMock(side_effect=lambda i: canale if i == canale.id else None)
    ambiente.membri[ADMIN].roles = []
    ambiente.bot.fetch_invite = AsyncMock()
    monkeypatch.setattr(svc, "invite_tracker", InviteTracker())
    monkeypatch.setattr(svc, "_verificati", BoundedCache(100))
    monkeypatch.setattr(svc, "url_pubblico", lambda: "http://pannello.test")
    return SimpleNamespace(amb=ambiente, guild=guild, canale=canale)


async def _accendi(inviti, acceso=True):
    from core.database import db
    await db.set_module_active_for_guild(GUILD, "invites", acceso, changed_by=None)


@pytest.mark.asyncio
async def test_il_link_porta_all_invito_dedicato(inviti):
    await _accendi(inviti)
    await invite_links_repo.crea("server-anna", GUILD, ADMIN)
    client = await _client(inviti.amb.app)
    try:
        r = await client.get("/invito/server-anna", allow_redirects=False)
        assert r.status == 302 and r.headers["Location"] == "https://discord.gg/Abc123"
        assert r.headers["Cache-Control"] == "no-store"
        await client.get("/invito/server-anna", allow_redirects=False)
        assert inviti.canale.create_invite.await_count == 1  # creato una volta e riusato
        assert (await invite_links_repo.da_slug("server-anna")).last_used_at is not None
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_link_non_attivo_o_server_senza_permesso_senza_nomi(inviti, monkeypatch):
    await invite_links_repo.crea("server-anna", GUILD, ADMIN)
    client = await _client(inviti.amb.app)
    try:
        r = await client.get("/invito/server-anna", allow_redirects=False)  # modulo spento
        corpo = await r.text()
        assert r.status == 404 and "non è attivo" in corpo and "Anna" not in corpo and "prova" not in corpo
        assert (await client.get("/invito/non-esiste", allow_redirects=False)).status == 404
        assert (await client.get("/invito/Maiuscole", allow_redirects=False)).status == 404
        await _accendi(inviti)
        inviti.canale.permissions_for = MagicMock(return_value=discord.Permissions(create_instant_invite=False))
        r = await client.get("/invito/server-anna", allow_redirects=False)
        assert r.status == 503 and "Crea invito" in await r.text()
        inviti.guild.features = ["INVITES_DISABLED"]
        r = await client.get("/invito/server-anna", allow_redirects=False)
        assert r.status == 503 and "in pausa" in await r.text()
        # tetto degli inviti personali del server: pagina chiara, nessun invito nuovo
        inviti.guild.features = []
        inviti.canale.permissions_for = MagicMock(return_value=discord.Permissions(create_instant_invite=True))
        monkeypatch.setattr(l, "MAX_INVITI_PERSONALI", 0)
        r = await client.get("/invito/server-anna", allow_redirects=False)
        assert r.status == 503 and "numero massimo" in await r.text()
        inviti.canale.create_invite.assert_not_awaited()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_limite_per_ip_sull_apertura(inviti):
    client = await _client(inviti.amb.app)
    try:
        stati = [(await client.get("/invito/server-anna", allow_redirects=False)).status for _ in range(22)]
        assert stati[:20] == [404] * 20 and stati[20:] == [429, 429]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_miei_inviti_serve_l_accesso_e_il_csrf(inviti):
    await _accendi(inviti)
    client = await _client(inviti.amb.app)
    try:
        r = await client.get("/miei-inviti", allow_redirects=False)
        assert r.status == 302 and r.headers["Location"] == "/accedi"
        assert (await client.post("/miei-inviti", data={}, allow_redirects=False)).headers["Location"] == "/accedi"
        await _entra(client)
        pagina = await (await client.get("/miei-inviti")).text()
        assert "Server &lt;b&gt;di&lt;/b&gt; prova" in pagina and "Crea il mio link" in pagina
        csrf = await _csrf(client, "/miei-inviti")
        senza = await client.post("/miei-inviti", data={"guild_id": GUILD}, allow_redirects=False)
        assert senza.status == 403
        r = await client.post("/miei-inviti", data={"csrf": csrf, "guild_id": GUILD}, allow_redirects=False)
        assert r.headers["Location"].endswith("esito=link_creato")
        pagina = await (await client.get("/miei-inviti?esito=link_creato")).text()
        assert "Il tuo link è pronto" in pagina and "http://pannello.test/invito/server-b-di-b-prova-" in pagina
        sbagliato = await client.post("/miei-inviti", data={"csrf": csrf, "guild_id": "x"}, allow_redirects=False)
        assert sbagliato.headers["Location"].endswith("esito=non_nel_server")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_miei_inviti_dice_perche_non_puoi(inviti):
    await _accendi(inviti)
    inviti.guild.get_role = MagicMock(return_value=fake_role(55))
    await svc.imposta_opzioni(inviti.guild, ruolo_link=55, changed_by=1)
    client = await _client(inviti.amb.app)
    try:
        await _entra(client)
        pagina = await (await client.get("/miei-inviti")).text()
        assert "riservato a un ruolo" in pagina and "Crea il mio link" not in pagina
        csrf = await _csrf(client, "/miei-inviti")
        r = await client.post("/miei-inviti", data={"csrf": csrf, "guild_id": GUILD}, allow_redirects=False)
        assert r.headers["Location"].endswith("esito=ruolo_mancante")
        assert await invite_links_repo.dell_utente(ADMIN) == []
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_pagina_admin_permessi_csrf_ed_escape(inviti):
    await _accendi(inviti)
    pagina_url = f"/server/{GUILD}/inviti"
    client = await _client(inviti.amb.app)
    try:
        assert (await client.get(pagina_url, allow_redirects=False)).headers["Location"] == "/accedi"
        await _entra(client)
        pagina = await (await client.get(pagina_url)).text()
        assert "bene&lt;b&gt;venuto" in pagina and "bene<b>venuto" not in pagina
        csrf = await _csrf(client, pagina_url)
        dati = {"canale_id": str(inviti.canale.id), "ruolo_id": ""}
        assert (await client.post(pagina_url, data=dati, allow_redirects=False)).status == 403
        r = await client.post(pagina_url, data={**dati, "csrf": csrf}, allow_redirects=False)
        assert r.headers["Location"].endswith("esito=salvato")
        assert (await svc.leggi_opzioni(GUILD)).canale_log_id == inviti.canale.id
        r = await client.post(pagina_url, data={**dati, "csrf": csrf}, allow_redirects=False)
        assert r.headers["Location"].endswith("esito=invariato")
        for cattivo in ({"canale_id": "999"}, {"canale_id": "x"}, {"ruolo_id": "12345"}):
            r = await client.post(pagina_url, data={"csrf": csrf, **cattivo}, allow_redirects=False)
            assert r.headers["Location"].endswith("esito=non_valido")
        # il permesso si ricontrolla a ogni richiesta
        inviti.amb.membri[ADMIN] = fake_member(ADMIN, guild_permissions=discord.Permissions())
        assert (await client.get(pagina_url)).status == 403
        assert (await client.post(pagina_url, data={**dati, "csrf": csrf}, allow_redirects=False)).status == 403
    finally:
        await client.close()
