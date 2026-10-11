"""
core/feed_alert_gate.py
===========================
Controllo comune ai watcher di avvisi (feed, Twitch, YouTube): il
modulo `feed_alerts` deve essere attivo sul server ad ogni giro, non
solo quando si crea la sottoscrizione (LC-7, M 11.4). Se è spento il
watcher non pubblica e non spende quota.
"""

from __future__ import annotations

from core.database import db

MODULE_FEED_ALERTS = "feed_alerts"


async def modulo_alert_attivo(guild_id: int) -> bool:
    return await db.is_module_active_for_guild(guild_id, MODULE_FEED_ALERTS)


async def filtra_attive(sottoscrizioni: list) -> list:
    """Tiene solo le sottoscrizioni il cui server ha il modulo attivo
    (un controllo per server, non per sottoscrizione)."""
    esito: dict[int, bool] = {}
    tenute = []
    for s in sottoscrizioni:
        if s.guild_id not in esito:
            esito[s.guild_id] = await modulo_alert_attivo(s.guild_id)
        if esito[s.guild_id]:
            tenute.append(s)
    return tenute


class AvvisoUnaVolta:
    """Logga un problema una sola volta finche' dura; `riarma` quando passa."""

    def __init__(self) -> None:
        self._attivi: set = set()

    def prima_volta(self, chiave) -> bool:
        if chiave in self._attivi:
            return False
        self._attivi.add(chiave)
        return True

    def riarma(self, chiave) -> None:
        self._attivi.discard(chiave)
