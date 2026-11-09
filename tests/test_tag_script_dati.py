"""Dati per server degli script (B26): {dati:...}, tetti, errori registrati, prova senza salvare."""
import random
from datetime import datetime, timezone

import pytest

from core import tag_script_logic as ts
from core.repositories.tag_script_repo import TagScriptRepository

ADESSO = datetime(2026, 11, 9, 15, 30, tzinfo=timezone.utc)
G = 77


def ctx(archivio=None, **kw):
    return ts.Contesto(adesso=ADESSO, rng=random.Random(1), archivio=archivio, **kw)


# ------------------------------------------------------------------ nel motore
async def test_dati_scrivi_leggi_cancella():
    a = ts.ArchivioMemoria()
    r = await ts.esegui("{dati:set|punti|5}{dati:get|punti}", ctx(a))
    assert r.testo == "5" and a.dati == {"punti": "5"}
    assert (await ts.esegui("{dati:get|manca|nessuno}", ctx(a))).testo == "nessuno"
    assert (await ts.esegui("{dati:del|punti}{dati:get|punti|-}", ctx(a))).testo == "-"
    assert (await ts.esegui("{store:set|k|v}{db:get|k}", ctx(a))).testo == "v"


async def test_contatore_con_calcola():
    a = ts.ArchivioMemoria({"giri": "2"})
    r = await ts.esegui("{dati:set|giri|{calcola:{dati:get|giri|0}+1}}{dati:get|giri}", ctx(a))
    assert r.testo == "3"


async def test_senza_archivio_e_errore():
    r = await ts.esegui("{dati:get|x}", ctx(None))
    assert r.errore and r.errore.chiave == "tag_script_dati_non_disponibili"


async def test_tetto_scritture_per_uso():
    a = ts.ArchivioMemoria()
    ok = "".join("{dati:set|k%d|1}" % i for i in range(ts.MAX_SCRITTURE))
    assert (await ts.esegui(ok, ctx(a))).errore is None
    r = await ts.esegui(ok + "{dati:set|altro|1}", ctx(ts.ArchivioMemoria()))
    assert r.errore and r.errore.chiave == "tag_script_troppe_scritture"


async def test_valore_oltre_1kb_e_chiave_non_valida():
    a = ts.ArchivioMemoria()
    r = await ts.esegui("{dati:set|k|%s}" % ("é" * 600), ctx(a))  # 1200 byte
    assert r.errore and r.errore.chiave == "tag_script_dati_valore"
    for chiave in ("", "a b", "x" * 65, "{x}"):
        r = await ts.esegui("{dati:set|%s|1}" % chiave.replace("{x}", "\\{x\\}"), ctx(a))
        assert r.errore and r.errore.chiave == "tag_script_dati_chiave", chiave


async def test_archivio_pieno():
    a = ts.ArchivioMemoria(massimo=2)
    assert (await ts.esegui("{dati:set|a|1}{dati:set|b|1}{dati:set|a|2}", ctx(a))).errore is None
    r = await ts.esegui("{dati:set|c|1}", ctx(a))
    assert r.errore and r.errore.chiave == "tag_script_dati_pieni"


async def test_azione_sconosciuta_e_guasto_dell_archivio():
    r = await ts.esegui("{dati:drop|x}", ctx(ts.ArchivioMemoria()))
    assert r.errore and r.errore.chiave == "tag_script_dati_azione"

    class Rotto(ts.ArchivioMemoria):
        async def get(self, chiave):
            raise RuntimeError("db giù")

    r = await ts.esegui("{dati:get|x}", ctx(Rotto()))
    assert r.errore and r.errore.chiave == "tag_script_dati_errore"


async def test_prova_non_salva_ma_legge_i_dati_veri():
    vero = ts.ArchivioMemoria({"x": "1"})
    prova = ts.ArchivioProva(vero)
    r = await ts.esegui("{dati:set|x|2}{dati:set|y|3}{dati:get|x}{dati:get|y}", ctx(prova))
    assert r.testo == "23"
    assert vero.dati == {"x": "1"}
    assert (await ts.esegui("{dati:del|x}{dati:get|x|vuoto}", ctx(prova))).testo == "vuoto"
    assert vero.dati == {"x": "1"}


# ------------------------------------------------------------------ archivio su PostgreSQL
@pytest.fixture
def repo(clean_db):
    return TagScriptRepository(pool_provider=lambda: clean_db)


async def test_repo_dati(repo):
    assert await repo.imposta_dato(G, "a", "1", massimo=2) == "ok"
    assert await repo.imposta_dato(G, "a", "2", massimo=2) == "ok"  # riscrivere non conta
    assert await repo.imposta_dato(G, "b", "1", massimo=2) == "ok"
    assert await repo.imposta_dato(G, "c", "1", massimo=2) == "pieno"
    assert await repo.leggi_dato(G, "a") == "2"
    assert await repo.leggi_dato(G + 1, "a") is None
    assert await repo._pool.fetchval("SELECT count(*) FROM tag_dati WHERE guild_id = $1", G) == 2
    await repo.togli_dato(G, "a")
    assert await repo.leggi_dato(G, "a") is None


async def test_repo_dati_in_parallelo_non_superano_il_tetto(repo):
    import asyncio
    esiti = await asyncio.gather(*(repo.imposta_dato(G, f"k{i}", "1", massimo=5) for i in range(20)))
    assert esiti.count("ok") == 5 and await repo._pool.fetchval("SELECT count(*) FROM tag_dati WHERE guild_id = $1", G) == 5


async def test_repo_archivio_del_server(repo):
    a = repo.archivio(G, massimo=1)
    await a.set("k", "v")
    assert await a.get("k") == "v"
    with pytest.raises(ts.ErroreScript) as e:
        await a.set("altra", "v")
    assert e.value.chiave == "tag_script_dati_pieni"
    await a.delete("k")
    assert await a.get("k") is None


async def test_repo_errori_ultimi_dieci(repo):
    for i in range(14):
        await repo.registra_errore(G, "dado", "tag_script_tempo", f"n{i}")
    await repo.registra_errore(G, "altro", "tag_script_regex", "x")
    righe = await repo.ultimi_errori(G, "dado")
    assert len(righe) == 10 and righe[0]["dettaglio"] == "n13" and righe[-1]["dettaglio"] == "n4"
    assert len(await repo.ultimi_errori(G, "altro")) == 1
    await repo.togli_errori(G, "dado")
    assert await repo.ultimi_errori(G, "dado") == []


async def test_tetto_per_autore_a_pieno_b_scrive_ancora(repo):
    for i in range(2):
        assert await repo.imposta_dato(G, f"a{i}", "1", massimo=100, autore=1, massimo_autore=2) == "ok"
    assert await repo.imposta_dato(G, "a2", "1", massimo=100, autore=1, massimo_autore=2) == "pieno"
    assert await repo.imposta_dato(G, "a0", "9", massimo=100, autore=1, massimo_autore=2) == "ok"  # riscrivere non conta
    assert await repo.imposta_dato(G, "b0", "1", massimo=100, autore=2, massimo_autore=2) == "ok"
    assert await repo.imposta_dato(G, "s0", "1", massimo=100, autore=3, massimo_autore=None) == "ok"  # staff: nessun tetto per autore


async def test_archivio_passa_autore_e_tetto(repo):
    a = repo.archivio(G, massimo=100, autore=5, massimo_autore=1)
    await a.set("x", "1")
    with pytest.raises(ts.ErroreScript):
        await a.set("y", "1")
