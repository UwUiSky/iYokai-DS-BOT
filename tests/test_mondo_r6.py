"""
tests/test_mondo_r6.py
======================
Gettoni, vacanza, diretta, casa, fattoria, personaggi, avventura, borsa finta, vendita automatica, eventi in chat e
bonus a tempo (#125 r6eco). Funzioni coperte: catalogo #125
"""

import asyncio
import random
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from core import mondo_logic as ml
from core.repositories.inventario_repo import InventarioRepository
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.mondo_repo import MondoRepository
from core.repositories.progressi_repo import ProgressiRepository
from core.repositories.shop_repo import ShopRepository
from tests.support.concorrenza import apri_connessioni

G = 100
OGGI = date(2026, 11, 20)


@pytest.fixture
def r(clean_db):
    return SimpleNamespace(m=MondoRepository(pool_provider=lambda: clean_db), lev=LevelingRepository(pool_provider=lambda: clean_db),
                           pr=ProgressiRepository(pool_provider=lambda: clean_db), shop=ShopRepository(pool_provider=lambda: clean_db),
                           inv=InventarioRepository(pool_provider=lambda: clean_db), pool=clean_db)


async def _saldo(r, u):
    return (await r.lev.get_totals(G, u)).coins_total


def test_logica_pura():
    assert ml.serie_diretta(0, None, OGGI) == 1 and ml.serie_diretta(3, OGGI, OGGI) is None
    assert ml.serie_diretta(3, OGGI - timedelta(days=1), OGGI) == 4 and ml.serie_diretta(3, OGGI - timedelta(days=2), OGGI) == 1
    assert ml.paga_diretta(1) == 30 and ml.paga_diretta(100) == 130
    assert "🛏️" in ml.disegna_casa({"letto"}) and ml.disegna_casa(set()).count("⬛") == 12
    assert len({p for _, _, p in ml.MOBILI.values()}) == len(ml.MOBILI)
    rng = random.Random(3)
    for s, base in ml.SIMBOLI.items():
        p = base
        for _ in range(2000):
            p = ml.passo_prezzo(p, base, rng)
            assert base // 2 <= p <= base * 2
    assert ml.ordine_scatta("compra", 50, 60) and not ml.ordine_scatta("compra", 70, 60) and ml.ordine_scatta("vendi", 70, 60)
    assert ml.costo_con_commissione(100, 1) == 103 and ml.ricavo_con_commissione(100, 1) == 97
    assert len(ml.personaggi()) == 6 and all(0 <= p["g"] < len(p["r"]) for p in ml.personaggi())
    nodi = ml.avventura()["nodi"]
    assert all(n in nodi for v in nodi.values() for _, n in v.get("s", [])) and ml.avventura()["inizio"] in nodi


@pytest.mark.asyncio
async def test_diretta_una_volta_al_giorno_anche_insieme(r):
    await apri_connessioni(r.pool, 4)
    e = await asyncio.gather(*(r.m.diretta(G, 1, OGGI) for _ in range(3)))
    assert [x for x in e if x] == [(1, 30)] and await _saldo(r, 1) == 30
    assert await r.m.diretta(G, 1, OGGI + timedelta(days=1)) == (2, 35)


@pytest.mark.asyncio
async def test_casa_con_i_gettoni_globali(r):
    assert await r.m.compra_mobile(1, "letto") == "poche" and await r.m.casa(1) == set()
    for i in range(6):
        assert (await r.m.missione(G, 1, f"npc{i}", OGGI, True, 10)) == "ok"
    assert await r.m.gettoni(1) == 6
    assert await r.m.compra_mobile(1, "letto") == "ok" and await r.m.gettoni(1) == 0 and await r.m.compra_mobile(1, "letto") == "gia"
    assert await r.m.casa(1) == {"letto"} and await r.m.gettoni(2) == 0  # i gettoni sono di una persona, in ogni server
    assert await r.m.missione(G, 1, "npc0", OGGI, True, 10) == "gia" and await r.m.missione(G, 1, "npc0", OGGI + timedelta(days=1), False, 10) == "sbagliata"


