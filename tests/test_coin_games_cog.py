"""
tests/test_coin_games_cog.py
============================
NF-40 (#111): comandi /giochi gioca, /fun misura, e il listener. Archivio su PostgreSQL vero.
Funzioni coperte: SPEC §23.16
"""

import random
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

import cogs.fun.coin_games as modulo
from core.repositories.leveling_repo import LevelingRepository
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_message,
    fake_text_channel,
)
from tests.support.moduli import attiva_livelli

GUILD = 100


@pytest.fixture
async def scena(monkeypatch, clean_db):
    import core.database as database_module
    from core.command_groups import costruisci_gruppi, registra_comandi_del_cog

    await attiva_livelli(monkeypatch, clean_db, GUILD)
    await database_module.db.set_module_active_for_guild(GUILD, "fun", True)
    monkeypatch.setattr(modulo, "db", database_module.db)
    monete = LevelingRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "leveling_repo", monete)
    cog = modulo.CoinGamesCog(bot=None)
    comandi = {
        c.qualified_name: c
        for c in registra_comandi_del_cog(cog, gruppi=costruisci_gruppi(), tree=None)
    }
    return SimpleNamespace(cog=cog, comandi=comandi, monete=monete)


def _interazione(user_id=1):
    return fake_interaction(guild=fake_guild(GUILD), user=fake_member(user_id, name=f"u{user_id}"))


def _scelta(valore, nome=None):
    return SimpleNamespace(value=valore, name=nome or valore)


def _testo(interazione):
    chiamata = interazione.response.send_message.await_args
    if chiamata.args:
        return chiamata.args[0]
    return chiamata.kwargs["embed"].description


class _Rng:
    def __init__(self, *valori):
        self._valori = list(valori)

    def randint(self, a, b):
        return self._valori.pop(0)

    def choice(self, seq):
        return seq[self._valori.pop(0)]


async def _libera_attesa(scena):
    await scena.monete._pool.execute("UPDATE leveling_totals SET ultima_partita_at = NULL")


# ----------------------------------------------------------------------
# /giochi gioca
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_due_partite_insieme_ne_passa_una_sola(scena):
    from tests.support.concorrenza import apri_connessioni
    import asyncio

    await scena.monete.add_coins(GUILD, 1, 1000)
    await apri_connessioni(scena.monete._pool, 6)
    scena.cog._rng = _Rng(*([1] * 10))  # croce: ogni partita persa costa la puntata
    interazioni = [_interazione() for _ in range(5)]

    await asyncio.gather(*(
        scena.comandi["giochi gioca"].callback(
            scena.cog, i, gioco=_scelta("monetina"), puntata=10, scelta=_scelta("testa")
        )
        for i in interazioni
    ))

    assert (await scena.monete.get_totals(GUILD, 1)).coins_total == 990
    messaggi = [_testo(i) for i in interazioni]
    assert sum("Piano" in m for m in messaggi) == 4


@pytest.mark.asyncio
async def test_gioca_richiede_anche_il_modulo_livelli(scena):
    import core.database as database_module

    await scena.monete.add_coins(GUILD, 1, 100)
    await database_module.db.set_module_active_for_guild(GUILD, "leveling", False)
    interazione = _interazione()

    await scena.comandi["giochi gioca"].callback(
        scena.cog, interazione, gioco=_scelta("dadi"), puntata=10, scelta=None
    )

    assert (await scena.monete.get_totals(GUILD, 1)).coins_total == 100
    assert "Livelli" in _testo(interazione)


@pytest.mark.asyncio
async def test_i_comandi_sono_sotto_fun(scena):
    for nome in ("giochi gioca", "fun misura"):
        assert nome in scena.comandi


@pytest.mark.asyncio
async def test_vincita_e_perdita_cambiano_il_saldo(scena):
    await scena.monete.add_coins(GUILD, 1, 100)
    scena.cog._rng = _Rng(0)  # esce testa
    await scena.comandi["giochi gioca"].callback(
        scena.cog, _interazione(), gioco=_scelta("monetina"), puntata=40, scelta=_scelta("testa")
    )
    assert (await scena.monete.get_totals(GUILD, 1)).coins_total == 140

    await _libera_attesa(scena)
    scena.cog._rng = _Rng(1)  # esce croce
    interazione = _interazione()
    await scena.comandi["giochi gioca"].callback(
        scena.cog, interazione, gioco=_scelta("monetina"), puntata=40, scelta=_scelta("testa")
    )
    assert (await scena.monete.get_totals(GUILD, 1)).coins_total == 100
    assert "perso" in _testo(interazione)


@pytest.mark.asyncio
async def test_senza_coin_a_sufficienza_non_si_gioca(scena):
    await scena.monete.add_coins(GUILD, 1, 10)
    interazione = _interazione()
    await scena.comandi["giochi gioca"].callback(
        scena.cog, interazione, gioco=_scelta("dadi"), puntata=50, scelta=None
    )
    assert "abbastanza" in _testo(interazione)
    assert (await scena.monete.get_totals(GUILD, 1)).coins_total == 10


@pytest.mark.asyncio
async def test_monetina_senza_lato_e_rifiutata(scena):
    await scena.monete.add_coins(GUILD, 1, 100)
    interazione = _interazione()
    await scena.comandi["giochi gioca"].callback(
        scena.cog, interazione, gioco=_scelta("monetina"), puntata=10, scelta=None
    )
    assert "testa o croce" in _testo(interazione)
    assert (await scena.monete.get_totals(GUILD, 1)).coins_total == 100


@pytest.mark.asyncio
async def test_due_partite_di_fila_vengono_fermate(scena):
    await scena.monete.add_coins(GUILD, 1, 100)
    scena.cog._rng = random.Random(1)
    await scena.comandi["giochi gioca"].callback(
        scena.cog, _interazione(), gioco=_scelta("dadi"), puntata=10, scelta=None
    )
    dopo_la_prima = (await scena.monete.get_totals(GUILD, 1)).coins_total
    interazione = _interazione()
    await scena.comandi["giochi gioca"].callback(
        scena.cog, interazione, gioco=_scelta("dadi"), puntata=10, scelta=None
    )
    assert "Aspetta" in _testo(interazione)
    assert (await scena.monete.get_totals(GUILD, 1)).coins_total == dopo_la_prima


@pytest.mark.asyncio
async def test_modulo_spento_nessuna_partita(scena):
    import core.database as database_module

    await database_module.db.set_module_active_for_guild(GUILD, "fun", False)
    await scena.monete.add_coins(GUILD, 1, 100)
    interazione = _interazione()
    await scena.comandi["giochi gioca"].callback(
        scena.cog, interazione, gioco=_scelta("dadi"), puntata=10, scelta=None
    )
    assert "non è attivo" in _testo(interazione)
    assert (await scena.monete.get_totals(GUILD, 1)).coins_total == 100


# ----------------------------------------------------------------------
# /fun misura
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_misura_risponde_con_una_percentuale(scena):
    interazione = _interazione()
    await scena.comandi["fun misura"].callback(scena.cog, interazione, tema="coraggio", membro=None)
    assert "coraggio" in _testo(interazione) and "%" in _testo(interazione)


@pytest.mark.asyncio
async def test_misura_rifiuta_i_temi_su_caratteristiche_protette(scena):
    interazione = _interazione()
    await scena.comandi["fun misura"].callback(scena.cog, interazione, tema="quanto sei gay", membro=None)
    assert "non misuro" in _testo(interazione)
    assert interazione.response.send_message.await_args.kwargs.get("ephemeral") is True
