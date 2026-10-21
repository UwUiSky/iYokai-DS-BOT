"""
tests/test_alt_detection.py
===========================
Verifica dalla pagina web e account doppi (NF-21, SPEC §4.2–4.3): link
firmato e a scadenza, impronte senza IP e diverse tra server, doppi solo
nello stesso server, avviso allo staff senza ban, pagina del pannello.
"""

import re
import secrets
from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import discord
import pytest
from aiohttp.test_utils import TestClient, TestServer

import core.database as database_module
from core import alt_detection_logic as logica
from core import panel_bridge
from core.repositories.fingerprint_repo import FingerprintRepository
from core.repositories.verify_repo import verify_repo
from core.repositories.web_panel_session_repo import WebPanelSessionRepository
from core.verify_logic import VerifyOutcome
from core.web_panel_server import build_app
from tests.support.discord_fakes import fake_guild, fake_member

CHIAVE = "k" * 40
GUILD = 9100
MEMBRO = 41
ALT = 42


# ---------------------------------------------------------------- logica
def test_token_firmato_e_a_scadenza():
    token = logica.crea_token(CHIAVE, GUILD, MEMBRO, adesso=1000)
    assert logica.leggi_token(CHIAVE, token, adesso=1000) == (GUILD, MEMBRO)
    assert logica.leggi_token(CHIAVE, token, adesso=1000 + logica.DURATA_LINK_SECONDI + 1) is None
    assert logica.leggi_token("x" * 40, token, adesso=1000) is None
    falso = token.replace(f"-{MEMBRO}-", f"-{ALT}-")
    assert logica.leggi_token(CHIAVE, falso, adesso=1000) is None
    assert logica.leggi_token(CHIAVE, "1-2-3", adesso=0) is None


def test_impronte_senza_ip_e_diverse_tra_server():
    a = logica.impronte_richiesta(CHIAVE, GUILD, "203.0.113.7", "Firefox", "it")
    b = logica.impronte_richiesta(CHIAVE, GUILD + 1, "203.0.113.7", "Firefox", "it")
    assert set(a) == {logica.TIPO_IP, logica.TIPO_BROWSER}
    assert "203.0.113.7" not in str(a)
    assert a[logica.TIPO_IP] != b[logica.TIPO_IP]
    # IPv6: la stessa rete /64 dà la stessa impronta.
    x = logica.impronte_richiesta(CHIAVE, GUILD, "2001:db8::1", None, None)
    y = logica.impronte_richiesta(CHIAVE, GUILD, "2001:db8::ffff", None, None)
    assert x == y and logica.TIPO_BROWSER not in x
    assert logica.impronte_richiesta(CHIAVE, GUILD, "?", None, None) == {}


def test_ip_di_un_proxy_o_di_una_rete_interna_non_fa_impronta():
    # Pannello dietro un proxy non dichiarato (WEB_PANEL_TRUSTED_PROXY vuoto) o in Docker: tutti
    # arrivano dallo stesso IP interno e sarebbero tutti «doppi» di tutti.
    for ip in ("127.0.0.1", "10.0.0.5", "172.17.0.1", "192.168.1.10", "::1", "fd00::5", "::ffff:127.0.0.1"):
        assert logica.TIPO_IP not in logica.impronte_richiesta(CHIAVE, GUILD, ip, "Firefox", "it"), ip
    assert logica.TIPO_IP in logica.impronte_richiesta(CHIAVE, GUILD, "198.51.100.9", None, None)


def test_solo_la_stessa_rete_fa_un_doppio():
    doppi = logica.valuta_doppi([(7, "browser"), (8, "ip"), (9, "ip"), (9, "browser"), (MEMBRO, "ip")], MEMBRO)
    assert doppi == [logica.Doppio(9, logica.LIVELLO_ALTO), logica.Doppio(8, logica.LIVELLO_MEDIO)]
    testo = logica.testo_avviso("<@41>", MEMBRO, doppi)
    assert "Nessuna azione automatica" in testo and "`9`" in testo


# ------------------------------------------------------------ repository
@pytest.mark.asyncio
async def test_repo_trova_i_doppi_solo_nello_stesso_server(clean_db):
    repo = FingerprintRepository(pool_provider=lambda: clean_db)
    assert await repo.registra(GUILD, ALT, {"ip": "aaa", "browser": "bbb"}) == []
    await repo.registra(GUILD + 1, 77, {"ip": "aaa"})
    uguali = await repo.registra(GUILD, MEMBRO, {"ip": "aaa", "browser": "zzz"})
    assert uguali == [(ALT, "ip")]
    # Rinnovare le proprie impronte non crea un doppio con se stessi.
    assert await repo.registra(GUILD, MEMBRO, {"ip": "aaa"}) == [(ALT, "ip")]
    await repo.salva_doppi(GUILD, MEMBRO, [(ALT, "medio")])
    await repo.salva_doppi(GUILD, MEMBRO, [(ALT, "alto")])
    righe = await repo.elenco_doppi(GUILD)
    assert [(r["user_id"], r["altro_user_id"], r["livello"]) for r in righe] == [(MEMBRO, ALT, "alto")]


