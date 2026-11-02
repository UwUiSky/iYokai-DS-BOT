"""
tests/test_immagini_trappola.py
===============================
Libreria delle immagini trappola (D62, come D39): candidata nel server che segnala, condivisa con
3 proprietari diversi (server con almeno 25 membri), certa solo con l'approvazione dell'owner del bot.
Confronto per SHA-256 e per dHash (distanza).
"""

import pytest

from core import immagini_trappola_logic as lg
from core.immagini_trappola_service import LibreriaImmagini
from core.repositories.immagini_trappola_repo import ImmaginiTrappolaRepository

SHA = "a1" * 32
SHA2 = "b2" * 32
SHA3 = "c3" * 32


def test_dhash_signed_unsigned_vanno_e_vengono():
    for v in (0, 1, 2**63 - 1, 2**63, 2**64 - 1):
        s = lg.dhash_a_database(v)
        assert -(2**63) <= s < 2**63 and lg.dhash_dal_database(s) == v
    assert lg.dhash_a_database(None) is None and lg.dhash_dal_database(None) is None


def test_sha_valido():
    assert lg.sha_valido(SHA.upper()) == SHA
    for no in ("", "abc", "g" * 64, "a" * 63, None, 5):
        assert lg.sha_valido(no) is None
    assert lg.prefisso_valido("A1B2C3D4") == "a1b2c3d4" and lg.prefisso_valido("a1b") is None


def test_stato_dopo_segnalazione():
    assert lg.stato_dopo_segnalazione(lg.CANDIDATA, 2) == lg.CANDIDATA
    assert lg.stato_dopo_segnalazione(lg.CANDIDATA, 3) == lg.CONDIVISA
    assert lg.stato_dopo_segnalazione(lg.APPROVATA, 9) == lg.APPROVATA
    assert lg.stato_dopo_segnalazione(lg.RIFIUTATA, 9) == lg.RIFIUTATA


def test_verdetto_per_stato():
    assert lg.verdetto_di(lg.APPROVATA) == "malevola" and lg.verdetto_di(lg.CONDIVISA) == "malevola"
    assert lg.verdetto_di(lg.CANDIDATA) == "sospetta" and lg.verdetto_di(lg.RIFIUTATA) is None


def test_trova_per_impronta_prende_la_piu_vicina():
    voci = [lg.Voce(SHA, 0b0, lg.APPROVATA), lg.Voce(SHA2, 0b111111111, lg.APPROVATA)]
    t = lg.trova_per_impronta(0b11, voci)
    assert t and t.voce.sha256 == SHA and t.distanza == 2 and t.tipo == "uguale"
    t = lg.trova_per_impronta(0b11111111 << 8, [lg.Voce(SHA, 0, lg.APPROVATA)])
    assert t and t.tipo == "simile" and t.distanza == 8
    simile = lg.trova_per_impronta(0b111111, [lg.Voce(SHA, 0, lg.CONDIVISA)])
    assert simile and simile.tipo == "simile"
    assert lg.trova_per_impronta(2**40 - 1, [lg.Voce(SHA, 0, lg.CONDIVISA)]) is None
    assert lg.trova_per_impronta(0, [lg.Voce(SHA, None, lg.CONDIVISA)]) is None


@pytest.fixture
def libreria(clean_db):
    repo = ImmaginiTrappolaRepository(pool_provider=lambda: clean_db)
    return LibreriaImmagini(repo=repo), repo


@pytest.mark.asyncio
async def test_candidata_vale_solo_nel_server_che_ha_segnalato(libreria):
    lib, _ = libreria
    await lib.segnala(SHA, 0xFF, "coda con archivio", guild_id=1, owner_id=10, membri=100)
    assert (await lib.cerca_sha(SHA, 1)).stato == lg.CANDIDATA
    assert await lib.cerca_sha(SHA, 2) is None


@pytest.mark.asyncio
async def test_tre_proprietari_diversi_la_rendono_condivisa(libreria):
    lib, _ = libreria
    await lib.segnala(SHA, 5, "x", guild_id=1, owner_id=10, membri=100)
    await lib.segnala(SHA, 5, "x", guild_id=2, owner_id=10, membri=100)  # stesso proprietario: non conta
    await lib.segnala(SHA, 5, "x", guild_id=3, owner_id=11, membri=100)
    assert await lib.cerca_sha(SHA, 99) is None
    await lib.segnala(SHA, 5, "x", guild_id=4, owner_id=12, membri=100)
    assert (await lib.cerca_sha(SHA, 99)).stato == lg.CONDIVISA


