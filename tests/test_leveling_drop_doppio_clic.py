"""
tests/test_leveling_drop_doppio_clic.py
=======================================
BUG-17 (#33): due clic insieme sullo stesso drop devono pagare una
volta sola. Il saldo è letto dal database vero.
Funzioni coperte: SPEC §15.6
"""

import asyncio

import pytest

import cogs.leveling.leveling as leveling_module
from cogs.leveling.leveling import LevelingCog
from core.repositories.leveling_repo import LevelingRepository
from tests.support.discord_fakes import fake_interaction, fake_member

GUILD_ID = 100
IMPORTO = 40


@pytest.mark.asyncio
async def test_due_clic_insieme_pagano_una_volta_sola(clean_db, monkeypatch):
    repo = LevelingRepository(pool_provider=lambda: clean_db)
    chiamate: list[int] = []
    add_coins_vero = repo.add_coins

    async def add_coins_contato(guild_id, user_id, amount):
        chiamate.append(user_id)
        return await add_coins_vero(guild_id, user_id, amount)

    monkeypatch.setattr(repo, "add_coins", add_coins_contato)
    monkeypatch.setattr(leveling_module, "leveling_repo", repo)

    view = LevelingCog.DropClaimView(GUILD_ID, IMPORTO)
    bottone = view.children[0]
    primo = fake_interaction(user=fake_member(1, "primo"))
    secondo = fake_interaction(user=fake_member(2, "secondo"))

    await asyncio.gather(
        view.raccogli.callback(primo),
        view.raccogli.callback(secondo),
    )

    assert len(chiamate) == 1
    saldi = [
        (await repo.get_totals(GUILD_ID, 1)).coins_total,
        (await repo.get_totals(GUILD_ID, 2)).coins_total,
    ]
    assert sorted(saldi) == [0, IMPORTO]
    assert bottone.disabled is True
    view.stop()
