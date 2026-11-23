"""
tests/test_battaglia_fun.py
===========================
Battaglia a turni tra due utenti (FUN-019, #131): regole, turni, puntata atomica, timeout, blocchi, statistiche.
Funzioni coperte: FUN-019
"""

import asyncio
import random
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cogs.fun.battaglia import BattagliaCog, BattagliaView
from core import battaglia_logic as bl
from core.repositories.battaglie_repo import BattaglieRepository
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.partite_repo import PartiteRepository
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

G = 100


class RngFisso(random.Random):
    """Il valore minimo del tiro, salvo `tiri` dati a mano per il test sull'abilità a vuoto."""

    def __init__(self, tiri=None):
        super().__init__(1)
        self.tiri = list(tiri or [])

    def randint(self, a, b):
        return self.tiri.pop(0) if self.tiri else a


def test_attacco_difesa_e_abilita():
    a, b = bl.Combattente(), bl.Combattente()
    e = bl.esegui(a, b, bl.ATTACCO, RngFisso())
    assert (e.danno, b.pv) == (8, 92)
    bl.esegui(b, a, bl.DIFESA, RngFisso())
    assert b.guardia and b.pv == 95
    e = bl.esegui(a, b, bl.ATTACCO, RngFisso())  # guardia: dimezzato, e la guardia è consumata
    assert e.parato and e.danno == 4 and b.pv == 91 and not b.guardia
    e = bl.esegui(a, b, bl.ABILITA, RngFisso([90, 18]))  # tiro a vuoto escluso (90 > 25), danno 18
    assert e.danno == 18 and b.pv == 73 and a.ricarica == bl.RICARICA_ABILITA


def test_abilita_ricarica_e_a_vuoto():
    a, b = bl.Combattente(), bl.Combattente()
    e = bl.esegui(a, b, bl.ABILITA, RngFisso([10]))  # 10 <= 25: a vuoto
    assert e.mancato and b.pv == 100
    assert not bl.puo_agire(a, bl.ABILITA)
    with pytest.raises(ValueError):
        bl.esegui(a, b, bl.ABILITA, RngFisso())
    for _ in range(bl.RICARICA_ABILITA):
        bl.inizia_turno(a)
    assert bl.puo_agire(a, bl.ABILITA) and not bl.puo_agire(a, "fuga")


def test_la_cura_non_supera_i_punti_vita_e_la_guardia_dura_un_giro():
    a, b = bl.Combattente(), bl.Combattente()
    assert bl.esegui(a, b, bl.DIFESA).curato == 0 and a.pv == 100
    bl.inizia_turno(a)
    assert not a.guardia  # al suo turno successivo la guardia è finita


def test_vincitore_e_limite_dei_turni():
    a, b = bl.Combattente(pv=0), bl.Combattente(pv=5)
    assert bl.vincitore(a, b, 3) == 2
    assert bl.vincitore(bl.Combattente(pv=0), bl.Combattente(pv=0), 3) == 0
    assert bl.vincitore(bl.Combattente(pv=50), bl.Combattente(pv=40), 3) is None
    assert bl.vincitore(bl.Combattente(pv=50), bl.Combattente(pv=40), bl.TURNI_MASSIMI) == 1
    assert bl.vincitore(bl.Combattente(pv=40), bl.Combattente(pv=40), bl.TURNI_MASSIMI) == 0
    assert bl.barra(100) == "█" * 10 and bl.barra(0) == "░" * 10 and bl.barra(1).startswith("█")