@pytest.mark.asyncio
async def test_fattoria_costo_posto_e_raccolto_una_volta(r):
    await r.lev.add_coins(G, 1, 100)
    assert await r.m.pianta(G, 1, 1, "grano") == "ok" and await r.m.pianta(G, 1, 1, "fiore") == "occupato" and await _saldo(r, 1) == 90
    await r.pool.execute("UPDATE leveling_totals SET coins_total = 0")
    assert await r.m.pianta(G, 1, 2, "zucca") == "poche" and len(await r.m.orto(G, 1)) == 1  # il posto non resta occupato
    assert await r.m.raccogli(G, 1) == ([], 0)
    await r.pool.execute("UPDATE economia_fattoria SET piantato_at = now() - interval '3 hours'")
    await apri_connessioni(r.pool, 4)
    e = await asyncio.gather(r.m.raccogli(G, 1), r.m.raccogli(G, 1))
    assert sorted(len(c) for c, _ in e) == [0, 1] and await _saldo(r, 1) == 18


@pytest.mark.asyncio
async def test_avventura_premio_una_volta_ogni_pausa(r):
    assert await r.m.finale_avventura(G, 1, 60, 1, 3600) and not await r.m.finale_avventura(G, 1, 60, 1, 3600)
    assert await _saldo(r, 1) == 60 and await r.m.gettoni(1) == 1


@pytest.mark.asyncio
async def test_borsa_scambi_commissione_limiti_e_ordini(r):
    await r.lev.add_coins(G, 1, 100_000)
    prezzi = await r.m.prezzi()
    assert set(prezzi) == set(ml.SIMBOLI)
    s0 = await _saldo(r, 1)
    esito, p = await r.m.scambia(G, 1, "KITSU", 10, "compra")
    assert esito == "ok" and s0 - await _saldo(r, 1) == ml.costo_con_commissione(p, 10) and await r.m.portafoglio(G, 1) == {"KITSU": 10}
    assert (await r.m.scambia(G, 1, "KITSU", 100, "vendi"))[0] == "non_hai"
    esito, p = await r.m.scambia(G, 1, "KITSU", 10, "vendi")
    assert esito == "ok" and await r.m.portafoglio(G, 1) == {} and await _saldo(r, 1) < s0  # comprare e rivendere subito costa
    await r.m.scambia(G, 1, "TANUK", 100, "compra")
    for _ in range(9):
        await r.m.scambia(G, 1, "TANUK", 100, "compra")
    assert (await r.m.scambia(G, 1, "TANUK", 1, "compra"))[0] == "troppe"
    await r.pool.execute("UPDATE leveling_totals SET coins_total = 0")
    assert (await r.m.scambia(G, 1, "YOKAI", 1, "compra"))[0] == "poche"
    for i in range(5):
        assert await r.m.ordine(G, 2, "SAKUR", "compra", 1, 10) == "ok"
    assert await r.m.ordine(G, 2, "SAKUR", "compra", 1, 10) == "troppi"


@pytest.mark.asyncio
async def test_ordini_scattano_al_passo_dei_prezzi_e_se_non_si_puo_spariscono(r):
    await r.lev.add_coins(G, 1, 1000)
    await r.m.prezzi()
    await r.m.ordine(G, 1, "KITSU", "compra", 2, 100_000)  # sempre vero
    await r.m.ordine(G, 1, "SAKUR", "compra", 100, 100_000)  # costa troppo: fallisce e si toglie
    await r.m.ordine(G, 1, "ONIGI", "vendi", 1, 1)  # senza titoli: non_hai, si toglie
    await r.pool.execute("UPDATE economia_borsa_prezzi SET aggiornato_at = now() - interval '2 hours'")
    await r.m.prezzi()
    assert await r.m.portafoglio(G, 1) == {"KITSU": 2} and await r.m.ordini(G, 1) == []


@pytest.mark.asyncio
async def test_autovendita_vende_i_pezzi_quando_il_cambio_arriva_alla_soglia(r):
    n = await r.shop.add_item(G, "Spada", 100, None, None)
    item = await r.shop.get_item(n if isinstance(n, int) else n.id, G)
    await r.lev.add_coins(G, 1, 1000)
    for _ in range(3):
        await r.shop.buy_item(G, 1, item)
    from core.leveling_logic import tasso_del_giorno

    tasso = tasso_del_giorno(G, datetime.now(timezone.utc).date())  # il cambio vero di oggi, lo stesso della rivendita
    assert await r.m.autovendita(G, 1, item.id, tasso) == "ok" and await r.m.autovendita(G, 1, 99999, tasso) == "non_c_e"
    assert await r.m.autovendite_del_giorno(lambda g: tasso - 1) == 0
    saldo = await _saldo(r, 1)
    assert await r.m.autovendite_del_giorno(lambda g: tasso) == 3 and await _saldo(r, 1) == saldo + 3 * tasso
    assert await r.m.togli_autovendita(G, 1, item.id) and not await r.m.togli_autovendita(G, 1, item.id)


