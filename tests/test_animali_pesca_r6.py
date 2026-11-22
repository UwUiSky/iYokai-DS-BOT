"""
tests/test_animali_pesca_r6.py
==============================
Animali avanzati (ECO-125..129) e pesca avanzata (ECO-135..137, 139..141). Funzioni coperte: catalogo #125
"""

import asyncio
import random
from datetime import date
from types import SimpleNamespace

import pytest

from core import animali_avanzati_logic as lg
from core.repositories.animali_avanzati_repo import AnimaliAvanzatiRepository
from core.repositories.animali_repo import AnimaliRepository
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.pesca_repo import PescaRepository
from tests.support.concorrenza import apri_connessioni

G = 100
OGGI = date(2026, 11, 20)


@pytest.fixture
def r(clean_db):
    return SimpleNamespace(
        av=AnimaliAvanzatiRepository(pool_provider=lambda: clean_db), an=AnimaliRepository(pool_provider=lambda: clean_db),
        pe=PescaRepository(pool_provider=lambda: clean_db), lev=LevelingRepository(pool_provider=lambda: clean_db), pool=clean_db,
    )


async def _animale(r, user, nome="Micio"):
    await r.lev.add_coins(G, user, 5000)
    assert await r.an.compra(G, user, "gatto", nome) == "ok"
    return (await r.an.elenco(G, user))[0]["id"]


def test_logica_pura():
    assert lg.costo_sitter(3) == 120 and lg.punti_abilita(45, 3) == 5
    with pytest.raises(ValueError):
        lg.costo_sitter(8)
    assert lg.pausa_pesca(set(), 0) == 900 and lg.pausa_pesca({"pazienza"}, 3) == 540 and lg.capienza({"capiente"}) == 300
    rng = random.Random(1)
    nulli = lambda ab, esca: sum(lg.pesca_con(random.Random(s), "stagno", ab, esca) is None for s in range(3000))
    assert nulli({"occhio"}, False) < nulli(set(), False) and nulli(set(), True) < nulli(set(), False)
    assert lg.perle_per("sardina") == 1 and lg.perle_per("koi dorato") == 24
    assert lg.livello_stagione(250) == 2 and lg.livello_stagione(99999) == 10 and lg.premio_stagione(3) == 60
    assert lg.lanci_rete(3599) == 0 and lg.lanci_rete(7300) == 2 and lg.lanci_rete(10**7) == 12
    assert lg.nasce_cucciolo(random.Random(0)) in (True, False) and lg.stagione(OGGI) == "2026-11"
    assert 0.2 < sum(lg.nasce_cucciolo(random.Random(s)) for s in range(2000)) / 2000 < 0.3


@pytest.mark.asyncio
async def test_sitter_paga_una_volta_e_tiene_pieni_i_bisogni(r):
    a = await _animale(r, 1)
    saldo = (await r.lev.get_totals(G, 1)).coins_total
    assert await r.av.sitter(G, 2, a, 2) == "non_tuo" and await r.av.sitter(G, 1, a, 2) == "ok"
    assert (await r.lev.get_totals(G, 1)).coins_total == saldo - 80 and await r.av.sitter(G, 1, a, 2) == "attivo"
    assert await r.pool.fetchval("SELECT fame_at > now() + interval '1 day' FROM economia_animali WHERE id = $1", a)
    await r.pool.execute("UPDATE leveling_totals SET coins_total = 1 WHERE user_id = 1")
    await r.pool.execute("UPDATE economia_animali SET sitter_fino = NULL")
    assert await r.av.sitter(G, 1, a, 1) == "poche"


@pytest.mark.asyncio
async def test_lotta_esperienza_pausa_e_proprietari(r):
    a, b = await _animale(r, 1), await _animale(r, 2)
    assert await r.av.lotta(G, a, 2, b, 1, True) == "non_tuo"
    assert await r.av.lotta(G, a, 1, b, 2, True) == "ok"
    xp = {x: await r.pool.fetchval("SELECT xp FROM economia_animali WHERE id = $1", x) for x in (a, b)}
    assert xp[a] == lg.XP_VITTORIA and xp[b] == lg.XP_SCONFITTA
    assert await r.av.lotta(G, a, 1, b, 2, False) == "pausa"
    await apri_connessioni(r.pool, 4)
    await r.pool.execute("UPDATE economia_animali SET lotta_at = NULL")
    e = await asyncio.gather(r.av.lotta(G, a, 1, b, 2, True), r.av.lotta(G, b, 2, a, 1, True))
    assert sorted(e) == ["ok", "pausa"]  # incrociate insieme: nessuno stallo, una sola passa


@pytest.mark.asyncio
async def test_incontro_una_volta_al_giorno_e_cucciolo_nella_coda(r):
    a, b = await _animale(r, 1), await _animale(r, 2)
    assert await r.av.incontro(G, OGGI, a, 2, b, 1, True, "gatto") == ("non_tuo", False)
    assert await r.av.incontro(G, OGGI, a, 1, b, 2, True, "volpe") == ("ok", True)
    assert await r.av.incontro(G, OGGI, b, 2, a, 1, True, "volpe") == ("gia", False)  # stessa coppia, altro verso
    assert await r.av.incontro(G, date(2026, 11, 21), b, 2, a, 1, False, "volpe") == ("ok", False)
    coda = await r.av.da_adottare(G)
    assert [(c["specie"], c["nome"]) for c in coda] == [("volpe", "Cucciolo")]


