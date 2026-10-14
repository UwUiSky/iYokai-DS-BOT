"""
tests/test_leveling_cog_smoke.py
===================================
Smoke test del cog livelli/economia. Oltre al solito controllo di
caricamento e registrazione premium, verifica che:
- on_message compaia in bot.extra_events (stessa lezione già nota:
  serve il decorator @commands.Cog.listener())
- il task periodico _voice_xp_tick si avvii senza sollevare
  eccezioni al caricamento del cog (avviato in __init__, con
  before_loop che aspetta bot.wait_until_ready() — qui verifichiamo
  solo che l'avvio in sé non fallisca, non un giro reale del task,
  che richiederebbe server e canali vocali veri)
"""

import discord
from discord import app_commands
from discord.ext import commands

from core.premium import registry
from tests.support.percorsi import percorsi_del_gruppo
from cogs.leveling.leveling import MODULE_LEVELING, setup as leveling_setup


async def test_leveling_cog_si_carica_correttamente():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await leveling_setup(bot)

    cog = bot.get_cog("LevelingCog")
    assert cog is not None

    module = registry.get(MODULE_LEVELING)
    assert module is not None
    assert module.premium_capable is False

    assert "on_message" in bot.extra_events

    assert {"rank", "balance", "daily", "work", "pay", "leaderboard", "shop list", "shop buy", "cassa"} <= percorsi_del_gruppo("level")
    assert {"livello-add", "livello-remove", "livello-list"} <= {
        p.split()[-1] for p in percorsi_del_gruppo("gestione") if p.startswith("ruoli ")
    }
    assert {
        "vincitori-set", "vincitori-off", "shop-add", "shop-remove",
        "cassa-premium", "assegna-lobby", "assegna-winner", "giveaway", "xp", "monete",
    } <= percorsi_del_gruppo("economia")
    assert {"bacheca set", "bacheca disable", "tesoreria dona", "boost individuale", "boost gilda"} <= percorsi_del_gruppo("clan")

    # Il task periodico deve essere avviato (non sollevare eccezioni
    # all'avvio del cog) — before_loop attende bot.wait_until_ready(),
    # quindi non gira davvero qui, ma deve risultare "in esecuzione"
    # nel senso di discord.py (task registrato, in attesa).
    assert cog._voice_xp_tick.is_running() is True

    # Pulizia: fermiamo il task per non lasciarlo agganciato
    # all'event loop dopo la fine del test.
    cog._voice_xp_tick.cancel()
