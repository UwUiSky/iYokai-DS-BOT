"""
core/autorole_logic.py
======================
Decide quali ruoli dare e quando (NF-07, SPEC §22.1-22.3), con le
condizioni su altri ruoli e il ruolo ridato se tolto (catalogo #123,
RUO-034..038). Funzioni semplici, provabili senza Discord.
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
    richiesti: tuple[int, ...] = ()
    esclusi: tuple[int, ...] = ()
    ridai: bool = False


def regola_vale_per(regola: RegolaAutoruolo, ruoli_posseduti: set[int]) -> bool:
    """La regola vale se il membro ha almeno uno dei ruoli richiesti (se ce ne sono) e nessun escluso."""
    if regola.richiesti and not ruoli_posseduti.intersection(regola.richiesti):
        return False
    return not ruoli_posseduti.intersection(regola.esclusi)


def scegli_in_ordine(regole: Iterable[RegolaAutoruolo], ruoli_posseduti: set[int]) -> list[int]:
    """
    I ruoli delle regole che valgono, valutate una alla volta come se i ruoli già
    scelti fossero dati: due regole che si escludono a vicenda non danno entrambi i
    ruoli, una regola che ne richiede un'altra la segue. Un ruolo non si sceglie se
    toglierebbe il diritto a uno già scelto. Si ripete finché cambia qualcosa
    (ogni giro aggiunge un ruolo: finisce sempre).
    """
    regole = list(regole)
    attuali = set(ruoli_posseduti)
    scelte: list[RegolaAutoruolo] = []
    cambiato = True
    while cambiato:
        cambiato = False
        for regola in regole:
            if regola.role_id in attuali or not regola_vale_per(regola, attuali):
                continue
            if any(regola.role_id in scelta.esclusi for scelta in scelte):
                continue
            scelte.append(regola)
            attuali.add(regola.role_id)
            cambiato = True
    return [r.role_id for r in scelte]


def ruoli_da_ridare_se_tolti(
    regole: Iterable[RegolaAutoruolo], prima: set[int], dopo: set[int]
) -> list[int]:
    """I ruoli automatici con `ridai` appena tolti a un membro che ne ha ancora diritto."""
    tolti = prima - dopo
    return scegli_in_ordine([r for r in regole if r.ridai and r.role_id in tolti], dopo)


def ruoli_da_sincronizzare(regole: Iterable[RegolaAutoruolo], ruoli_posseduti: set[int]) -> list[int]:
    """Per un membro già nel server: i ruoli automatici che gli mancano (senza ritardo)."""
    return scegli_in_ordine(regole, ruoli_posseduti)


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
    regole = list(regole)
    # Con un ritardo la condizione si controlla allo scatto.
    dopo = [
        (r.role_id, r.delay_seconds) for r in regole if r.delay_seconds > 0 and r.role_id not in ruoli_posseduti
    ]
    subito = scegli_in_ordine([r for r in regole if r.delay_seconds == 0], ruoli_posseduti)
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