@pytest.mark.asyncio
async def test_adozione_un_solo_adottante_posti_e_niente_riprendere(r):
    a = await _animale(r, 1)
    assert await r.av.abbandona(G, 2, a) == "non_tuo" and await r.av.abbandona(G, 1, a) == "ok"
    assert await r.av.adotta(G, 1, a) == "tuo_ex"
    for u in (2, 3):
        await r.lev.add_coins(G, u, 10)
    await apri_connessioni(r.pool, 4)
    e = await asyncio.gather(r.av.adotta(G, 2, a), r.av.adotta(G, 3, a))
    assert sorted(e) == ["non_c_e", "ok"]
    assert await r.pool.fetchval("SELECT count(*) FROM economia_animali WHERE user_id IN (2, 3)") == 1
    b = await _animale(r, 4)
    await r.av.abbandona(G, 4, b)
    vincitore = 2 if await r.pool.fetchval("SELECT user_id FROM economia_animali WHERE id = $1", a) == 2 else 3
    assert await r.av.adotta(G, vincitore, b) == "pieno"  # un solo posto


@pytest.mark.asyncio
async def test_coda_di_adozione_piena(r):
    a = await _animale(r, 1)
    for _ in range(lg.CODA_ADOZIONE_MAX):
        await r.pool.execute("INSERT INTO economia_animali (guild_id, user_id, specie, nome) VALUES ($1, 0, 'rana', 'x')", G)
    assert await r.av.abbandona(G, 1, a) == "piena"
    assert await r.av.incontro(G, OGGI, a, 1, a + 1, 1, True, "gatto") == ("non_tuo", False)


@pytest.mark.asyncio
async def test_pesca_profilo_perle_stagione_storico_e_abilita(r):
    for i in range(25):
        await r.an.pesca(G, 1, OGGI, "carpa", 0, capienza=300)
    p = await r.pe.profilo(G, 1)
    assert p.lanci == 25 and p.pescati == 25 and p.perle == 25  # carpa: 5 monete = 1 perla
    assert await r.pe.stagione_stato(G, 1, OGGI) == (125, 0)
    assert len(await r.pe.storico(G, 1)) == 15
    assert await r.pe.punti_liberi(G, 1) == 1 + 1  # 25 pesci = 1, una specie vista = 1
    assert await r.pe.sblocca(G, 1, "occhio") == "ok" and await r.pe.sblocca(G, 1, "occhio") == "gia"
    assert await r.pe.sblocca(G, 1, "mercante") == "poche" and await r.pe.sblocca(G, 1, "boh") == "sconosciuta"
    assert (await r.pe.profilo(G, 1)).abilita == frozenset({"occhio"})
    n, monete = await r.an.vendi_pesci(G, 1, 10)
    assert (n, monete) == (25, 25 * 5 * 110 // 100) and (await r.pe.storico(G, 1, 1))[0]["tipo"] == "vendita"


@pytest.mark.asyncio
async def test_esche_attrezzi_e_pass_si_riscuotono_una_volta(r):
    await r.pool.execute("INSERT INTO economia_pesca_profilo (guild_id, user_id, perle) VALUES ($1, 1, 60)", G)
    assert await r.pe.compra_attrezzo(G, 1, "esca") == ("ok", 5) and await r.pe.compra_attrezzo(G, 1, "canna") == ("ok", 20)
    assert await r.pe.compra_attrezzo(G, 1, "rete") == ("ok", 30) and await r.pe.compra_attrezzo(G, 1, "rete") == ("gia", 0)
    assert (await r.pe.compra_attrezzo(G, 1, "canna"))[0] == "poche"
    p = await r.pe.profilo(G, 1)
    assert (p.perle, p.esche, p.canna) == (5, 1, 1) and p.rete_at is not None
    assert await r.an.pesca(G, 1, OGGI, None, 0, usa_esca=True) is False and (await r.pe.profilo(G, 1)).esche == 0
    await r.pool.execute("INSERT INTO economia_pesca_stagione (guild_id, user_id, stagione, punti) VALUES ($1, 1, '2026-11', 250)", G)
    await apri_connessioni(r.pool, 4)
    e = await asyncio.gather(*(r.pe.riscuoti_stagione(G, 1, OGGI) for _ in range(4)))
    assert sorted(x for x in e if x) == [20, 40] and e.count(None) == 2  # solo due livelli pronti, ognuno una volta


@pytest.mark.asyncio
async def test_rete_aspetta_un_ora_pesca_e_si_azzera(r):
    assert await r.pe.riscuoti_rete(G, 1, OGGI, lambda n: []) is None  # senza rete
    await r.pool.execute("INSERT INTO economia_pesca_profilo (guild_id, user_id, rete_at) VALUES ($1, 1, now())", G)
    assert await r.pe.riscuoti_rete(G, 1, OGGI, lambda n: []) is None  # non è passata un'ora
    await r.pool.execute("UPDATE economia_pesca_profilo SET rete_at = now() - interval '3 hours 5 minutes'")
    await apri_connessioni(r.pool, 4)
    e = await asyncio.gather(r.pe.riscuoti_rete(G, 1, OGGI, lambda n: ["sardina"] * n), r.pe.riscuoti_rete(G, 1, OGGI, lambda n: ["sardina"] * n))
    assert [len(x) for x in e if x is not None] == [3] and e.count(None) == 1  # una sola riscossione
    assert (await r.an.deposito(G, 1)) == {"sardina": 3}
