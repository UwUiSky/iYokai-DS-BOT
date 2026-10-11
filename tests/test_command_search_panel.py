"""
tests/test_command_search_panel.py
==================================
Pannello di -cerca-comando senza testo, ricerca con testo, completamento,
-chiedi e registrazione dell'ultimo comando (issue #147). Limiti di Discord
verificati sui componenti: al massimo 25, 5 per riga, 5 righe.
Funzioni coperte: NF-06 (issue #147)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from cogs.utility import command_search as modulo
from cogs.utility.command_search import CommandSearchCog
from core.command_access import Livello
from core.command_groups import NOME_CERCA_COMANDO, NOME_CHIEDI, costruisci_gruppi
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member


async def _cb(interaction):  # pragma: no cover
    pass


def _bot(n_gruppi_extra: int = 0) -> commands.Bot:
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    gruppi = costruisci_gruppi()
    for nome in ("fun", "mod", "modban", "level"):
        gruppi[nome].add_command(app_commands.Command(name="uno", description=f"Comando di {nome}", callback=_cb))
        bot.tree.add_command(gruppi[nome])
    for i in range(n_gruppi_extra):
        g = app_commands.Group(name=f"extra{i}", description="extra")
        g.add_command(app_commands.Command(name="x", description="x", callback=_cb))
        bot.tree.add_command(g)
    bot.tree.add_command(app_commands.Command(name=NOME_CERCA_COMANDO, description="Cerca un comando", callback=_cb))
    bot.tree.add_command(app_commands.Command(name=NOME_CHIEDI, description="Chiedi aiuto", callback=_cb))
    return bot


@pytest.fixture
def cog(monkeypatch):
    c = CommandSearchCog(_bot())
    repo = MagicMock()
    repo.ultimo = AsyncMock(return_value=None)
    repo.registra = AsyncMock()
    monkeypatch.setattr(modulo, "command_usage_repo", repo)
    c.repo = repo
    # Nessun accesso a Discord: gli ID arrivano da qui.
    c.cache_ids.ottieni = AsyncMock(return_value={"fun": 5, "mod": 6, "modban": 7, "level": 8, "-cerca-comando": 9})

    async def solo_mod(interaction, livello):
        return livello is Livello.MOD

    monkeypatch.setattr(modulo, "puo_usare", solo_mod)
    monkeypatch.delenv("WIKI_BASE_URL", raising=False)
    return c


def _invio(interazione):
    chiamata = interazione.response.send_message.call_args
    return chiamata.kwargs


def _componenti(view):
    righe = {}
    for c in view.children:
        righe.setdefault(c.row if c.row is not None else 0, []).append(c)
    return len(view.children), righe


def _etichette(view):
    return [c.label for c in view.children]


async def test_pannello_senza_testo_mostra_ultimo_comando_e_categorie_filtrate(cog):
    cog.repo.ultimo.return_value = "fun uno"
    i = fake_interaction()
    await cog.search.callback(cog, i, query=None)

    inviato = _invio(i)
    assert inviato["ephemeral"] is True
    assert "</fun uno:5>" in inviato["embed"].description
    etichette = _etichette(inviato["view"])
    # Visibili: fun, level (senza livello), mod (puo_usare); non modban. "generali" per i comandi di primo livello.
    assert "fun" in etichette and "level" in etichette and "mod" in etichette and "generali" in etichette
    assert "modban" not in etichette
    cog.repo.ultimo.assert_awaited_once_with(i.guild.id, i.user.id)


async def test_pannello_senza_ultimo_comando_non_ha_menzioni(cog):
    i = fake_interaction()
    await cog.search.callback(cog, i, query=None)
    assert "</" not in _invio(i)["embed"].description


async def test_pannello_rispetta_i_limiti_di_discord_con_molte_categorie(monkeypatch):
    c = CommandSearchCog(_bot(n_gruppi_extra=40))
    c.cache_ids.ottieni = AsyncMock(return_value={})
    repo = MagicMock(ultimo=AsyncMock(return_value=None))
    monkeypatch.setattr(modulo, "command_usage_repo", repo)
    monkeypatch.setattr(modulo, "puo_usare", AsyncMock(return_value=True))
    monkeypatch.setenv("WIKI_BASE_URL", "https://wiki.example")
    i = fake_interaction()
    await c.search.callback(c, i, query=None)

    view = _invio(i)["view"]
    totale, righe = _componenti(view)
    assert totale <= 25
    assert len(righe) <= 5 and all(len(r) <= 5 for r in righe.values())
    categorie = [b for b in view.children if b.label not in ("◀", "▶", "Apri nella wiki")]
    assert len(categorie) == 20  # pagina 1 su 3
    # Pagina successiva.
    freccia = next(b for b in view.children if b.label == "▶")
    i2 = fake_interaction()
    await freccia.callback(i2)
    nuova = i2.response.edit_message.call_args.kwargs["view"]
    assert _componenti(nuova)[0] <= 25
    assert {b.label for b in nuova.children}.isdisjoint({b.label for b in categorie})


async def test_bottone_wiki_solo_se_la_variabile_e_impostata(cog, monkeypatch):
    i = fake_interaction()
    await cog.search.callback(cog, i, query=None)
    assert all(b.label != "Apri nella wiki" for b in _invio(i)["view"].children)

    monkeypatch.setenv("WIKI_BASE_URL", "https://wiki.example")
    i = fake_interaction()
    await cog.search.callback(cog, i, query=None)
    wiki = next(b for b in _invio(i)["view"].children if b.label == "Apri nella wiki")
    assert wiki.url == "https://wiki.example"


async def test_click_su_categoria_mostra_i_comandi_e_si_torna_indietro(cog):
    i = fake_interaction()
    await cog.search.callback(cog, i, query=None)
    view = _invio(i)["view"]
    bottone = next(b for b in view.children if b.label == "fun")

    i2 = fake_interaction()
    await bottone.callback(i2)
    modifica = i2.response.edit_message.call_args.kwargs
    assert "</fun uno:5>" in modifica["embed"].description
    indietro = next(b for b in modifica["view"].children if b.label == "Indietro")

    i3 = fake_interaction()
    await indietro.callback(i3)
    assert "Cerca un comando" in i3.response.edit_message.call_args.kwargs["embed"].title


async def test_ricerca_con_testo_da_risultati_con_menzione_e_opzioni(cog):
    i = fake_interaction()
    await cog.search.callback(cog, i, query="comando di fun")
    inviato = _invio(i)
    campo = inviato["embed"].fields[0]
    assert "</fun uno:5>" in campo.value
    assert len(inviato["embed"]) <= 6000


async def test_ricerca_non_mostra_comandi_di_gruppi_non_accessibili(cog):
    i = fake_interaction()
    await cog.search.callback(cog, i, query="modban")
    inviato = _invio(i)
    assert "Nessun comando trovato" in inviato["embed"].title


async def test_in_dm_avvisa_che_i_comandi_si_usano_nei_server(cog):
    i = fake_interaction()
    i.guild = None
    await cog.search.callback(cog, i, query=None)
    assert "server" in _invio(i)["embed"].description.lower()
    cog.repo.ultimo.assert_awaited_once_with(None, i.user.id)


async def test_ricerca_in_dm_avvisa_anche_nei_risultati(cog):
    i = fake_interaction()
    i.guild = None
    await cog.search.callback(cog, i, query="comando di fun")
    assert "server" in (_invio(i)["embed"].footer.text or "").lower()


async def test_completamento_al_massimo_25_scelte_e_solo_gruppi_accessibili(monkeypatch):
    c = CommandSearchCog(_bot(n_gruppi_extra=40))
    monkeypatch.setattr(modulo, "puo_usare", AsyncMock(return_value=False))
    i = fake_interaction()
    scelte = await c.autocompleta_query(i, "")
    assert 0 < len(scelte) <= 25
    assert all(isinstance(s, app_commands.Choice) and len(s.name) <= 100 and len(s.value) <= 100 for s in scelte)
    assert not any(s.value.startswith("modban") for s in scelte)
    assert not any(s.value.startswith("mod ") for s in scelte)


async def test_completamento_filtra_per_testo(cog):
    scelte = await cog.autocompleta_query(fake_interaction(), "level")
    assert [s.value for s in scelte][0] == "level uno"


async def test_chiedi_mostra_lo_stesso_pannello(cog):
    i = fake_interaction()
    cog.repo.ultimo.return_value = "mod uno"
    await cog.chiedi.callback(cog, i)
    inviato = _invio(i)
    assert "</mod uno:6>" in inviato["embed"].description
    assert "mod" in _etichette(inviato["view"])


async def test_il_cog_registra_chiedi_di_primo_livello_anche_in_dm():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    comando = bot.tree.get_command(NOME_CHIEDI)
    assert comando is not None and not isinstance(comando, app_commands.Group)
    assert comando.guild_only is False
    opzioni = {o["name"]: o for o in comando.to_dict(bot.tree)["options"]}
    assert opzioni["domanda"]["max_length"] <= 500 and not opzioni["domanda"].get("required")
    q = {o["name"]: o for o in bot.tree.get_command(NOME_CERCA_COMANDO).to_dict(bot.tree)["options"]}["query"]
    assert q["autocomplete"] is True and not q.get("required")


async def test_listener_registra_l_ultimo_comando(cog):
    comando = MagicMock(spec=app_commands.Command)
    comando.qualified_name = "fun uno"
    i = fake_interaction()
    await cog.on_app_command_completion(i, comando)
    cog.repo.registra.assert_awaited_once_with(i.guild.id, i.user.id, "fun uno")


async def test_listener_ignora_i_comandi_di_ricerca_e_i_menu_contestuali(cog):
    for nome in (NOME_CERCA_COMANDO, NOME_CHIEDI):
        c = MagicMock(spec=app_commands.Command)
        c.qualified_name = nome
        await cog.on_app_command_completion(fake_interaction(), c)
    menu = MagicMock(spec=app_commands.ContextMenu)
    menu.qualified_name = "Segnala"
    await cog.on_app_command_completion(fake_interaction(), menu)
    cog.repo.registra.assert_not_awaited()


async def test_listener_non_solleva_se_il_database_fallisce(cog):
    cog.repo.registra.side_effect = RuntimeError("db giù")
    c = MagicMock(spec=app_commands.Command)
    c.qualified_name = "fun uno"
    await cog.on_app_command_completion(fake_interaction(), c)  # nessuna eccezione


async def test_listener_in_dm_registra_con_guild_none(cog):
    c = MagicMock(spec=app_commands.Command)
    c.qualified_name = "utility ping"
    i = fake_interaction()
    i.guild = None
    await cog.on_app_command_completion(i, c)
    cog.repo.registra.assert_awaited_once_with(None, i.user.id, "utility ping")
