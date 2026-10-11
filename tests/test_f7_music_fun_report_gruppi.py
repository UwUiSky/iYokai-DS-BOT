"""
tests/test_f7_music_fun_report_gruppi.py
========================================
I comandi di musica, radio, fun e report stanno nei gruppi giusti, col
nome giusto (mappa F7 passo 3b): /music (con loop, volume, nonstop),
/owner radio, /fun, /utility report, /admin config canale-report.
Funzioni coperte: NF-05 (issue #76)
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.command_access import Livello
from core.command_groups import GRUPPI
from tests.support.percorsi import percorsi_del_gruppo

MUSIC_ATTESI = {
    "play", "skip", "stop", "pause", "resume", "queue", "clear-queue", "shuffle",
    "nowplaying", "disconnect",
    "loop track", "loop queue", "volume set", "volume up", "volume down", "nonstop on", "nonstop off",
}
RADIO_ATTESI = {
    "radio add-track", "radio add-local", "radio remove-track", "radio list-tracks",
    "radio start", "radio stop",
}
VECCHI_TOP = {
    "play", "skip", "stop", "pause", "resume", "queue", "clear-queue", "shuffle", "nowplaying",
    "disconnect", "loop", "volume", "nonstop", "nonstop-main",
}


async def _scarica(bot):
    for cog in list(bot.cogs):
        await bot.remove_cog(cog)


async def test_musica_e_radio_stanno_nei_gruppi_giusti():
    from cogs.music.player import setup as music_setup

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await music_setup(bot)
    try:
        assert MUSIC_ATTESI <= percorsi_del_gruppo("music")
        assert RADIO_ATTESI <= percorsi_del_gruppo("owner")
        top = {c.name for c in bot.tree.get_commands()}
        assert not top & VECCHI_TOP
        assert "music" in top
        assert "owner" not in top  # /owner lo aggiunge main.py solo nel server dell'owner
    finally:
        await _scarica(bot)


async def test_music_un_livello_di_sottogruppi_e_al_massimo_25_figli():
    from cogs.music.player import setup as music_setup

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await music_setup(bot)
    try:
        assert len(GRUPPI["music"].commands) <= 25
        for figlio in GRUPPI["music"].commands:
            if isinstance(figlio, app_commands.Group):
                assert not any(isinstance(n, app_commands.Group) for n in figlio.commands)
            assert not figlio.description.startswith("[")
        assert GRUPPI["music"].livello is None
        assert GRUPPI["owner"].livello is Livello.OWNER
        radio = GRUPPI["owner"].get_command("radio")
        assert radio is not None and not any(c.description.startswith("[") for c in radio.commands)
    finally:
        await _scarica(bot)


async def test_fun_ha_tutti_i_comandi_nel_gruppo_condiviso():
    from cogs.fun.entertainment import setup as ent_setup
    from cogs.fun.ship_rate import setup as ship_setup

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await ent_setup(bot)
    await ship_setup(bot)
    try:
        assert percorsi_del_gruppo("fun") >= {
            "coinflip", "dice", "rps", "8ball", "joke", "quote", "fact", "grayscale", "invert",
            "blur", "pixelate", "meme", "animal", "search-image", "ship", "rate",
        }
        top = {c.name for c in bot.tree.get_commands()}
        assert "fun" in top and not top & {"ship", "rate"}
        assert GRUPPI["fun"].livello is None
    finally:
        await _scarica(bot)
