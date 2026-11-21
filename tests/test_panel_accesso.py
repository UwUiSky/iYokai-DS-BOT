"""
tests/test_panel_accesso.py
===========================
Ruoli del pannello in lettura e in scrittura (CFG-002) e politica dei comandi che vale anche nel pannello (CFG-027),
con aiohttp TestClient, sessioni vere su PostgreSQL e permessi ricontrollati a ogni richiesta.
"""

import secrets
from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import core.database as database_module
from core import command_groups, panel_bridge, web_panel_accesso as accesso
from core.config_schema import ImpostazioneNonValida
from core.database import db
from core.premium import PremiumModule, registry
from core.repositories.web_panel_session_repo import WebPanelSessionRepository
from core.web_panel_server import build_app
from tests.support.discord_fakes import fake_guild, fake_member, fake_role
from tests.test_web_panel_server import URL, _client, _csrf, _entra, _OAuthFinto

GUILD = 8801
ADMIN, LETTORE, SCRITTORE, ESTRANEO = 51, 52, 53, 54
R_LETTURA, R_SCRITTURA, R_ALTRO, R_MANAGED = 7001, 7002, 7003, 7004


@pytest.fixture
def ambiente(monkeypatch, clean_db, reset_premium_registry):
    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    monkeypatch.setattr(panel_bridge, "_cache_membri", OrderedDict())
    registry.register(PremiumModule("music", "Musica", "Prova", category="music"))
    ruoli = {
        R_LETTURA: fake_role(R_LETTURA, "Lettori"), R_SCRITTURA: fake_role(R_SCRITTURA, "Scrittori"),
        R_ALTRO: fake_role(R_ALTRO, "Altro"), R_MANAGED: fake_role(R_MANAGED, "Bot", managed=True),
    }
    membri = {
        ADMIN: fake_member(ADMIN, guild_permissions=discord.Permissions(manage_guild=True)),
        LETTORE: fake_member(LETTORE, roles=[ruoli[R_LETTURA]]),
        SCRITTORE: fake_member(SCRITTORE, roles=[ruoli[R_SCRITTURA]]),
        ESTRANEO: fake_member(ESTRANEO, roles=[ruoli[R_ALTRO]]),
    }
    guild = fake_guild(guild_id=GUILD, name="Server", owner_id=1)
    guild.roles = list(ruoli.values())
    guild.get_member = MagicMock(side_effect=lambda uid: membri.get(uid))
    guild.get_role = MagicMock(side_effect=lambda rid: ruoli.get(rid))
    guild.fetch_member = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404), "no"))
    bot = MagicMock()
    bot.guilds = [guild]
    bot.get_guild = MagicMock(side_effect=lambda gid: guild if gid == GUILD else None)
    bot.tree.get_commands = MagicMock(return_value=[])
    bot.application_id = 4242
    oauth = _OAuthFinto()
    sessioni = WebPanelSessionRepository(pool_provider=lambda: clean_db)
    app = build_app(
        bot=bot, sessioni=sessioni, oauth=oauth, client_id="1", client_secret="s" * 8,
        url_pubblico=URL, chiave=secrets.token_urlsafe(48),
    )
    return SimpleNamespace(app=app, bot=bot, guild=guild, oauth=oauth, membri=membri, ruoli=ruoli, pool=clean_db)


async def _come(ambiente, utente):
    ambiente.oauth.utente_id = utente
    client = await _client(ambiente.app)
    await _entra(client)
    return client


async def _imposta(ambiente, livello, ruoli):
    await accesso.imposta_ruoli(ambiente.guild, livello, ruoli, ADMIN)


