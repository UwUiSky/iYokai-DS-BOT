"""Inneschi dei tag (B27): intervallo, orario (cron), esclusioni, validazione, archivio con tetto di 25."""
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from core import tag_inneschi_logic as L
from core.repositories.tag_inneschi_repo import TagInneschiRepository

ROMA = ZoneInfo("Europe/Rome")
G = 91


def roma(*a):
    return datetime(*a, tzinfo=ROMA)


def test_intervallo():
    assert L.leggi_intervallo("30m") == 1800
    assert L.leggi_intervallo("2h") == 7200
    assert L.leggi_intervallo("1g") == 86400
    assert L.leggi_intervallo("1h30m") == 5400
    assert L.leggi_intervallo("9m") is None  # minimo 10 minuti
    assert L.leggi_intervallo("31g") is None
    assert L.leggi_intervallo("boh") is None
    assert L.leggi_intervallo("") is None


def test_cron_valido_e_normalizzato():
    assert L.leggi_cron("0  9 * * 1") == "0 9 * * 1"
    assert L.leggi_cron("*/15 8-18 * * 1-5") == "*/15 8-18 * * 1-5"
    for storto in ("61 * * * *", "* * * *", "* * * * * *", "a b c d e", "*/0 * * * *", "5-1 * * * *", "* 24 * * *", "* * 0 * *", "* * * 13 *", "x" * 200):
        assert L.leggi_cron(storto) is None, storto


def test_prossimo_cron():
    assert L.prossimo_cron("0 9 * * *", roma(2026, 11, 9, 10, 0)) == roma(2026, 11, 10, 9, 0)
    assert L.prossimo_cron("0 9 * * *", roma(2026, 11, 9, 8, 59)) == roma(2026, 11, 9, 9, 0)
    assert L.prossimo_cron("*/15 * * * *", roma(2026, 11, 9, 10, 0)) == roma(2026, 11, 9, 10, 15)
    assert L.prossimo_cron("0 9 * * 1", roma(2026, 11, 9, 10, 0)) == roma(2026, 11, 16, 9, 0)  # lunedì
    assert L.prossimo_cron("30 20 31 12 *", roma(2026, 11, 9, 10, 0)) == roma(2026, 12, 31, 20, 30)
    assert L.prossimo_cron("0 0 30 2 *", roma(2026, 11, 9, 10, 0)) is None  # il 30 febbraio non c'è
    assert L.prossimo_cron("0 12 1 * 0", roma(2026, 11, 9, 10, 0)) == roma(2026, 11, 15, 12, 0)  # giorno 1 oppure domenica


def test_cron_troppo_fitto():
    assert L.cron_troppo_fitto("*/5 * * * *")
    assert L.cron_troppo_fitto("0,5 * * * *")
    assert not L.cron_troppo_fitto("*/10 * * * *")
    assert not L.cron_troppo_fitto("0 9 * * *")
    assert L.cron_troppo_fitto("* * * * *")


def test_escludi():
    assert L.leggi_escludi("23-7 sab dom") == "23-7 sab dom"
    assert L.leggi_escludi("") == ""
    assert L.leggi_escludi("25-7") is None and L.leggi_escludi("boh") is None and L.leggi_escludi("x" * 300) is None
    assert L.escluso("23-7", roma(2026, 11, 9, 23, 30)) and L.escluso("23-7", roma(2026, 11, 9, 6, 59))
    assert not L.escluso("23-7", roma(2026, 11, 9, 7, 0))
    assert L.escluso("sab dom", roma(2026, 11, 14, 12, 0))
    assert not L.escluso("sab dom", roma(2026, 11, 9, 12, 0))
    assert not L.escluso("", roma(2026, 11, 9, 12, 0))
    assert L.escluso("9-17", roma(2026, 11, 9, 12, 0))


