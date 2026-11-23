"""
tests/test_voto.py
==================
Modulo «voto» (LIV-019, ECO-048, ECO-049, CFG-039): firma e segreto, voto letto con cura, due voti uguali pagano una
volta, un voto si riscatta una volta sola, spento senza chiave.
Funzioni coperte: catalogo #124, #125, #122
"""

import asyncio
import hashlib
import hmac
import json
from unittest.mock import AsyncMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

import cogs.leveling.voto as modulo
from core import voto_server
from core.repositories.voto_repo import VotoRepository
from core.voto_logic import leggi_voto, segreto_valido, verifica
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

SEGRETO = "segreto-di-prova"
G = 800


def _firma(corpo: bytes, t: float, segreto: str = SEGRETO) -> str:
    return f"t={int(t)},v1=" + hmac.new(segreto.encode(), f"{int(t)}.".encode() + corpo, hashlib.sha256).hexdigest()


def test_verifica_segreto_e_firma():
    assert verifica(SEGRETO, SEGRETO, None, b"{}") and not verifica(SEGRETO, "altro", None, b"{}")
    assert not verifica("", "", None, b"{}") and not verifica("corto", "corto", None, b"{}")  # senza chiave valida, mai
    assert not segreto_valido("   ") and segreto_valido(SEGRETO)
    corpo = b'{"type":"vote.create"}'
    assert verifica(SEGRETO, None, _firma(corpo, 1000), corpo, adesso=1100)
    assert not verifica(SEGRETO, None, _firma(corpo, 1000), corpo + b" ", adesso=1100)  # corpo cambiato
    assert not verifica(SEGRETO, None, _firma(corpo, 1000), corpo, adesso=1000 + 301)  # firma vecchia
    assert not verifica(SEGRETO, None, _firma(corpo, 1000, "altro-segreto"), corpo, adesso=1000)
    assert not verifica(SEGRETO, None, "t=abc,v1=00", corpo) and not verifica(SEGRETO, None, "rotta", corpo)


@pytest.mark.parametrize("corpo, atteso", [
    (b'{"type":"upvote","user":"123"}', 123), (b'{"type":"upvote","user":456}', 456),
    (b'{"type":"vote.create","data":{"user":{"platform_id":"789"}}}', 789),
    (b'{"type":"test","user":"1"}', None), (b'{"type":"upvote","user":"-5"}', None), (b'{"type":"upvote","user":"0"}', None),
    (b'{"type":"upvote","user":true}', None), (b'{"type":"upvote","user":"1e5"}', None), (b'[1]', None), (b"non json", None),
    (b'{"type":"upvote","user":"' + b"9" * 30 + b'"}', None), (b'{"type":"upvote"}', None),
])
def test_lettura_del_voto(corpo, atteso):
    voto = leggi_voto(corpo)
    assert (voto.user_id if voto else None) == atteso


@pytest.fixture
def repo(clean_db):
    return VotoRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_due_voti_uguali_pagano_una_volta(repo, clean_db):
    await repo.imposta(G, attivo=True, monete=50, xp=30, xp_bonus_pct=10)
    await apri_connessioni(clean_db, 6)
    ids = await asyncio.gather(*(repo.registra("topgg", 5) for _ in range(5)))
    assert len([i for i in ids if i]) == 1  # il sito rinvia lo stesso voto: ne vale uno
    assert await repo.registra("altrosito", 5) is not None  # un altro sito è un altro voto
    premi = await asyncio.gather(*(repo.riscatta(G, 5) for _ in range(5)))
    assert len([p for p in premi if p]) == 2  # due voti, due premi, nessuno doppio
    tot = await clean_db.fetchrow("SELECT coins_total, xp_total FROM leveling_totals WHERE guild_id = $1 AND user_id = 5", G)
    assert (tot["coins_total"], tot["xp_total"]) == (100, 60)
    assert await repo.riscatta(G, 5) is None and await repo.da_riscattare(5) == 0


@pytest.mark.asyncio
async def test_riscatto_spento_o_senza_voti_non_da_nulla(repo, clean_db):
    assert await repo.riscatta(G, 5) is None  # nessun voto
    await repo.registra("topgg", 5)
    assert await repo.riscatta(G, 5) is None and await repo.da_riscattare(5) == 1  # server spento: il voto resta
    await repo.imposta(G, attivo=True, monete=7)
    assert (await repo.riscatta(G, 5)).monete == 7
    await clean_db.execute("INSERT INTO voti (sito, user_id, ricevuto_at) VALUES ('x', 6, now() - interval '8 days')")
    assert await repo.riscatta(G, 6) is None  # dopo 7 giorni il voto si perde


