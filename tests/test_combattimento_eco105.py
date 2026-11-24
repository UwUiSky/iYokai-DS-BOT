"""
tests/test_combattimento_eco105.py
==================================
Combattimento a più giocatori con regole su misura (ECO-105): regole pure con seme fisso, riparto del piatto,
turni con bottoni, timeout, annullamento con rimborso a tutti. PostgreSQL vero dove si toccano le monete.
Funzioni coperte: ECO-105
"""

import asyncio
import random
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cogs.fun._combattimento import VistaCombattimento, gioca_combattimento
from cogs.fun.sala import MOTORI, SalaCog, Tavolo
from core import combattimento_logic as cb
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.partite_repo import PartiteRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

G = 100


def nessuno_in_blacklist(monkeypatch) -> None:
    from core import ui_base

    async def nessuno(interaction):
        return False
    monkeypatch.setattr(ui_base, "_utente_o_server_in_blacklist", nessuno)


class RngFisso(random.Random):
    """`random()` sempre sotto o sopra la soglia del colpo."""

    def __init__(self, valore: float) -> None:
        super().__init__(1)
        self.valore = valore

    def random(self) -> float:
        return self.valore


class RngSeq(random.Random):
    def __init__(self, valori: list[float]) -> None:
        super().__init__(1)
        self.valori, self.n = valori, 0

    def random(self) -> float:
        v = self.valori[self.n % len(self.valori)]
        self.n += 1
        return v


def test_regole_si_controllano_una_volta_sola():
    assert cb.controlla_regole(3, 10) is None
    for vite, giri in ((0, 10), (6, 10), (3, 2), (3, 21)):
        assert cb.controlla_regole(vite, giri) is not None


def test_colpo_e_vite_con_turni_in_ordine():
    c = cb.Combattimento([1, 2, 3], vite=2, giri=5, oggetti=False, rng=RngFisso(0.0))  # random() < soglia: ogni colpo va a segno
    assert c.di_turno == 1 and c.vite == {1: 2, 2: 2, 3: 2}
    assert c.attacca(2, 1) == "non_turno" and c.attacca(1, 1) == "bersaglio_no" and c.attacca(1, 9) == "bersaglio_no"
    assert c.attacca(1, 2) == "colpito" and c.vite[2] == 1 and c.di_turno == 2
    assert c.attacca(2, 3) == "colpito" and c.attacca(3, 2) == "eliminato" and c.vivi == [1, 3]
    assert c.di_turno == 1 and c.vincitori is None
    assert c.attacca(1, 2) == "bersaglio_no"  # già fuori
    assert c.attacca(1, 3) == "eliminato"  # 3 aveva già perso una vita
    assert c.vincitori == [1] and c.attacca(1, 3) == "non_turno"  # a partita finita non si muove più


def test_colpo_mancato_passa_il_turno():
    c = cb.Combattimento([1, 2], 3, 5, False, RngFisso(0.99))
    assert c.attacca(1, 2) == "mancato" and c.vite[2] == 3 and c.di_turno == 2


def test_oggetti_pozione_e_scudo_solo_se_ammessi_e_una_volta():
    senza = cb.Combattimento([1, 2], 3, 5, False, RngFisso(0.0))
    assert senza.usa_pozione(1) == "no_oggetti" and senza.usa_scudo(1) == "no_oggetti" and senza.di_turno == 1
    c = cb.Combattimento([1, 2], 3, 6, True, RngFisso(0.0))
    assert c.usa_pozione(1) == "piena" and c.di_turno == 1  # a vite piene non serve e non costa il turno
    assert c.usa_scudo(2) == "non_turno"
    assert c.usa_scudo(1) == "scudo" and c.usa_scudo(1) == "non_turno"  # il turno è passato
    assert c.attacca(2, 1) == "parato" and c.vite[1] == 3  # lo scudo para un colpo e sparisce
    assert c.usa_scudo(1) == "gia_usato"
    assert c.attacca(1, 2) == "colpito" and c.attacca(2, 1) == "colpito" and c.vite[1] == 2
    assert c.usa_pozione(1) == "curato" and c.vite[1] == 3 and c.usa_pozione(1) == "non_turno"
    c.attacca(2, 1)
    assert c.usa_pozione(1) == "gia_usata"


def test_fine_per_giri_vince_chi_ha_piu_vite_e_i_pari_dividono():
    c = cb.Combattimento([1, 2], 5, 3, False, RngSeq([0.0, 0.99]))  # i colpi del primo vanno a segno, quelli del secondo no
    for _ in range(3):
        assert c.vincitori is None
        c.attacca(1, 2)
        c.attacca(2, 1)
    assert c.vincitori == [1] and c.vite == {1: 5, 2: 2}
    p = cb.Combattimento([1, 2], 3, 3, False, RngFisso(0.99))  # nessun colpo a segno
    for _ in range(3):
        p.attacca(1, 2)
        p.attacca(2, 1)
    assert sorted(p.vincitori) == [1, 2]


