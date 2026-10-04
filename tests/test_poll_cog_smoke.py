"""
tests/test_poll_cog_smoke.py
================================
Smoke test del cog Poll e dei limiti dichiarati sulle sue opzioni.
"""

from unittest.mock import create_autospec

import discord
from discord.ext import commands

from core.database import Database
from core.premium import registry
from tests.support.discord_fakes import fake_interaction
from cogs.utility.poll import MODULE_POLL, setup as poll_setup


async def test_poll_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await poll_setup(bot)

    assert bot.get_cog("PollCog") is not None

    module = registry.get(MODULE_POLL)
    assert module is not None
    assert module.premium_capable is False

    nomi_comandi = {c.name for c in bot.tree.get_commands()}
    assert "poll" in nomi_comandi


async def test_poll_dichiara_i_limiti_di_discord_su_domanda_e_risposte():
    """
    LIM-2: Discord accetta al massimo 300 caratteri per la domanda e 55
    per ogni risposta. Il limite va dichiarato sull'opzione del comando,
    così è Discord stesso a rifiutare un testo troppo lungo (una
    risposta di 56 caratteri non arriva nemmeno al bot).
    """
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await poll_setup(bot)

    opzioni = {o["name"]: o for o in bot.tree.get_command("poll").to_dict(bot.tree)["options"]}

    assert opzioni["question"]["max_length"] == 300
    risposte = [nome for nome in opzioni if nome.startswith("option")]
    assert len(risposte) == 10
    for nome in risposte:
        assert opzioni[nome]["max_length"] == 55, nome
        assert opzioni[nome]["min_length"] == 1, nome
    assert opzioni["option1"]["required"] is True
    assert opzioni["option2"]["required"] is True
    assert opzioni["option3"].get("required", False) is False


async def test_poll_con_dieci_opzioni_crea_dieci_risposte(monkeypatch):
    """Le dieci opzioni del comando arrivano tutte nel sondaggio."""
    import cogs.utility.poll as modulo

    db_finto = create_autospec(Database, instance=True)
    db_finto.is_module_active_for_guild.return_value = True
    monkeypatch.setattr(modulo, "db", db_finto)

    cog = modulo.PollCog(bot=None)
    interazione = fake_interaction()
    testi = [f"Risposta {numero}" for numero in range(1, 11)]

    await cog.poll.callback(cog, interazione, "x" * 300, *testi)

    sondaggio = interazione.response.send_message.call_args.kwargs["poll"]
    assert [risposta.text for risposta in sondaggio.answers] == testi
    assert sondaggio.question == "x" * 300
