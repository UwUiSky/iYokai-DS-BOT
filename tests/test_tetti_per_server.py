"""
tests/test_tetti_per_server.py
==============================
I tetti "al massimo N per server" devono reggere a richieste in parallelo (due /crea insieme):
con il solo `WHERE (SELECT count(*)) < N` due transazioni vedono lo stesso conteggio e passano
entrambe. Ogni test lancia più richieste del tetto contemporaneamente e conta le righe.
"""

import asyncio
import json

import pytest

from core.autorole_logic import MAX_REGOLE
from core.autoresponder_logic import MAX_RISPOSTE
from core.counter_logic import MAX_CONTATORI
from core.custom_command_logic import MAX_TAG
from core.embed_builder_logic import MAX_EMBED
from core.form_logic import MAX_MODULI, Domanda
from core.repositories.autorole_repo import AutoroleRepository
from core.repositories.autoresponder_repo import AutoresponderRepository
from core.repositories.counter_repo import CounterRepository
from core.repositories.custom_command_repo import CustomCommandRepository
from core.repositories.form_repo import FormRepository
from core.repositories.saved_embed_repo import SavedEmbedRepository

G = 900000000000000001
EXTRA = 8


async def _conta(pool, tabella):
    return await pool.fetchval(f"SELECT count(*) FROM {tabella} WHERE guild_id = $1", G)


@pytest.mark.asyncio
async def test_contatori(clean_db):
    r = CounterRepository(pool_provider=lambda: clean_db)
    await asyncio.gather(*(r.create(G, 1000 + i, "members", "m {n}", None, 1) for i in range(MAX_CONTATORI + EXTRA)))
    assert await _conta(clean_db, "counters") == MAX_CONTATORI


@pytest.mark.asyncio
async def test_comandi_personalizzati(clean_db):
    r = CustomCommandRepository(pool_provider=lambda: clean_db)
    await asyncio.gather(*(
        r.create_tag(G, f"t{i}", response="x", use_embed=False, role_id=None, role_action="nessuna",
                     cooldown_seconds=0, ping_ruoli=False, created_by=1)
        for i in range(MAX_TAG + EXTRA)
    ))
    assert await _conta(clean_db, "custom_commands") == MAX_TAG


@pytest.mark.asyncio
async def test_risposte_automatiche(clean_db):
    r = AutoresponderRepository(pool_provider=lambda: clean_db)
    await asyncio.gather(*(
        r.create(G, f"p{i}", match_mode="parziale", response="x", channel_id=None, role_id=None,
                 ping_ruoli=False, created_by=1)
        for i in range(MAX_RISPOSTE + EXTRA)
    ))
    assert await _conta(clean_db, "autoresponders") == MAX_RISPOSTE


@pytest.mark.asyncio
async def test_moduli(clean_db):
    r = FormRepository(pool_provider=lambda: clean_db)
    await asyncio.gather(*(
        r.create_form(G, f"m{i}", "t", 50, None, [Domanda("a")], 1) for i in range(MAX_MODULI + EXTRA)
    ))
    assert await _conta(clean_db, "forms") == MAX_MODULI


@pytest.mark.asyncio
async def test_embed_salvati(clean_db):
    r = SavedEmbedRepository(pool_provider=lambda: clean_db)
    await asyncio.gather(*(r.create(G, f"e{i}", json.dumps({"title": "t"}), 1) for i in range(MAX_EMBED + EXTRA)))
    assert await _conta(clean_db, "saved_embeds") == MAX_EMBED


@pytest.mark.asyncio
async def test_ruoli_automatici(clean_db):
    r = AutoroleRepository(pool_provider=lambda: clean_db)
    await asyncio.gather(*(r.add_rule(G, 100 + i, 0, 1) for i in range(MAX_REGOLE + EXTRA)))
    assert await _conta(clean_db, "autorole_rules") == MAX_REGOLE