@pytest.mark.asyncio
async def test_server_piccolo_non_conta_per_la_soglia(libreria):
    lib, _ = libreria
    for g, o in ((1, 10), (2, 11), (3, 12), (4, 13)):
        await lib.segnala(SHA, 5, "x", guild_id=g, owner_id=o, membri=10)
    assert await lib.cerca_sha(SHA, 99) is None
    assert (await lib.cerca_sha(SHA, 1)).stato == lg.CANDIDATA


@pytest.mark.asyncio
async def test_solo_l_owner_del_bot_la_rende_certa_e_la_rifiutata_non_vale(libreria):
    lib, _ = libreria
    await lib.segnala(SHA, 5, "x", guild_id=1, owner_id=10, membri=100)
    assert await lib.imposta_stato(SHA[:10], lg.APPROVATA) == "ok"
    assert (await lib.cerca_sha(SHA, 77)).stato == lg.APPROVATA
    assert await lib.imposta_stato(SHA, lg.RIFIUTATA) == "ok"
    assert await lib.cerca_sha(SHA, 77) is None and await lib.cerca_sha(SHA, 1) is None
    await lib.segnala(SHA, 5, "x", guild_id=5, owner_id=20, membri=100)  # una rifiutata resta tale
    assert await lib.cerca_sha(SHA, 5) is None


@pytest.mark.asyncio
async def test_prefisso_ambiguo_o_assente(libreria):
    lib, _ = libreria
    await lib.segnala("ab" + "0" * 62, None, "x", 1, 10, 100)
    await lib.segnala("ab" + "1" * 62, None, "x", 1, 10, 100)
    assert await lib.imposta_stato("abababab", lg.APPROVATA) == "assente"
    assert await lib.imposta_stato("ab", lg.APPROVATA) == "non_valido"
    assert await lib.imposta_stato("ab000000", lg.APPROVATA) == "ok"
    assert await lib.imposta_stato("abababab", lg.APPROVATA) == "assente"
    # due che iniziano allo stesso modo
    await lib.segnala("cd" + "0" * 62, None, "x", 1, 10, 100)
    await lib.segnala("cd" + "0" * 61 + "1", None, "x", 1, 10, 100)
    assert await lib.imposta_stato("cd000000", lg.APPROVATA) == "ambiguo"


@pytest.mark.asyncio
async def test_impronta_percettiva_trova_la_versione_ritoccata(libreria):
    lib, _ = libreria
    await lib.aggiungi(SHA, 0b1010, "owner")
    t = await lib.cerca_impronta(0b1011, guild_id=3)
    assert t and t.voce.stato == lg.APPROVATA and t.tipo == "uguale"


@pytest.mark.asyncio
async def test_tetto_di_candidate_per_server(libreria, monkeypatch):
    lib, _ = libreria
    monkeypatch.setattr(lg, "MAX_CANDIDATE_PER_SERVER", 2)
    esiti = [await lib.segnala(f"{n:064x}", None, "x", 1, 10, 100) for n in range(4)]
    assert [e is not None for e in esiti] == [True, True, False, False]


@pytest.mark.asyncio
async def test_elenca_e_conta(libreria):
    lib, _ = libreria
    await lib.segnala(SHA, 1, "x", 1, 10, 100)
    await lib.aggiungi(SHA2, None, "owner")
    assert (await lib.conta())[lg.CANDIDATA] == 1 and (await lib.conta())[lg.APPROVATA] == 1
    assert [v.sha256 for v in await lib.elenca(lg.CANDIDATA, 5)] == [SHA]


@pytest.mark.asyncio
async def test_database_fermo_non_ferma_il_filtro():
    class Rotto:
        async def globali(self):
            raise RuntimeError("giu'")

        async def del_server(self, g):
            raise RuntimeError("giu'")

    lib = LibreriaImmagini(repo=Rotto())
    assert await lib.cerca_sha(SHA, 1) is None
    assert await lib.cerca_impronta(1, 1) is None
