"""
tests/test_security_casi_nuke_117.py
====================================
SIC-017: il registro degli attacchi fermati dall'anti-nuke ha un numero
per server, una lista a pagine e un tetto.
"""

import asyncio

import pytest

from core.repositories import security_repo as modulo
from core.repositories.security_repo import security_repo


@pytest.fixture
def repo(clean_db, monkeypatch):
    monkeypatch.setattr(security_repo, "_pool_provider", lambda: clean_db)
    return security_repo


@pytest.mark.asyncio
async def test_i_numeri_partono_da_uno_e_sono_per_server(repo):
    assert await repo.create_nuke_case(1, 10, "channel", "x", "ban") == 1
    assert await repo.create_nuke_case(1, 10, "role", "y", "ban") == 2
    assert await repo.create_nuke_case(2, 10, "role", "y", "ban") == 1


@pytest.mark.asyncio
async def test_due_casi_insieme_non_prendono_lo_stesso_numero(repo):
    numeri = await asyncio.gather(*(repo.create_nuke_case(3, 10, "channel", "x", "ban") for _ in range(8)))
    assert sorted(numeri) == list(range(1, 9))


@pytest.mark.asyncio
async def test_il_caso_ricorda_i_ruoli_tolti_e_si_puo_rilasciare_una_volta(repo):
    n = await repo.create_nuke_case(1, 10, "channel", "x", "quarantena", (5, 6))
    caso = await repo.get_nuke_case(1, n)
    assert caso.removed_role_ids == (5, 6)
    assert caso.released_at is None
    assert await repo.mark_nuke_case_released(1, n) is True
    assert await repo.mark_nuke_case_released(1, n) is False
    assert (await repo.get_nuke_case(1, n)).released_at is not None
    assert await repo.get_nuke_case(1, 99) is None


@pytest.mark.asyncio
async def test_lista_a_pagine_dal_piu_recente(repo):
    for _ in range(12):
        await repo.create_nuke_case(1, 10, "channel", "x", "ban")
    pagina1, totale = await repo.list_nuke_cases(1, page=1, per_page=10)
    pagina2, _ = await repo.list_nuke_cases(1, page=2, per_page=10)
    assert totale == 12
    assert [c.case_number for c in pagina1] == list(range(12, 2, -1))
    assert [c.case_number for c in pagina2] == [2, 1]


@pytest.mark.asyncio
async def test_si_tengono_solo_gli_ultimi_casi(repo, monkeypatch):
    monkeypatch.setattr(modulo, "MAX_CASI_NUKE_PER_SERVER", 3)
    for _ in range(5):
        await repo.create_nuke_case(1, 10, "channel", "x", "ban")
    casi, totale = await repo.list_nuke_cases(1)
    assert totale == 3
    assert [c.case_number for c in casi] == [5, 4, 3]
