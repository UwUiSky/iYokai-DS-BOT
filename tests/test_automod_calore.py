"""
tests/test_automod_calore.py
============================
Il calore dentro l'AutoMod: le regole con punti fanno salire il calore di chi le fa scattare, alla soglia scattano
le azioni del server e il calore riparte; il calore cala col tempo; il canale fermo pesa di più.
Funzioni coperte: SPEC §6 (AMD-068, 069, 072)
"""

from dataclasses import replace
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from core import automod_azioni as azioni_motore
from core import automod_regole_service as servizio
from core.automod_advanced_logic import CaloreConfig
from core.automod_calore_logic import CanaliFermi, Termometro
from core.automod_regole_logic import Regola, azioni_dai_nomi_vecchi
from core.repositories.automod_advanced_repo import automod_advanced_repo
from tests.test_automod_regole_filtri import GUILD_ID, _caps_attivo, _msg, cog  # noqa: F401  (la fixture)

import cogs.automod.automod as modulo_automod


@pytest.fixture
def isola(monkeypatch):
    f = AsyncMock()
    monkeypatch.setattr(azioni_motore.bot_roles, "isola", f)
    return f


@pytest.fixture
def ora(monkeypatch):
    t = {"v": 1000.0}
    monkeypatch.setattr(modulo_automod, "_adesso", lambda: t["v"])
    monkeypatch.setattr(modulo_automod, "termometro", Termometro())
    monkeypatch.setattr(modulo_automod, "canali_fermi", CanaliFermi())
    return t


async def _prepara(cog, calore_regola=60, **opzioni):
    await _caps_attivo(cog)
    s = await automod_advanced_repo.get_settings(GUILD_ID)
    c = CaloreConfig(attivo=True, soglia=100, calo_per_minuto=10, warn=False, timeout_secondi=600, **opzioni)
    await automod_advanced_repo.save_settings(replace(s, config=replace(s.config, calore=c)))
    await servizio.salva(
        GUILD_ID,
        Regola(chiave="anti_caps", tipo="filtro", nome="anti_caps", azioni=azioni_dai_nomi_vecchi(("delete",), 600),
               calore=calore_regola),
        1,
    )


async def test_alla_soglia_scatta_il_timeout_e_il_calore_riparte(cog, isola, ora):
    await _prepara(cog)
    await cog.on_message(_msg())
    isola.assert_not_awaited()  # 60 su 100
    await cog.on_message(_msg())
    isola.assert_awaited_once()  # 120: soglia
    assert isola.await_args.args[1] == timedelta(seconds=600)
    await cog.on_message(_msg())
    assert isola.await_count == 1  # ripartito da zero: 60


async def test_il_calore_cala_col_tempo(cog, isola, ora):
    await _prepara(cog)
    await cog.on_message(_msg())
    ora["v"] += 300  # -50 punti
    await cog.on_message(_msg())
    isola.assert_not_awaited()  # 10 + 60 = 70


async def test_canale_fermo_pesa_di_piu(cog, isola, ora):
    await _prepara(cog, calore_regola=30, fermo_minuti=10, fermo_peso=3)
    await cog.on_message(_msg())  # canale mai visto: 30
    ora["v"] += 3600
    await cog.on_message(_msg())  # fermo da un'ora: 30 x 3 = 90, meno il calo (cap a 0) = 90
    isola.assert_not_awaited()
    await cog.on_message(_msg())  # canale attivo: +30 -> 120
    isola.assert_awaited_once()


async def test_spento_o_senza_punti_non_scatta_nulla(cog, isola, ora):
    await _prepara(cog, calore_regola=0)
    for _ in range(5):
        await cog.on_message(_msg())
    isola.assert_not_awaited()


async def test_persone_diverse_hanno_calore_diverso(cog, isola, ora):
    await _prepara(cog)
    await cog.on_message(_msg(autore=1))
    await cog.on_message(_msg(autore=2))
    isola.assert_not_awaited()
