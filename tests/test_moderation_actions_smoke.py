"""
tests/test_moderation_actions_smoke.py
==========================================
"Smoke test": verifica che il cog si carichi davvero dentro un
discord.ext.commands.Bot reale, senza però connettersi al gateway
Discord (bot.load_extension() non richiede login — chiama solo
setup(bot) del modulo, esattamente come farebbe core/cog_manager.py
in produzione).

Cosa verifica per davvero:
- il modulo si importa senza errori
- setup(bot) viene eseguito senza eccezioni
- il cog risulta caricato nel bot
- si registra nel PremiumRegistry con i parametri attesi
  (premium_capable=False, com'è nello schema: le azioni base
  restano sempre gratis)
- registra l'handler del tempban nello scheduler

Cosa NON verifica (richiede una connessione Discord vera, quindi va
controllato sul server di test): che /warn, /kick, /ban ecc.
rispondano correttamente a un'interazione reale.

Usa il registry e lo scheduler GLOBALI (non istanze isolate) perché
è esattamente il percorso che main.py segue in produzione tramite
core/cog_manager.py — è quello il comportamento da verificare.
Per questo questo file contiene UN SOLO test: registry.register()
solleva un errore se lo stesso nome modulo viene registrato due
volte, quindi setup() per questo cog deve girare una volta sola
nell'intera sessione di test.
"""

import discord
from discord.ext import commands

from core.premium import registry
from core.scheduler import scheduler
from cogs.moderation.actions import MODULE_ACTIONS, setup as actions_setup
from cogs.moderation.actions import SCHEDULED_TEMPBAN_EXPIRE


async def test_actions_cog_si_carica_e_si_registra_correttamente():
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)

    await actions_setup(bot)

    # Il cog risulta caricato nel bot.
    assert bot.get_cog("ModerationActionsCog") is not None

    # Registrato nel sistema premium, e coerente con lo schema:
    # le azioni base sono SEMPRE gratuite.
    module = registry.get(MODULE_ACTIONS)
    assert module is not None
    assert module.premium_capable is False
    assert module.is_premium_active is False

    # L'handler del tempban è agganciato allo scheduler: se in futuro
    # qualcuno lo rimuove per errore, questo test lo segnala subito
    # invece di scoprirlo mesi dopo con un tempban che non scade mai.
    assert SCHEDULED_TEMPBAN_EXPIRE in scheduler._handlers