def test_chi_non_muove_esce_e_resta_uno_solo():
    c = cb.Combattimento([1, 2, 3], 3, 5, False, RngFisso(0.0))
    c.esci(1)  # era di turno
    assert c.vivi == [2, 3] and c.di_turno == 2
    c.esci(3)  # non era di turno
    assert c.vivi == [2] and c.vincitori == [2]
    c.esci(2)  # l'ultimo non esce
    assert c.vivi == [2]


def test_piatto_diviso_senza_perdere_monete():
    assert cb.ripartisci_piatto([1, 2, 3], 10, [2]) == {1: 0, 2: 30, 3: 0}
    ripartito = cb.ripartisci_piatto([1, 2, 3, 4], 10, [1, 3, 4])
    assert sum(ripartito.values()) == 40 and ripartito[2] == 0 and sorted(ripartito[u] for u in (1, 3, 4)) == [13, 13, 14]
    assert cb.ripartisci_piatto([1, 2], 7, []) == {1: 7, 2: 7}  # nessun vincitore: tutti rimborsati
    with pytest.raises(ValueError):
        cb.ripartisci_piatto([1, 2], 5, [9])


def test_partita_registrata_tra_i_motori_da_2_a_6():
    assert MOTORI["combattimento"][0] == "sala:combattimento" and MOTORI["combattimento"][2:] == (2, 6)


def _tavolo(giocatori, puntata=10):
    i = fake_interaction(guild=fake_guild(G), user=fake_member(giocatori[0]))
    for m in giocatori:
        i.guild.get_member = lambda uid: fake_member(uid)
    i.followup.send = AsyncMock(return_value=SimpleNamespace(edit=AsyncMock()))
    tv = Tavolo(i, giocatori, puntata, "coin")
    tv.regole = SimpleNamespace(vite=2, giri=4, oggetti=True)
    return tv


@pytest.mark.asyncio
async def test_vista_solo_chi_e_di_turno_muove_e_gli_estranei_no(monkeypatch):
    nessuno_in_blacklist(monkeypatch)
    tv = _tavolo([1, 2, 3])
    comb = cb.Combattimento([1, 2, 3], 2, 4, True, RngFisso(0.0))
    vista = VistaCombattimento(tv, comb, {u: f"N{u}" for u in (1, 2, 3)}, host_id=1, testi={})
    estraneo = fake_interaction(guild=fake_guild(G), user=fake_member(9))
    assert await vista.interaction_check(estraneo) is False
    fuori_turno = fake_interaction(guild=fake_guild(G), user=fake_member(2))
    await vista.attacca_a(2)(fuori_turno)
    assert fuori_turno.response.send_message.await_args.kwargs["ephemeral"] is True and comb.vite[2] == 2
    giusto = fake_interaction(guild=fake_guild(G), user=fake_member(1))
    giusto.response.edit_message = AsyncMock()
    await vista.attacca_a(2)(giusto)
    assert comb.vite[2] == 1 and comb.di_turno == 2


def test_a_partita_iniziata_non_esiste_il_bottone_annulla():
    tv = _tavolo([1, 2])
    comb = cb.Combattimento([1, 2], 2, 4, True, RngFisso(0.0))
    vista = VistaCombattimento(tv, comb, {1: "A", 2: "B"}, host_id=1, testi={})
    assert not hasattr(vista, "annulla_partita") and not hasattr(vista, "annullata")
    assert all("nnulla" not in (getattr(i, "label", "") or "") for i in vista.children)


@pytest.mark.asyncio
async def test_creatore_eliminato_non_puo_riprendere_la_puntata(clean_db, monkeypatch):
    """Prima il creatore poteva annullare anche da eliminato: ora la partita finisce solo con un vincitore."""
    import cogs.fun._combattimento as modulo
    lev, partite = LevelingRepository(pool_provider=lambda: clean_db), PartiteRepository(pool_provider=lambda: clean_db)
    for u in (1, 2):
        await lev.add_coins(G, u, 100)
    await partite.apri_gruppo(G, [1, 2], "sala:combattimento", 40, 0)
    tv = _tavolo([1, 2], 40)
    tv.regole = SimpleNamespace(vite=1, giri=5, oggetti=False)
    comb_ref = {}
    orig = cb.Combattimento

    class Spia(orig):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            comb_ref["c"] = self

    monkeypatch.setattr(modulo.cb, "Combattimento", Spia)
    monkeypatch.setattr(modulo, "PAUSA", 0.01)
    compito = asyncio.create_task(gioca_combattimento(tv))
    await asyncio.sleep(0.05)
    comb = comb_ref["c"]
    assert comb.di_turno == 1
    comb.esci(1)  # il creatore è eliminato: vince 2
    restituzioni = await asyncio.wait_for(compito, 10)
    assert restituzioni == {1: 0, 2: 80}
    await partite.chiudi_gruppo(G, "sala:combattimento", restituzioni)
    assert (await lev.get_totals(G, 1)).coins_total == 60 and (await lev.get_totals(G, 2)).coins_total == 140


