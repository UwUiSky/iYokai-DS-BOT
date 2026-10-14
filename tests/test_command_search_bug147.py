"""
tests/test_command_search_bug147.py
===================================
Correzioni dal cacciatore-bug su #147: cache degli ID senza blocchi, livelli per
singolo comando (`@richiedi`) sull'albero vero, guild_id, query di soli spazi,
defer prima delle chiamate lente.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from cogs.utility import command_search as modulo
from cogs.utility.command_search import CommandSearchCog
from core import command_search_logic as L
from core.command_access import Livello, richiedi
from core.command_groups import costruisci_gruppi
from tests.support.discord_fakes import fake_interaction
from tests.support.full_tree import build_full_bot, close_full_bot, connect_db_if_needed


class _C:
    def __init__(self, nome, id_):
        self.name, self.id = nome, id_


async def test_fetch_lenta_non_blocca_gli_altri_ne_supera_il_timeout():
    async def lenta():
        await asyncio.sleep(5)
        return [_C("fun", 1)]

    cache = L.CacheIdComandi(ttl=3600, attesa_minima=0, timeout=0.2)
    inizio = time.monotonic()
    ids = await asyncio.gather(cache.ottieni(lenta), cache.ottieni(lenta), cache.ottieni(lenta))
    assert time.monotonic() - inizio < 1.0
    assert ids == [{}, {}, {}]


async def test_cache_piena_non_aspetta_una_fetch_lenta_in_corso():
    stato = {"lenta": False}
    orologio = [0.0]

    async def fetch():
        if stato["lenta"]:
            await asyncio.sleep(5)
        return [_C("fun", 1)]

    cache = L.CacheIdComandi(ttl=10, attesa_minima=0, timeout=0.2, orologio=lambda: orologio[0])
    await cache.ottieni(fetch)
    stato["lenta"] = True
    orologio[0] = 11.0  # scaduta: parte la fetch lenta, scade il timeout
    await cache.ottieni(fetch)
    inizio = time.monotonic()
    assert await cache.ottieni(fetch) == {"fun": 1}
    assert time.monotonic() - inizio < 1.0


async def test_errore_di_discord_tiene_i_vecchi_id_e_riprova_dopo_l_attesa():
    stato = {"rompi": False, "n": 0}
    orologio = [0.0]

    async def fetch():
        stato["n"] += 1
        if stato["rompi"]:
            raise RuntimeError("giù")
        return [_C("fun", 2)]

    cache = L.CacheIdComandi(ttl=10, attesa_minima=60, timeout=1, orologio=lambda: orologio[0])
    await cache.ottieni(fetch)
    stato["rompi"] = True
    orologio[0] = 11.0
    assert await cache.ottieni(fetch) == {"fun": 2}  # errore: vecchi ID, nessuna eccezione
    n = stato["n"]
    await cache.ottieni(fetch)
    assert stato["n"] == n  # non riprova prima di 60 s
    stato["rompi"] = False
    orologio[0] = 80.0
    await cache.ottieni(fetch)
    assert stato["n"] == n + 1


async def _cb(interaction):  # pragma: no cover
    pass


def _albero_con_richiedi() -> commands.Bot:
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    gruppi = costruisci_gruppi()
    aperto = app_commands.Command(name="aperto", description="Per tutti", callback=_cb)

    gruppi["fun"].add_command(aperto)
    gruppi["fun"].add_command(_con_richiedi("protetto", Livello.ADMIN))
    bot.tree.add_command(gruppi["fun"])
    bot.tree.add_command(_con_richiedi("solo-mod", Livello.MOD))  # primo livello
    return bot


def _con_richiedi(nome: str, livello: Livello) -> app_commands.Command:
    async def cb(interaction):  # pragma: no cover
        pass

    return richiedi(livello)(app_commands.Command(name=nome, description="d", callback=cb))


async def test_il_pannello_filtra_anche_i_richiedi_dei_singoli_comandi(monkeypatch):
    cog = CommandSearchCog(_albero_con_richiedi())

    async def solo_mod(interaction, livello):
        return livello is Livello.MOD

    monkeypatch.setattr(modulo, "puo_usare", solo_mod)
    visibili = {c.percorso for c in await cog._comandi_accessibili(fake_interaction())}
    assert visibili == {"fun aperto", "solo-mod"}


@pytest.mark.parametrize("consenti", [False, True])
async def test_albero_vero_nessun_comando_con_livello_negato_e_visibile(monkeypatch, consenti):
    creato = await connect_db_if_needed()
    bot, falliti = await build_full_bot()
    try:
        assert not falliti
        cog = CommandSearchCog(bot)
        chiesti = []

        async def puo(interaction, livello):
            chiesti.append(livello)
            return consenti

        monkeypatch.setattr(modulo, "puo_usare", puo)
        # NF-06: qui contano i livelli; i moduli del server hanno il loro test (test_command_search_bilingue).
        monkeypatch.setattr(modulo.db, "is_module_active_for_guild", AsyncMock(return_value=True))
        tutti = L.raccogli_comandi(bot.tree.get_commands())
        visibili = await cog._comandi_accessibili(fake_interaction())
        con_livello = [c for c in tutti if c.livelli]
        assert con_livello, "l'albero vero deve avere comandi con un livello"
        if consenti:
            assert len(visibili) == len(tutti)
        else:
            assert not any(c.livelli for c in visibili)
            assert {c.percorso for c in visibili} == {c.percorso for c in tutti if not c.livelli}
        assert len(chiesti) <= len(Livello)  # una domanda per livello, non per comando
    finally:
        await close_full_bot(bot)
        if creato:
            from core.database import db

            await db.close()


@pytest.fixture
def cog(monkeypatch):
    c = CommandSearchCog(_albero_con_richiedi())
    repo = MagicMock(ultimo=AsyncMock(return_value=None), registra=AsyncMock())
    monkeypatch.setattr(modulo, "command_usage_repo", repo)
    c.repo = repo
    monkeypatch.setattr(modulo, "puo_usare", AsyncMock(return_value=True))
    return c


async def test_usa_guild_id_anche_se_il_server_non_e_in_cache(cog):
    i = fake_interaction()
    i.guild = None
    i.guild_id = 4242
    cog.cache_ids.ottieni = AsyncMock(return_value={})
    await cog.search.callback(cog, i, query=None)
    cog.repo.ultimo.assert_awaited_once_with(4242, i.user.id)
    embed = i.followup.send.call_args.kwargs["embed"]
    assert "In privato" not in embed.description


async def test_listener_usa_guild_id(cog):
    c = MagicMock(spec=app_commands.Command)
    c.qualified_name = "fun aperto"
    i = fake_interaction()
    i.guild = None
    i.guild_id = 4242
    await cog.on_app_command_completion(i, c)
    cog.repo.registra.assert_awaited_once_with(4242, i.user.id, "fun aperto")


async def test_defer_prima_di_chiamare_discord(cog):
    ordine = []
    i = fake_interaction()
    i.guild_id = i.guild.id
    i.response.defer.side_effect = lambda **kw: ordine.append("defer")

    async def ids(fetch, serve=()):
        ordine.append("ids")
        return {}

    cog.cache_ids.ottieni = ids
    await cog.search.callback(cog, i, query=None)
    await cog.search.callback(cog, i, query="aperto")
    assert ordine[:2] == ["defer", "ids"]
    assert ordine[2:4] == ["defer", "ids"]
    assert i.followup.send.await_count == 2


@pytest.mark.parametrize("testo", [" ", "     "])
async def test_query_di_soli_spazi_e_rifiutata_con_messaggio(cog, testo):
    i = fake_interaction()
    i.guild_id = 1
    await cog.search.callback(cog, i, query=testo)
    i.response.send_message.assert_awaited_once()
    assert i.response.send_message.call_args.kwargs["ephemeral"] is True
    assert "parola" in i.response.send_message.call_args.args[0].lower()
    cog.repo.ultimo.assert_not_awaited()


async def test_chiedi_con_spazi_rifiuta_e_con_domanda_lunga_avvisa(cog):
    i = fake_interaction()
    i.guild_id = 1
    await cog.chiedi.callback(cog, i, domanda="   ")
    assert "parola" in i.response.send_message.call_args.args[0].lower()

    i = fake_interaction()
    i.guild_id = 1
    cog.cache_ids.ottieni = AsyncMock(return_value={})
    await cog.chiedi.callback(cog, i, domanda="aperto " * 40)
    assert "100" in i.followup.send.call_args.kwargs["content"]


async def test_chiedi_taglia_la_domanda_a_100_caratteri(cog):
    visti = []

    async def spia(interaction, query, nota=None):
        visti.append((query, nota))

    cog._ricerca = spia
    await cog.chiedi.callback(cog, fake_interaction(), domanda="x" * 150)
    assert len(visti[0][0]) == 100 and "100" in visti[0][1]
    await cog.chiedi.callback(cog, fake_interaction(), domanda="  breve  ")
    assert visti[1] == ("breve", None)


async def test_il_pannello_chiede_anche_l_id_del_gruppo_dell_ultimo_comando(cog):
    i = fake_interaction()
    i.guild_id = i.guild.id
    cog.repo.ultimo.return_value = "gruppoassente comando"  # non è tra i comandi visibili
    spia = AsyncMock(return_value={})
    cog.cache_ids.ottieni = spia
    await cog.search.callback(cog, i, query=None)
    assert "gruppoassente" in spia.call_args.args[1]


async def test_cog_load_pulisce_i_dati_vecchi(monkeypatch):
    repo = MagicMock(giorni=90, tetto=5, pulisci=AsyncMock(return_value=0))
    monkeypatch.setattr(modulo, "command_usage_repo", repo)
    await CommandSearchCog(_albero_con_richiedi()).cog_load()
    repo.pulisci.assert_awaited_once_with(90, 5)
    repo.pulisci.side_effect = RuntimeError("db non pronto")
    await CommandSearchCog(_albero_con_richiedi()).cog_load()  # non solleva
