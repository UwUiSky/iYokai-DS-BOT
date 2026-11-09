"""B28: comandi e menu del server — montaggio nell'albero, sync (5 minuti, 200 al giorno), risposta con il tag."""
import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import cogs.utility.slash_server as modulo
from cogs.utility.slash_server import SlashServerCog
from core import slash_server_logic as L
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

G = 4242


def scelta(v):
    return SimpleNamespace(value=v)


class RepoFinto:
    """Archivio in memoria con la stessa interfaccia: i test guardano il comportamento del cog, non il database."""

    def __init__(self):
        self.c, self.m, self.s = {}, {}, None

    async def pubblica(self, g, nome, sotto, tag, descr, chi):
        self.c[(nome, sotto)] = {"nome": nome, "sotto": sotto, "tag": tag, "descrizione": descr}
        return "ok"

    async def togli(self, g, nome, sotto):
        return self.c.pop((nome, sotto), None) is not None

    async def comandi(self, g):
        return list(self.c.values())

    async def comando(self, g, nome, sotto):
        return self.c.get((nome, sotto))

    async def aggiungi_menu(self, g, nome, tipo, tag, chi):
        self.m[(nome, tipo)] = {"nome": nome, "tipo": tipo, "tag": tag}
        return "ok"

    async def togli_menu(self, g, nome, tipo):
        return self.m.pop((nome, tipo), None) is not None

    async def menu(self, g):
        return list(self.m.values())

    async def una_voce_di_menu(self, g, nome, tipo):
        return self.m.get((nome, tipo))

    async def server_con_voci(self):
        return [G]

    async def stato(self, g):
        return self.s

    async def salva_sync(self, g, quando, imp, nomi, giorno, creazioni):
        self.s = {"ultimo_sync": quando, "impronta": imp, "nomi": json.dumps(nomi), "giorno": giorno, "creazioni": creazioni, "in_coda": False}

    async def segna_in_coda(self, g, valore):
        self.s = {**(self.s or {"ultimo_sync": None, "impronta": "", "nomi": "[]", "giorno": None, "creazioni": 0}), "in_coda": valore}


@pytest.fixture
def cog(monkeypatch):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    bot.tree.sync = AsyncMock(return_value=[])
    c = SlashServerCog(bot)
    repo = RepoFinto()
    monkeypatch.setattr(modulo, "slash_server_repo", repo)
    sched = MagicMock()
    sched.schedule = AsyncMock(return_value=1)
    monkeypatch.setattr(modulo, "scheduler", sched)
    ccr = MagicMock()
    ccr.get_tag = AsyncMock(return_value=SimpleNamespace(name="regole"))
    ccr.search_names = AsyncMock(return_value=[])
    monkeypatch.setattr(modulo, "custom_command_repo", ccr)
    dbf = MagicMock()
    dbf.is_module_active_for_guild = AsyncMock(return_value=True)
    monkeypatch.setattr(modulo, "db", dbf)
    c.repo, c.sched, c.bot_tree = repo, sched, bot.tree
    return c


def _i():
    server = fake_guild()
    server.id = G
    utente = fake_member(5)
    utente.guild = server
    return fake_interaction(guild=server, user=utente)


def _ora(monkeypatch, quando):
    monkeypatch.setattr(modulo, "adesso", lambda: quando)


NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


async def test_pubblica_monta_il_comando_e_sincronizza(cog, monkeypatch):
    _ora(monkeypatch, NOW)
    i = _i()
    await cog.pubblica.callback(cog, i, "Regole", "regole", "", "Le regole del server")
    assert cog.bot_tree.get_command("regole", guild=discord.Object(id=G)) is not None
    cog.bot_tree.sync.assert_awaited_once()
    assert cog.bot_tree.sync.await_args.kwargs["guild"].id == G
    assert cog.repo.s["impronta"] and cog.repo.s["creazioni"] == 1


