"""
tests/test_ticket_roblox_tkt088.py
==================================
TKT-088 (D121): nel ticket, il profilo Roblox di chi lo apre, da Bloxlink e dall'API pubblica di Roblox. Spento senza la
chiave nel .env e se il server non lo accende. Cache di un'ora, mai testo non controllato. Rete finta.
"""

import json
from types import SimpleNamespace

import pytest

from core import ticket_roblox as tr


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    tr._cache.clear()
    monkeypatch.setattr(tr, "config", SimpleNamespace(BLOXLINK_API_KEY="chiave-finta"))
    yield
    tr._cache.clear()


def _rete(monkeypatch, risposte):
    chiamate = []

    async def finta(url, **kw):
        chiamate.append((url, kw))
        for chiave, valore in risposte.items():
            if chiave in url:
                return valore if valore is None else json.dumps(valore)
        return None

    monkeypatch.setattr(tr.safe_http, "safe_richiesta", finta)
    return chiamate


BLOX = {"robloxID": "12345"}
ROBLOX = {"name": "Giocatore_1", "displayName": "Giocatore", "created": "2020-05-01T10:00:00.000Z", "isBanned": False, "id": 12345}


async def test_senza_chiave_e_spento_e_non_chiama_la_rete(monkeypatch):
    monkeypatch.setattr(tr, "config", SimpleNamespace(BLOXLINK_API_KEY=""))
    chiamate = _rete(monkeypatch, {})
    assert tr.disponibile() is False
    assert await tr.profilo(1, 2) is None
    assert chiamate == []


async def test_profilo_completo_con_chiave_nell_intestazione(monkeypatch):
    chiamate = _rete(monkeypatch, {"blox.link": BLOX, "users.roblox.com": ROBLOX})
    p = await tr.profilo(10, 20)
    assert p.nome == "Giocatore_1" and p.id == 12345 and p.creato.startswith("2020-05-01")
    assert chiamate[0][0].endswith("/guilds/10/discord-to-roblox/20")
    assert chiamate[0][1]["headers"]["Authorization"] == "chiave-finta"
    assert "Authorization" not in (chiamate[1][1].get("headers") or {})  # la chiave va solo a Bloxlink


async def test_cache_di_un_ora_anche_per_chi_non_e_collegato(monkeypatch):
    chiamate = _rete(monkeypatch, {"blox.link": None})
    assert await tr.profilo(10, 20) is None
    assert await tr.profilo(10, 20) is None
    assert len(chiamate) == 1


async def test_risposte_strane_si_scartano(monkeypatch):
    _rete(monkeypatch, {"blox.link": {"robloxID": "12; DROP"}, "users.roblox.com": ROBLOX})
    assert await tr.profilo(10, 20) is None
    tr._cache.clear()
    _rete(monkeypatch, {"blox.link": BLOX, "users.roblox.com": {"name": "x" * 80, "displayName": "a", "created": "boh"}})
    assert await tr.profilo(10, 20) is None


def test_il_campo_per_l_embed_non_pinga_e_ha_tetto():
    p = tr.Profilo(id=1, nome="Nome", nome_visto="@everyone", creato="2020-05-01T10:00:00.000Z", bannato=True)
    testo = tr.come_testo(p)
    assert "@everyone" not in testo.replace("@​everyone", "") and "roblox.com/users/1/profile" in testo
    assert len(testo) <= 1000
