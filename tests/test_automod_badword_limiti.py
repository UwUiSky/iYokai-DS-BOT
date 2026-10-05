"""
tests/test_automod_badword_limiti.py
====================================
Limite di lunghezza delle parole vietate (LIM-29): Discord accetta al
massimo 60 caratteri per parola in una regola AutoMod. Il limite sta
nell'opzione del comando, così Discord rifiuta la parola prima che
venga salvata.
"""

import discord
import pytest
from discord.ext import commands

import cogs.automod.automod as modulo_automod


def _opzione_word(nome_comando: str) -> dict:
    # Un bot vero, non collegato: serve il suo albero per avere il
    # comando nella forma che viene mandata a Discord.
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    cog = modulo_automod.AutomodCog(bot)
    gruppo = cog.automod_group.to_dict(bot.tree)
    comando = next(c for c in gruppo["options"] if c["name"] == nome_comando)
    return next(o for o in comando["options"] if o["name"] == "word")


@pytest.mark.parametrize("nome_comando", ["badword-add", "badword-remove"])
def test_word_accetta_da_1_a_60_caratteri(nome_comando):
    opzione = _opzione_word(nome_comando)

    assert opzione["min_length"] == 1
    assert opzione["max_length"] == 60
