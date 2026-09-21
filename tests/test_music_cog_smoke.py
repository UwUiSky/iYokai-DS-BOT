"""
tests/test_music_cog_smoke.py
=================================
Smoke test del cog Music. setup() prova anche a connettersi a un
nodo Lavalink (wavelink.Pool.connect()) — in questo ambiente non c'è
nessun nodo in ascolto, quindi la connessione fallisce per davvero:
verifica che questo fallimento sia catturato e non impedisca il
caricamento del resto del cog (comandi, registrazione del modulo),
esattamente come progettato per un nodo temporaneamente
irraggiungibile in produzione.
"""

import discord
from discord.ext import commands

from core.premium import registry
from cogs.music.player import MODULE_MUSIC, setup as music_setup


async def test_music_cog_si_carica_anche_se_lavalink_non_e_raggiungibile():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

    await music_setup(bot)  # non deve sollevare, nonostante nessun nodo Lavalink reale

    assert bot.get_cog("MusicCog") is not None

    module = registry.get(MODULE_MUSIC)
    assert module is not None
    assert module.premium_capable is False

    nomi_comandi = {c.name for c in bot.tree.get_commands()}
    assert {"play", "skip", "stop", "pause", "resume", "queue", "volume", "disconnect"} <= nomi_comandi
