"""
tests/test_leveling_classifica_e_calcolo.py
===========================================
LIV-063 (classifica fino a 100 posizioni, a pagine), LIV-074 (quanti messaggi
mancano a un livello) ed ECO-016 (posizione in classifica accanto al saldo).
Funzioni coperte: SPEC §15 (catalogo #124 e #125)
"""

from types import SimpleNamespace

import pytest

import cogs.leveling.leveling as modulo
from core.leveling_logic import stima_per_livello, xp_for_level
from core.repositories.leveling_repo import LevelingRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.moduli import attiva_livelli

GUILD = 100


# ----------------------------------------------------------------------
# Logica pura
# ----------------------------------------------------------------------
def test_stima_per_livello():
    stima = stima_per_livello(
        xp_attuale=0, livello_obiettivo=2, xp_per_messaggio=15, attesa_secondi=60, xp_voce_minuto=5
    )
    assert stima.xp_mancanti == xp_for_level(2)  # 5*4 + 50*2 = 120
    assert stima.messaggi == 8  # 120 / 15
    assert stima.minuti_vocale == 24  # 120 / 5
    assert stima.secondi_minimi_testo == 8 * 60


def test_stima_con_xp_gia_sufficienti_non_chiede_nulla():
    stima = stima_per_livello(10**6, 5, 15, 60, 5)
    assert (stima.xp_mancanti, stima.messaggi, stima.minuti_vocale) == (0, 0, 0)


def test_stima_senza_xp_vocale_non_divide_per_zero():
    assert stima_per_livello(0, 3, 15, 60, 0).minuti_vocale is None


# ----------------------------------------------------------------------
# Archivio: posizione per coin
# ----------------------------------------------------------------------
@pytest.fixture
def repo(clean_db):
    return LevelingRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_posizione_per_coin(repo):
    await repo.add_coins(GUILD, 1, 300)
    await repo.add_coins(GUILD, 2, 500)
    await repo.add_coins(GUILD, 3, 300)
    await repo.add_coins(GUILD + 1, 4, 9999)  # altro server
    assert await repo.get_coins_position(GUILD, 2) == 1
    assert await repo.get_coins_position(GUILD, 1) == 2
    assert await repo.get_coins_position(GUILD, 3) == 2  # a pari coin, stessa posizione
    assert await repo.get_coins_position(GUILD, 99) is None


# ----------------------------------------------------------------------
# Comandi
# ----------------------------------------------------------------------
@pytest.fixture
async def scena(monkeypatch, clean_db):
    from core.command_groups import costruisci_gruppi, registra_comandi_del_cog
    from core.repositories.leveling_settings_repo import leveling_settings_repo

    await attiva_livelli(monkeypatch, clean_db, GUILD)
    monkeypatch.setattr(leveling_settings_repo, "_pool_provider", lambda: clean_db)
    leveling_settings_repo._cache = type(leveling_settings_repo._cache)(max_size=100)
    monete = LevelingRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "leveling_repo", monete)
    cog = modulo.LevelingCog(bot=None)
    cog.cog_unload()
    comandi = {
        c.qualified_name: c
        for c in registra_comandi_del_cog(cog, gruppi=costruisci_gruppi(), tree=None)
    }
    return SimpleNamespace(cog=cog, comandi=comandi, monete=monete, impostazioni=leveling_settings_repo)


def _interazione(user_id=1):
    return fake_interaction(guild=fake_guild(GUILD), user=fake_member(user_id, name=f"u{user_id}"))


def _scelta(valore, nome=None):
    return SimpleNamespace(value=valore, name=nome or valore)


@pytest.mark.asyncio
async def test_la_classifica_arriva_a_100_posizioni_a_pagine(scena):
    for utente in range(1, 61):
        await scena.monete.add_coins(GUILD, utente, 1000 - utente)
    interazione = _interazione()

    await scena.comandi["level leaderboard"].callback(
        scena.cog, interazione, metric=_scelta("coins", "Coin"), period=_scelta("alltime", "Di sempre"),
        posizioni=100,
    )

    chiamata = interazione.response.send_message.await_args
    assert chiamata.kwargs["view"] is not None  # più pagine
    prima = chiamata.kwargs["embed"].description
    assert "<@1>" in prima and len(prima) < 4096


@pytest.mark.asyncio
async def test_la_classifica_di_base_resta_di_dieci(scena):
    for utente in range(1, 31):
        await scena.monete.add_coins(GUILD, utente, 1000 - utente)
    interazione = _interazione()
    await scena.comandi["level leaderboard"].callback(
        scena.cog, interazione, metric=_scelta("coins", "Coin"), period=_scelta("alltime", "Di sempre"),
    )
    embed = interazione.response.send_message.await_args.kwargs["embed"]
    assert embed.description.count("<@") == 10


@pytest.mark.asyncio
async def test_balance_mostra_la_posizione(scena):
    await scena.monete.add_coins(GUILD, 1, 100)
    await scena.monete.add_coins(GUILD, 2, 900)
    interazione = _interazione()
    await scena.comandi["level balance"].callback(scena.cog, interazione, member=None)
    testo = interazione.response.send_message.await_args.args[0]
    assert "100" in testo and "#2" in testo


@pytest.mark.asyncio
async def test_calcola_usa_i_numeri_del_server(scena):
    await scena.impostazioni.set_options(GUILD, text_xp=20, text_cooldown_seconds=30, voice_xp_per_minute=10)
    interazione = _interazione()
    await scena.comandi["level calcola"].callback(scena.cog, interazione, livello=2, member=None)
    embed = interazione.response.send_message.await_args.kwargs["embed"]
    testo = embed.description
    assert str(xp_for_level(2)) in testo
    assert "**6** messaggi" in testo  # 120 XP / 20
    assert "**12** minuti" in testo  # 120 XP / 10


@pytest.mark.asyncio
async def test_calcola_oltre_il_livello_massimo_e_rifiutato(scena):
    await scena.impostazioni.set_options(GUILD, max_level=10)
    interazione = _interazione()
    await scena.comandi["level calcola"].callback(scena.cog, interazione, livello=11, member=None)
    assert "livello massimo" in interazione.response.send_message.await_args.args[0].lower()
