"""
core/autorole_logic.py
======================
Decide quali ruoli dare e quando (NF-07, SPEC §22.1-22.3). Funzioni
semplici, provabili senza Discord.
Funzioni coperte: SPEC §22 (NF-07)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

# Quante regole di ruolo automatico per server (il tetto dei ruoli di Discord è 250:
# qui basta molto meno e il comando resta leggibile).
MAX_REGOLE = 20
# Un ruolo può essere dato al massimo dopo 7 giorni.
MAX_RITARDO_SECONDI = 7 * 24 * 3600
# I ruoli di chi esce si tengono al massimo 30 giorni (dato personale, NF-04).
MAX_GIORNI_MEMORIA = 30
GIORNI_MEMORIA_PREDEFINITI = 30


@dataclass(frozen=True)
class RegolaAutoruolo:
    role_id: int
    delay_seconds: int = 0


def piano_ingresso(
    regole: Iterable[RegolaAutoruolo],
    *,
    is_bot: bool,
    ruoli_posseduti: set[int],
) -> tuple[list[int], list[tuple[int, int]]]:
    """
    Per chi è appena entrato: (ruoli da dare subito, [(ruolo, secondi di attesa)]).
    Niente ai bot; niente per i ruoli che il membro ha già.
    """
    if is_bot:
        return [], []
    subito: list[int] = []
    dopo: list[tuple[int, int]] = []
    for regola in regole:
        if regola.role_id in ruoli_posseduti:
            continue
        if regola.delay_seconds > 0:
            dopo.append((regola.role_id, regola.delay_seconds))
        else:
            subito.append(regola.role_id)
    return subito, dopo


def ruoli_da_ricordare(ruoli_membro: Iterable) -> list[int]:
    """Gli ID dei ruoli di chi esce che valgono la pena: niente @everyone né ruoli gestiti da integrazioni."""
    return [r.id for r in ruoli_membro if not r.is_default() and not r.managed]


def ruoli_da_ridare(
    ruoli_ricordati: list[int], uscito_il: datetime, ora: datetime, giorni: int
) -> list[int]:
    """I ruoli ricordati, se il rientro è entro `giorni` (mai oltre 30); altrimenti niente."""
    finestra = min(max(giorni, 1), MAX_GIORNI_MEMORIA)
    if ora - uscito_il > timedelta(days=finestra):
        return []
    return list(ruoli_ricordati)


def membro_in_attesa(in_attesa_discord: bool, verifica_attiva: bool, ha_ruolo_verificato: bool) -> bool:
    """
    Il ruolo automatico aspetta se il membro non ha ancora accettato le regole
    di Discord (Membership Screening) o se la verifica del server è attiva e
    il ruolo di verificato non è ancora arrivato.
    """
    if in_attesa_discord:
        return True
    return verifica_attiva and not ha_ruolo_verificato
