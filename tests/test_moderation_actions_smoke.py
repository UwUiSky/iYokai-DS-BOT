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
from discord import app_commands
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

    # "Reason obbligatorio" (SPEC.md §5.9): verificato esplicitamente
    # sui comandi che lo richiedono, non solo a occhio sul codice —
    # se in futuro qualcuno reintroduce reason: str | None = None per
    # errore, questo test lo blocca subito. /untimeout non ha reason
    # (è una revoca, non un'azione punitiva) e resta fuori apposta.
    comandi_con_reason_obbligatorio = {
        "warn", "kick", "ban", "tempban", "unban", "timeout"
    }
    for command in bot.tree.get_commands():
        if not isinstance(command, app_commands.Command):
            continue
        if command.name not in comandi_con_reason_obbligatorio:
            continue
        reason_param = next(p for p in command.parameters if p.name == "reason")
        assert reason_param.required is True, (
            f"/{command.name}: reason deve essere obbligatorio"
        )
