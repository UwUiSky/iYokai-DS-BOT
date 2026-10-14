"""
tests/test_coin_games_logic.py
==============================
NF-40 (#111): regole dei giochi con le monete, misuratore a tema libero e
gioco del conteggio. Logica pura e archivio su PostgreSQL vero.
Funzioni coperte: SPEC §23.16
"""

import asyncio
import random
from datetime import date

import pytest

from core.coin_games_logic import (
    PUNTATA_MASSIMA,
    gioca_dadi,
    gioca_monetina,
    gioca_slot,
    ritorno_atteso_slot,
)
from core.fun_logic import compute_misura, tema_ammesso


# ----------------------------------------------------------------------
# Giochi
# ----------------------------------------------------------------------
class _Rng:
    """Dadi truccati dal test: restituisce i valori dati, uno alla volta."""

    def __init__(self, *valori):
        self._valori = list(valori)

    def randint(self, a, b):
        return self._valori.pop(0)

    def choice(self, seq):
        return seq[self._valori.pop(0)]


def test_monetina_vince_il_doppio_perde_tutto():
    assert gioca_monetina("testa", 100, _Rng(0)).restituzione == 200  # esce testa
    assert gioca_monetina("testa", 100, _Rng(1)).restituzione == 0
    assert gioca_monetina("croce", 100, _Rng(1)).restituzione == 200
    with pytest.raises(ValueError):
        gioca_monetina("lato", 100, _Rng(0))


def test_dadi_vince_chi_ha_il_numero_piu_alto_e_il_pari_restituisce():
    assert gioca_dadi(50, _Rng(6, 2)).restituzione == 100
    assert gioca_dadi(50, _Rng(2, 6)).restituzione == 0
    pari = gioca_dadi(50, _Rng(3, 3))
    assert pari.restituzione == 50 and pari.vinto is False


def test_slot_tre_uguali_otto_volte_due_uguali_una_volta_e_mezza():
    assert gioca_slot(100, _Rng(0, 0, 0)).restituzione == 800
    assert gioca_slot(100, _Rng(0, 0, 3)).restituzione == 150
    assert gioca_slot(100, _Rng(0, 3, 0)).restituzione == 150
    assert gioca_slot(100, _Rng(1, 2, 3)).restituzione == 0


@pytest.mark.parametrize("puntata", [1, 3, 7, 100, PUNTATA_MASSIMA])
def test_la_slot_ha_un_vantaggio_per_il_banco_con_ogni_puntata(puntata):
    assert 0.5 < ritorno_atteso_slot(puntata) < 1.0


def test_gli_esiti_veri_non_rendono_mai_piu_del_massimo_possibile():
    rng = random.Random(5)
    for _ in range(500):
        assert 0 <= gioca_slot(100, rng).restituzione <= 800
        assert 0 <= gioca_dadi(100, rng).restituzione <= 200
        assert 0 <= gioca_monetina("testa", 100, rng).restituzione <= 200


# ----------------------------------------------------------------------
# Misuratore
# ----------------------------------------------------------------------
def test_la_misura_e_stabile_nello_stesso_giorno_e_cambia_con_il_tema():
    giorno = date(2026, 10, 13)
    a = compute_misura(42, "coraggio", giorno)
    assert a == compute_misura(42, "coraggio", giorno)
    assert a == compute_misura(42, "  CORAGGIO ", giorno)  # maiuscole e spazi non contano
    assert 0 <= a <= 100
    valori = {compute_misura(42, f"tema {i}", giorno) for i in range(30)}
    assert len(valori) > 5  # non è sempre lo stesso numero
    assert compute_misura(42, "coraggio", date(2026, 10, 14)) != a or compute_misura(
        42, "coraggio", date(2026, 10, 15)
    ) != a  # cambia con i giorni


@pytest.mark.parametrize(
    "tema, atteso",
    [
        ("coraggio", True),
        ("quanto sei pronto per il lunedì", True),
        ("pizza con l'ananas", True),
        ("quanto sei gay", False),
        ("Omosessualità", False),
        ("che religione sei", False),
        ("quanto sei musulmano", False),
        ("la tua razza", False),
        ("disabilità", False),
        ("", False),
        ("   ", False),
        # parole intere: nessun falso allarme dentro altre parole
        ("voglia di celebrare", True),
        ("quanto sei ateniese", True),
        ("la tua transizione al lunedì", True),
        ("quanto sei stratosferico", True),
        ("fame di marzapane", True),
        # varianti e imbrogli
        ("quanto sei g a y", False),
        ("quanto sei g.a.y", False),
        ("quanto sei gаy", False),   # la "а" è cirillica
        ("quanto sei ｇａｙ", False),  # lettere a larghezza intera
        ("quanto sei ga\u200by", False),  # carattere invisibile in mezzo
        ("quanto sei MUSULMANO", False),
        ("la tua  razza", False),
        ("quanto sei ebreo", False),
        ("quanto sei cristiаno", False),  # "а" cirillica
        ("quanto sei ateo", False),
    ],
)
def test_il_tema_libero_non_misura_caratteristiche_protette(tema, atteso):
    assert tema_ammesso(tema) is atteso


# ----------------------------------------------------------------------
# Archivio: la partita è una scrittura sola
# ----------------------------------------------------------------------
GUILD = 100


@pytest.fixture
def repo(clean_db):
    from core.repositories.leveling_repo import LevelingRepository

    return LevelingRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_gioca_toglie_la_puntata_e_da_la_restituzione(repo, clean_db):
    await repo.add_coins(GUILD, 1, 100)
    assert await repo.gioca(GUILD, 1, 40, 80) == 140  # vinta: +40
    assert await repo.gioca(GUILD, 1, 40, 0) == 100  # persa: -40
    assert await repo.gioca(GUILD, 1, 40, 40) == 100  # pari
    # I giochi non fanno salire la classifica del mese: resta solo il +100 iniziale.
    mese = await clean_db.fetchval(
        "SELECT coins FROM leveling_activity WHERE guild_id = $1 AND user_id = 1", GUILD
    )
    assert mese == 100


@pytest.mark.asyncio
async def test_gioca_senza_saldo_non_scrive_nulla(repo):
    await repo.add_coins(GUILD, 1, 30)
    assert await repo.gioca(GUILD, 1, 31, 62) is None
    assert await repo.gioca(GUILD, 2, 1, 2) is None  # chi non ha mai avuto coin
    assert (await repo.get_totals(GUILD, 1)).coins_total == 30


@pytest.mark.asyncio
async def test_partite_insieme_non_spendono_due_volte(repo, clean_db):
    from tests.support.concorrenza import apri_connessioni

    await apri_connessioni(clean_db)
    await repo.add_coins(GUILD, 1, 100)
    esiti = await asyncio.gather(*(repo.gioca(GUILD, 1, 60, 0) for _ in range(6)))
    assert sorted(e for e in esiti if e is not None) == [40]
    assert (await repo.get_totals(GUILD, 1)).coins_total == 40
