"""
core/verify_paese_logic.py
==========================
Paese dell'account nella verifica web (D53), senza rete né Discord: i paesi del
server, il codice dal record della banca dati e la regola della soglia.
Il paese è un indizio, mai un motivo di blocco: la regola dice solo quando
mettere in attesa e far decidere allo staff.
Funzioni coperte: SPEC §4.2 (paese, D53)
"""

from __future__ import annotations

import re

MAX_PAESI = 10
_CODICE = re.compile(r"^[A-Za-z]{2}$")

STATO_OK = "ok"
STATO_ATTESA = "attesa"
STATO_APPROVATA = "approvata"
STATO_RIFIUTATA = "rifiutata"

MINUTI_DI_BASE = 10


def leggi_paesi(testo) -> frozenset[str]:
    """I codici ISO (2 lettere, maiuscole) di un elenco «IT, CH». Le voci storte si ignorano."""
    if not isinstance(testo, str):
        return frozenset()
    voci = (v.strip() for v in testo.split(","))
    return frozenset(v.upper() for v in voci if _CODICE.match(v))


def paesi_validi(valore) -> bool:
    """Controllo dello schema: vuoto, oppure fino a 10 codici di 2 lettere separati da virgola."""
    if not isinstance(valore, str):
        return False
    if valore.strip() == "":
        return True
    voci = [v.strip() for v in valore.split(",")]
    return len(voci) <= MAX_PAESI and all(_CODICE.match(v) for v in voci)


def codice_da_record(record) -> str | None:
    """Il codice del paese dal record MMDB (DB-IP o GeoLite2). Nient'altro del record viene letto."""
    if not isinstance(record, dict):
        return None
    for chiave in ("country", "registered_country"):
        sezione = record.get(chiave)
        codice = sezione.get("iso_code") if isinstance(sezione, dict) else None
        if isinstance(codice, str) and _CODICE.match(codice):
            return codice.upper()
    return None


def tenere_in_attesa(da_fuori: bool, verifiche_da_fuori: int, soglia: int) -> bool:
    """
    `verifiche_da_fuori`: quelle nella finestra, compresa questa. Si ferma solo chi viene
    da fuori paese e solo a soglia raggiunta. Soglia 0 = funzione spenta.
    """
    return soglia > 0 and da_fuori and verifiche_da_fuori >= soglia
