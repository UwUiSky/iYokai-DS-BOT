"""
tests/test_sala_r6.py
=====================
Giochi a più giocatori con sala d'attesa (#125 r6eco): ECO-091, 101-103, 105, 110-114.
Regole pure con seme fisso, puntate bloccate a tutti in una transazione, rimborso, solo i giocatori agiscono.
Funzioni coperte: catalogo #125
"""

import asyncio
import random
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cogs.fun.sala import SalaCog, VistaBomba, VistaGiocatori, rimborso, vince_il_piatto
from core import sala_logic as sl
from core.repositories.contenuti_repo import ContenutiRepository
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.partite_repo import EsitoApertura, PartiteRepository
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

G = 100


def test_roulette_il_banco_ha_il_vantaggio_e_chi_perde_prende_zero():
    rng = random.Random(1)
    totale = vinti = 0
    for _ in range(20000):
        _, pag = sl.risolvi_roulette({1: ("rosso", None)}, 10, rng)
        totale += pag[1]
    assert 0.93 < totale / (20000 * 10) < 1.0  # ×2 su 18/37: resa 0,973
    uscito, pag = sl.risolvi_roulette({1: ("numero", 7), 2: ("nero", None)}, 10, random.Random(5))
    assert pag[1] in (0, 360) and pag[2] in (0, 20) and (uscito == 7) == (pag[1] == 360)
    with pytest.raises(ValueError):
        sl.risolvi_roulette({1: ("boh", None)}, 10, rng)


def test_corsa_e_lotta_hanno_sempre_un_vincitore_tra_i_giocatori():
    for seme in range(30):
        rng = random.Random(seme)
        v, storia = sl.corsa({1: 1.0, 2: 1.2, 3: 1.0}, rng)
        assert v in (1, 2, 3) and storia and max(storia[-1].values()) >= sl.LUNGHEZZA_CORSA
        w, fuori = sl.lotta({1: 50, 2: 70, 3: 50, 4: 50}, rng)
        assert w in (1, 2, 3, 4) and sorted([w, *fuori]) == [1, 2, 3, 4]
    assert sl.velocita_animale(10, True) == pytest.approx(1.2) and sl.velocita_animale(10, False) == 1.0
    assert sl.forza_lottatore(None) == 50 and sl.forza_lottatore(5) == 60 and sl.forza_lottatore(10) == 70
    forti = sum(sl.lotta({1: 70, 2: 50}, random.Random(s))[0] == 1 for s in range(400))
    assert 200 < forti < 330  # l'animale forte vince di più, ma non sempre


def test_bomba_turni_eliminazione_e_ultimo_rimasto():
    b = sl.Bomba([1, 2, 3], random.Random(3))
    assert b.taglia(2, 0) == "non_turno" and b.taglia(1, 99) == "filo_no"
    senza_bomba = next(f for f in b.fili if f != b.bomba)
    assert b.taglia(1, senza_bomba) == "salvo" and b.di_turno == 2
    assert b.taglia(2, b.bomba) == "esplode" and b.vivi == [1, 3] and len(b.fili) == 3  # nuovo giro con un filo in più dei vivi
    assert b.di_turno == 3
    assert b.taglia(3, b.bomba) == "vince" and b.vincitore == 1
    assert b.taglia(1, 0) == "non_turno"  # a partita finita non si taglia più


def test_bomba_chi_non_muove_esce():
    b = sl.Bomba([1, 2, 3], random.Random(1))
    b.esci(2)
    assert b.vivi == [1, 3] and b.di_turno == 1
    b.esci(1)
    assert b.vincitore == 3
    b.esci(3)  # l'ultimo non esce
    assert b.vivi == [3]


def test_carte_si_gioca_solo_stesso_colore_o_valore_e_vince_chi_finisce():
    p = sl.PartitaCarte([1, 2], random.Random(2))
    assert all(len(m) == sl.CARTE_IN_MANO for m in p.mani.values())
    tutte = [c for m in p.mani.values() for c in m] + p.mazzo + [p.cima]
    assert len(tutte) == 72
    assert p.gioca(2, 0) == "non_turno"
    p.cima = (0, 5)
    p.mani[1] = [(1, 2), (0, 9), (3, 5)]
    assert p.gioca(1, 0) == "non_valida" and p.gioca(1, 7) == "non_valida" and p.di_turno == 1
    assert p.gioca(1, 1) == "ok" and p.cima == (0, 9) and p.di_turno == 2
    p.mani[2] = [(0, 1)]
    assert p.gioca(2, 0) == "vince" and p.vincitore == 2 and p.gioca(1, 0) == "non_turno"