@pytest.mark.asyncio
async def test_codice_in_chat_primo_che_lo_scrive_giusto_vince_una_volta(r):
    e = await r.m.crea_evento(G, "codice", "Kitsune7", 50, 0, 0, 10, 9)
    assert (await r.m.prendi_evento(G, e, 1, "sbagliato"))[0] == "sbagliato" and await _saldo(r, 1) == 0
    await apri_connessioni(r.pool, 4)
    ris = await asyncio.gather(r.m.prendi_evento(G, e, 1, "kitsune7"), r.m.prendi_evento(G, e, 2, "KITSUNE7"))
    assert sorted(x[0] for x in ris) == ["ok", "preso"] and await _saldo(r, 1) + await _saldo(r, 2) == 50
    assert (await r.m.prendi_evento(G, e + 99, 1, "x"))[0] == "scaduto"
    await r.pool.execute("UPDATE economia_chat_eventi SET scade_at = now() - interval '1 minute'")
    assert (await r.m.prendi_evento(G, e, 3, "kitsune7"))[0] == "scaduto"


@pytest.mark.asyncio
async def test_bonus_a_tempo_personale_e_del_server_e_arriva_nel_guadagno(r):
    assert await r.m.bonus_percento(G, 1) == 0
    e = await r.m.crea_evento(G, "bonus", None, 0, 30, 60, 10, 9)
    assert (await r.m.prendi_evento(G, e, 1))[0] == "ok" and await r.m.bonus_percento(G, 1) == 30 and await r.m.bonus_percento(G, 2) == 0
    await r.m.bonus_server(G, 50, 30)
    assert await r.m.bonus_percento(G, 1) == 80 and await r.m.bonus_percento(G, 2) == 50
    await r.m.bonus_server(G, 90, 30)
    assert await r.m.bonus_percento(G, 1) == 100  # tetto
    await r.pool.execute("UPDATE economia_bonus_tempo SET fino = now() - interval '1 minute'")
    assert await r.m.bonus_percento(G, 1) == 0
    r2 = await r.m.crea_evento(G, "raro", None, 200, 0, 0, 10, 9)
    assert (await r.m.prendi_evento(G, r2, 4))[0] == "ok" and await _saldo(r, 4) == 200


@pytest.mark.asyncio
async def test_eventi_casuali_un_solo_giro_alla_volta(r):
    await r.m.imposta_eventi(G, 555, True)
    await r.m.imposta_eventi(G + 1, 556, False)
    assert [x["guild_id"] for x in await r.m.eventi_pronti()] == [G] and await r.m.eventi_pronti() == []


@pytest.mark.asyncio
async def test_vacanza_ferma_la_serie_e_non_si_ripaga(r):
    adesso = datetime.now(timezone.utc)
    await r.pr.registra_riscossione(G, 1, adesso - timedelta(hours=30))
    assert await r.m.compra_vacanza(G, 2, 3) == "nessuna_serie"
    assert await r.m.compra_vacanza(G, 1, 3) == "poche"
    await r.lev.add_coins(G, 1, 200)
    assert await r.m.compra_vacanza(G, 1, 3) == "ok" and await _saldo(r, 1) == 140 and await r.m.compra_vacanza(G, 1, 3) == "attiva"
    await r.pool.execute("UPDATE progress_serie SET ultima_at = $1, vacanza_da = $2, vacanza_fino = $3 WHERE user_id = 1",
                         adesso - timedelta(days=5), adesso - timedelta(days=4), adesso + timedelta(days=1))
    esito = await r.pr.registra_riscossione(G, 1, adesso)  # 5 giorni dopo, ma 4 sono di vacanza: la serie continua
    assert esito.serie == 2
    senza = ProgressiRepository(pool_provider=lambda: r.pool)
    await r.pool.execute("UPDATE progress_serie SET ultima_at = $1, vacanza_da = NULL, vacanza_fino = NULL, scudi = 0, serie = 5 WHERE user_id = 1", adesso - timedelta(days=5))
    assert (await senza.registra_riscossione(G, 1, adesso)).serie == 1  # senza vacanza la serie riparte
