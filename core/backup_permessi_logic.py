"""
core/backup_permessi_logic.py
=============================
Chi può creare e chi può caricare un backup: tre livelli per server.
Creare (salvare, esportare, pubblicare un modello) non cambia il server;
caricare (ricaricare, importare, usare un modello, ripristinare) sì.
Funzioni coperte: BKP-018
"""

from __future__ import annotations

SETTING_LIVELLO = "backup_livello_permessi"

LIVELLO_ADMIN_TUTTO = "admin_tutto"
LIVELLO_ADMIN_CREA = "admin_crea"
LIVELLO_SOLO_OWNER = "solo_owner"
LIVELLO_PREDEFINITO = LIVELLO_ADMIN_CREA

LIVELLI = {
    LIVELLO_ADMIN_TUTTO: "Gli admin creano e caricano",
    LIVELLO_ADMIN_CREA: "Gli admin creano, solo l'owner carica",
    LIVELLO_SOLO_OWNER: "Solo l'owner crea e carica",
}

AZIONE_CREA = "crea"
AZIONE_CARICA = "carica"


def puo(livello: str | None, azione: str, *, e_owner: bool, e_admin: bool) -> bool:
    """True se chi ha questi ruoli può fare l'azione al livello dato."""
    if e_owner:
        return True
    if not e_admin:
        return False
    livello = livello if livello in LIVELLI else LIVELLO_PREDEFINITO
    if livello == LIVELLO_SOLO_OWNER:
        return False
    if livello == LIVELLO_ADMIN_CREA:
        return azione == AZIONE_CREA
    return True
