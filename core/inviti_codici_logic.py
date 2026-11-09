"""
core/inviti_codici_logic.py
===========================
Logica pura dei codici d'invito (D69 B12): righe dell'elenco, pagine, quali inviti cancellare.
Nessuna dipendenza da discord.py: gli inviti sono oggetti con code, uses, max_uses, channel_id, expires_at.
Funzioni coperte: catalogo UTL-166, 167, 174, 180, 181
"""

from __future__ import annotations

from dataclasses import dataclass

CODICI_PER_PAGINA = 10
MAX_INVITI_SERVER = 1000  # tetto di Discord (LIM-36)
MAX_USI_INVITO = 100
MAX_CANCELLAZIONI_PER_GIRO = 200  # a un invito al secondo: circa tre minuti
MAX_ETICHETTE_SERVER = 500
MAX_ETICHETTA = 50


@dataclass(frozen=True)
class InvitoVisto:
    codice: str
    usi: int
    usi_massimi: int
    canale_id: int | None
    scade_il: int | None  # timestamp, None se non scade
    creatore_id: int | None


def da_invito(invito) -> InvitoVisto:
    """Dall'invito di discord.py (o da un oggetto con gli stessi campi) a un valore semplice."""
    scade = getattr(invito, "expires_at", None)
    canale = getattr(invito, "channel", None)
    creatore = getattr(invito, "inviter", None)
    return InvitoVisto(
        codice=invito.code, usi=invito.uses or 0, usi_massimi=invito.max_uses or 0,
        canale_id=getattr(canale, "id", None), scade_il=int(scade.timestamp()) if scade else None,
        creatore_id=getattr(creatore, "id", None),
    )


def pagine(totale: int, per_pagina: int = CODICI_PER_PAGINA) -> int:
    return max(1, (totale + per_pagina - 1) // per_pagina)


def riga_codice(i: InvitoVisto, etichetta: str | None) -> str:
    usi = f"{i.usi}/{i.usi_massimi}" if i.usi_massimi else f"{i.usi}"
    scade = f" · scade <t:{i.scade_il}:R>" if i.scade_il else ""
    canale = f" · <#{i.canale_id}>" if i.canale_id else ""
    nome = f" **{etichetta}**" if etichetta else ""
    return f"`{i.codice}`{nome} · usi {usi}{canale}{scade}"


def da_cancellare(
    inviti: list[InvitoVisto], *, codice: str | None = None, usi_sotto: int | None = None,
    canale_id: int | None = None, protetti: set[str] = frozenset(),
) -> list[InvitoVisto]:
    """Gli inviti da togliere secondo UN solo criterio. I codici protetti (link personali) restano."""
    criteri = [c is not None for c in (codice, usi_sotto, canale_id)]
    if sum(criteri) != 1:
        return []
    scelti = []
    for i in inviti:
        if i.codice in protetti:
            continue
        if codice is not None and i.codice != codice:
            continue
        if usi_sotto is not None and i.usi >= usi_sotto:
            continue
        if canale_id is not None and i.canale_id != canale_id:
            continue
        scelti.append(i)
    return scelti
