"""
core/ticket_log_logic.py
========================
Il log delle azioni sui ticket (TKT-076): quali azioni esistono, come si leggono dal comando e come si
puliscono i testi che finiscono nel log. Niente Discord, niente database.
Funzioni coperte: SPEC §13 (TKT-076)
"""

from __future__ import annotations

# Un interruttore per azione. «voto» porta anche la risposta al questionario (TKT-066).
AZIONI = ("creato", "chiuso", "riaperto", "rinominato", "eliminato", "preso", "passato", "priorita", "voto")
TUTTE = "tutte"
MAX_DETTAGLIO = 1024  # un campo di embed


class ErroreLog(ValueError):
    """Azione sconosciuta: il testo è per chi amministra."""


def azioni_scelte(nome: str) -> tuple[str, ...]:
    """`tutte` oppure il nome di una sola azione."""
    nome = (nome or "").strip().lower()
    if nome == TUTTE:
        return AZIONI
    if nome not in AZIONI:
        raise ErroreLog("Azione sconosciuta: " + ", ".join(AZIONI) + " o tutte.")
    return (nome,)


def dettaglio_sicuro(testo: str | None) -> str | None:
    """Un testo scelto da un utente (nuovo nome, motivo, risposta) pronto per un campo del log: senza caratteri di
    controllo o invisibili, tagliato a 1024. Le menzioni sono spente comunque dall'invio (allowed_mentions)."""
    import unicodedata

    pulito = "".join(c for c in (testo or "") if c in "\n " or (c.isprintable() and unicodedata.category(c) not in ("Cf", "Cc")))
    pulito = pulito.replace("`", "'").strip()
    if not pulito:
        return None
    return pulito if len(pulito) <= MAX_DETTAGLIO else pulito[: MAX_DETTAGLIO - 1] + "…"
