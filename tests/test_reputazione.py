"""
tests/test_reputazione.py
=========================
Reputazione tra membri (LIV-076…088): pausa, tetto, mai a se stessi, blocchi, concorrenza, registro, ruoli per soglia.
Funzioni coperte: catalogo #124
"""

import asyncio
from types import SimpleNamespace

import pytest

from core.reputazione_logic import bersaglio_del_grazie, puo_agire, puo_togliere
from core.repositories.reputazione_repo import MAX_PREMI, ReputazioneRepository
from core.repositories.sociale_repo import SocialeRepository
from tests.support.concorrenza import apri_connessioni

G = 500


@pytest.fixture
def r(clean_db):
    return SimpleNamespace(rep=ReputazioneRepository(pool_provider=lambda: clean_db), soc=SocialeRepository(pool_provider=lambda: clean_db), pool=clean_db)


def test_logica_ruoli_e_grazie():
    assert puo_agire([1, 2], None, None) and puo_agire([1], 1, None) and not puo_agire([2], 1, None) and not puo_agire([1, 3], None, 3)
    assert not puo_togliere([1], None, False) and puo_togliere([1], 1, False) and puo_togliere([], None, True)
    assert bersaglio_del_grazie("grazie mille <@5>", [(5, False)], 9) == 5
    assert bersaglio_del_grazie("grazie <@9>", [(9, False)], 9) is None  # a se stessi
    assert bersaglio_del_grazie("grazie bot", [(7, True)], 9) is None
    assert bersaglio_del_grazie("grazie a tutti", [(5, False), (6, False)], 9) is None
    assert bersaglio_del_grazie("ciao <@5>", [(5, False)], 9) is None


@pytest.mark.asyncio
async def test_spenta_di_base_poi_dare_e_togliere(r):
    assert (await r.rep.muovi(G, 1, 2, 1)).stato == "spenta"
    await r.rep.imposta(G, attiva=True, pausa_secondi=3600, tetto_giornaliero=3, massimo_per_comando=2)
    e = await r.rep.muovi(G, 1, 2, 1)
    assert (e.stato, e.punti) == ("ok", 1)
    assert (await r.rep.muovi(G, 1, 3, 1)).stato == "pausa"  # la pausa vale per chi dà
    assert (await r.rep.muovi(G, 1, 1, 1)).stato == "se_stessi"
    assert (await r.rep.muovi(G, 4, 2, 3)).stato == "massimo"
    assert (await r.rep.muovi(G, 4, 2, -1)).punti == 0 and await r.rep.punti_e_posizione(G, 2) == (0, 1)


@pytest.mark.asyncio
async def test_tetto_giornaliero_e_blocco(r):
    await r.rep.imposta(G, attiva=True, pausa_secondi=3600, tetto_giornaliero=2, massimo_per_comando=2)
    assert (await r.rep.muovi(G, 1, 2, 2)).stato == "ok"
    await r.pool.execute("DELETE FROM reputazione_pausa")  # la pausa non c'entra: conta il tetto
    assert (await r.rep.muovi(G, 1, 3, 1)).stato == "tetto"
    await r.soc.blocca(7, 8)  # 7 ha bloccato 8
    assert (await r.rep.muovi(G, 8, 7, 1)).stato == "bloccato"
    assert (await r.rep.muovi(G, 7, 8, 1)).stato == "ok"


@pytest.mark.asyncio
async def test_due_comandi_insieme_pagano_una_volta(r):
    await r.rep.imposta(G, attiva=True, pausa_secondi=3600, tetto_giornaliero=10)
    await apri_connessioni(r.pool, 5)
    esiti = await asyncio.gather(*(r.rep.muovi(G, 1, 2 + n, 1) for n in range(4)))
    assert sorted(e.stato for e in esiti) == ["ok", "pausa", "pausa", "pausa"]
    assert await r.pool.fetchval("SELECT sum(punti) FROM reputazione_punti WHERE guild_id = $1", G) == 1
    assert await r.pool.fetchval("SELECT count(*) FROM reputazione_registro WHERE guild_id = $1", G) == 1


@pytest.mark.asyncio
async def test_tetto_con_concorrenza(r):
    await r.rep.imposta(G, attiva=True, pausa_secondi=3600, tetto_giornaliero=1)
    await apri_connessioni(r.pool, 5)
    esiti = await asyncio.gather(*(r.rep.muovi(G, 1, 2 + n, 1) for n in range(4)))
    assert [e.stato for e in esiti].count("ok") == 1


@pytest.mark.asyncio
async def test_staff_classifica_registro_azzera(r):
    await r.rep.imposta(G, attiva=True, pausa_secondi=3600)
    assert await r.rep.imposta_punti(G, 2, 10, 99) == 10 and await r.rep.imposta_punti(G, 3, 4, 99) == 4
    await r.rep.muovi(G, 3, 2, 1)
    assert await r.rep.classifica(G) == [(2, 11), (3, 4)]
    assert await r.rep.punti_e_posizione(G, 3) == (4, 2) and await r.rep.punti_e_posizione(G, 77) == (0, None)
    assert [x["fonte"] for x in await r.rep.registro(G, 2)] == ["utente", "staff"]
    assert await r.rep.cancella(G, 2, 99) == 11 and await r.rep.punti_e_posizione(G, 2) == (0, None)
    assert await r.rep.azzera_server(G) == 1 and await r.rep.classifica(G) == [] and await r.rep.registro(G, 3) == []


@pytest.mark.asyncio
async def test_premi_a_soglia_e_tetto(r):
    for n in range(MAX_PREMI):
        assert await r.rep.metti_premio(G, n + 1, 1000 + n) == "ok"
    assert await r.rep.metti_premio(G, 99, 5) == "pieno" and await r.rep.metti_premio(G, 1, 55) == "ok"
    assert (await r.rep.premi(G))[0] == (1, 55) and await r.rep.togli_premio(G, 1) and not await r.rep.togli_premio(G, 1)


@pytest.mark.asyncio
async def test_impostazioni_solo_campi_noti(r):
    with pytest.raises(ValueError):
        await r.rep.imposta(G, colonna_strana=5)
    await r.rep.imposta(G, nome="onore", grazie_canali=[1, 2])
    i = await r.rep.impostazioni(G)
    assert i["nome"] == "onore" and list(i["grazie_canali"]) == [1, 2] and not i["attiva"]
