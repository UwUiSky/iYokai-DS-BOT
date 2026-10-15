"""
core/mod_bot.py
===============
Client minimale di iYokai Mod (D15): nessun comando, nessun listener.
Gli eventi li ascolta il bot principale; Mod esegue log e azioni di
sicurezza quando `core/bot_roles.py` lo sceglie. Facoltativo: senza
`YOKAI_MOD_TOKEN` non parte e fa tutto il principale.
Funzioni coperte: SPEC parte E (iYokai Mod, D15)
"""

from __future__ import annotations

import discord

# Oltre questa attesa per un rate limit, discord.py solleva RateLimited
# invece di aspettare: bot_roles passa allora il lavoro al principale.
ATTESA_MASSIMA_RATE_LIMIT = 30.0


def intent_mod() -> discord.Intents:
    """Solo i server: canali, ruoli e se stesso. Niente membri né messaggi."""
    intents = discord.Intents.none()
    intents.guilds = True
    return intents


class ModBot(discord.Client):
    def __init__(self) -> None:
        super().__init__(
            intents=intent_mod(),
            max_ratelimit_timeout=ATTESA_MASSIMA_RATE_LIMIT,
            # SEC-7: stesse menzioni sicure del bot principale.
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=False),
        )