@pytest.mark.asyncio
async def test_lettore_vede_ma_non_scrive(ambiente):
    await _imposta(ambiente, "lettura", [R_LETTURA])
    client = await _come(ambiente, LETTORE)
    try:
        assert "Server" in await (await client.get("/")).text()  # il suo server è nell'elenco
        pagina = await client.get(f"/server/{GUILD}")
        assert pagina.status == 200 and "sola lettura" in await pagina.text()
        csrf = await _csrf(client, f"/server/{GUILD}")
        scrittura = await client.post(f"/server/{GUILD}/lingua", data={"csrf": csrf, "lingua": "en"}, allow_redirects=False)
        assert scrittura.status == 403
        assert await db.get_guild_language(GUILD) != "en"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_scrittore_salva_ma_non_cambia_gli_accessi(ambiente):
    await _imposta(ambiente, "scrittura", [R_SCRITTURA])
    client = await _come(ambiente, SCRITTORE)
    try:
        csrf = await _csrf(client, f"/server/{GUILD}")
        ok = await client.post(f"/server/{GUILD}/lingua", data={"csrf": csrf, "lingua": "en"}, allow_redirects=False)
        assert ok.status == 302 and "esito=salvato" in ok.headers["Location"]
        assert (await client.get(f"/server/{GUILD}/accesso")).status == 403
        nega = await client.post(
            f"/server/{GUILD}/accesso", data={"csrf": csrf, "livello": "scrittura", "ruolo": str(R_ALTRO)}, allow_redirects=False
        )
        assert nega.status == 403
        assert (await accesso.leggi_ruoli(GUILD))["scrittura"] == frozenset({R_SCRITTURA})
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_il_ruolo_tolto_vale_alla_richiesta_dopo(ambiente):
    await _imposta(ambiente, "lettura", [R_LETTURA])
    client = await _come(ambiente, LETTORE)
    try:
        assert (await client.get(f"/server/{GUILD}")).status == 200
        ambiente.membri[LETTORE].roles = []  # il ruolo gli viene tolto
        assert (await client.get(f"/server/{GUILD}")).status == 403
        await _imposta(ambiente, "lettura", [])
        ambiente.membri[LETTORE].roles = [ambiente.ruoli[R_LETTURA]]
        assert (await client.get(f"/server/{GUILD}")).status == 403  # e il ruolo tolto dal pannello
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_estraneo_e_server_inesistente_hanno_la_stessa_risposta(ambiente):
    await _imposta(ambiente, "lettura", [R_LETTURA])
    client = await _come(ambiente, ESTRANEO)
    try:
        a = await client.get(f"/server/{GUILD}")
        b = await client.get("/server/999999")
        assert a.status == b.status == 403
        assert await a.text() == await b.text()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_admin_sceglie_i_ruoli_con_csrf_e_storico(ambiente):
    client = await _come(ambiente, ADMIN)
    try:
        csrf = await _csrf(client, f"/server/{GUILD}/accesso")
        senza = await client.post(f"/server/{GUILD}/accesso", data={"livello": "lettura", "ruolo": str(R_LETTURA)}, allow_redirects=False)
        assert senza.status == 403
        ok = await client.post(
            f"/server/{GUILD}/accesso", data={"csrf": csrf, "livello": "lettura", "ruolo": str(R_LETTURA)}, allow_redirects=False
        )
        assert ok.status == 302 and "esito=salvato" in ok.headers["Location"]
        assert (await accesso.leggi_ruoli(GUILD))["lettura"] == frozenset({R_LETTURA})
        storico = await ambiente.pool.fetch("SELECT key_name, changed_by FROM guild_config_history WHERE guild_id = $1", GUILD)
        assert [(r["key_name"], r["changed_by"]) for r in storico] == [("panel_ruoli_lettura", ADMIN)]
        # id storto: niente salvato
        storto = await client.post(
            f"/server/{GUILD}/accesso", data={"csrf": csrf, "livello": "lettura", "ruolo": "12abc"}, allow_redirects=False
        )
        assert "esito=non_valido" in storto.headers["Location"]
        assert (await accesso.leggi_ruoli(GUILD))["lettura"] == frozenset({R_LETTURA})
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_imposta_ruoli_rifiuta_i_valori_storti(ambiente):
    g = ambiente.guild
    for livello, ruoli in (
        ("admin", [R_ALTRO]), ("lettura", [GUILD]), ("lettura", [R_MANAGED]), ("lettura", [123456]),
        ("lettura", list(range(9000, 9011))),
    ):
        with pytest.raises(ImpostazioneNonValida):
            await accesso.imposta_ruoli(g, livello, ruoli, ADMIN)
    assert await accesso.imposta_ruoli(g, "lettura", [R_ALTRO, R_ALTRO], ADMIN) is True
    assert await accesso.imposta_ruoli(g, "lettura", [R_ALTRO], ADMIN) is False  # già così
    await accesso.imposta_ruoli(g, "scrittura", [R_ALTRO], ADMIN)  # un ruolo ha un solo livello
    assert (await accesso.leggi_ruoli(GUILD)) == {"lettura": frozenset(), "scrittura": frozenset({R_ALTRO})}


