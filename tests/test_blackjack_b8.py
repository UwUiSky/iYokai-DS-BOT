"""
tests/test_blackjack_b8.py
==========================
Blackjack e partite a più passi (#125 B8): ECO-088, ECO-089. Regole con mazzo fisso; la puntata
si toglie all'apertura, la partita si chiude una sola volta, le abbandonate tornano a chi giocava.
Funzioni coperte: catalogo #125
"""

import asyncio
import random
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cogs.fun.blackjack import BlackjackView
from core.blackjack_logic import e_blackjack, gioca_banco, nuovo_mazzo, restituzione, restituzione_resa, valore
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.partite_repo import EsitoApertura, PartiteRepository
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

G = 100


def test_valori_blackjack_e_pagamenti():
    assert valore([1, 13]) == 21 and e_blackjack([1, 12]) and not e_blackjack([5, 6, 10])
    assert valore([1, 1, 9]) == 21 and valore([1, 5, 10]) == 16 and valore([10, 10, 5]) == 25
    assert restituzione([10, 10, 5], [10, 7], 100) == 0  # sballato
    assert restituzione([1, 13], [10, 7], 100) == 250  # naturale 3:2
    assert restituzione([1, 13], [1, 12], 100) == 100  # naturale pari
    assert restituzione([10, 9], [10, 7], 100) == 200 and restituzione([10, 7], [10, 7], 100) == 100
    assert restituzione([10, 6], [10, 9], 100) == 0 and restituzione([10, 6], [10, 8, 9], 100) == 200  # banco sballa
    assert restituzione_resa(101) == 50
    m = nuovo_mazzo(random.Random(3))
    assert len(m) == 52 and sorted(m) == sorted([v for v in range(1, 14) for _ in range(4)])
    assert valore(gioca_banco([10, 2], [5, 9])) == 17 or valore(gioca_banco([10, 2], [9, 5])) >= 17


def test_il_banco_ha_un_vantaggio_giocando_sempre_fermo_a_17():
    rng = random.Random(11)
    tot = 0
    n = 20000
    for _ in range(n):
        m = nuovo_mazzo(rng)
        g, b = [m.pop(), m.pop()], [m.pop(), m.pop()]
        while valore(g) < 17:
            g.append(m.pop())
        if valore(g) <= 21:
            gioca_banco(b, m)
        tot += restituzione(g, b, 100) - 100
    assert tot / n < 0  # in media il giocatore perde


@pytest.fixture
def r(clean_db):
    return SimpleNamespace(
        p=PartiteRepository(pool_provider=lambda: clean_db), lev=LevelingRepository(pool_provider=lambda: clean_db), pool=clean_db
    )


@pytest.mark.asyncio
async def test_apertura_toglie_la_puntata_una_partita_alla_volta_e_rispetta_la_pausa(r):
    await r.lev.add_coins(G, 1, 100)
    assert (await r.p.apri(G, 1, "blackjack", 101, 0)).esito is EsitoApertura.POCHE
    assert (await r.lev.get_totals(G, 1)).coins_total == 100
    a = await r.p.apri(G, 1, "blackjack", 60, 0)
    assert a.esito is EsitoApertura.APERTA and (await r.lev.get_totals(G, 1)).coins_total == 40
    assert (await r.p.apri(G, 1, "blackjack", 10, 0)).esito is EsitoApertura.GIA_APERTA
    assert (await r.lev.get_totals(G, 1)).coins_total == 40  # niente tolto per la seconda
    await r.p.chiudi(a.partita_id, G, 1, 0)
    assert (await r.p.apri(G, 1, "blackjack", 10, 3600)).esito is EsitoApertura.PAUSA
    with pytest.raises(ValueError):
        await r.p.apri(G, 1, "blackjack", 0, 0)


@pytest.mark.asyncio
async def test_chiusura_paga_una_volta_sola_anche_insieme(r):
    await r.lev.add_coins(G, 1, 100)
    a = await r.p.apri(G, 1, "blackjack", 50, 0)
    await apri_connessioni(r.pool, 4)
    esiti = await asyncio.gather(*[r.p.chiudi(a.partita_id, G, 1, 100) for _ in range(4)])
    assert len([e for e in esiti if e]) == 1
    assert (await r.lev.get_totals(G, 1)).coins_total == 150
    assert await r.p.chiudi(a.partita_id, G, 2, 100) is None


@pytest.mark.asyncio
async def test_raddoppio_e_rimborso_delle_abbandonate(r):
    await r.lev.add_coins(G, 1, 100)
    a = await r.p.apri(G, 1, "blackjack", 60, 0)  # restano 40
    assert await r.p.raddoppia(a.partita_id, G, 1) is False  # servono altri 60
    await r.lev.add_coins(G, 1, 60)
    assert await r.p.raddoppia(a.partita_id, G, 1) is True  # restano 40, puntata 120
    assert (await r.lev.get_totals(G, 1)).coins_total == 40
    await r.pool.execute("UPDATE economia_partite_aperte SET scade_at = now() - interval '1 second'")
    assert await r.p.rimborsa_scadute() == 1 and await r.p.rimborsa_scadute() == 0
    assert (await r.lev.get_totals(G, 1)).coins_total == 160  # puntata finale restituita intera
    assert await r.p.chiudi(a.partita_id, G, 1, 999) is None  # chiusa dal rimborso: non si paga


@pytest.mark.asyncio
async def test_vista_solo_il_giocatore_e_chiusura_unica(r, monkeypatch):
    import cogs.fun.blackjack as modulo
    import core.ui_base as ui

    async def nessuno(*a, **k):
        return False

    monkeypatch.setattr(ui, "_utente_o_server_in_blacklist", nessuno)
    monkeypatch.setattr(modulo, "partite_repo", r.p)
    monkeypatch.setattr(modulo, "economia_repo", SimpleNamespace(registra_partita=AsyncMock()))
    await r.lev.add_coins(G, 1, 100)
    a = await r.p.apri(G, 1, "blackjack", 50, 0)
    view = BlackjackView(a.partita_id, G, 1, 50, "coin")
    view.giocatore, view.banco, view.mazzo = [10, 9], [10, 7], [2, 3]
    estraneo = fake_interaction(guild=fake_guild(G), user=fake_member(2))
    assert await view.interaction_check(estraneo) is False
    i = fake_interaction(guild=fake_guild(G), user=fake_member(1))
    i.response.edit_message = AsyncMock()
    await view.stai.callback(i)
    assert (await r.lev.get_totals(G, 1)).coins_total == 150  # 19 contro 17: vince
    i2 = fake_interaction(guild=fake_guild(G), user=fake_member(1))
    await view.stai.callback(i2)  # già finita
    await view.on_timeout()  # il timeout dopo la fine non paga di nuovo
    assert (await r.lev.get_totals(G, 1)).coins_total == 150