@pytest.mark.asyncio
async def test_mossa_vincente_chiude_la_partita_prima_di_ogni_await(monkeypatch):
    """Un clic concorrente durante l'await del testo della mossa finale non cambia l'esito: un solo esito, pagato."""
    nessuno_in_blacklist(monkeypatch)
    import cogs.fun._combattimento as modulo
    tv = _tavolo([1, 2])
    comb = cb.Combattimento([1, 2], 1, 4, False, RngFisso(0.0))
    vista = VistaCombattimento(tv, comb, {1: "A", 2: "B"}, host_id=1, testi={})
    vista.ultima_mossa = 0
    visto = {}

    async def lento(interaction, chiave, **k):
        if chiave == "cmb_chiusa":
            return "chiusa"
        visto["finita_durante_await"] = vista.finita
        concorrente = fake_interaction(guild=fake_guild(G), user=fake_member(2))
        concorrente.response.send_message = AsyncMock()
        await vista.attacca_a(1)(concorrente)  # mossa concorrente a partita già chiusa
        visto["rifiutata"] = concorrente.response.send_message.await_count == 1
        return "x"

    monkeypatch.setattr(modulo, "testo_per", lento)
    mossa = fake_interaction(guild=fake_guild(G), user=fake_member(1))
    mossa.response.edit_message = AsyncMock()
    await vista.attacca_a(2)(mossa)
    assert comb.vincitori == [1] and vista.finita is True
    assert visto == {"finita_durante_await": True, "rifiutata": True}


@pytest.mark.asyncio
async def test_chiusura_del_gruppo_e_unica_pagamento_o_rimborso(clean_db):
    lev, partite = LevelingRepository(pool_provider=lambda: clean_db), PartiteRepository(pool_provider=lambda: clean_db)
    for u in (1, 2):
        await lev.add_coins(G, u, 100)
    await partite.apri_gruppo(G, [1, 2], "sala:combattimento", 40, 0)
    esiti = await asyncio.gather(
        partite.chiudi_gruppo(G, "sala:combattimento", {1: 80, 2: 0}),
        partite.chiudi_gruppo(G, "sala:combattimento", {1: 40, 2: 40}),
    )
    assert sorted(len(e) for e in esiti) == [0, 2]  # una sola chiusura paga, l'altra non tocca niente
    totale = sum([(await lev.get_totals(G, u)).coins_total for u in (1, 2)])
    assert totale == 200  # 120 rimasti dopo le puntate + 80 di piatto, mai di più


@pytest.mark.asyncio
async def test_gioco_completo_il_vincitore_prende_il_piatto(clean_db, monkeypatch):
    import cogs.fun._combattimento as modulo
    lev, partite = LevelingRepository(pool_provider=lambda: clean_db), PartiteRepository(pool_provider=lambda: clean_db)
    for u in (1, 2, 3):
        await lev.add_coins(G, u, 100)
    esito, _ = await partite.apri_gruppo(G, [1, 2, 3], "sala:combattimento", 40, 0)
    assert esito.value == "aperta"
    tv = _tavolo([1, 2, 3], 40)
    monkeypatch.setattr(modulo, "SECONDI_TURNO", 0.05)
    monkeypatch.setattr(modulo, "PAUSA", 0.01)
    tv.rng = RngFisso(0.0)
    tv.regole = SimpleNamespace(vite=1, giri=5, oggetti=False)
    # nessuno clicca: chi è di turno scade e esce, resta uno solo
    restituzioni = await asyncio.wait_for(gioca_combattimento(tv), 10)
    assert sum(restituzioni.values()) == 120 and sorted(restituzioni.values()) == [0, 0, 120]
    await partite.chiudi_gruppo(G, "sala:combattimento", restituzioni)
    saldi = sorted([(await lev.get_totals(G, u)).coins_total for u in (1, 2, 3)])
    assert saldi == [60, 60, 180]