def test_carte_pesca_passa_il_turno_e_chi_esce_lascia_le_carte():
    p = sl.PartitaCarte([1, 2, 3], random.Random(4))
    n = len(p.mani[1])
    assert p.pesca(2) is None and p.di_turno == 1  # non è il suo turno
    assert p.pesca(1) is not None and len(p.mani[1]) == n + 1 and p.di_turno == 2
    p.esci(2)
    assert p.ordine == [1, 3] and p.di_turno == 3
    p.esci(3)
    assert p.vincitore == 1


def test_bingo_cartella_e_riga():
    rng = random.Random(7)
    c = sl.cartella_bingo(rng)
    assert len(c) == 3 and all(len(r) == 5 for r in c) and len({n for r in c for n in r}) == 15
    assert not sl.ha_bingo(c, set()) and sl.ha_bingo(c, set(c[1])) and not sl.ha_bingo(c, set(c[1][:4]))
    assert sorted(sl.ordine_estrazione(rng)) == list(range(1, 51))
    assert "[" in sl.testo_cartella(c, set(c[0]))


def test_impiccato_e_quiz_dal_file_del_repository():
    i = sl.Impiccato("gatto")
    assert i.prova("g") == "giusta" and i.prova("G") == "gia" and i.prova("z") == "sbagliata" and i.mascherata == "G \\_ \\_ \\_ \\_"
    for c in "ATO":
        i.prova(c)
    assert i.vinta and i.finita and i.prova("b") == "finita"
    with pytest.raises(ValueError):
        i.prova("1")
    persa = sl.Impiccato("gatto")
    for c in "BCDEFH":
        persa.prova(c)
    assert persa.finita and not persa.vinta
    parole = sl.parole_impiccato()
    assert len(parole) > 100 and all(p.isalpha() and p.isascii() and p.isupper() for p in parole)
    domande = sl.domande_quiz()
    assert len(domande) >= 50 and all(len(set(d["r"])) == 4 for d in domande)
    scelte = sl.scegli_domande(random.Random(9))
    assert len(scelte) == 5 and len({d["d"] for d in scelte}) == 5
    originali = {d["d"]: d for d in domande}
    for d in scelte:  # il rimescolamento mantiene giusta la risposta giusta
        o = originali[d["d"]]
        assert d["r"][d["g"]] == o["r"][o["g"]]


def test_piatto_e_rimborso_non_creano_monete():
    assert vince_il_piatto([1, 2, 3], 10, 2) == {1: 0, 2: 30, 3: 0} and rimborso([1, 2], 10) == {1: 10, 2: 10}


@pytest.fixture
def r(clean_db):
    return SimpleNamespace(
        p=PartiteRepository(pool_provider=lambda: clean_db), lev=LevelingRepository(pool_provider=lambda: clean_db),
        con=ContenutiRepository(pool_provider=lambda: clean_db), pool=clean_db,
    )


async def _saldi(r, utenti):
    return [(await r.lev.get_totals(G, u)).coins_total for u in utenti]


@pytest.mark.asyncio
async def test_puntata_a_tutti_in_una_transazione_e_se_uno_non_puo_nessuno_paga(r):
    for u, m in ((1, 100), (2, 100), (3, 5)):
        await r.lev.add_coins(G, u, m)
    esito, chi = await r.p.apri_gruppo(G, [1, 2, 3], "sala:bomba", 20, 0)
    assert esito is EsitoApertura.POCHE and chi == 3
    assert await _saldi(r, [1, 2, 3]) == [100, 100, 5]  # nessuno ha pagato
    assert await r.pool.fetchval("SELECT count(*) FROM economia_partite_aperte") == 0
    esito, chi = await r.p.apri_gruppo(G, [1, 2], "sala:bomba", 20, 0)
    assert esito is EsitoApertura.APERTA and await _saldi(r, [1, 2]) == [80, 80]
    esito, chi = await r.p.apri_gruppo(G, [2, 3], "sala:carte", 1, 0)
    assert esito is EsitoApertura.GIA_APERTA and chi == 2 and await _saldi(r, [3]) == [5]  # una partita alla volta


