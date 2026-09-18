"""
tests/test_role_menus_cog_smoke.py
======================================
Smoke test del cog Role Menu. Oltre ai controlli standard, verifica
esplicitamente la costruzione delle view DINAMICHE (numero di
bottoni/opzioni variabile, mai testato prima in questo progetto — i
pannelli precedenti avevano sempre un solo bottone fisso) e la loro
persistenza.
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import registry
from core.repositories.role_menu_repo import RoleMenuOption
from cogs.utility.role_menus import (
    MODULE_ROLE_MENUS,
    RoleMenuCog,
    setup as role_menus_setup,
)


async def test_role_menus_cog_si_carica_correttamente(clean_db):
    # A differenza degli altri smoke test, questo richiede il
    # SINGLETON db (core.database.db) davvero connesso, non solo il
    # pool isolato clean_db: setup() interroga il repository globale
    # role_menu_repo, che passa da db.pool — esattamente come accade
    # in produzione, dove db.connect() avviene sempre PRIMA del
    # caricamento dei cog (vedi la sequenza in main.py). Nessun altro
    # test del progetto connette il singleton (tutti usano pool
    # isolati per-test passati esplicitamente ai repository) perché
    # questo è il primo cog il cui setup() query il DB al
    # caricamento — non un'eccezione al pattern, un caso nuovo.
    from core.database import db

    await db.connect()
    try:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        await role_menus_setup(bot)
    finally:
        await db.close()

    assert bot.get_cog("RoleMenuCog") is not None

    module = registry.get(MODULE_ROLE_MENUS)
    assert module is not None
    assert module.premium_capable is False

    rolemenu_group = None
    for command in bot.tree.get_commands():
        if isinstance(command, app_commands.Group) and command.name == "rolemenu":
            rolemenu_group = command
            break
    assert rolemenu_group is not None

    sottocomandi = {c.name for c in rolemenu_group.commands}
    assert {"create", "add-option", "remove-option", "delete"} <= sottocomandi

    assert {"on_raw_reaction_add", "on_raw_reaction_remove"} <= set(bot.extra_events.keys())


def _opzioni_di_prova(n: int) -> list[RoleMenuOption]:
    return [
        RoleMenuOption(
            id=i, menu_id=1, role_id=100 + i, emoji="🎮", label=f"Ruolo {i}", position=i
        )
        for i in range(n)
    ]


def test_build_button_view_numero_bottoni_corrisponde_alle_opzioni():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = RoleMenuCog(bot)
    opzioni = _opzioni_di_prova(4)

    view = cog._build_button_view(menu_id=1, options=opzioni)

    assert len(view.children) == 4
    assert view.is_persistent() is True
    assert view.timeout is None


def test_build_button_view_custom_id_codifica_menu_e_ruolo():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = RoleMenuCog(bot)
    opzioni = _opzioni_di_prova(1)

    view = cog._build_button_view(menu_id=42, options=opzioni)

    bottone = view.children[0]
    assert bottone.custom_id == "iyokai_rolemenu_btn:42:100"


def test_build_button_view_zero_opzioni_nessun_bottone():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = RoleMenuCog(bot)

    view = cog._build_button_view(menu_id=1, options=[])

    assert len(view.children) == 0


def test_build_select_view_opzioni_corrispondono():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = RoleMenuCog(bot)
    opzioni = _opzioni_di_prova(3)

    view = cog._build_select_view(menu_id=1, options=opzioni, max_selectable=None)

    assert len(view.children) == 1
    select = view.children[0]
    assert isinstance(select, discord.ui.Select)
    assert len(select.options) == 3
    assert view.is_persistent() is True


def test_build_select_view_max_selectable_none_significa_tutte():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = RoleMenuCog(bot)
    opzioni = _opzioni_di_prova(5)

    view = cog._build_select_view(menu_id=1, options=opzioni, max_selectable=None)

    select = view.children[0]
    assert select.max_values == 5


def test_build_select_view_max_selectable_limitato():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = RoleMenuCog(bot)
    opzioni = _opzioni_di_prova(5)

    view = cog._build_select_view(menu_id=1, options=opzioni, max_selectable=2)

    select = view.children[0]
    assert select.max_values == 2


def test_build_select_view_max_selectable_non_supera_il_numero_di_opzioni():
    # Se max_selectable configurato è più alto del numero di opzioni
    # effettivamente presenti (es. un'opzione è stata rimossa dopo),
    # Discord rifiuterebbe max_values > len(options) — il codice deve
    # limitarlo da solo, non fidarsi ciecamente del valore salvato.
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = RoleMenuCog(bot)
    opzioni = _opzioni_di_prova(2)

    view = cog._build_select_view(menu_id=1, options=opzioni, max_selectable=10)

    select = view.children[0]
    assert select.max_values == 2


def test_build_select_view_custom_id_codifica_il_menu():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = RoleMenuCog(bot)
    opzioni = _opzioni_di_prova(1)

    view = cog._build_select_view(menu_id=77, options=opzioni, max_selectable=None)

    select = view.children[0]
    assert select.custom_id == "iyokai_rolemenu_select:77"
