"""
tests/test_case_system_smoke.py
==================================
Verifica un punto delicato: cogs/moderation/case_system.py combina
@app_commands.command(...) con @requires_module(...) (core/premium.py)
sullo STESSO metodo. Il decorator @requires_module usa
functools.wraps, che copia __wrapped__ — discord.py, quando costruisce
il comando slash, deve riuscire a leggere i parametri REALI del
metodo originale (es. `member: discord.Member`) attraverso il
wrapper, non fermarsi a `*args, **kwargs`.

Se questo si rompe, l'errore si manifesterebbe SOLO al momento in cui
discord.py prova a registrare il comando (add_cog/sync) — un tipo di
bug che passerebbe inosservato leggendo il codice, va verificato
eseguendolo per davvero.
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import registry
from cogs.moderation.case_system import MODULE_CASE_SYSTEM, setup as case_system_setup


async def test_case_system_cog_si_carica_e_i_parametri_sono_letti_correttamente():
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)

    await case_system_setup(bot)

    cog = bot.get_cog("ModerationCaseSystemCog")
    assert cog is not None

    # Verifica il punto critico: il comando /modcase history deve
    # avere un parametro "member" di tipo Member, non essersi
    # perso dietro il *args/**kwargs del decorator @requires_module.
    modcase_group = None
    for command in bot.tree.get_commands():
        if isinstance(command, app_commands.Group) and command.name == "modcase":
            modcase_group = command
            break
    assert modcase_group is not None, "Il gruppo /modcase non risulta registrato"

    history_cmd = modcase_group.get_command("history")
    assert history_cmd is not None

    param_names = [p.name for p in history_cmd.parameters]
    assert "member" in param_names, (
        "Il parametro 'member' non è stato letto correttamente da "
        "discord.py attraverso il decorator @requires_module - i "
        "parametri sono andati persi nel wrapping."
    )

    view_cmd = modcase_group.get_command("view")
    assert view_cmd is not None
    assert "case_number" in [p.name for p in view_cmd.parameters]

    # Stessa verifica sul gruppo /modnote.
    modnote_group = None
    for command in bot.tree.get_commands():
        if isinstance(command, app_commands.Group) and command.name == "modnote":
            modnote_group = command
            break
    assert modnote_group is not None

    add_cmd = modnote_group.get_command("add")
    assert add_cmd is not None
    add_param_names = [p.name for p in add_cmd.parameters]
    assert "member" in add_param_names
    assert "note" in add_param_names

    # Registrazione premium corretta: questo modulo è candidato
    # premium (a differenza delle azioni base), coerente con lo
    # schema di progetto.
    module = registry.get(MODULE_CASE_SYSTEM)
    assert module is not None
    assert module.premium_capable is True
