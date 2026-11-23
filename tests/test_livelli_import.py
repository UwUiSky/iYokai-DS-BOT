"""
tests/test_livelli_import.py
============================
Import dei livelli da un file dell'admin (LIV-072): ogni campo controllato, mai XP tolti, due import insieme non si pestano.
Funzioni coperte: catalogo #124
"""

import asyncio
import json

import pytest

from core.livelli_import_logic import MAX_RIGHE, ImportNonValido, leggi_file
from core.repositories.livelli_import_repo import LivelliImportRepository
from tests.support.concorrenza import apri_connessioni

G = 700


def _json(righe):
    return json.dumps(righe).encode()


def test_formati_accettati():
    assert [(r.user_id, r.xp) for r in leggi_file(_json([{"id": "5", "xp": 10}, {"user_id": 6, "XP": 3.0}]), "a.json")] == [(5, 10), (6, 3)]
    assert [(r.user_id, r.xp) for r in leggi_file(_json({"players": [{"id": "7", "xp": 1}]}), "mee6.json")] == [(7, 1)]
    assert [(r.user_id, r.xp) for r in leggi_file("﻿id,xp,level\n8,100,2\n".encode(), "x.csv")] == [(8, 100)]


@pytest.mark.parametrize("contenuto, nome", [
    (b"non json", "a.json"), (_json([]), "a.json"), (_json([{"id": 1, "xp": -1}]), "a.json"), (_json([{"id": 0, "xp": 1}]), "a.json"),
    (_json([{"id": 1, "xp": 1.5}]), "a.json"), (_json([{"id": True, "xp": 1}]), "a.json"), (_json([{"id": "1e3", "xp": 1}]), "a.json"),
    (_json([{"id": 1, "xp": 10**12}]), "a.json"), (_json([{"id": 1}]), "a.json"), (_json([1, 2]), "a.json"),
    (_json([{"id": 1, "xp": 1}, {"id": 1, "xp": 2}]), "a.json"), (_json({"a": [], "b": []}), "a.json"),
    (b"id,xp\n1,abc\n", "a.csv"), (b"\xff\xfe", "a.csv"), (b"id,xp\n1,1\n", "a.txt"), (b"x" * (3 * 1024 * 1024), "a.json"),
    (_json([{"id": i, "xp": 1} for i in range(1, MAX_RIGHE + 2)]), "a.json"),
])
def test_un_campo_sbagliato_blocca_tutto(contenuto, nome):
    with pytest.raises(ImportNonValido):
        leggi_file(contenuto, nome)


@pytest.mark.asyncio
async def test_import_non_toglie_mai_xp_e_si_ripete(clean_db):
    repo = LivelliImportRepository(pool_provider=lambda: clean_db)
    await clean_db.execute("INSERT INTO leveling_totals (guild_id, user_id, xp_total, level, coins_total) VALUES ($1, 1, 5000, 9, 77), ($1, 2, 10, 0, 0)", G)
    righe = leggi_file(_json([{"id": 1, "xp": 100}, {"id": 2, "xp": 1000}, {"id": 3, "xp": 0}]), "a.json")
    assert await repo.importa(G, righe) == (2, 1)
    dati = {r["user_id"]: (r["xp_total"], r["level"], r["coins_total"]) for r in await clean_db.fetch("SELECT * FROM leveling_totals WHERE guild_id = $1", G)}
    assert dati[1] == (5000, 9, 77) and dati[2][0] == 1000 and dati[2][1] > 0 and dati[3][0] == 0
    assert await repo.importa(G, righe) == (0, 3)  # lo stesso file due volte non cambia nulla
    assert await repo.importa(G + 1, righe, tetto_livello=1) == (3, 0)
    assert await clean_db.fetchval("SELECT level FROM leveling_totals WHERE guild_id = $1 AND user_id = 2", G + 1) == 1


@pytest.mark.asyncio
async def test_due_import_insieme_danno_lo_stesso_risultato(clean_db):
    repo = LivelliImportRepository(pool_provider=lambda: clean_db)
    righe = leggi_file(_json([{"id": n, "xp": 100 * n} for n in range(1, 40)]), "a.json")
    await apri_connessioni(clean_db, 4)
    esiti = await asyncio.gather(*(repo.importa(G, righe) for _ in range(3)))
    assert sorted(e[0] for e in esiti) == [0, 0, 39]
    assert await clean_db.fetchval("SELECT count(*) FROM leveling_totals WHERE guild_id = $1", G) == 39