@pytest.mark.asyncio
async def test_copia_dei_dati_senza_l_id_dell_altro_account(clean_db):
    """«I miei dati» di uno dei due non deve dire chi è l'altro (stessa casa, stessa rete: dato di un terzo)."""
    from core.forget_user_service import esporta_utente

    repo = FingerprintRepository(pool_provider=lambda: clean_db)
    await repo.salva_doppi(GUILD, MEMBRO, [(ALT, "medio")])
    for chi, altro in ((ALT, MEMBRO), (MEMBRO, ALT)):
        dati = await esporta_utente(clean_db, chi)
        assert "verify_doppi" in dati["tabelle"]
        assert str(altro) not in str(dati["tabelle"]["verify_doppi"]), chi


# --------------------------------------------------- pannello e ponte
def _bot(membri, cog):
    guild = fake_guild(guild_id=GUILD, name="Server <i>prova</i>", owner_id=1)
    guild.get_member = MagicMock(side_effect=lambda uid: membri.get(uid))
    guild.fetch_member = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404), "no"))
    guild.get_channel = MagicMock(return_value=None)
    bot = MagicMock()
    bot.guilds = [guild]
    bot.get_guild = MagicMock(side_effect=lambda gid: guild if gid == GUILD else None)
    bot.get_cog = MagicMock(return_value=cog)
    return bot


@pytest.fixture
async def ambiente(monkeypatch, clean_db):
    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    monkeypatch.setattr(panel_bridge, "_cache_membri", OrderedDict())
    repo = FingerprintRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(panel_bridge, "fingerprint_repo", repo)
    await database_module.db.set_module_active_for_guild(GUILD, "verify", True)
    await verify_repo.set_config(
        guild_id=GUILD, method="web", verified_role_id=500, min_account_age_days=0,
        min_mutual_servers=0, captcha_enabled=False, log_channel_id=None,
    )
    cog = SimpleNamespace(run_checks_and_finalize=AsyncMock(return_value=VerifyOutcome(True, "Verificato.")))
    membri = {MEMBRO: fake_member(MEMBRO), ALT: fake_member(ALT)}
    bot = _bot(membri, cog)
    app = build_app(
        bot=bot, sessioni=WebPanelSessionRepository(pool_provider=lambda: clean_db), oauth=MagicMock(),
        client_id="1", client_secret="s" * 8, url_pubblico="http://pannello.test", chiave=CHIAVE,
        proxy_fidati=frozenset({"127.0.0.1"}),
    )
    client = TestClient(TestServer(app), cookie_jar=aiohttp.CookieJar(unsafe=True))
    await client.start_server()
    yield SimpleNamespace(client=client, cog=cog, repo=repo, bot=bot)
    await client.close()


async def _verifica(client, user_id, ua="Firefox"):
    token = logica.crea_token(CHIAVE, GUILD, user_id)
    intestazioni = {"User-Agent": ua, "X-Forwarded-For": "198.51.100.9"}  # dal proxy fidato
    pagina = await client.get(f"/verifica/{token}", headers=intestazioni)
    assert pagina.status == 200
    testo = await pagina.text()
    assert "Server &lt;i&gt;prova&lt;/i&gt;" in testo and "IP non viene mai salvato" in testo
    campo = re.search(r'name="campo" value="([^"]+)"', testo).group(1)
    return await client.post(f"/verifica/{token}", data={"campo": campo}, headers=intestazioni)


@pytest.mark.asyncio
async def test_pagina_verifica_e_doppio_segnalato(ambiente, monkeypatch):
    avvisi = []

    async def _avvisa(guild, membro, doppi):
        avvisi.append((membro.id, doppi))
        return True

    import cogs.security.alt_detection as cog_alt

    monkeypatch.setattr(cog_alt, "avvisa_staff", _avvisa)
    primo = await _verifica(ambiente.client, ALT)
    assert "Verificato." in await primo.text()
    assert avvisi == []
    secondo = await _verifica(ambiente.client, MEMBRO)
    assert secondo.status == 200
    assert avvisi == [(MEMBRO, [logica.Doppio(ALT, logica.LIVELLO_ALTO)])]
    assert ambiente.cog.run_checks_and_finalize.await_count == 2
    righe = await ambiente.repo.elenco_doppi(GUILD)
    assert [(r["user_id"], r["altro_user_id"]) for r in righe] == [(MEMBRO, ALT)]
    async with database_module.db.pool.acquire() as conn:
        assert "198.51.100.9" not in str(await conn.fetch("SELECT * FROM verify_impronte"))