@pytest.fixture
def r(clean_db, monkeypatch):
    import cogs.fun.battaglia as m
    import core.ui_base as ui
    from core.repositories.leveling_settings_repo import LevelingSettingsRepository
    from core.repositories.sociale_repo import SocialeRepository

    async def nessuno(*a, **k):
        return False

    monkeypatch.setattr(ui, "_utente_o_server_in_blacklist", nessuno)
    partite = PartiteRepository(pool_provider=lambda: clean_db)
    battaglie = BattaglieRepository(pool_provider=lambda: clean_db)
    sociale = SocialeRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(m, "partite_repo", partite)
    monkeypatch.setattr(m, "battaglie_repo", battaglie)
    monkeypatch.setattr(m, "sociale_repo", sociale)
    monkeypatch.setattr(m, "leveling_settings_repo", LevelingSettingsRepository(pool_provider=lambda: clean_db))
    return SimpleNamespace(p=partite, b=battaglie, s=sociale, lev=LevelingRepository(pool_provider=lambda: clean_db), pool=clean_db)


def _i(membro):
    i = fake_interaction(guild=fake_guild(G), user=membro)
    i.response.edit_message = AsyncMock()
    return i


async def _saldi(r, *utenti):
    return [(await r.lev.get_totals(G, u)).coins_total for u in utenti]


@pytest.mark.asyncio
async def test_solo_lo_sfidato_accetta_e_senza_posta_non_si_toccano_le_monete(r):
    a, b = fake_member(1), fake_member(2)
    v = BattagliaView(G, a, b, 0, "coin", RngFisso())
    await v._accetta(_i(a))
    assert v.fase == "attesa"
    await v._accetta(_i(b))
    assert v.fase == "in_corso" and v.timeout == bl.TEMPO_TURNO
    assert await v.interaction_check(_i(fake_member(9))) is False  # un estraneo non tocca la battaglia


@pytest.mark.asyncio
async def test_agisce_solo_chi_e_di_turno_e_il_clic_doppio_conta_una_volta(r):
    a, b = fake_member(1), fake_member(2)
    v = BattagliaView(G, a, b, 0, "coin", RngFisso())
    await v._accetta(_i(b))
    ie = _i(b)
    await v._gioca(ie, bl.ATTACCO)  # tocca ad a
    assert ie.response.send_message.await_args.kwargs["ephemeral"] is True and v.c[1].pv == 100
    await asyncio.gather(v._gioca(_i(a), bl.ATTACCO), v._gioca(_i(a), bl.ATTACCO))  # due clic insieme
    assert v.c[2].pv == 92 and v.turno == 2 and v.turni == 1


@pytest.mark.asyncio
async def test_abilita_in_ricarica_e_rifiutata(r):
    a, b = fake_member(1), fake_member(2)
    v = BattagliaView(G, a, b, 0, "coin", RngFisso([90, 18]))
    await v._accetta(_i(b))
    await v._gioca(_i(a), bl.ABILITA)
    await v._gioca(_i(b), bl.DIFESA)
    i = _i(a)
    await v._gioca(i, bl.ABILITA)  # ancora in ricarica
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True and v.turno == 1 and v.turni == 2


@pytest.mark.asyncio
async def test_con_puntata_le_monete_si_tolgono_insieme_o_per_niente(r):
    await r.lev.add_coins(G, 1, 100)
    await r.lev.add_coins(G, 2, 10)
    a, b = fake_member(1), fake_member(2)
    v = BattagliaView(G, a, b, 50, "coin", RngFisso())
    await v._accetta(_i(b))  # b non ha 50: a non perde niente
    assert v.fase == "fine" and await _saldi(r, 1, 2) == [100, 10]
    assert await r.pool.fetchval("SELECT count(*) FROM economia_partite_aperte") == 0
    await r.lev.add_coins(G, 2, 90)
    v = BattagliaView(G, a, b, 50, "coin", RngFisso())
    await v._accetta(_i(b))
    assert v.fase == "in_corso" and await _saldi(r, 1, 2) == [50, 50]
    await v._accetta(_i(b))  # secondo clic: niente di nuovo
    assert await _saldi(r, 1, 2) == [50, 50]


