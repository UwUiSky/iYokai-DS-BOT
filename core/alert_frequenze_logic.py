"""
core/alert_frequenze_logic.py
=============================
Ogni quanti secondi controllano i watcher degli avvisi (ALR-034, 035). L'owner del bot può cambiarli con
variabili d'ambiente, ma mai sotto un minimo che protegge le quote dei servizi esterni (LIM-16, LIM-46).
Funzioni coperte: SPEC §10.1, §10.13 (#129 ALR-034, 035)
"""

from __future__ import annotations

import os

# nome: (variabile d'ambiente, predefinito, minimo) in secondi
FREQUENZE: dict[str, tuple[str, int, int]] = {
    "feed": ("ALERT_FEED_SECONDI", 300, 120),
    "twitch": ("ALERT_TWITCH_SECONDI", 90, 30),
    "youtube": ("ALERT_YOUTUBE_SECONDI", 300, 120),
    "kick": ("ALERT_KICK_SECONDI", 120, 60),
    "picarto": ("ALERT_PICARTO_SECONDI", 180, 60),
    "eventi": ("ALERT_EVENTI_TWITCH_SECONDI", 1800, 600),
}
MASSIMO = 86400


def intervallo(nome: str) -> int:
    """Secondi tra due controlli: la variabile se è un numero valido (alzata al minimo), altrimenti il predefinito."""
    variabile, predefinito, minimo = FREQUENZE[nome]
    try:
        valore = int(os.environ.get(variabile, "").strip())
    except ValueError:
        return predefinito
    return max(minimo, min(valore, MASSIMO))
