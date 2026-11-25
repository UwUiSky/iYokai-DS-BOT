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


class FreniInvio:
    """
    Quando Discord rifiuta un invio con 403 (nessun permesso) o 404 (canale sparito) riprovare ogni giro non serve
    e si accumulano richieste non valide: Discord blocca l'indirizzo IP di tutti i bot dopo 10.000 in 10 minuti.
    Qui ogni chiave (una sottoscrizione) ha una pausa che cresce a ogni rifiuto e, al quinto di fila, si dice di
    disattivarla. Un invio riuscito azzera tutto.
    """

    PAUSE_SECONDI = (600.0, 1800.0, 7200.0, 21600.0)  # 10 minuti, 30 minuti, 2 ore, 6 ore
    RIFIUTI_PER_DISATTIVARE = 5

    def __init__(self) -> None:
        self._rifiuti: dict = {}
        self._fino_a: dict = {}

    def puo_provare(self, chiave, adesso: float) -> bool:
        return adesso >= self._fino_a.get(chiave, 0.0)

    def rifiutato(self, chiave, adesso: float) -> bool:
        """Registra un rifiuto. Restituisce True se la sottoscrizione va disattivata."""
        n = self._rifiuti.get(chiave, 0) + 1
        self._rifiuti[chiave] = n
        if n >= self.RIFIUTI_PER_DISATTIVARE:
            self.dimentica(chiave)
            return True
        self._fino_a[chiave] = adesso + self.PAUSE_SECONDI[min(n, len(self.PAUSE_SECONDI)) - 1]
        return False

    def riuscito(self, chiave) -> None:
        self.dimentica(chiave)

    def dimentica(self, chiave) -> None:
        self._rifiuti.pop(chiave, None)
        self._fino_a.pop(chiave, None)
