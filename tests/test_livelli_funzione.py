"""
tests/test_livelli_funzione.py
==============================
Livelli di abbonamento per funzione (D57): un punto solo, `/premium` e `/vip` che nascono
e spariscono con i livelli, una sola sincronizzazione per cambio.
Funzioni coperte: D57, D56
"""

from __future__ import annotations

import asyncio

import discord
import pytest
from discord.ext import commands

from cogs.utility.livelli_comandi import LivelliComandiCog
from core import livelli_funzione as lf
from core.command_sync import SincronizzatoreDifferito


@pytest.fixture(autouse=True)
def _tutto_gratuito(monkeypatch):
    lf.azzera_livelli()
    monkeypatch.setitem(lf.FUNZIONI, "finta", ("Funzione finta", ("fun dice",)))
    monkeypatch.setitem(lf.FUNZIONI, "finta2", ("Altra finta", ("fun joke",)))
    yield
    lf.azzera_livelli()


class _SyncFinta:
    def __init__(self):
        self.chiamate = 0

    async def __call__(self):
        self.chiamate += 1


async def _cog():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    sync = _SyncFinta()
    cog = LivelliComandiCog(bot, SincronizzatoreDifferito(sync, attesa=0.01, intervallo_minimo=0))
    await cog.cog_load()
    return bot, cog, sync


def test_di_default_tutto_gratuito():
    assert lf.livello_di("finta") == lf.GRATUITO
    assert not lf.serve_premium() and not lf.serve_vip()
    assert "gratuite" in lf.testo_elenco((lf.PREMIUM,))


def test_livello_o_funzione_sconosciuti():
    with pytest.raises(lf.LivelloNonValido):
        lf.imposta_livello("non_esiste", lf.PREMIUM)
    with pytest.raises(lf.LivelloNonValido):
        lf.imposta_livello("finta", "oro")


def test_elenco_per_livello():
    lf.imposta_livello("finta", lf.PREMIUM)
    lf.imposta_livello("finta2", lf.VIP20)
    assert "`/fun dice`" in lf.testo_elenco((lf.PREMIUM,))
    assert "fun joke" not in lf.testo_elenco((lf.PREMIUM,))
    testo = lf.testo_elenco((lf.VIP5, lf.VIP20))
    assert "VIP 20" in testo and "`/fun joke`" in testo


async def test_con_tutto_gratuito_i_comandi_non_si_registrano():
    bot, cog, sync = await _cog()
    assert bot.tree.get_command("premium") is None and bot.tree.get_command("vip") is None
    await cog.cog_unload()


async def test_i_comandi_nascono_e_spariscono_con_i_livelli_e_una_sync_per_cambio():
    bot, cog, sync = await _cog()
    lf.imposta_livello("finta", lf.PREMIUM)
    assert bot.tree.get_command("premium") is not None and bot.tree.get_command("vip") is None
    lf.imposta_livello("finta2", lf.VIP5)  # stesso istante: una sola sync per i due cambi
    assert bot.tree.get_command("vip") is not None
    await cog.sincronizzatore.attendi()
    assert sync.chiamate == 1
    lf.imposta_livello("finta2", lf.VIP20)  # /vip c'è già: l'albero non cambia, nessuna sync
    await asyncio.sleep(0.05)
    assert sync.chiamate == 1
    lf.imposta_livello("finta", lf.GRATUITO)
    lf.imposta_livello("finta2", lf.GRATUITO)
    assert bot.tree.get_command("premium") is None and bot.tree.get_command("vip") is None
    await cog.sincronizzatore.attendi()
    assert sync.chiamate == 2
    await cog.cog_unload()


async def test_sincronizzatore_unisce_le_richieste_ravvicinate():
    sync = _SyncFinta()
    s = SincronizzatoreDifferito(sync, attesa=0.01, intervallo_minimo=0)
    for _ in range(5):
        s.richiedi()
    await s.attendi()
    assert sync.chiamate == 1


async def test_sincronizzatore_rispetta_l_intervallo_minimo():
    sync = _SyncFinta()
    s = SincronizzatoreDifferito(sync, attesa=0.01, intervallo_minimo=0.2)
    s.richiedi()
    await s.attendi()
    inizio = asyncio.get_running_loop().time()
    s.richiedi()
    await s.attendi()
    assert asyncio.get_running_loop().time() - inizio >= 0.15
    assert sync.chiamate == 2


async def test_i_comandi_rispondono_con_l_elenco():
    from unittest.mock import AsyncMock, MagicMock

    from cogs.utility.livelli_comandi import crea_comandi

    lf.imposta_livello("finta", lf.PREMIUM)
    premium, _ = crea_comandi()
    inter = MagicMock()
    inter.response.send_message = AsyncMock()
    await premium.callback(inter)
    assert "fun dice" in inter.response.send_message.call_args.args[0]


async def test_i_percorsi_delle_funzioni_esistono_nell_albero_vero(monkeypatch):
    from core.command_groups import GRUPPI
    from tests.support.full_tree import build_full_bot, close_full_bot, connect_db_if_needed

    monkeypatch.undo()  # le funzioni finte non servono qui
    creato = await connect_db_if_needed()
    bot, falliti = await build_full_bot()
    try:
        assert not falliti, falliti
        for chiave, (_, percorsi) in lf.FUNZIONI.items():
            for percorso in percorsi:
                nodo = GRUPPI[percorso.split()[0]]
                for parte in percorso.split()[1:]:
                    nodo = nodo.get_command(parte)
                    assert nodo is not None, f"{chiave}: '/{percorso}' non esiste"
    finally:
        await close_full_bot(bot)
        if creato:
            from core.database import db

            await db.close()
