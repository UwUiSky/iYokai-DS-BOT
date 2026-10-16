"""
tests/test_leveling_catalogo_r7.py
==================================
Voci del catalogo livelli ed economia (#124, #125): elenco pubblico di
ruoli-premio e moltiplicatori (LIV-048, LIV-027), pause attive (ECO-020),
registro degli ultimi 25 level-up (LIV-039). Database vero.
Funzioni coperte: SPEC §22.14
"""

from datetime import datetime, timedelta, timezone

import discord
import pytest

import cogs.leveling.leveling as modulo
from core.repositories.level_reward_repo import level_reward_repo
from core.repositories.leveling_repo import MAX_LEVEL_UP_REGISTRATI, LevelingRepository
from core.repositories.leveling_settings_repo import leveling_settings_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.moduli import attiva_livelli

GUILD = 100


@pytest.fixture
async def scena(monkeypatch, clean_db):
    await attiva_livelli(monkeypatch, clean_db, GUILD)
    repo = LevelingRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "leveling_repo", repo)
    leveling_settings_repo._cache.clear()
    cog = modulo.LevelingCog(bot=None)
    cog.cog_unload()
    yield cog, repo
    leveling_settings_repo._cache.clear()


def _interazione(user_id=1):
    return fake_interaction(guild=fake_guild(GUILD), user=fake_member(user_id, name=f"u{user_id}"))


# ---------------------------------------------------------------- LIV-039
@pytest.mark.asyncio
async def test_il_registro_tiene_solo_gli_ultimi_25_level_up(scena):
    _, repo = scena
    for livello in range(1, 31):
        await repo.registra_level_up(GUILD, 7, livello)
    await repo.registra_level_up(GUILD + 1, 8, 99)  # un altro server non conta

    ultimi = await repo.ultimi_level_up(GUILD)

    assert len(ultimi) == MAX_LEVEL_UP_REGISTRATI
    assert [livello for _, livello, _ in ultimi][:2] == [30, 29]
    assert ultimi[-1][1] == 6


@pytest.mark.asyncio
async def test_il_level_up_annunciato_entra_nel_registro_e_nel_comando(scena):
    cog, repo = scena
    membro = fake_member(5, name="u5")
    # Annuncio spento: il registro si riempie lo stesso.
    impostazioni = modulo.LevelingSettings(levelup_mode="spento")
    await cog._annuncia_level_up(membro, fake_guild(GUILD), None, 4, impostazioni)
    interazione = _interazione()

    await cog.livelli_recenti.callback(cog, interazione)

    embed = interazione.response.send_message.await_args.kwargs["embed"]
    assert "<@5>" in embed.description and "**4**" in embed.description


@pytest.mark.asyncio
async def test_livelli_recenti_vuoto(scena):
    cog, _ = scena
    interazione = _interazione()
    await cog.livelli_recenti.callback(cog, interazione)
    assert interazione.response.send_message.await_args.kwargs["ephemeral"] is True


# ---------------------------------------------------------- LIV-048, 027
@pytest.mark.asyncio
async def test_premi_elenca_ruoli_premio_e_moltiplicatori(scena):
    cog, _ = scena
    await level_reward_repo.add_reward(GUILD, 10, 555)
    await leveling_settings_repo.set_rule(GUILD, "mult_canale", 777, 2.0)
    interazione = _interazione()

    await cog.premi.callback(cog, interazione)

    invio = interazione.response.send_message.await_args
    testo = invio.kwargs["embed"].description
    assert "Livello **10** → <@&555>" in testo
    assert "×2 in <#777>" in testo
    assert invio.kwargs.get("ephemeral") is False


@pytest.mark.asyncio
async def test_premi_senza_nulla_lo_dice(scena):
    cog, _ = scena
    interazione = _interazione()
    await cog.premi.callback(cog, interazione)
    assert interazione.response.send_message.await_args.kwargs["ephemeral"] is True


# ---------------------------------------------------------------- ECO-020
@pytest.mark.asyncio
async def test_attese_mostra_daily_in_attesa_e_work_disponibile(scena):
    cog, repo = scena
    adesso = datetime.now(timezone.utc)
    await repo.claim_daily(GUILD, 1, 10, modulo.DAILY_COOLDOWN_SECONDS, adesso - timedelta(hours=1))
    interazione = _interazione()

    await cog.attese.callback(cog, interazione)

    testo = interazione.response.send_message.await_args.args[0]
    righe = testo.splitlines()
    assert righe[0].startswith("**Daily**: tra 22h") or righe[0].startswith("**Daily**: tra 23h")
    assert righe[1] == "**Work**: disponibile ora"
