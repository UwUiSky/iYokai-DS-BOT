"""
core/security_raid_state.py
===========================
Stato in memoria "questo server è sotto raid" (M 10.16 / LIM-35).

L'anti-raid lo aggiorna a ogni ingresso di raid; chi manda messaggi
a chi entra (benvenuto privato, verifica) chiede `raid_in_corso()` e,
se è vero, sta zitto: durante un raid ogni DM in più è rumore e
rischio di blocco per il bot.

Vale `DURATA_RAID_SECONDI` dopo l'ultimo ingresso di raid (la stessa
durata del blocco dell'anti-raid). Tetto di server tenuti in memoria.
"""

from __future__ import annotations

from datetime import datetime

import discord

from core.bounded_cache import BoundedCache

DURATA_RAID_SECONDI = 15 * 60

_ultimo_ingresso: BoundedCache[int, datetime] = BoundedCache(max_size=5000)


def segna_raid(guild_id: int, now: datetime | None = None) -> None:
    """Un ingresso di raid è appena stato rilevato in questo server."""
    _ultimo_ingresso.set(guild_id, now or discord.utils.utcnow())


def raid_in_corso(guild_id: int, now: datetime | None = None) -> bool:
    ultimo = _ultimo_ingresso.get(guild_id)
    if ultimo is None:
        return False
    adesso = now or discord.utils.utcnow()
    return (adesso - ultimo).total_seconds() <= DURATA_RAID_SECONDI


def azzera(guild_id: int) -> None:
    """Il blocco è finito (o il modulo è stato spento)."""
    _ultimo_ingresso.delete(guild_id)
