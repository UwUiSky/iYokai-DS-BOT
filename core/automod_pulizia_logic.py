"""
core/automod_pulizia_logic.py
=============================
Pulizia di un canale a intervalli (AMD-073) e per tipo di messaggio (AMD-074). Logica pura: intervallo, tipi,
quali messaggi cancellare e come dividerli fra cancellazione in blocco (2-100 messaggi, meno di 14 giorni) e una
per una (al massimo 100 per giro), con l'alt dopo tre rifiuti 403.
Funzioni coperte: SPEC §6 (AMD-073, 074)
"""

from __future__ import annotations

import re

from core.phishing_logic import codici_invito

TIPI = ("persone", "bot", "link", "inviti", "allegati", "tutti")
MIN_OGNI_S = 3600  # non più spesso di un'ora
MAX_OGNI_S = 30 * 86400
MAX_GIRO_BLOCCO = 100  # messaggi per chiamata di cancellazione in blocco (limite di Discord)
MAX_SINGOLI = 100  # messaggi più vecchi di 14 giorni, uno per uno, per giro e per canale
MAX_ESAMINATI = 500  # messaggi letti dalla cronologia per giro
MARGINE_BLOCCO_GIORNI = 13.9  # Discord rifiuta il blocco con messaggi oltre i 14 giorni: un po' di margine
MAX_RIGHE_PER_SERVER = 10
MAX_CANALI_PER_CICLO = 10
MAX_403 = 3
_UNITA = {"d": 86400, "h": 3600, "m": 60}
_OGNI = re.compile(r"^(?:(\d{1,3})([dhm]))(?:(\d{1,3})([dhm]))?$")
_LINK = re.compile(r"https?://", re.IGNORECASE)


class PuliziaNonValida(ValueError):
    """L'intervallo o il tipo scritti non vanno bene."""


def leggi_ogni(testo: str) -> int:
    """«6h», «2d», «90m», «1h30m» -> secondi, tra 1 ora e 30 giorni."""
    m = _OGNI.match((testo or "").strip().lower())
    if not m:
        raise PuliziaNonValida("intervallo")
    totale = int(m.group(1)) * _UNITA[m.group(2)]
    if m.group(3):
        if m.group(4) == m.group(2):
            raise PuliziaNonValida("intervallo")
        totale += int(m.group(3)) * _UNITA[m.group(4)]
    if not MIN_OGNI_S <= totale <= MAX_OGNI_S:
        raise PuliziaNonValida("intervallo")
    return totale


def scrivi_ogni(secondi: int) -> str:
    giorni, resto = divmod(secondi, 86400)
    ore, resto = divmod(resto, 3600)
    minuti = resto // 60
    return "".join(f"{n}{u}" for n, u in ((giorni, "d"), (ore, "h"), (minuti, "m")) if n) or "0m"


def corrisponde(tipo: str, *, e_bot: bool, testo: str, allegati: int) -> bool:
    if tipo == "tutti":
        return True
    if tipo == "persone":
        return not e_bot
    if tipo == "bot":
        return e_bot
    if tipo == "link":
        return bool(_LINK.search(testo or ""))
    if tipo == "inviti":
        return bool(codici_invito(testo or ""))
    if tipo == "allegati":
        return allegati > 0
    return False


def da_cancellare(*, fissato: bool, incluso_fissati: bool) -> bool:
    """I messaggi fissati restano, salvo scelta esplicita del server."""
    return incluso_fissati or not fissato


def dividi(voci: list[tuple[int, float]]) -> tuple[list[list[int]], list[int]]:
    """Da (id, età in giorni): blocchi da 2 a 100 per i recenti e, al massimo MAX_SINGOLI, i singoli per i vecchi.
    Un recente rimasto solo (un blocco da 1) passa fra i singoli, sempre dentro il tetto."""
    recenti = [i for i, eta in voci if eta < MARGINE_BLOCCO_GIORNI]
    vecchi = [i for i, eta in voci if eta >= MARGINE_BLOCCO_GIORNI]
    blocchi = [recenti[k:k + MAX_GIRO_BLOCCO] for k in range(0, len(recenti), MAX_GIRO_BLOCCO)]
    singoli = vecchi
    if blocchi and len(blocchi[-1]) == 1:
        singoli = [*blocchi.pop(), *vecchi]
    return blocchi, singoli[:MAX_SINGOLI]


class Esito:
    """Quanto è successo in un giro; dopo MAX_403 rifiuti si ferma."""

    def __init__(self) -> None:
        self.cancellati = 0
        self.rifiuti = 0

    def vieta(self) -> None:
        self.rifiuti += 1

    @property
    def fermo(self) -> bool:
        return self.rifiuti >= MAX_403
