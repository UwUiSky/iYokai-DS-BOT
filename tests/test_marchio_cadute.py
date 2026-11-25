"""
tests/test_marchio_cadute.py
============================
Un bot con marchio che cade non riparte subito ogni volta: pause crescenti, e dopo troppe cadute di fila si spegne
e l'owner lo sa. Un client che resta su a lungo riparte da zero; uno fermato a mano non conta come caduta.
Funzioni coperte: consiglio 25/11/2026, seri di stabilità (blocco C)
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from core import whitelabel_bot as wb


class _Repo:
    def __init__(self):
        self.stati = []
        self.abilitato = True

    async def imposta_stato(self, guild_id, stato, dettaglio=None):
        self.stati.append(stato)

    async def imposta_abilitato(self, guild_id, valore):
        self.abilitato = valore


@pytest.fixture
def scena(monkeypatch):
    repo = _Repo()
    monkeypatch.setattr(wb, "whitelabel_repo", repo)
    orologio = {"t": 1000.0}
    monkeypatch.setattr(wb.time, "monotonic", lambda: orologio["t"])
    avvisi = []
    import core.avvisi_owner as ao

    monkeypatch.setattr(ao.avvisi_owner, "caduto", lambda bot, nome, det="": avvisi.append(nome))
    return wb.GestoreMarchio(SimpleNamespace()), repo, orologio, avvisi


async def test_le_pause_crescono_a_ogni_caduta(scena):
    gestore, repo, orologio, _ = scena
    attese = []
    for _ in range(4):
        gestore._avviato_il[1] = orologio["t"]
        await gestore._dopo_caduta(1)
        attese.append(gestore._riprova_dopo[1] - orologio["t"])
    assert attese == [5.0, 10.0, 20.0, 40.0]


async def test_in_pausa_non_riparte(scena):
    gestore, *_ = scena
    gestore._riprova_dopo[1] = 2000.0
    # `_avvia` esce prima di creare il client: con pausa attiva e tutto il resto a posto torna False.
    import core.premium as premium

    async def si(*a, **k):
        return True

    premium.guild_has_premium_access, vera = si, premium.guild_has_premium_access
    try:
        from unittest.mock import AsyncMock

        wb.whitelabel_repo.get_con_token = AsyncMock(return_value=(SimpleNamespace(enabled=True, status_text=None, application_id=1), "t"))
        assert await gestore._avvia(1) is False
        assert 1 not in gestore._client
    finally:
        premium.guild_has_premium_access = vera


async def test_dopo_troppe_cadute_si_spegne_e_si_avvisa(scena):
    gestore, repo, orologio, avvisi = scena
    for _ in range(wb.MAX_CADUTE_DI_FILA):
        gestore._avviato_il[1] = orologio["t"]
        await gestore._dopo_caduta(1)
    assert repo.abilitato is False and avvisi == ["marchio:1"]


async def test_un_client_rimasto_su_a_lungo_azzera_la_serie(scena):
    gestore, _, orologio, _ = scena
    for _ in range(3):
        gestore._avviato_il[1] = orologio["t"]
        await gestore._dopo_caduta(1)
    gestore._avviato_il[1] = orologio["t"]
    orologio["t"] += wb.STABILE_DOPO_SECONDI + 1
    await gestore._dopo_caduta(1)
    assert gestore._errori_di_fila[1] == 1


async def test_il_client_che_si_chiude_da_solo_e_una_caduta_ma_uno_fermato_a_mano_no(scena):
    gestore, repo, orologio, _ = scena

    class _Client:
        def __init__(self):
            self.chiuso = asyncio.Event()

        async def start(self, token):
            await self.chiuso.wait()

    da_solo = _Client()
    gestore._client[1] = da_solo
    da_solo.chiuso.set()
    await gestore._esegui(1, da_solo, "t")
    assert gestore._errori_di_fila.get(1) == 1

    voluto = _Client()
    gestore._client[2] = voluto
    voluto.chiuso.set()
    gestore._client.pop(2)  # `ferma` lo toglie prima di chiuderlo
    await gestore._esegui(2, voluto, "t")
    assert 2 not in gestore._errori_di_fila