@pytest.mark.asyncio
async def test_politica_comando_spento_blocca_la_scrittura_nel_pannello(ambiente):
    await _imposta(ambiente, "scrittura", [R_SCRITTURA])
    client = await _come(ambiente, SCRITTORE)
    try:
        csrf = await _csrf(client, f"/server/{GUILD}")
        dati = {"csrf": csrf, "chiave": "music_max_volume", "valore": "80"}
        ok = await client.post(f"/server/{GUILD}/modulo/music", data=dati, allow_redirects=False)
        assert ok.status == 302 and "esito=salvato" in ok.headers["Location"]
        await db.set_guild_setting(GUILD, "policy_comandi_off", ["admin-musica"], changed_by=ADMIN)
        dati["valore"] = "90"
        bloccato = await client.post(f"/server/{GUILD}/modulo/music", data=dati, allow_redirects=False)
        assert bloccato.status == 403
        assert await db.get_guild_setting(GUILD, "music_max_volume") == 80
        assert (await client.get(f"/server/{GUILD}/modulo/music")).status == 200  # leggere resta possibile
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_politica_ruolo_richiesto_non_blocca_chi_gestisce_il_server(ambiente):
    await db.set_guild_setting(GUILD, "policy_ruoli_richiesti", {"admin-musica": [R_ALTRO]}, changed_by=ADMIN)
    await _imposta(ambiente, "scrittura", [R_SCRITTURA])
    scrittore = await _come(ambiente, SCRITTORE)
    try:
        csrf = await _csrf(scrittore, f"/server/{GUILD}")
        r = await scrittore.post(
            f"/server/{GUILD}/modulo/music", data={"csrf": csrf, "chiave": "music_max_volume", "valore": "70"}, allow_redirects=False
        )
        assert r.status == 403
    finally:
        await scrittore.close()
    admin = await _come(ambiente, ADMIN)
    try:
        csrf = await _csrf(admin, f"/server/{GUILD}")
        r = await admin.post(
            f"/server/{GUILD}/modulo/music", data={"csrf": csrf, "chiave": "music_max_volume", "valore": "70"}, allow_redirects=False
        )
        assert r.status == 302 and "esito=salvato" in r.headers["Location"]
    finally:
        await admin.close()


def test_i_gruppi_della_mappa_esistono():
    nomi = set(command_groups.nomi_gruppi())
    assert set(accesso.GRUPPO_PER_AREA.values()) <= nomi
    assert set(accesso.GRUPPO_PER_MODULO.values()) <= nomi
    assert accesso.percorso_comando("/server/1/modulo/music") == "admin-musica"
    assert accesso.percorso_comando("/server/1/lingua") is None


@pytest.mark.asyncio
async def test_panoramica_si_apre_anche_se_il_punteggio_non_arriva(ambiente, monkeypatch):
    from core import web_panel_panoramica

    async def _rotta(guild):
        raise RuntimeError("segnali non disponibili")

    monkeypatch.setattr("cogs.security.security_score._collect_signals", _rotta)
    await _imposta(ambiente, "lettura", [R_LETTURA])
    client = await _come(ambiente, LETTORE)
    try:
        r = await client.get(f"/server/{GUILD}/panoramica")
        testo = await r.text()
        assert r.status == 200 and "moduli accesi" in testo and "non è disponibile" in testo
        assert "RuntimeError" not in testo
    finally:
        await client.close()
    assert web_panel_panoramica.riassumi_moduli([{"attivo": False, "titolo": "B"}, {"attivo": True, "titolo": "A"}])["accesi"] == 1
