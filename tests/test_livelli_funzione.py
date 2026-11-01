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


async def test_livello_o_funzione_sconosciuti():
    with pytest.raises(lf.LivelloNonValido):
        lf.applica_livello("non_esiste", lf.PREMIUM)
    with pytest.raises(lf.LivelloNonValido):
        lf.applica_livello("finta", "oro")
    with pytest.raises(lf.LivelloNonValido):
        await lf.imposta_livello("finta", "oro")


def test_elenco_per_livello():
    lf.applica_livello("finta", lf.PREMIUM)
    lf.applica_livello("finta2", lf.VIP20)
    assert "`/fun dice`" in lf.testo_elenco((lf.PREMIUM,))
    assert "fun joke" not in lf.testo_elenco((lf.PREMIUM,))
    testo = lf.testo_elenco((lf.VIP5, lf.VIP20))
    assert "VIP 20" in testo and "`/fun joke`" in testo
    assert lf.aree_disponibili((lf.PREMIUM,), "fu") == ["fun"]
    assert lf.aree_disponibili((lf.PREMIUM,), "xx") == []


async def test_con_tutto_gratuito_i_comandi_non_si_registrano():
    bot, cog, sync = await _cog()
    assert bot.tree.get_command("premium") is None and bot.tree.get_command("vip") is None
    await cog.cog_unload()


async def test_i_comandi_nascono_e_spariscono_con_i_livelli_e_una_sync_per_cambio():
    bot, cog, sync = await _cog()
    lf.applica_livello("finta", lf.PREMIUM)
    assert bot.tree.get_command("premium") is not None and bot.tree.get_command("vip") is None
    lf.applica_livello("finta2", lf.VIP5)  # stesso istante: una sola sync per i due cambi
    assert bot.tree.get_command("vip") is not None
    await cog.sincronizzatore.attendi()
    assert sync.chiamate == 1
    lf.applica_livello("finta2", lf.VIP20)  # /vip c'è già: l'albero non cambia, nessuna sync
    await asyncio.sleep(0.05)
    assert sync.chiamate == 1
    lf.applica_livello("finta", lf.GRATUITO)
    lf.applica_livello("finta2", lf.GRATUITO)
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


async def test_i_sotto_comandi_sono_fissi_e_rispondono():
    from unittest.mock import AsyncMock, MagicMock

    from cogs.utility.livelli_comandi import crea_gruppi

    lf.applica_livello("finta", lf.PREMIUM)
    premium, vip = crea_gruppi()
    assert sorted(c.name for c in premium.commands) == ["elenco", "info"]
    assert sorted(c.name for c in vip.commands) == ["elenco", "info"]
    inter = MagicMock()
    inter.user.id = 5
    inter.response.send_message = AsyncMock()
    await premium.get_command("elenco").callback(inter, None)
    embed = inter.response.send_message.call_args.kwargs["embed"]
    assert "fun dice" in embed.description


@pytest.mark.parametrize("quante", [0, 1, 30, 200, 665])
async def test_elenco_paginato_regge_30_200_665_funzioni_premium(monkeypatch, quante):
    """L'albero non cambia con il numero di funzioni; ogni pagina resta nei limiti di embed e menu."""
    from cogs.utility.livelli_comandi import ElencoLivelliView, crea_gruppi
    from core.command_groups import GRUPPI
    from tests.test_command_tree_invariants import conta_caratteri

    funzioni = {f"f{i}": (f"Funzione numero {i}", (f"music cmd{i}", f"music altro{i}")) for i in range(quante)}
    monkeypatch.setattr(lf, "FUNZIONI", funzioni)
    for chiave in funzioni:
        lf.applica_livello(chiave, lf.PREMIUM, funzioni)
    premium, vip = crea_gruppi()
    assert conta_caratteri(premium) < 1500 and len(premium.commands) == 2
    righe = lf.righe_per_area((lf.PREMIUM,))
    assert len(righe) == quante
    n = lf.numero_pagine(righe)
    assert n == max(1, -(-quante // lf.PER_PAGINA))
    visti = 0
    for pagina in range(n):
        vista = ElencoLivelliView("Comandi Premium", (lf.PREMIUM,), None, 1, pagina)
        assert len(vista.embed.description) <= 4096
        assert len(vista.embed.footer.text) <= 2048
        assert len(vista.menu.options) <= 25
        visti += len(vista._voci)
        assert vista.indietro.disabled == (pagina == 0)
        assert vista.avanti.disabled == (pagina == n - 1)
    assert visti == quante
    assert len(lf.aree_disponibili((lf.PREMIUM,), "")) <= 25
    assert GRUPPI  # l'albero dei gruppi condivisi non è toccato


async def test_pagina_fuori_misura_si_riporta_nei_limiti():
    righe = [(lf.PREMIUM, f"n{i}", ("a b",)) for i in range(25)]
    assert len(lf.voci_pagina(righe, 99)) == 5
    assert len(lf.voci_pagina(righe, -3)) == 10


async def test_riga_lunga_si_taglia():
    riga = lf.riga_voce(lf.VIP5, "x" * 50, tuple(f"gruppo comando{i}" for i in range(60)))
    assert len(riga) <= 300


async def test_motivo_negato_solo_se_la_funzione_non_e_gratuita():
    from unittest.mock import MagicMock

    inter = MagicMock()
    inter.user.id = 999
    inter.command.qualified_name = "fun dice"
    assert await lf.motivo_negato(inter) is None
    lf.applica_livello("finta", lf.VIP5)
    assert "VIP 5" in await lf.motivo_negato(inter)
    from core.config import config

    inter.user.id = config.OWNER_ID
    assert await lf.motivo_negato(inter) is None
    inter.command.qualified_name = "fun joke"
    inter.user.id = 999
    assert await lf.motivo_negato(inter) is None


async def test_i_livelli_stanno_nel_database(clean_db, monkeypatch):
    from core import database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    await lf.imposta_livello("finta", lf.PREMIUM)
    lf.azzera_livelli()
    assert lf.livello_di("finta") == lf.GRATUITO
    await lf.carica_livelli()
    assert lf.livello_di("finta") == lf.PREMIUM
    await lf.imposta_livello("finta", lf.GRATUITO)
    righe = await clean_db.fetch("SELECT * FROM livelli_funzione")
    assert righe == []


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
