"""
tests/test_giro_periodico.py
============================
Prova la classe comune dei lavori periodici (core/giro_periodico.py) e il cricchetto:
nessun `tasks.loop` fuori da quella classe.
Funzioni coperte: consiglio 25/11/2026, critico 10.
"""

from __future__ import annotations

import ast
import asyncio
import os
from pathlib import Path

import asyncpg
import pytest

from core import giro_periodico as gp
from core.database import db

RADICE = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _pulisci(monkeypatch):
    """Pause minime e registro dei giri pulito: i test non devono aspettare minuti."""
    monkeypatch.setattr(gp, "PAUSA_BASE_SECONDI", 0.01)
    monkeypatch.setattr(gp, "GIRI", {})
    monkeypatch.setattr(gp, "ascoltatori_caduta", [])
    monkeypatch.setattr(gp, "ascoltatori_ripresa", [])


def test_pausa_raddoppia_con_tetto():
    assert gp.pausa_dopo_errori(0) == 0
    assert gp.pausa_dopo_errori(1) == gp.PAUSA_BASE_SECONDI
    assert gp.pausa_dopo_errori(2) == 2 * gp.PAUSA_BASE_SECONDI
    assert gp.pausa_dopo_errori(500) == gp.PAUSA_MASSIMA_SECONDI


async def test_un_errore_non_ferma_il_giro():
    chiamate = []

    @gp.giro_periodico(seconds=0.01, subito=True)
    async def lavoro():
        chiamate.append(1)
        if len(chiamate) <= 2:
            raise ConnectionError("database giù")

    lavoro.start()
    for _ in range(200):
        if len(chiamate) >= 5:
            break
        await asyncio.sleep(0.02)
    try:
        assert len(chiamate) >= 5, "il giro si è fermato dopo l'errore"
        assert lavoro.is_running()
        assert lavoro.errori_consecutivi == 0
        assert lavoro.ultimo_ok is not None
    finally:
        lavoro.cancel()


async def test_errore_non_di_rete_non_uccide_il_giro():
    """tasks.Loop ferma per sempre il giro con un errore qualunque: qui no."""
    chiamate = []

    @gp.giro_periodico(seconds=0.01, subito=True)
    async def lavoro():
        chiamate.append(1)
        raise ValueError("bug")

    lavoro.start()
    await asyncio.sleep(0.3)
    try:
        assert lavoro.is_running()
        assert len(chiamate) >= 3
        assert lavoro.errori_consecutivi >= 3
        assert "ValueError" in lavoro.ultimo_errore
    finally:
        lavoro.cancel()


async def test_avviso_dopo_errori_di_fila_e_al_ritorno():
    caduti, tornati = [], []
    gp.ascoltatori_caduta.append(lambda nome, n, testo: caduti.append((nome, n)))
    gp.ascoltatori_ripresa.append(lambda nome: tornati.append(nome))
    sbaglia = {"si": True}

    @gp.giro_periodico(seconds=0.01, subito=True)
    async def lavoro():
        if sbaglia["si"]:
            raise RuntimeError("giù")

    lavoro.start()
    await asyncio.sleep(0.3)
    sbaglia["si"] = False
    await asyncio.sleep(0.3)
    lavoro.cancel()
    assert len(caduti) == 1, "un solo avviso, senza spam"
    assert caduti[0][1] == gp.ERRORI_PER_AVVISO
    assert len(tornati) == 1


async def test_copia_per_ogni_istanza_di_un_cog():
    class Cog:
        @gp.giro_periodico(seconds=1, subito=True)
        async def giro(self):
            pass

    a, b = Cog(), Cog()
    assert a.giro is not b.giro
    assert a.giro._injected is a


