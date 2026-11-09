"""Comandi e menu del server (B28): nomi, impronta, regole di sync, archivio con tetti."""
import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest

from core import slash_server_logic as L
from core.repositories.slash_server_repo import SlashServerRepository

G = 61
ADESSO = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def test_nomi_dei_comandi():
    assert L.normalizza_nome(" Regole ") == "regole"
    assert L.normalizza_nome("a b") is None and L.normalizza_nome("x" * 33) is None and L.normalizza_nome("") is None
    glob = {"tag", "utility"}
    assert L.errore_nome_comando("regole", glob) is None
    assert L.errore_nome_comando("tag", glob) == "slash_nome_globale"
    for riservato in ("admin", "admin-x", "moderatori", "mod", "founder1"):
        assert L.errore_nome_comando(riservato, glob) == "slash_nome_riservato", riservato
    assert L.errore_nome_comando("a/b", glob) == "slash_nome_non_valido"


def test_nomi_dei_menu():
    glob = {"Apri ticket"}
    assert L.errore_nome_menu("Dai il benvenuto", glob) is None
    assert L.errore_nome_menu("apri TICKET", glob) == "slash_nome_globale"
    assert L.errore_nome_menu("Admin cose", glob) == "slash_nome_riservato"
    assert L.errore_nome_menu("", glob) == "slash_menu_nome_non_valido"
    assert L.errore_nome_menu("x" * 33, glob) == "slash_menu_nome_non_valido"


def test_impronta_non_dipende_dall_ordine_e_cambia_con_le_definizioni():
    a = [("b", "", "Bi"), ("a", "x", "Ex")]
    m = [("Saluta", "utente")]
    assert L.impronta(a, m) == L.impronta(list(reversed(a)), m)
    assert L.impronta(a, m) != L.impronta(a + [("c", "", "Ci")], m)
    assert L.impronta(a, m) != L.impronta(a, [])
    assert L.impronta(a, m) != L.impronta([("b", "", "Bi"), ("a", "x", "Altro")], m)


def test_creazioni_nuove_contano_i_nomi_di_discord():
    vecchi = L.nomi_di_discord([("a", "x", "d"), ("a", "y", "d")], [])
    assert vecchi == ["c:a"]  # un gruppo conta uno
    nuovi = L.nomi_di_discord([("a", "x", "d"), ("b", "", "d")], [("Saluta", "utente")])
    assert L.creazioni_nuove(vecchi, nuovi) == 2


def test_attesa_tra_due_sync():
    assert L.attesa_sync(None, ADESSO) == 0
    assert L.attesa_sync(ADESSO - timedelta(seconds=299), ADESSO) == 1
    assert L.attesa_sync(ADESSO - timedelta(minutes=5), ADESSO) == 0
    assert L.attesa_sync(ADESSO - timedelta(seconds=10), ADESSO) == 290
    assert L.creazioni_di_oggi(date(2026, 11, 8), 150, date(2026, 11, 9)) == 0
    assert L.creazioni_di_oggi(date(2026, 11, 9), 150, date(2026, 11, 9)) == 150
    assert L.quando_riprovare(ADESSO - timedelta(seconds=100), ADESSO) == ADESSO + timedelta(seconds=200)


@pytest.fixture
def repo(clean_db):
    return SlashServerRepository(pool_provider=lambda: clean_db)


async def test_pubblica_aggiorna_e_rispetta_i_tetti(repo):
    assert await repo.pubblica(G, "regole", "", "regole", "Le regole", 1) == "ok"
    assert await repo.pubblica(G, "regole", "", "altro", "Nuove", 1) == "ok"  # aggiorna
    assert (await repo.comando(G, "regole", ""))["tag"] == "altro"
    assert await repo.pubblica(G, "regole", "uno", "t", "d", 1) == "conflitto"
    assert await repo.pubblica(G, "wiki", "uno", "t", "d", 1) == "ok"
    assert await repo.pubblica(G, "wiki", "", "t", "d", 1) == "conflitto"
    for i in range(L.MAX_COMANDI - 2):
        assert await repo.pubblica(G, f"c{i}", "", "t", "d", 1) == "ok"
    assert await repo.pubblica(G, "ultimo", "", "t", "d", 1) == "pieno"
    assert await repo.pubblica(G, "wiki", "due", "t", "d", 1) == "ok"  # un sotto-comando in più non è un nome in più
    assert await repo.pubblica(G + 1, "ultimo", "", "t", "d", 1) == "ok"


async def test_sotto_comandi_al_massimo_25(repo):
    for i in range(L.MAX_SOTTO):
        assert await repo.pubblica(G, "g", f"s{i}", "t", "d", 1) == "ok"
    assert await repo.pubblica(G, "g", "extra", "t", "d", 1) == "troppi"
    assert await repo.pubblica(G, "g", "s0", "nuovo", "d", 1) == "ok"  # riscrivere uno che c'è va bene


async def test_tetto_dei_nomi_in_parallelo(repo):
    esiti = await asyncio.gather(*(repo.pubblica(G, f"p{i}", "", "t", "d", 1) for i in range(40)))
    assert esiti.count("ok") == L.MAX_COMANDI


async def test_menu_cinque_per_tipo(repo):
    for i in range(L.MAX_MENU):
        assert await repo.aggiungi_menu(G, f"m{i}", "utente", "t", 1) == "ok"
    assert await repo.aggiungi_menu(G, "m9", "utente", "t", 1) == "pieno"
    assert await repo.aggiungi_menu(G, "m0", "utente", "altro", 1) == "ok"  # aggiorna
    assert await repo.aggiungi_menu(G, "m9", "messaggio", "t", 1) == "ok"  # altro tipo, altro tetto
    assert (await repo.una_voce_di_menu(G, "m0", "utente"))["tag"] == "altro"
    assert await repo.togli_menu(G, "m0", "utente") and not await repo.togli_menu(G, "m0", "utente")
    assert len(await repo.menu(G)) == L.MAX_MENU


async def test_togli_comando_e_stato(repo):
    await repo.pubblica(G, "regole", "", "t", "d", 1)
    assert await repo.togli(G, "regole", "") and not await repo.togli(G, "regole", "")
    assert await repo.stato(G) is None
    await repo.segna_in_coda(G, True)
    assert (await repo.stato(G))["in_coda"] is True
    await repo.salva_sync(G, ADESSO, "abc", ["c:a"], date(2026, 11, 9), 3)
    s = await repo.stato(G)
    assert s["impronta"] == "abc" and s["creazioni"] == 3 and s["in_coda"] is False
    import json
    assert json.loads(s["nomi"]) == ["c:a"]
    assert G in await repo.server_con_voci()