@pytest.mark.asyncio
async def test_bonus_xp_e_riscatto_automatico(repo):
    await repo.imposta(G, attivo=True, xp_bonus_pct=25, xp_bonus_ore=12)
    assert await repo.fattore_xp(G, 5) == 1.0
    await repo.registra("topgg", 5)
    await repo.riscatta(G, 5)
    assert await repo.fattore_xp(G, 5) == 1.25 and await repo.fattore_xp(G + 1, 5) == 1.0
    assert await repo.auto_di(5) is None
    await repo.imposta_auto(5, G)
    assert await repo.auto_di(5) == G
    await repo.imposta_auto(5, None)
    assert await repo.auto_di(5) is None
    with pytest.raises(ValueError):
        await repo.imposta(G, colonna_strana=1)


@pytest.mark.asyncio
async def test_server_web_rifiuta_chi_non_ha_il_segreto_e_accetta_il_voto():
    visti = []

    async def registra(sito, user_id):
        visti.append(user_id)
        return len(visti) if user_id not in visti[:-1] else None

    dopo = []

    async def dopo_voto(u):
        dopo.append(u)

    app = voto_server.build_app(segreto=SEGRETO, registra=registra, dopo_voto=dopo_voto)
    async with TestClient(TestServer(app)) as c:
        corpo = json.dumps({"type": "upvote", "user": "42"})
        assert (await c.post("/voto", data=corpo)).status == 401
        assert (await c.post("/voto", data=corpo, headers={"Authorization": "sbagliato"})).status == 401
        assert visti == []
        r = await c.post("/voto", data=corpo, headers={"Authorization": SEGRETO})
        assert r.status == 200 and (await r.json())["voto"] is True and dopo == [42]
        r = await c.post("/voto", data=corpo, headers={"Authorization": SEGRETO})
        assert (await r.json())["voto"] is False and dopo == [42]  # ripetuto: nessun secondo premio
        r = await c.post("/voto", data='{"type":"test"}', headers={"Authorization": SEGRETO})
        assert r.status == 200 and (await r.json())["voto"] is False
        assert (await c.post("/voto", data=b"x" * 40_000, headers={"Authorization": SEGRETO})).status == 413


@pytest.mark.asyncio
async def test_senza_chiave_nessuna_rotta():
    app = voto_server.build_app(segreto="", registra=AsyncMock())
    async with TestClient(TestServer(app)) as c:
        assert (await c.post("/voto", data="{}", headers={"Authorization": ""})).status == 404


@pytest.mark.asyncio
async def test_cog_spento_senza_chiave_e_acceso_con_chiave(repo, clean_db, monkeypatch):
    from core.repositories.leveling_settings_repo import leveling_settings_repo

    monkeypatch.setattr(leveling_settings_repo, "_pool_provider", lambda: clean_db)
    leveling_settings_repo._cache = type(leveling_settings_repo._cache)(max_size=10)
    monkeypatch.setattr(modulo, "voto_repo", repo)
    monkeypatch.setattr(modulo, "_comando_rifiutato", AsyncMock(return_value=False))

    async def testo(interaction, chiave, **kw):
        return chiave

    monkeypatch.setattr(modulo, "testo_per", testo)
    monkeypatch.setattr(modulo, "modulo_acceso", lambda: False)
    cog = modulo.VotoCog(bot=None)
    await cog.cog_load()  # senza chiave: nessun errore e nessuna porta
    assert cog._runner is None
    i = fake_interaction(guild=fake_guild(G), user=fake_member(5))
    await cog.voto.callback(cog, i, None)
    assert i.response.send_message.call_args.args[0] == "voto_spento"
    monkeypatch.setattr(modulo, "modulo_acceso", lambda: True)
    i = fake_interaction(guild=fake_guild(G), user=fake_member(5))
    await cog.voto.callback(cog, i, None)
    assert i.response.send_message.call_args.args[0] == "voto_server_spento"
    await repo.imposta(G, attivo=True)
    i = fake_interaction(guild=fake_guild(G), user=fake_member(5))
    await cog.voto.callback(cog, i, None)
    assert i.response.send_message.call_args.args[0] == "voto_niente"
    leveling_settings_repo._cache = type(leveling_settings_repo._cache)(max_size=10)