@pytest.mark.asyncio
async def test_proxy_non_dichiarato_nessun_doppio(ambiente, monkeypatch):
    """Due persone diverse dietro lo stesso proxy locale non dichiarato: nessun avviso allo staff."""
    avvisi = []

    async def _avvisa(guild, membro, doppi):
        avvisi.append(membro.id)
        return True

    import cogs.security.alt_detection as cog_alt

    monkeypatch.setattr(cog_alt, "avvisa_staff", _avvisa)
    for user_id in (ALT, MEMBRO):
        token = logica.crea_token(CHIAVE, GUILD, user_id)
        testo = await (await ambiente.client.get(f"/verifica/{token}")).text()
        campo = re.search(r'name="campo" value="([^"]+)"', testo).group(1)
        # Senza X-Forwarded-For l'IP è quello del proxy (127.0.0.1) per tutti.
        await ambiente.client.post(f"/verifica/{token}", data={"campo": campo}, headers={"User-Agent": f"UA-{user_id}"})
    assert avvisi == []
    assert await ambiente.repo.elenco_doppi(GUILD) == []


@pytest.mark.asyncio
async def test_link_scaduto_o_campo_falso_rifiutati(ambiente):
    scaduto = logica.crea_token(CHIAVE, GUILD, MEMBRO, adesso=1)
    assert (await ambiente.client.get(f"/verifica/{scaduto}")).status == 400
    token = logica.crea_token(CHIAVE, GUILD, MEMBRO)
    risposta = await ambiente.client.post(f"/verifica/{token}", data={"campo": "x"})
    assert risposta.status == 400
    ambiente.cog.run_checks_and_finalize.assert_not_awaited()


@pytest.mark.asyncio
async def test_server_senza_modalita_web_rifiuta(ambiente):
    await verify_repo.set_config(
        guild_id=GUILD, method="button", verified_role_id=500, min_account_age_days=0,
        min_mutual_servers=0, captcha_enabled=False, log_channel_id=None,
    )
    token = logica.crea_token(CHIAVE, GUILD, MEMBRO)
    risposta = await ambiente.client.get(f"/verifica/{token}")
    assert risposta.status == 400
    assert "non usa più la verifica dalla pagina web" in await risposta.text()


def test_link_verifica_solo_con_pannello_acceso(monkeypatch):
    import dataclasses

    from core.config import config

    monkeypatch.setattr(panel_bridge, "config", dataclasses.replace(config, WEB_PANEL_SECRET_KEY=""))
    assert panel_bridge.link_verifica_web(GUILD, MEMBRO) is None
    acceso = dataclasses.replace(
        config, WEB_PANEL_SECRET_KEY=secrets.token_urlsafe(40), WEB_PANEL_PUBLIC_URL="https://pannello.test/",
        OAUTH2_CLIENT_ID="1", OAUTH2_CLIENT_SECRET="segreto",
    )
    monkeypatch.setattr(panel_bridge, "config", acceso)
    link = panel_bridge.link_verifica_web(GUILD, MEMBRO)
    assert link.startswith("https://pannello.test/verifica/")
    assert logica.leggi_token(acceso.WEB_PANEL_SECRET_KEY, link.rsplit("/", 1)[1]) == (GUILD, MEMBRO)


@pytest.mark.asyncio
async def test_avviso_allo_staff_senza_menzioni(monkeypatch):
    import cogs.security.alt_detection as cog_alt

    canale = MagicMock(spec=discord.TextChannel)
    canale.send = AsyncMock()
    guild = fake_guild(guild_id=GUILD)
    guild.get_channel = MagicMock(return_value=canale)
    monkeypatch.setattr(
        cog_alt.verify_repo, "get_config", AsyncMock(return_value=SimpleNamespace(log_channel_id=5))
    )
    assert await cog_alt.avvisa_staff(guild, fake_member(MEMBRO), [logica.Doppio(ALT, "medio")])
    kwargs = canale.send.await_args.kwargs
    assert kwargs["allowed_mentions"].users is False
    assert str(ALT) in kwargs["embed"].description