@pytest.mark.asyncio
async def test_chiusura_paga_il_vincitore_una_volta_sola_e_il_totale_non_cambia(r):
    for u in (1, 2, 3):
        await r.lev.add_coins(G, u, 100)
    await r.p.apri_gruppo(G, [1, 2, 3], "sala:bomba", 30, 0)
    pagati = await r.p.chiudi_gruppo(G, "sala:bomba", vince_il_piatto([1, 2, 3], 30, 2))
    assert pagati == {1: 0, 2: 90, 3: 0} and await _saldi(r, [1, 2, 3]) == [70, 160, 70]
    assert await r.p.chiudi_gruppo(G, "sala:bomba", vince_il_piatto([1, 2, 3], 30, 2)) == {}  # secondo tentativo: niente
    assert sum(await _saldi(r, [1, 2, 3])) == 300
    assert await r.pool.fetchval("SELECT count(*) FROM economia_partite_aperte") == 0


@pytest.mark.asyncio
async def test_due_sale_insieme_con_lo_stesso_giocatore_una_sola_parte(r):
    for u in (1, 2, 3):
        await r.lev.add_coins(G, u, 100)
    await apri_connessioni(r.pool, 4)
    a, b = await asyncio.gather(r.p.apri_gruppo(G, [1, 2], "sala:bomba", 40, 0), r.p.apri_gruppo(G, [2, 3], "sala:carte", 40, 0))
    assert sorted([a[0].value, b[0].value]) == ["aperta", "gia_aperta"]
    assert sum(await _saldi(r, [1, 2, 3])) == 300 - 80  # pagano solo i due della sala partita
    assert await r.pool.fetchval("SELECT count(*) FROM economia_partite_aperte") == 2


@pytest.mark.asyncio
async def test_riavvio_rimborsa_le_puntate_delle_sale_ma_non_il_blackjack(r):
    for u in (1, 2):
        await r.lev.add_coins(G, u, 100)
    await r.p.apri_gruppo(G, [1], "sala:bingo", 50, 0)
    ap = await r.p.apri(G, 2, "blackjack", 50, 0)
    assert ap.esito is EsitoApertura.APERTA and await _saldi(r, [1, 2]) == [50, 50]
    assert await r.p.rimborsa_gioco("sala:") == 1
    assert await _saldi(r, [1, 2]) == [100, 50] and await r.pool.fetchval("SELECT count(*) FROM economia_partite_aperte") == 1
    assert await r.p.rimborsa_gioco("sala:") == 0  # si ripete senza effetti


@pytest.mark.asyncio
async def test_premi_di_quiz_con_tetto_giornaliero_anche_insieme(r):
    assert await r.con.premia(G, 1, "quiz", 250, 300) == 250
    assert await r.con.premia(G, 1, "quiz", 250, 300) == 50
    assert await r.con.premia(G, 1, "quiz", 10, 300) == 0
    assert await r.con.premia(G, 1, "impiccato", 20, 300) == 20  # il tetto è per tipo
    await apri_connessioni(r.pool, 4)
    dati = await asyncio.gather(*(r.con.premia(G, 2, "quiz", 100, 300) for _ in range(5)))
    assert sum(dati) == 300 and (await r.lev.get_totals(G, 2)).coins_total == 300


@pytest.mark.asyncio
async def test_solo_i_giocatori_della_sala_agiscono(clean_db, monkeypatch):
    import core.ui_base as ui

    async def nessuno(*a, **k):
        return False

    monkeypatch.setattr(ui, "_utente_o_server_in_blacklist", nessuno)
    vista = VistaGiocatori([1, 2], 30)
    estraneo = fake_interaction(guild=fake_guild(G), user=fake_member(9))
    assert await vista.interaction_check(estraneo) is False
    estraneo.response.send_message.assert_awaited()
    assert await vista.interaction_check(fake_interaction(guild=fake_guild(G), user=fake_member(2))) is True
    bomba = sl.Bomba([1, 2], random.Random(1))
    vb = VistaBomba(bomba, [1, 2])
    assert await vb.interaction_check(fake_interaction(guild=fake_guild(G), user=fake_member(7))) is False
