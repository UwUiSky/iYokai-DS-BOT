"""
tests/test_stipendi_b9.py
=========================
Stipendi per ruolo, tasse, giro automatico e monete per messaggio (#125 B9): ECO-033, 034, 035, 036, 037, 038.
Funzioni coperte: catalogo #125
"""

import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import discord
import pytest

from cogs.leveling.stipendi import StipendiCog
from core.repositories.guild_chest_repo import GuildChestRepository
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.leveling_settings_repo import LevelingSettingsRepository
from core.repositories.rischio_repo import RischioRepository
from core.repositories.stipendi_repo import EsitoRiscossione, StipendiRepository
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.moduli import attiva_livelli

G = 100


@pytest.fixture
def r(clean_db):
    return SimpleNamespace(
        s=StipendiRepository(pool_provider=lambda: clean_db), lev=LevelingRepository(pool_provider=lambda: clean_db),
        imp=LevelingSettingsRepository(pool_provider=lambda: clean_db), rk=RischioRepository(pool_provider=lambda: clean_db),
        cassa=GuildChestRepository(pool_provider=lambda: clean_db), pool=clean_db,
    )


@pytest.mark.asyncio
async def test_imposta_limiti_e_valori(r):
    for brutto in (0, 100_001, -100_001):
        with pytest.raises(ValueError):
            await r.s.imposta(G, 1, brutto, False)
    for ruolo in range(10):
        assert await r.s.imposta(G, ruolo, 10, False) is True
    assert await r.s.imposta(G, 99, 10, False) is False  # l'11° no
    assert await r.s.imposta(G, 3, 20, True) is True  # ma si può cambiare uno esistente
    assert await r.s.rimuovi(G, 3) and not await r.s.rimuovi(G, 3)
    assert len(await r.s.elenco(G)) == 9


@pytest.mark.asyncio
async def test_riscossione_contanti_banca_tassa_e_pausa(r):
    await r.s.imposta(G, 1, 100, False)
    await r.s.imposta(G, 2, 50, True)
    await r.s.imposta(G, 3, -500, False)
    await r.lev.add_coins(G, 7, 30)
    x = await r.s.riscuoti(G, 7, [1, 2, 3, 77])
    assert (x.esito, x.contanti, x.banca, x.tassa) == (EsitoRiscossione.FATTO, 100, 50, 130)  # tassa 500 ma ha solo 130
    b = await r.rk.banca(G, 7)
    assert (b.contanti, b.banca) == (0, 50)
    assert await r.cassa.get_balance(G) == 130
    assert (await r.s.riscuoti(G, 7, [1])).esito is EsitoRiscossione.PAUSA
    assert (await r.s.riscuoti(G, 8, [77])).esito is EsitoRiscossione.NESSUNO


@pytest.mark.asyncio
async def test_riscossione_insieme_paga_una_volta_e_rispetta_il_tetto(r):
    await r.s.imposta(G, 1, 100, False)
    await apri_connessioni(r.pool, 4)
    esiti = await asyncio.gather(*[r.s.riscuoti(G, 7, [1]) for _ in range(4)])
    assert [e.esito for e in esiti].count(EsitoRiscossione.FATTO) == 1
    assert (await r.lev.get_totals(G, 7)).coins_total == 100
    await r.imp.set_options(G, tetto_saldo=150)
    await r.s.riscuoti(G, 8, [1], 1)
    assert (await r.lev.get_totals(G, 8)).coins_total == 100


@pytest.mark.asyncio
async def test_giro_automatico_una_volta_al_giorno_per_server(r):
    d = date(2026, 11, 18)
    esiti = await asyncio.gather(*[r.s.giro_automatico(G, d) for _ in range(3)])
    assert esiti.count(True) == 1
    assert await r.s.giro_automatico(G, date(2026, 11, 19)) is True and await r.s.giro_automatico(G + 1, d) is True


@pytest.mark.asyncio
async def test_monete_per_messaggio_con_tetto_giornaliero(r):
    d = date(2026, 11, 18)
    assert await r.s.monete_messaggio(G, 1, d, 5, 12) == 5
    assert await r.s.monete_messaggio(G, 1, d, 5, 12) == 5
    assert await r.s.monete_messaggio(G, 1, d, 5, 12) == 0  # 15 > 12
    assert await r.s.monete_messaggio(G, 1, date(2026, 11, 19), 5, 12) == 5
    assert await r.s.monete_messaggio(G, 2, d, 20, 12) == 0  # un messaggio più grande del tetto non passa
    assert (await r.lev.get_totals(G, 2)).coins_total == 0
    assert (await r.lev.get_totals(G, 1)).coins_total == 15
    await apri_connessioni(r.pool, 6)
    dati = await asyncio.gather(*[r.s.monete_messaggio(G, 3, d, 5, 12) for _ in range(6)])
    assert sorted(dati) == [0, 0, 0, 0, 5, 5]
    assert await r.s.aggiungi_canale(G, 5) and await r.s.canali_monete(G) == {5}
    for c in range(100, 124):
        await r.s.aggiungi_canale(G, c)
    assert await r.s.aggiungi_canale(G, 999) is False
    await r.s.togli_canale(G, 5)
    assert 5 not in await r.s.canali_monete(G)


def _msg(uid, canale=5, bot=False):
    m = MagicMock()
    m.guild = fake_guild(G)
    m.author = fake_member(uid, bot=bot)
    m.channel = MagicMock(id=canale)
    m.type = discord.MessageType.default
    return m


@pytest.mark.asyncio
async def test_ascolto_solo_canali_scelti_pausa_e_bot(monkeypatch, clean_db, r):
    await attiva_livelli(monkeypatch, clean_db, G)
    import cogs.leveling.stipendi as modulo
    monkeypatch.setattr(modulo, "stipendi_repo", r.s)
    cog = StipendiCog(bot=MagicMock(guilds=[]))
    cog._giro.cancel()
    await r.s.aggiungi_canale(G, 5)
    await r.imp.set_options(G, msg_coins=4, msg_coins_pausa=60)
    from core.repositories.leveling_settings_repo import leveling_settings_repo
    leveling_settings_repo._cache.clear()
    await cog.on_message(_msg(1))
    await cog.on_message(_msg(1))  # in pausa
    await cog.on_message(_msg(2, bot=True))
    await cog.on_message(_msg(3, canale=6))
    assert [(await r.lev.get_totals(G, u)).coins_total for u in (1, 2, 3)] == [4, 0, 0]
    leveling_settings_repo._cache.clear()