async def test_pubblica_rifiuta_nomi_riservati_e_globali(cog):
    cog.bot_tree.add_command(discord.app_commands.Command(name="tag", description="x", callback=_vuota))
    for nome in ("admin-x", "moderatori", "founder", "tag", "a b"):
        i = _i()
        await cog.pubblica.callback(cog, i, nome, "regole", "", "d")
    assert cog.repo.c == {}
    cog.bot_tree.sync.assert_not_awaited()


async def _vuota(interaction: discord.Interaction) -> None:
    pass


async def test_pubblica_tag_inesistente(cog):
    cog.ccr = modulo.custom_command_repo
    modulo.custom_command_repo.get_tag.return_value = None
    await cog.pubblica.callback(cog, _i(), "regole", "nope", "", "d")
    assert cog.repo.c == {}


async def test_con_sotto_comando_diventa_un_gruppo(cog, monkeypatch):
    _ora(monkeypatch, NOW)
    await cog.pubblica.callback(cog, _i(), "wiki", "regole", "uno", "Uno")
    gruppo = cog.bot_tree.get_command("wiki", guild=discord.Object(id=G))
    assert isinstance(gruppo, discord.app_commands.Group) and [c.name for c in gruppo.commands] == ["uno"]


async def test_seconda_modifica_entro_5_minuti_va_in_coda(cog, monkeypatch):
    _ora(monkeypatch, NOW)
    await cog.pubblica.callback(cog, _i(), "uno", "regole", "", "d")
    _ora(monkeypatch, NOW + timedelta(seconds=60))
    await cog.pubblica.callback(cog, _i(), "due", "regole", "", "d")
    assert cog.bot_tree.sync.await_count == 1
    args = cog.sched.schedule.await_args.args
    assert args[2] == L.AZIONE_SYNC and args[3] == NOW + timedelta(seconds=300) and args[4] == {"guild_id": G}
    # un terzo cambio non prenota un'altra volta
    await cog.pubblica.callback(cog, _i(), "tre", "regole", "", "d")
    assert cog.sched.schedule.await_count == 1
    # a scadenza il giro dello scheduler fa la sync con tutto
    _ora(monkeypatch, NOW + timedelta(seconds=301))
    await cog.handle_sync(G, 0, {"guild_id": G})
    assert cog.bot_tree.sync.await_count == 2
    assert {c.name for c in cog.bot_tree.get_commands(guild=discord.Object(id=G))} == {"uno", "due", "tre"}
    assert cog.repo.s["in_coda"] is False


async def test_senza_cambi_non_si_sincronizza(cog, monkeypatch):
    _ora(monkeypatch, NOW)
    await cog.pubblica.callback(cog, _i(), "uno", "regole", "", "d")
    _ora(monkeypatch, NOW + timedelta(hours=1))
    assert await cog.sincronizza(G) == ("uguale", 0)
    assert cog.bot_tree.sync.await_count == 1


async def test_limite_di_200_creazioni_al_giorno(cog, monkeypatch):
    _ora(monkeypatch, NOW)
    cog.repo.s = {"ultimo_sync": NOW - timedelta(hours=1), "impronta": "x", "nomi": "[]", "giorno": NOW.date(), "creazioni": 200, "in_coda": False}
    i = _i()
    await cog.pubblica.callback(cog, i, "uno", "regole", "", "d")
    cog.bot_tree.sync.assert_not_awaited()
    assert "giorn" in i.followup.send.await_args.args[0]
    # il giorno dopo il conto riparte
    _ora(monkeypatch, NOW + timedelta(days=1))
    assert (await cog.sincronizza(G))[0] == "fatto"


async def test_sync_fallita_riprova_dopo_5_minuti(cog, monkeypatch):
    _ora(monkeypatch, NOW)
    cog.bot_tree.sync.side_effect = discord.HTTPException(MagicMock(status=500), "boom")
    await cog.pubblica.callback(cog, _i(), "uno", "regole", "", "d")
    assert cog.repo.s is None or cog.repo.s["impronta"] == ""
    assert cog.sched.schedule.await_args.args[3] == NOW + timedelta(seconds=300)


