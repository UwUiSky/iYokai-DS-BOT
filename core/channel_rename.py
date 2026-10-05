"""
core/channel_rename.py
======================
Rinomina di un canale rispettando il limite di Discord: 2 rinomine ogni
10 minuti per canale (LIM-3). Alla terza discord.py resterebbe in attesa
fino a 10 minuti e il comando scadrebbe; qui invece si risponde subito
con "riprova tra N minuti". Usato da /ticket rename e /voice rename.
Funzioni coperte: SPEC §12, §13
"""

from __future__ import annotations

import asyncio
import math
import time

import discord

# Limite di Discord, non ufficiale ma noto: 2 rinomine ogni 10 minuti
# per canale, contando anche quelle fatte a mano dagli utenti.
RENAME_WINDOW_SECONDS = 600
MAX_RENAMES_PER_WINDOW = 2

# Una rinomina normale risponde in meno di un secondo. Se dopo 5 non è
# tornata, Discord ci sta facendo aspettare per il limite.
RENAME_TIMEOUT_SECONDS = 5.0


class RenameRateLimited(Exception):
    """Il canale ha già avuto 2 rinomine negli ultimi 10 minuti."""

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"Rinomina possibile tra {retry_after:.0f} secondi")
        self.retry_after = retry_after


class ChannelRenameTracker:
    """
    Tiene in memoria quando il bot ha rinominato ogni canale. Dopo un
    riavvio riparte da zero: per questo rename_channel ha anche un
    tempo massimo di attesa.
    """

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._renames: dict[int, list[float]] = {}

    def _recent(self, channel_id: int) -> list[float]:
        limite = self._clock() - RENAME_WINDOW_SECONDS
        return [quando for quando in self._renames.get(channel_id, []) if quando > limite]

    def seconds_until_allowed(self, channel_id: int) -> float:
        """0 se il canale si può rinominare adesso, altrimenti i secondi da aspettare."""
        recenti = self._recent(channel_id)
        if len(recenti) < MAX_RENAMES_PER_WINDOW:
            return 0
        piu_vecchia = recenti[-MAX_RENAMES_PER_WINDOW]
        return max(0.0, piu_vecchia + RENAME_WINDOW_SECONDS - self._clock())

    def record(self, channel_id: int) -> None:
        """Segna una rinomina riuscita e dimentica i canali con rinomine scadute."""
        self._renames[channel_id] = self._recent(channel_id) + [self._clock()]
        for altro in list(self._renames):
            if not self._recent(altro):
                del self._renames[altro]

    def block(self, channel_id: int) -> None:
        """Segna il canale come pieno: Discord ha detto che il limite è raggiunto."""
        self._renames[channel_id] = [self._clock()] * MAX_RENAMES_PER_WINDOW

    def tracked_channels(self) -> int:
        return len(self._renames)


rename_tracker = ChannelRenameTracker()


def rename_limit_message(retry_after: float) -> str:
    """Il testo per l'utente quando il limite è raggiunto."""
    minuti = max(1, math.ceil(retry_after / 60))
    quanto = "1 minuto" if minuti == 1 else f"{minuti} minuti"
    return (
        "Discord permette 2 rinomine ogni 10 minuti per canale. "
        f"Riprova tra circa {quanto}."
    )


async def rename_channel(
    channel: discord.abc.GuildChannel,
    name: str,
    *,
    reason: str | None = None,
    tracker: ChannelRenameTracker = rename_tracker,
) -> None:
    """
    Rinomina il canale. Solleva RenameRateLimited se il limite è
    raggiunto (senza chiamare Discord, oppure interrompendo l'attesa
    imposta da Discord). Gli altri errori di Discord
    (discord.HTTPException) escono così come sono: li gestisce chi
    chiama, che sa cosa rispondere all'utente.
    """
    attesa = tracker.seconds_until_allowed(channel.id)
    if attesa > 0:
        raise RenameRateLimited(attesa)

    try:
        await asyncio.wait_for(
            channel.edit(name=name, reason=reason), timeout=RENAME_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        tracker.block(channel.id)
        raise RenameRateLimited(RENAME_WINDOW_SECONDS) from None
    except discord.RateLimited as errore:
        tracker.block(channel.id)
        raise RenameRateLimited(errore.retry_after) from None

    tracker.record(channel.id)
