"""B28: sync d'avvio con i comandi del server montati prima; nomi riservati; _monta che non si rompe."""
import discord
import pytest
from discord import app_commands
from discord.ext import commands
from unittest.mock import AsyncMock

import cogs.utility.slash_server as modulo
from cogs.utility.slash_server import SlashServerCog, monta_per_avvio
from core import slash_server_logic as L
from core.command_sync import SCOPE_GLOBALE, impronta_albero_tradotto, scope_guild, sincronizza_all_avvio
from tests.test_slash_server_cog import G, RepoFinto

MAIN = 4242  # lo stesso server dei comandi del test


class StatoFinto:
    def __init__(self, dati=None):
        self.dati = dict(dati or {})

    async def leggi(self, scope):
        return self.dati.get(scope)

    async def salva(self, scope, impronta):
        self.dati[scope] = impronta


def _bot_con_cog(monkeypatch):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    gruppo = app_commands.Group(name="owner", description="x")

    @gruppo.command(name="stato", description="x")
    async def _s(interaction: discord.Interaction) -> None: ...

    bot.tree.add_command(gruppo, guild=discord.Object(id=MAIN))
    cog = SlashServerCog(bot)
    repo = RepoFinto()
    monkeypatch.setattr(modulo, "slash_server_repo", repo)
    return bot, cog, repo


async def test_sync_d_avvio_nel_server_main_ha_owner_e_comandi_del_server(monkeypatch):
    bot, cog, repo = _bot_con_cog(monkeypatch)
    await bot.add_cog(cog)
    await repo.pubblica(MAIN, "regole", "", "regole", "d", 1)
    visti = []

    async def sync(*, guild=None):
        visti.append(sorted(c.name for c in bot.tree.get_commands(guild=guild)))
        return []

    bot.tree.sync = sync
    await monta_per_avvio(bot)
    await sincronizza_all_avvio(bot.tree, guild_sviluppo_id=None, guild_owner_id=MAIN, stato=StatoFinto())
    assert ["owner", "regole"] in visti


async def test_stato_uguale_ma_albero_incompleto_viene_rimandato(monkeypatch):
    bot, cog, repo = _bot_con_cog(monkeypatch)
    await bot.add_cog(cog)
    await repo.pubblica(MAIN, "regole", "", "regole", "d", 1)
    guild = discord.Object(id=MAIN)
    # impronta salvata quando l'albero aveva solo /owner
    vecchia = await impronta_albero_tradotto(bot.tree.get_commands(guild=guild), bot.tree)
    stato = StatoFinto({scope_guild(MAIN): vecchia})
    bot.tree.sync = AsyncMock(return_value=[])
    await monta_per_avvio(bot)
    esiti = await sincronizza_all_avvio(bot.tree, guild_sviluppo_id=None, guild_owner_id=MAIN, stato=stato)
    assert esiti[scope_guild(MAIN)] != "saltata"
    bot.tree.sync.assert_any_await(guild=guild)


async def test_owner_e_riservato_e_i_comandi_di_guild_contano_come_globali(monkeypatch):
    bot, cog, repo = _bot_con_cog(monkeypatch)
    cog_globali = cog._globali()
    assert "owner" in cog_globali
    assert L.errore_nome_comando("owner", cog_globali) is not None
    assert L.errore_nome_menu("Owner", cog_globali) is not None


async def test_monta_salta_una_collisione_senza_rompersi(monkeypatch, caplog):
    bot, cog, repo = _bot_con_cog(monkeypatch)
    await repo.pubblica(MAIN, "owner", "", "regole", "d", 1)  # già nel database, prima del divieto
    await repo.pubblica(MAIN, "regole", "", "regole", "d", 1)
    await cog._monta(MAIN)
    assert bot.tree.get_command("regole", guild=discord.Object(id=MAIN)) is not None
    assert bot.tree.get_command("owner", guild=discord.Object(id=MAIN)).commands  # il gruppo vero è intatto
    assert "owner" in caplog.text
