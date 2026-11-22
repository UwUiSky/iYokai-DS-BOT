"""
tests/test_panel_backup.py
==========================
Pagina dei backup nel pannello (BKP-041, SPEC §24.9): elenco, scheda ed eliminazione con conferma, con gli stessi permessi
dei comandi (BKP-018). Nessun caricamento dal web. Sessioni e database veri, Discord finto.
"""

import discord
import pytest

from core.backup_permessi_logic import LIVELLO_SOLO_OWNER, SETTING_LIVELLO
from core.database import db
from core.repositories.backup_struttura_repo import BackupStrutturaRepository, backup_struttura_repo
from tests.support.discord_fakes import fake_member
from tests.test_web_panel_server import ADMIN, GUILD, _client, _csrf, _entra, ambiente  # noqa: F401

BASE = f"/server/{GUILD}/backup"
PROPRIETARIO = 1
ALTRO_SERVER = 8801


@pytest.fixture
async def bk(ambiente, clean_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(backup_struttura_repo, "_pool_provider", lambda: clean_db)
    for g in (GUILD, ALTRO_SERVER):
        await db.ensure_guild_exists(g)
    # Il proprietario del server (id 1) e un admin vero (31, «Amministratore»).
    ambiente.membri[PROPRIETARIO] = fake_member(PROPRIETARIO, guild_permissions=discord.Permissions(administrator=True))
    ambiente.membri[ADMIN] = fake_member(ADMIN, guild_permissions=discord.Permissions(administrator=True, manage_guild=True))
    dati = {"ruoli": [{"nome": "a"}, {"nome": "b"}], "canali": [{"nome": "c"}]}
    ambiente.copia = await backup_struttura_repo.salva_struttura(GUILD, "Copia <b>1</b>", ADMIN, dati)
    ambiente.altra = await backup_struttura_repo.salva_struttura(ALTRO_SERVER, "Di un altro", ADMIN, dati)
    return ambiente


@pytest.mark.asyncio
async def test_elenco_e_scheda_con_escape(bk):
    client = await _client(bk.app)
    try:
        assert (await client.get(BASE, allow_redirects=False)).headers["Location"] == "/accedi"
        await _entra(client)
        pagina = await (await client.get(BASE)).text()
        assert "Copia &lt;b&gt;1&lt;/b&gt;" in pagina and "Di un altro" not in pagina
        scheda = await (await client.get(f"{BASE}/{bk.copia}")).text()
        assert "ruoli" in scheda and "2" in scheda and "Copia &lt;b&gt;1&lt;/b&gt;" in scheda
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_copia_di_un_altro_server_non_si_vede_ne_si_elimina(bk):
    client = await _client(bk.app)
    try:
        await _entra(client)
        assert (await client.get(f"{BASE}/{bk.altra}")).status == 404
        csrf = await _csrf(client, BASE)
        r = await client.post(f"{BASE}/{bk.altra}/elimina", data={"csrf": csrf})
        assert r.status == 404
        assert await backup_struttura_repo.leggi_struttura(ALTRO_SERVER, bk.altra) is not None
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_eliminazione_chiede_conferma_csrf_e_si_registra(bk):
    client = await _client(bk.app)
    try:
        await _entra(client)
        conferma = await (await client.get(f"{BASE}/{bk.copia}/elimina")).text()
        assert "method=\"post\"" in conferma and await backup_struttura_repo.leggi_struttura(GUILD, bk.copia)
        csrf = await _csrf(client, f"{BASE}/{bk.copia}/elimina")
        assert (await client.post(f"{BASE}/{bk.copia}/elimina", data={})).status == 403
        assert await backup_struttura_repo.leggi_struttura(GUILD, bk.copia) is not None
        r = await client.post(f"{BASE}/{bk.copia}/elimina", data={"csrf": csrf}, allow_redirects=False)
        assert r.status == 302 and r.headers["Location"].startswith(BASE)
        assert await backup_struttura_repo.leggi_struttura(GUILD, bk.copia) is None
        registro = await backup_struttura_repo.leggi_registro(GUILD)
        assert registro[0]["azione"] == "elimina" and registro[0]["user_id"] == ADMIN and "web" in registro[0]["dettaglio"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_stessi_permessi_dei_comandi(bk):
    await db.set_guild_setting(GUILD, SETTING_LIVELLO, LIVELLO_SOLO_OWNER)
    client = await _client(bk.app)
    try:
        await _entra(client)  # admin non proprietario, livello «solo owner»: niente, né lettura né eliminazione
        assert (await client.get(BASE)).status == 403
        assert (await client.get(f"{BASE}/{bk.copia}")).status == 403
        r = await client.post(f"{BASE}/{bk.copia}/elimina", data={"csrf": "x"})
        assert r.status == 403
        assert await backup_struttura_repo.leggi_struttura(GUILD, bk.copia) is not None
    finally:
        await client.close()
    bk.oauth.utente_id = PROPRIETARIO
    client = await _client(bk.app)
    try:
        await _entra(client)
        assert (await client.get(BASE)).status == 200
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_senza_amministratore_non_si_entra_e_non_si_carica_dal_web(bk):
    bk.membri[ADMIN] = fake_member(ADMIN, guild_permissions=discord.Permissions(manage_guild=True))
    client = await _client(bk.app)
    try:
        await _entra(client)
        assert (await client.get(BASE)).status == 403
        bk.membri[ADMIN] = fake_member(ADMIN, guild_permissions=discord.Permissions(administrator=True))
        for percorso in (f"{BASE}/carica", f"{BASE}/{bk.copia}/carica"):
            for metodo in (client.get, client.post):
                assert (await metodo(percorso)).status in (404, 405)
    finally:
        await client.close()