@pytest.mark.asyncio
async def test_il_vincitore_incassa_una_volta_e_le_statistiche_si_aggiornano(r):
    await r.lev.add_coins(G, 1, 100)
    await r.lev.add_coins(G, 2, 100)
    a, b = fake_member(1), fake_member(2)
    v = BattagliaView(G, a, b, 40, "coin", RngFisso())
    await v._accetta(_i(b))
    v.c[2].pv = 5
    await v._gioca(_i(a), bl.ATTACCO)  # 8 danni: b a terra
    assert v.fase == "fine" and await _saldi(r, 1, 2) == [140, 60]
    await v._fine(None, 2)  # chiusura doppia: niente
    await v.on_timeout()
    assert await _saldi(r, 1, 2) == [140, 60]
    assert await r.b.statistiche(G, 1) == (1, 0) and await r.b.statistiche(G, 2) == (0, 1)


@pytest.mark.asyncio
async def test_chi_non_agisce_entro_il_tempo_perde(r):
    await r.lev.add_coins(G, 1, 100)
    await r.lev.add_coins(G, 2, 100)
    a, b = fake_member(1), fake_member(2)
    v = BattagliaView(G, a, b, 30, "coin", RngFisso())
    v.messaggio = _i(a)
    v.messaggio.edit_original_response = AsyncMock()
    await v._accetta(_i(b))
    await v.on_timeout()  # tocca ad a e non agisce: vince b
    assert v.fase == "fine" and await _saldi(r, 1, 2) == [70, 130]
    assert await r.b.statistiche(G, 2) == (1, 0)


@pytest.mark.asyncio
async def test_limite_dei_turni_pareggio_restituisce_le_puntate(r):
    await r.lev.add_coins(G, 1, 100)
    await r.lev.add_coins(G, 2, 100)
    a, b = fake_member(1), fake_member(2)
    v = BattagliaView(G, a, b, 30, "coin", RngFisso())
    await v._accetta(_i(b))
    v.turni = bl.TURNI_MASSIMI - 1
    v.c[1].pv = v.c[2].pv = 100
    await v._gioca(_i(a), bl.DIFESA)  # nessun danno: ultimo turno, stessi PV
    assert v.fase == "fine" and await _saldi(r, 1, 2) == [100, 100]
    assert await r.b.statistiche(G, 1) == (0, 0)


@pytest.mark.asyncio
async def test_statistiche_in_concorrenza(r):
    await apri_connessioni(r.pool, 6)
    await asyncio.gather(*(r.b.registra(G, 1, 2) for _ in range(6)))
    assert await r.b.statistiche(G, 1) == (6, 0) and await r.b.statistiche(G, 2) == (0, 6)
    assert await r.b.classifica(G) == [(1, 6, 0), (2, 0, 6)]


@pytest.mark.asyncio
async def test_il_comando_rispetta_blocchi_e_bersagli(r, monkeypatch):
    import cogs.fun.battaglia as m

    async def attivo(*a, **k):
        return True

    monkeypatch.setattr(m.db, "is_module_active_for_guild", attivo)
    cog = BattagliaCog.__new__(BattagliaCog)
    a, b = fake_member(1), fake_member(2)
    for bersaglio in (a, fake_member(3, bot=True)):  # se stesso, un bot
        i = _i(a)
        await BattagliaCog.battaglia.callback(cog, i, bersaglio, 0)
        assert i.response.send_message.await_args.kwargs["ephemeral"] is True
    await r.s.blocca(2, 1)  # b ha bloccato a: nessuna sfida
    i = _i(a)
    await BattagliaCog.battaglia.callback(cog, i, b, 0)
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True
    i = _i(b)  # e viceversa: a non sfida chi ha bloccato
    await r.s.sblocca(2, 1)
    await r.s.blocca(1, 2)
    await BattagliaCog.battaglia.callback(cog, i, a, 0)
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True
    await r.s.sblocca(1, 2)
    i = _i(a)
    await BattagliaCog.battaglia.callback(cog, i, b, 0)
    assert i.response.send_message.await_args.kwargs.get("view") is not None
