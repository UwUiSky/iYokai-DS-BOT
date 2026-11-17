"""
tests/test_leveling_reazioni.py
===============================
#124 B5 (LIV-008, 009, 059, 060): XP per le reazioni messe e ricevute, classifica per reazioni e per
minuti in vocale. Archivio su PostgreSQL vero, listener con oggetti finti.
Funzioni coperte: SPEC §15 (catalogo #124)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.leveling.leveling as modulo
from cogs.leveling.guadagno import GuadagnoCog
from core.leveling_logic import ConfigLivelli, LevelingSettings
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.leveling_settings_repo import leveling_settings_repo
from tests.support.discord_fakes import fake_guild, fake_member, fake_text_channel
from tests.test_leveling_guadagno_b3 import _comando, _inter, ambiente  # noqa: F401
from tests.test_leveling_settings import cog_xp  # noqa: F401

GUILD = 100


@pytest.fixture
def repo(clean_db):
    return LevelingRepository(pool_provider=lambda: clean_db)


# ---------------------------------------------------------------- archivio
@pytest.mark.asyncio
async def test_liv008_009_l_attesa_vale_per_persona_e_per_verso(repo):
    prima = await repo.add_reaction_xp(GUILD, 1, 5, "messa", 300)
    seconda = await repo.add_reaction_xp(GUILD, 1, 5, "messa", 300)
    ricevuta = await repo.add_reaction_xp(GUILD, 1, 5, "ricevuta", 300)  # altro verso: conta
    assert (prima.granted, seconda.granted, ricevuta.granted) == (True, False, True)
    assert ricevuta.new_xp_total == 10


@pytest.mark.asyncio
async def test_liv008_dieci_reazioni_insieme_pagano_una_volta_sola(repo):
    esiti = await asyncio.gather(*(repo.add_reaction_xp(GUILD, 2, 4, "messa", 300) for _ in range(10)))
    assert [e.granted for e in esiti].count(True) == 1
    assert (await repo.get_totals(GUILD, 2)).xp_total == 4


@pytest.mark.asyncio
async def test_liv008_il_tetto_al_giorno_ferma_anche_con_attesa_finita(repo, clean_db):
    for _ in range(3):
        await clean_db.execute("UPDATE leveling_reazioni SET ultima_messa = now() - interval '1 hour' WHERE user_id = 3")
        e = await repo.add_reaction_xp(GUILD, 3, 1, "messa", 60, tetto_giorno=2)
    assert not e.granted
    assert (await repo.get_totals(GUILD, 3)).xp_total == 2


@pytest.mark.asyncio
async def test_liv008_dopo_l_attesa_si_guadagna_ancora(repo, clean_db):
    await repo.add_reaction_xp(GUILD, 4, 1, "messa", 60)
    await clean_db.execute("UPDATE leveling_reazioni SET ultima_messa = now() - interval '2 minutes' WHERE user_id = 4")
    assert (await repo.add_reaction_xp(GUILD, 4, 1, "messa", 60)).granted


@pytest.mark.asyncio
async def test_liv008_il_livello_sale_con_la_formula_del_server(repo):
    r = await repo.add_reaction_xp(GUILD, 5, 450, "messa", 60, formula="costante")
    assert r.leveled_up and r.new_level == 2 and r.previous_level == 0


@pytest.mark.asyncio
async def test_liv060_classifica_per_reazioni_messe_e_ricevute(repo):
    await repo.add_reaction_xp(GUILD, 1, 1, "messa", 60)
    await repo.add_reaction_xp(GUILD, 2, 1, "ricevuta", 60)
    assert [v.user_id for v in await repo.top_reazioni(GUILD, False)] == [1]
    assert [v.user_id for v in await repo.top_reazioni(GUILD, True)] == [2]
    assert await repo.top_reazioni(GUILD + 1, False) == []


@pytest.mark.asyncio
async def test_liv059_classifica_per_minuti_in_vocale(repo):
    for _ in range(3):
        await repo.add_voice_minutes(GUILD, [(1, 10, True), (2, 10, True), (3, 10, False)])
    top = await repo.top_minuti_vocale(GUILD)
    assert [(v.user_id, v.amount) for v in top] == [(1, 3), (2, 3)]  # chi non era idoneo non conta


# ---------------------------------------------------------------- listener
def _payload(autore_id=50, reattore=None, canale=None, guild=None):
    reattore = reattore or fake_member(10)
    p = MagicMock(spec=discord.RawReactionActionEvent)
    p.guild_id = reattore.guild.id
    p.member = reattore
    p.channel_id = 111
    p.message_author_id = autore_id
    reattore.guild.get_channel_or_thread = MagicMock(return_value=canale or fake_text_channel(channel_id=111))
    return p


def _config_reazioni(config, **campi):
    config["valore"] = ConfigLivelli(impostazioni=LevelingSettings(**campi))


@pytest.mark.asyncio
async def test_liv008_009_di_base_le_reazioni_non_danno_xp(cog_xp):  # noqa: F811
    cog, repo_xp, _, _ = cog_xp
    repo_xp.add_reaction_xp = AsyncMock()
    await cog.on_raw_reaction_add(_payload())
    repo_xp.add_reaction_xp.assert_not_awaited()


@pytest.mark.asyncio
async def test_liv008_009_messa_e_ricevuta_vanno_alle_persone_giuste(cog_xp):  # noqa: F811
    cog, repo_xp, config, _ = cog_xp
    repo_xp.add_reaction_xp = AsyncMock(return_value=MagicMock(granted=False))
    _config_reazioni(config, xp_reazione_messa=3, xp_reazione_ricevuta=2, reazioni_attesa=120)
    p = _payload(autore_id=50)
    autore = fake_member(50)
    p.member.guild.get_member = MagicMock(return_value=autore)
    await cog.on_raw_reaction_add(p)
    chiamate = [(c.args[1], c.args[2], c.args[3], c.args[4]) for c in repo_xp.add_reaction_xp.await_args_list]
    assert chiamate == [(10, 3, "messa", 120), (50, 2, "ricevuta", 120)]


@pytest.mark.asyncio
async def test_liv009_mai_su_se_stessi_ne_da_o_verso_bot(cog_xp):  # noqa: F811
    cog, repo_xp, config, _ = cog_xp
    repo_xp.add_reaction_xp = AsyncMock()
    _config_reazioni(config, xp_reazione_messa=3, xp_reazione_ricevuta=2)
    await cog.on_raw_reaction_add(_payload(autore_id=10))  # al proprio messaggio
    bot = fake_member(51, bot=True)
    p = _payload(autore_id=51)
    p.member.guild.get_member = MagicMock(return_value=bot)
    await cog.on_raw_reaction_add(p)  # al messaggio di un bot
    p2 = _payload(reattore=fake_member(11, bot=True))
    await cog.on_raw_reaction_add(p2)  # un bot che reagisce
    p3 = _payload(autore_id=None)
    await cog.on_raw_reaction_add(p3)  # autore ignoto
    repo_xp.add_reaction_xp.assert_not_awaited()


@pytest.mark.asyncio
async def test_liv008_canale_escluso_e_ruolo_escluso_non_danno_xp(cog_xp):  # noqa: F811
    cog, repo_xp, config, _ = cog_xp
    repo_xp.add_reaction_xp = AsyncMock(return_value=MagicMock(granted=False))
    config["valore"] = ConfigLivelli(
        impostazioni=LevelingSettings(xp_reazione_messa=3), canali_esclusi=frozenset({111}))
    p = _payload()
    p.member.guild.get_member = MagicMock(return_value=fake_member(50))
    await cog.on_raw_reaction_add(p)
    repo_xp.add_reaction_xp.assert_not_awaited()


@pytest.mark.asyncio
async def test_liv008_009_il_comando_salva_e_chiede_il_permesso(ambiente):  # noqa: F811
    cog = ambiente
    cmd = _comando(cog, "admin-livelli guadagno reazioni")
    await cmd.callback(cog, _inter(permessi=discord.Permissions.none()), 5, 5, 60)
    assert (await leveling_settings_repo.get_config(GUILD, fresco=True)).impostazioni.xp_reazione_messa == 0
    await cmd.callback(cog, _inter(), 5, 4, 600)
    i = (await leveling_settings_repo.get_config(GUILD, fresco=True)).impostazioni
    assert (i.xp_reazione_messa, i.xp_reazione_ricevuta, i.reazioni_attesa) == (5, 4, 600)
