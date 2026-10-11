"""
core/tempban_logic.py
=====================
Regole semplici del ban temporaneo con rientro e del ban in isolamento:
quali ruoli salvare al momento del ban e quali ridare al ritorno.
Funzioni coperte: SPEC §5.11, §5.12 (issue #138)
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

# Come si comporta un ban a tempo.
MODO_FUORI = "fuori"  # tempban classico: fuori fino alla scadenza
MODO_RIENTRO = "rientro"  # fuori, poi invito e ruoli ridati al ritorno
MODO_ISOLAMENTO = "isolamento"  # resta nel server, vede un solo canale
MODI = (MODO_FUORI, MODO_RIENTRO, MODO_ISOLAMENTO)

# Un invito che deve valere oltre la scadenza non scade mai: si usa una sola volta.
INVITO_MAX_USI = 1
INVITO_MAX_ETA = 0


@dataclass(frozen=True)
class RuoloInfo:
    id: int
    position: int
    managed: bool = False
    is_default: bool = False


def ruoli_da_salvare(ruoli: Iterable[RuoloInfo]) -> list[int]:
    """Gli ID dei ruoli da ricordare al ban: non @everyone, non gestiti da integrazioni."""
    return [r.id for r in ruoli if not r.is_default and not r.managed]


def ruoli_da_ridare(
    salvati: Iterable[int], ruoli_server: Iterable[RuoloInfo], posizione_bot: int
) -> list[int]:
    """
    Dei ruoli salvati, quelli che si possono ridare: esistono ancora, sono
    sotto il ruolo del bot, non sono gestiti da integrazioni né @everyone.
    """
    esistenti = {r.id: r for r in ruoli_server}
    ridare = []
    for ruolo_id in salvati:
        ruolo = esistenti.get(ruolo_id)
        if ruolo is None or ruolo.is_default or ruolo.managed:
            continue
        if ruolo.position >= posizione_bot:
            continue
        ridare.append(ruolo_id)
    return ridare


def ruoli_da_tenere_in_isolamento(
    ruoli_membro: Iterable[RuoloInfo], posizione_bot: int
) -> list[int]:
    """
    Ruoli che restano al membro isolato perché il bot non può toglierli
    (gestiti da integrazioni o non sotto il bot). Gli altri si tolgono e
    si ridanno alla fine.
    """
    return [
        r.id
        for r in ruoli_membro
        if not r.is_default and (r.managed or r.position >= posizione_bot)
    ]


def testo_fine(timestamp: int) -> str:
    """Data di fine nel formato di Discord (si adatta al fuso di chi legge)."""
    return f"<t:{timestamp}:F> (<t:{timestamp}:R>)"