async def test_stato_salvato_e_ripresa_dopo_riavvio(clean_db, monkeypatch):
    monkeypatch.setattr(db, "_pool", clean_db)

    @gp.giro_periodico(minutes=10)
    async def lavoro():
        pass

    await lavoro._dopo_successo()
    riga = await clean_db.fetchrow("SELECT * FROM giri_periodici WHERE nome = $1", lavoro.nome)
    assert riga["ultimo_giro_ok"] is not None and riga["errori_consecutivi"] == 0

    # Un riavvio subito dopo: l'attesa iniziale è quasi tutto l'intervallo, non zero.
    attese = []

    async def finto_sleep(secondi):
        attese.append(secondi)

    monkeypatch.setattr(gp.asyncio, "sleep", finto_sleep)
    await lavoro._attesa_iniziale()
    assert attese and attese[0] > 500


async def test_errore_salvato_nel_database(clean_db, monkeypatch):
    monkeypatch.setattr(db, "_pool", clean_db)

    @gp.giro_periodico(minutes=10, subito=True)
    async def lavoro():
        pass

    async def senza_attesa(secondi):
        return None

    monkeypatch.setattr(gp.asyncio, "sleep", senza_attesa)
    await lavoro._dopo_errore(ValueError("guasto"))
    riga = await clean_db.fetchrow("SELECT * FROM giri_periodici WHERE nome = $1", lavoro.nome)
    assert riga["errori_consecutivi"] == 1
    assert "guasto" in riga["testo_errore"]


async def test_solo_il_leader_gira(clean_db):
    """Con il lock già preso da un altro processo, questo non è leader e salta il giro."""
    dsn = os.environ["DATABASE_URL"]
    altro = await asyncpg.connect(dsn)
    try:
        assert await altro.fetchval("SELECT pg_try_advisory_lock($1)", gp.CHIAVE_LEADERSHIP)
        mio = gp.Leadership()
        assert await mio.sono_leader(dsn) is False
        await altro.execute("SELECT pg_advisory_unlock($1)", gp.CHIAVE_LEADERSHIP)
        await mio.rilascia()
        assert await mio.sono_leader(dsn) is True
        await mio.rilascia()
    finally:
        await altro.close()


async def test_database_non_raggiungibile_non_spegne_i_giri():
    mio = gp.Leadership()
    assert await mio.sono_leader("postgresql://x:y@127.0.0.1:1/niente") is True


# ---------------------------------------------------------------- cricchetto


def _file_di_produzione():
    for cartella in ("core", "cogs"):
        yield from (RADICE / cartella).rglob("*.py")
    yield RADICE / "main.py"


def test_cricchetto_nessun_tasks_loop_fuori_da_giro_periodico():
    """Ogni lavoro periodico passa da `giro_periodico`: un `tasks.loop` a mano muore alla prima eccezione."""
    fuori = []
    for percorso in _file_di_produzione():
        if percorso.name == "giro_periodico.py":
            continue
        albero = ast.parse(percorso.read_text(encoding="utf-8"))
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.Attribute) and nodo.attr == "loop" and isinstance(nodo.value, ast.Name) and nodo.value.id == "tasks":
                fuori.append(f"{percorso.relative_to(RADICE)}:{nodo.lineno}")
            if isinstance(nodo, ast.ImportFrom) and nodo.module == "discord.ext.tasks":
                fuori.append(f"{percorso.relative_to(RADICE)}:{nodo.lineno} (import)")
    assert not fuori, "usa core.giro_periodico.giro_periodico: " + ", ".join(fuori)


async def test_errore_nella_preparazione_non_uccide_il_giro():
    """`before_loop` che fallisce (database giù, bot non pronto) si riprova: in `tasks.Loop` il giro morirebbe."""
    prove = []
    chiamate = []

    @gp.giro_periodico(seconds=0.01, subito=True)
    async def lavoro():
        chiamate.append(1)

    @lavoro.before_loop
    async def prepara():
        prove.append(1)
        if len(prove) < 3:
            raise RuntimeError("database giù")

    lavoro.start()
    for _ in range(200):
        if len(chiamate) >= 2:
            break
        await asyncio.sleep(0.02)
    try:
        assert len(prove) == 3 and len(chiamate) >= 2
    finally:
        lavoro.cancel()
