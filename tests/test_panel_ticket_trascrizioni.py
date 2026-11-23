"""
tests/test_panel_ticket_trascrizioni.py
=======================================
Trascrizioni dei ticket nel pannello (TKT-072, D111): elenco con ricerca, apertura con CSP propria, solo lo staff del
ticket (riletto a ogni richiesta), stessa risposta per «non esiste» e «non puoi», CSRF sulle opzioni, escape di Jinja.
Sessioni e database veri, Discord finto.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from core import panel_bridge, ticket_trascrizioni_servizio as servizio
from core.database import db
from core.oauth_crypto import generate_key
from core.repositories.ticket_repo import ticket_repo
from core.repositories.ticket_trascrizioni_repo import ticket_trascrizioni_repo as repo
from tests.support.discord_fakes import fake_member, fake_role
from tests.test_web_panel_server import ADMIN, GUILD, _client, _csrf, _entra, ambiente  # noqa: F401
import core.web_panel_ticket_trascrizioni as modulo

BASE = f"/server/{GUILD}/ticket/trascrizioni"
RUOLO_STAFF = 4040
UTENTE_TICKET = 700000000000000001
PAGINA = "<!doctype html><html><body><p>messaggio riservato</p><img src=\"data:image/png;base64,QUJD\"></body></html>"


@pytest.fixture
async def tz(ambiente, clean_db, monkeypatch):  # noqa: F811
    for r in (repo, ticket_repo):
        monkeypatch.setattr(r, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(servizio, "config", SimpleNamespace(TICKET_TRASCRIZIONI_KEY=generate_key(), OAUTH_ENCRYPTION_KEY=""))
    monkeypatch.setattr(modulo, "config", servizio.config)
    await db.ensure_guild_exists(GUILD)
    await db.set_guild_setting(GUILD, "ticket_support_role_ids", [RUOLO_STAFF])
    ruolo = fake_role(RUOLO_STAFF, "Supporto")
    ambiente.membri[ADMIN] = fake_member(ADMIN, "Mario", roles=[ruolo], guild_permissions=discord.Permissions(manage_guild=True))
    await ticket_repo.create_ticket(GUILD, UTENTE_TICKET, 5551, category_label="Aiuto")
    ticket = await ticket_repo.get_ticket_by_channel(5551)
    await clean_db.execute("UPDATE tickets SET status='closed', close_reason='risolto <b>bene</b>', rating=5 WHERE id=$1", ticket.id)
    ambiente.ticket = await ticket_repo.get_ticket_by_channel(5551)
    ambiente.rid = await servizio.conserva(GUILD, ambiente.ticket, [PAGINA])
    return ambiente


@pytest.mark.asyncio
async def test_elenco_apertura_e_csp_propria(tz):
    client = await _client(tz.app)
    try:
        await _entra(client)
        pagina = await (await client.get(BASE)).text()
        assert f"{BASE}/{tz.rid}" in pagina and str(UTENTE_TICKET) in pagina
        assert "<b>bene</b>" not in pagina and "&lt;b&gt;bene&lt;/b&gt;" in pagina  # il motivo e' testo
        r = await client.get(f"{BASE}/{tz.rid}")
        assert r.status == 200 and "messaggio riservato" in await r.text()
        csp = r.headers["Content-Security-Policy"]
        assert "img-src data:" in csp and "script" not in csp and "sandbox" in csp
        assert r.headers["Cache-Control"] == "no-store" and r.headers["X-Content-Type-Options"] == "nosniff"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_ricerca_per_utente_voto_e_motivo(tz):
    client = await _client(tz.app)
    try:
        await _entra(client)
        async def cerca(**q):
            return await (await client.get(BASE, params=q)).text()
        assert f"{BASE}/{tz.rid}" in await cerca(utente=f"<@{UTENTE_TICKET}>")
        assert f"{BASE}/{tz.rid}" in await cerca(voto="5", motivo="risolto")
        assert f"{BASE}/{tz.rid}" not in await cerca(utente="700000000000000002")
        assert f"{BASE}/{tz.rid}" not in await cerca(voto="1")
        assert f"{BASE}/{tz.rid}" not in await cerca(motivo="mai scritto")
        assert (await client.get(BASE, params={"utente": "x" * 500, "pannello": "zz", "voto": "99", "pagina": "-3"})).status == 200
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_estraneo_e_trascrizione_inesistente_hanno_la_stessa_risposta(tz, monkeypatch):
    # Legge il pannello (ruolo «lettura»), ma non e' staff di questo ticket e non ha «Gestisci server».
    monkeypatch.setattr(panel_bridge, "livello_accesso", AsyncMock(return_value="lettura"))
    tz.membri[ADMIN] = fake_member(ADMIN, "Estraneo", roles=[], guild_permissions=discord.Permissions())
    await db.set_guild_setting(GUILD, "ticket_support_role_ids", [999])
    client = await _client(tz.app)
    try:
        await _entra(client)
        niente = await client.get(f"{BASE}/{tz.rid}")
        inesistente = await client.get(f"{BASE}/999999")
        assert niente.status == inesistente.status == 404
        assert await niente.text() == await inesistente.text()
        assert "messaggio riservato" not in await niente.text()
        assert f"{BASE}/{tz.rid}" not in await (await client.get(BASE)).text()  # nemmeno nell'elenco
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_scaduta_altro_server_e_dato_alterato_sono_non_trovate(tz, clean_db):
    client = await _client(tz.app)
    try:
        await _entra(client)
        corpo = await (await client.get(f"{BASE}/999999")).text()
        await clean_db.execute("UPDATE ticket_trascrizioni SET scade_il = now() - interval '1 second'")
        r = await client.get(f"{BASE}/{tz.rid}")
        assert r.status == 404 and await r.text() == corpo
        await clean_db.execute("UPDATE ticket_trascrizioni SET scade_il = now() + interval '1 day', guild_id = 1")
        assert (await client.get(f"{BASE}/{tz.rid}")).status == 404
        await clean_db.execute(f"UPDATE ticket_trascrizioni SET guild_id = {GUILD}, cifrato = 'v2.aaaaaaaa.AAAA'")
        r = await client.get(f"{BASE}/{tz.rid}")
        assert r.status == 404 and await r.text() == corpo
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_staff_solo_admin_e_permessi_riletti_a_ogni_richiesta(tz, clean_db, monkeypatch):
    monkeypatch.setattr(panel_bridge, "livello_accesso", AsyncMock(return_value="lettura"))
    await clean_db.execute("UPDATE tickets SET solo_admin = TRUE WHERE id = $1", tz.ticket.id)
    await clean_db.execute("INSERT INTO ticket_ruoli_livello (guild_id, role_id, livello) VALUES ($1, 9999, 'admin')", GUILD)
    tz.membri[ADMIN] = fake_member(ADMIN, "Staff", roles=[fake_role(RUOLO_STAFF, "Supporto")], guild_permissions=discord.Permissions())
    client = await _client(tz.app)
    try:
        await _entra(client)
        # staff semplice (senza «Gestisci server») su un ticket «solo admin»: non lo vede
        assert (await client.get(f"{BASE}/{tz.rid}")).status == 404
        await clean_db.execute("UPDATE tickets SET solo_admin = FALSE WHERE id = $1", tz.ticket.id)
        assert (await client.get(f"{BASE}/{tz.rid}")).status == 200
        tz.membri[ADMIN] = fake_member(ADMIN, "Ex staff", roles=[], guild_permissions=discord.Permissions())
        assert (await client.get(f"{BASE}/{tz.rid}")).status == 404
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_opzioni_con_csrf_e_giorni_validi(tz):
    client = await _client(tz.app)
    try:
        await _entra(client)
        csrf = await _csrf(client, BASE)
        assert (await client.post(f"{BASE}/opzioni", data={"giorni": "30", "attiva": "1"})).status == 403
        assert (await repo.opzioni(GUILD)).giorni == 90
        for cattivo in ("0", "91", "abc", ""):
            r = await client.post(f"{BASE}/opzioni", data={"csrf": csrf, "giorni": cattivo, "attiva": "1"}, allow_redirects=False)
            assert "esito=trascrizioni_giorni" in r.headers["Location"]
        r = await client.post(f"{BASE}/opzioni", data={"csrf": csrf, "giorni": "30", "attiva": "1"}, allow_redirects=False)
        assert "esito=trascrizioni_salvate" in r.headers["Location"]
        assert (await repo.opzioni(GUILD)) == SimpleNamespace_eq(True, 30)
        await client.post(f"{BASE}/opzioni", data={"csrf": csrf, "giorni": "30"})  # casella tolta = spenta
        assert (await repo.opzioni(GUILD)).attiva is False
    finally:
        await client.close()


def SimpleNamespace_eq(attiva, giorni):
    from core.repositories.ticket_trascrizioni_repo import Opzioni
    return Opzioni(attiva, giorni)
