"""
core/duration_logic.py
=========================
Parsing e formattazione di durate testuali ("30m", "12h", "7d", "2w")
— logica pura, nessuna dipendenza da Discord o dal database.

Vissuta originariamente dentro cogs/moderation/_shared.py (per
tempban/timeout); spostata qui quando è arrivato un secondo
consumatore reale che non ha nulla a che fare con la moderazione
(cogs/utility/reminders.py) — non ha senso che un modulo di utilità
debba importare da dentro il modulo di moderazione per una funzione
di parsing generica. cogs/moderation/_shared.py ora la re-esporta
(stessa funzione, non una copia), così i chiamanti esistenti che
importavano da lì non hanno dovuto cambiare nulla.
"""

from __future__ import annotations


def format_duration(seconds: int) -> str:
    """Converte un numero di secondi in una stringa leggibile in italiano."""
    if seconds < 60:
        return f"{seconds} secondi"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minuti"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} ore"
    days = hours // 24
    return f"{days} giorni"


_DURATION_UNITS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
}


def parse_duration(text: str) -> int:
    """
    Converte una durata scritta come "30m", "12h", "7d", "2w" in
    secondi. Solleva ValueError con un messaggio comprensibile se il
    formato non è valido — il chiamante lo intercetta e lo mostra
    all'utente così com'è, non serve tradurlo di nuovo.

    Formato accettato: un numero intero positivo seguito da UNA
    lettera tra s/m/h/d/w (secondi/minuti/ore/giorni/settimane).
    Niente numeri decimali, niente combinazioni tipo "1h30m": tenerlo
    semplice riduce gli errori di parsing e copre comunque il 99%
    dei casi d'uso reali.
    """
    text = text.strip().lower()
    if len(text) < 2:
        raise ValueError(
            "Formato durata non valido. Esempi validi: 30m, 12h, 7d, 2w"
        )

    unit = text[-1]
    number_part = text[:-1]

    if unit not in _DURATION_UNITS:
        raise ValueError(
            f"Unità di tempo '{unit}' non riconosciuta. "
            f"Usa: s (secondi), m (minuti), h (ore), d (giorni), w (settimane)"
        )

    if not number_part.isdigit():
        raise ValueError(
            "La durata deve essere un numero intero positivo seguito "
            "dall'unità, es. 30m, 12h, 7d"
        )

    value = int(number_part)
    if value <= 0:
        raise ValueError("La durata deve essere maggiore di zero.")

    return value * _DURATION_UNITS[unit]
