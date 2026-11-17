"""
tests/test_giochi_monete_b2.py
==============================
Roulette, carta, scala, statistiche e record (#125 B2): ECO-021, ECO-022, ECO-090, ECO-099,
ECO-100, ECO-115, ECO-116. Logica con seme fisso, partite su PostgreSQL vero.
Funzioni coperte: SPEC §23.16 (NF-40), catalogo #125
"""

import random
from collections import Counter

import pytest

from cogs.fun.giochi_monete import GiochiMoneteCog
from core.coin_games_logic import (
    PAGAMENTI_CARTA, SCOMMESSE_ROULETTE, gioca_carta, gioca_roulette, gioca_scala, numero_vince, resa_media_scala,
)
from core.repositories.economia_repo import economia_repo
from core.repositories.leveling_repo import leveling_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.moduli import attiva_livelli

G = 100


class _Fisso:
    def __init__(self, *valori):
        self.valori = list(valori)

    def randint(self, a, b):
        return self.valori.pop(0)

    def choice(self, seq):
        return seq[self.valori.pop(0)]


def test_roulette_colori_zero_e_numero():
    assert numero_vince("rosso", 1) and not numero_vince("nero", 1) and numero_vince("nero", 2)
    assert not any(numero_vince(s, 0) for s in SCOMMESSE_ROULETTE if s != "numero")
    assert numero_vince("numero", 0, 0) and not numero_vince("numero", 5, 6)
    assert numero_vince("colonna3", 36) and numero_vince("dozzina2", 13) and numero_vince("alto", 19)
    e = gioca_roulette("numero", 10, _Fisso(17), 17)
    assert e.restituzione == 360
    assert gioca_roulette("rosso", 10, _Fisso(0)).restituzione == 0
    for brutto in (("boh", None), ("numero", None), ("numero", 37)):
        with pytest.raises(ValueError):
            gioca_roulette(brutto[0], 10, _Fisso(1), brutto[1])


def test_roulette_ogni_scommessa_ha_vantaggio_del_banco():
    for scelta, molt in SCOMMESSE_ROULETTE.items():
        vincenti = sum(numero_vince(scelta, n, 7) for n in range(37))
        assert vincenti * molt / 37 < 1, scelta


def test_carta_pagamenti_e_scelte():
    assert gioca_carta("colore", "rosso", 100, _Fisso(0, 5)).restituzione == 190  # cuori = rosso
    assert gioca_carta("colore", "nero", 100, _Fisso(0, 5)).restituzione == 0
    assert gioca_carta("valore", "A", 10, _Fisso(2, 0)).restituzione == 120
    assert gioca_carta("seme", "picche", 10, _Fisso(3, 4)).restituzione == 38
    with pytest.raises(ValueError):
        gioca_carta("seme", "rosso", 10, _Fisso(0, 0))
    assert 19 / 20 < 1 and PAGAMENTI_CARTA["seme"] / 40 < 1 and PAGAMENTI_CARTA["valore"] / 130 < 1


def test_scala_resa_sotto_uno_e_distribuzione():
    assert resa_media_scala() < 1
    rng = random.Random(1)
    c = Counter(gioca_scala(100, rng).restituzione for _ in range(20000))
    assert set(c) == {0, 50, 150, 300, 600, 2000}
    assert gioca_scala(7, _Fisso(1)).restituzione == 0 and gioca_scala(100, _Fisso(100)).restituzione == 20000 // 10


@pytest.fixture
async def cog(monkeypatch, clean_db):
    await attiva_livelli(monkeypatch, clean_db, G)

    async def attivo(self, guild_id, nome):
        return True

    from core.database import db
    monkeypatch.setattr(type(db), "is_module_active_for_guild", attivo)
    c = GiochiMoneteCog(bot=None)
    yield c
    leveling_settings_repo._cache.clear()


def _i(uid=1):
    return fake_interaction(guild=fake_guild(G), user=fake_member(uid))


def _scelta(v):
    from types import SimpleNamespace
    return SimpleNamespace(value=v, name=v)


@pytest.mark.asyncio
async def test_puntate_del_server_pausa_e_statistiche(cog, clean_db):
    await leveling_repo.add_coins(G, 1, 1000)
    await leveling_settings_repo.set_options(G, puntata_min=10, puntata_max=100, attesa_gioco=0)
    for p in (5, 101):
        i = _i()
        await cog.scala.callback(cog, i, p)
        assert i.response.send_message.await_args.kwargs.get("ephemeral") is True
    assert (await leveling_repo.get_totals(G, 1)).coins_total == 1000  # niente scalato
    for _ in range(5):
        await cog.scala.callback(cog, _i(), 50)
    righe = await economia_repo.statistiche_giocatore(G, 1)
    assert righe[0]["gioco"] == "scala" and righe[0]["partite"] == 5
    assert (await leveling_repo.get_totals(G, 1)).coins_total == 1000 + righe[0]["netto"]


@pytest.mark.asyncio
async def test_pausa_tra_partite_e_saldo_non_basta(cog, clean_db):
    await leveling_repo.add_coins(G, 1, 60)
    await leveling_settings_repo.set_options(G, attesa_gioco=3600)
    await cog.scala.callback(cog, _i(), 50)
    i = _i()
    await cog.scala.callback(cog, i, 10)  # subito dopo: in pausa
    assert i.response.send_message.await_args.kwargs.get("ephemeral") is True
    await leveling_settings_repo.set_options(G, attesa_gioco=0)
    saldo = (await leveling_repo.get_totals(G, 1)).coins_total
    i2 = _i()
    await cog.scala.callback(cog, i2, 100)  # più del saldo
    assert (await leveling_repo.get_totals(G, 1)).coins_total == saldo


@pytest.mark.asyncio
async def test_record_una_riga_per_persona(cog, clean_db):
    await economia_repo.registra_partita(G, 1, "slot", 10, 100)
    await economia_repo.registra_partita(G, 1, "dadi", 10, 40)
    await economia_repo.registra_partita(G, 2, "slot", 10, 0)
    r = await economia_repo.vincite_piu_grosse(G)
    assert [(x["user_id"], x["vincita"], x["gioco"]) for x in r] == [(1, 90, "slot")]