def test_valida_per_tipo():
    assert L.valida("reazione", "👍") == ("👍", None)
    assert L.valida("reazione", "<:ok:123456789012345678>")[1] is None
    assert L.valida("reazione", "ciao")[1] == "inn_reazione_non_valida"
    assert L.valida("intervallo", " 30m ") == ("30m", None) and L.valida("intervallo", "5m")[1] == "inn_intervallo_non_valido"
    assert L.valida("orario", "0 9 * * *") == ("0 9 * * *", None)
    assert L.valida("orario", "*/5 * * * *")[1] == "inn_orario_troppo_fitto"
    assert L.valida("orario", "boh")[1] == "inn_orario_non_valido"
    assert L.valida("bottone", "benvenuto:2") == ("benvenuto:2", None)
    assert L.valida("bottone", "benvenuto")[1] == "inn_bottone_non_valido"
    assert L.valida("sconosciuto", "x")[1] == "inn_tipo_non_valido"


def test_prossimo_giro():
    adesso = datetime(2026, 11, 9, 9, 0, tzinfo=timezone.utc)
    assert L.prossimo_giro("intervallo", "30m", adesso) == datetime(2026, 11, 9, 9, 30, tzinfo=timezone.utc)
    assert L.prossimo_giro("orario", "0 12 * * *", adesso) == datetime(2026, 11, 9, 11, 0, tzinfo=timezone.utc)  # 12:00 a Roma = 11:00 UTC
    assert L.prossimo_giro("orario", "0 0 30 2 *", adesso) is None


# ------------------------------------------------------------------ archivio
@pytest.fixture
def repo(clean_db):
    return TagInneschiRepository(pool_provider=lambda: clean_db)


async def test_aggiungi_unico_e_tetto(repo):
    esito, nuovo_id = await repo.aggiungi(G, "dado", "reazione", "👍", None, "", 5)
    assert esito == "ok" and nuovo_id
    assert (await repo.aggiungi(G, "dado", "reazione", "👍", None, "", 5))[0] == "esiste"
    for i in range(L.MAX_INNESCHI - 1):
        assert (await repo.aggiungi(G, "dado", "intervallo", f"{10 + i}m", 7, "", 5))[0] == "ok"
    assert (await repo.aggiungi(G, "dado", "intervallo", "2g", 7, "", 5))[0] == "pieno"
    assert (await repo.aggiungi(G + 1, "dado", "intervallo", "2g", 7, "", 5))[0] == "ok"
    assert len(await repo.elenco(G)) == L.MAX_INNESCHI


async def test_tetto_in_parallelo(repo):
    esiti = await asyncio.gather(*(repo.aggiungi(G, "t", "intervallo", f"{10 + i}m", 7, "", 5) for i in range(40)))
    assert [e[0] for e in esiti].count("ok") == L.MAX_INNESCHI


async def test_cerca_per_tipo_e_togli(repo):
    _, a = await repo.aggiungi(G, "dado", "reazione", "👍", 7, "", 5)
    _, b = await repo.aggiungi(G, "altro", "ruolo_dato", "555", 7, "", 5)
    await repo.aggiungi(G, "x", "bottone", "benvenuto:1", None, "", 5)
    assert [r["id"] for r in await repo.per_tipo(G, "reazione")] == [a]
    assert [r["id"] for r in await repo.per_tipo(G, "ruolo_dato")] == [b]
    assert (await repo.prendi(G, a))["tag"] == "dado" and await repo.prendi(G + 1, a) is None
    assert (await repo.bottone(G, "benvenuto", 1))["tag"] == "x" and await repo.bottone(G, "benvenuto", 2) is None
    assert await repo.togli(G, a) and not await repo.togli(G, a)
    assert await repo.togli_per_tag(G, "altro") == 1
    assert await repo.togli_per_canale(G, 7) == 0
    await repo.aggiungi(G, "dado", "intervallo", "30m", 7, "", 5)
    assert await repo.togli_per_canale(G, 7) == 1
    await repo.aggiungi(G, "dado", "ruolo_dato", "55", 7, "", 5)
    await repo.aggiungi(G, "dado", "ruolo_tolto", "55", 7, "", 5)
    await repo.aggiungi(G, "dado", "ruolo_dato", "56", 7, "", 5)
    assert await repo.togli_per_ruolo(G, 55) == 2 and await repo.togli_per_ruolo(G, 55) == 0