async def test_il_comando_risponde_con_il_tag(cog, monkeypatch):
    _ora(monkeypatch, NOW)
    await cog.pubblica.callback(cog, _i(), "regole", "regole", "", "d")
    tag_cog = MagicMock()
    tag_cog.tag.callback = AsyncMock()
    cog.bot.get_cog = MagicMock(return_value=tag_cog)
    comando = cog.bot_tree.get_command("regole", guild=discord.Object(id=G))
    i = _i()
    await comando.callback(i, "ciao")
    tag_cog.tag.callback.assert_awaited_once_with(tag_cog, i, "regole", "ciao", None)


async def test_comando_sparito_o_tag_cog_assente(cog):
    i = _i()
    await cog._rispondi(i, "non-c-e", "", "", None)
    i.response.send_message.assert_awaited()


async def test_menu_utente_e_messaggio(cog, monkeypatch):
    _ora(monkeypatch, NOW)
    await cog.menu.callback(cog, _i(), scelta("aggiungi"), scelta("utente"), "Dai il benvenuto", "regole")
    await cog.menu.callback(cog, _i(), scelta("aggiungi"), scelta("messaggio"), "Rispondi con regole", "regole")
    tree = cog.bot_tree
    g = discord.Object(id=G)
    assert tree.get_command("Dai il benvenuto", guild=g, type=discord.AppCommandType.user) is not None
    assert tree.get_command("Rispondi con regole", guild=g, type=discord.AppCommandType.message) is not None
    tag_cog = MagicMock()
    tag_cog.tag.callback = AsyncMock()
    cog.bot.get_cog = MagicMock(return_value=tag_cog)
    bersaglio = fake_member(9)
    bersaglio.__class__ = discord.Member
    i = _i()
    await tree.get_command("Dai il benvenuto", guild=g, type=discord.AppCommandType.user).callback(i, bersaglio)
    assert tag_cog.tag.callback.await_args.args[2:] == ("regole", "", bersaglio)
    msg = SimpleNamespace(content="x" * 500, author=bersaglio)
    await tree.get_command("Rispondi con regole", guild=g, type=discord.AppCommandType.message).callback(i, msg)
    assert tag_cog.tag.callback.await_args.args[3] == "x" * 200


async def test_togli_smonta_e_sincronizza(cog, monkeypatch):
    _ora(monkeypatch, NOW)
    await cog.pubblica.callback(cog, _i(), "regole", "regole", "", "d")
    _ora(monkeypatch, NOW + timedelta(minutes=6))
    await cog.togli.callback(cog, _i(), "regole", "")
    assert cog.bot_tree.get_command("regole", guild=discord.Object(id=G)) is None
    assert cog.bot_tree.sync.await_count == 2
    i = _i()
    await cog.togli.callback(cog, i, "regole", "")  # già tolto
    i.response.send_message.assert_awaited()


async def test_all_avvio_si_rimonta_senza_sincronizzare(cog):
    await cog.repo.pubblica(G, "regole", "", "regole", "d", 1)
    await cog.repo.aggiungi_menu(G, "Menu", "utente", "regole", 1)
    await cog.on_ready()
    assert cog.bot_tree.get_command("regole", guild=discord.Object(id=G)) is not None
    cog.bot_tree.sync.assert_not_awaited()
    await cog.on_ready()  # una volta sola
    assert len(cog._montati[G]) == 2


async def test_elenco(cog, monkeypatch):
    await cog.repo.pubblica(G, "regole", "", "regole", "d", 1)
    i = _i()
    await cog.elenco.callback(cog, i)
    assert "regole" in i.response.send_message.await_args.args[0]
