"""
core/lista_limiti_logic.py
==============================
Elenchi che possono crescere senza superare i limiti di Discord
(messaggio 2000, descrizione dell'embed 4096). Funzioni pure.
"""

from __future__ import annotations

from typing import Sequence


def righe_entro_limite(righe: Sequence[str], limite: int = 4000) -> tuple[str, int]:
    """
    Unisce le righe finché stanno nel limite. Restituisce il testo e
    quante righe sono rimaste fuori; se ne restano, in coda c'è
    "… e altre N". Una riga sola più lunga del limite viene tagliata.
    """
    usate: list[str] = []
    totale = 0
    for indice, riga in enumerate(righe):
        resto = len(righe) - indice
        costo = len(riga) + (1 if usate else 0)
        ultima = resto == 1
        riserva = 0 if ultima else len(f"\n… e altre {resto - 1}")
        if totale + costo + riserva <= limite:
            usate.append(riga)
            totale += costo
            continue
        if not usate:  # una riga sola più lunga del limite
            usate.append(riga[: max(limite - len(f"\n… e altre {resto - 1}") - 1, 1)] + "…")
            resto -= 1
        return "\n".join(usate) + (f"\n… e altre {resto}" if resto else ""), resto
    return "\n".join(usate), 0


def dividi_in_pagine(righe: Sequence[str], limite: int = 1900) -> list[str]:
    """
    Pagine di testo, ognuna entro `limite` caratteri, senza spezzare le
    righe (una riga più lunga del limite viene tagliata). Sempre almeno
    una pagina.
    """
    pagine: list[str] = []
    corrente: list[str] = []
    lunghezza = 0
    for riga in righe:
        if len(riga) > limite:
            riga = riga[: limite - 1] + "…"
        costo = len(riga) + (1 if corrente else 0)
        if corrente and lunghezza + costo > limite:
            pagine.append("\n".join(corrente))
            corrente, lunghezza, costo = [], 0, len(riga)
        corrente.append(riga)
        lunghezza += costo
    pagine.append("\n".join(corrente))
    return pagine
