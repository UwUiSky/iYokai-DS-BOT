"""Ruoli per suono (#131, B11, FUN-076): regole pure, tetto di 20, controllo in /music suono, comando admin."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import cogs.fun.soundboard as modulo
from core.repositories.suoni_ruoli_repo import suoni_ruoli_repo
from core.suoni_ruoli_logic import MAX_RUOLI_PER_SUONO, puo_suonare
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.percorsi import comando_nel_gruppo, percorsi_del_gruppo

G = 505


def test_regole_pure():
    assert puo_suonare([], set())
    assert puo_suonare([(1, "consenti")], {1}) and not puo_suonare([(1, "consenti")], {2})
    assert not puo_suonare([(1, "vieta")], {1}) and puo_suonare([(1, "vieta")], {2})
    assert not puo_suonare([(1, "consenti"), (2, "vieta")], {1, 2})  # il divieto vince
    assert puo_suonare([(1, "consenti"), (2, "consenti")], {2})
    assert puo_suonare([(1, "consenti")], set(), amministratore=True)


async def test_albero_ha_suono_ruoli_nel_gruppo_admin_musica():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await modulo.setup(bot)
    assert "suono-ruoli" in percorsi_del_gruppo("admin-musica")
    comando_nel_gruppo("admin-musica", "suono-ruoli").to_dict(bot.tree)


@pytest.fixture
async def repo(monkeypatch, clean_db):
    import core.database as dm
    monkeypatch.setattr(dm.db, "_pool", clean_db)
    return suoni_ruoli_repo


async def test_repo_imposta_cambia_togli_e_tetto(repo):
    assert await repo.imposta(G, "s:1", 10, "consenti") == "ok"
    assert await repo.imposta(G, "s:1", 10, "vieta") == "ok"  # cambia modo, non conta due volte
    assert await repo.regole(G, "s:1") == [(10, "vieta")]
    for i in range(1, MAX_RUOLI_PER_SUONO):
        assert await repo.imposta(G, "s:1", 100 + i, "consenti") == "ok"
    assert await repo.imposta(G, "s:1", 999, "consenti") == "tetto"
    assert await repo.imposta(G, "s:1", 101, "vieta") == "ok"  # uno già in elenco si può cambiare
    assert await repo.imposta(G, "s:2", 999, "consenti") == "ok"  # il tetto è per suono
    assert await repo.togli(G, "s:1", 10) is True and await repo.togli(G, "s:1", 10) is False


async def test_tetto_regge_a_richieste_insieme(repo):
    await asyncio.gather(*(repo.imposta(G, "s:9", 1000 + i, "consenti") for i in range(MAX_RUOLI_PER_SUONO + 5)))
    assert len(await repo.regole(G, "s:9")) == MAX_RUOLI_PER_SUONO


async def test_ruolo_cancellato_esce_da_tutti_i_suoni(repo):
    await repo.imposta(G, "s:1", 7, "consenti")
    await repo.imposta(G, "s:2", 7, "vieta")
    await repo.imposta(G, "s:2", 8, "vieta")
    cog = modulo.SoundboardCog(SimpleNamespace())
    await cog.on_guild_role_delete(SimpleNamespace(id=7, guild=SimpleNamespace(id=G)))
    assert await repo.regole(G, "s:1") == [] and await repo.regole(G, "s:2") == [(8, "vieta")]


def _cog():
    cog = modulo.SoundboardCog(SimpleNamespace())
    cog._predefiniti = [SimpleNamespace(id=1, name="Grillo", emoji=None)]
    return cog


def _ruolo(i, default=False):
    r = MagicMock(spec=discord.Role)
    r.id, r.mention = i, f"<@&{i}>"
    r.is_default.return_value = default
    return r


async def test_comando_admin_consenti_vieta_mostra_togli(repo):
    cog = _cog()
    it = fake_interaction(guild=fake_guild(G), user=fake_member(1, "a"))
    scelta = lambda v: SimpleNamespace(value=v, name=v)
    await cog.suono_ruoli.callback(cog, it, "Grillo", scelta("consenti"), _ruolo(50))
    await cog.suono_ruoli.callback(cog, it, "d:1", scelta("vieta"), _ruolo(51))
    assert await repo.regole(G, "d:1") == [(50, "consenti"), (51, "vieta")]
    await cog.suono_ruoli.callback(cog, it, "d:1", scelta("mostra"), None)
    elenco = it.followup.send.await_args.args[0]
    assert "<@&50>" in elenco and "<@&51>" in elenco
    assert it.followup.send.await_args.kwargs["allowed_mentions"].roles is False
    await cog.suono_ruoli.callback(cog, it, "d:1", scelta("togli"), _ruolo(50))
    assert await repo.regole(G, "d:1") == [(51, "vieta")]
    # @everyone, ruolo mancante, suono sconosciuto: nessuna scrittura
    await cog.suono_ruoli.callback(cog, it, "d:1", scelta("vieta"), _ruolo(G, default=True))
    await cog.suono_ruoli.callback(cog, it, "d:1", scelta("vieta"), None)
    await cog.suono_ruoli.callback(cog, it, "boh", scelta("vieta"), _ruolo(52))
    assert await repo.regole(G, "d:1") == [(51, "vieta")]


async def test_music_suono_blocca_chi_non_ha_il_ruolo(repo, monkeypatch):
    from tests.test_soundboard_play import _cog as cog_di_prova, _interazione, _Musica, _WorkerGuild, _CanaleVoce

    player = SimpleNamespace(channel=_CanaleVoce(), playing=True)
    cog, suono_server, _ = cog_di_prova(_Musica(_WorkerGuild(player=player)), monkeypatch)
    monkeypatch.setattr(modulo, "suoni_ruoli_repo", repo)
    await repo.imposta(1, "s:5", 77, "consenti")
    it, testi = _interazione([suono_server])
    it.user.roles = [SimpleNamespace(id=1)]
    it.user.guild_permissions = SimpleNamespace(administrator=False)
    await cog.suono.callback(cog, it, nome="s:5")
    assert player.channel.suoni == [] and testi
    it.user.roles = [SimpleNamespace(id=77)]
    await cog.suono.callback(cog, it, nome="s:5")
    assert player.channel.suoni == [suono_server]
    for task in list(cog._task):
        task.cancel()
