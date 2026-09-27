"""
core/backup_snapshot_logic.py
=================================
Logica pura (nessun I/O) dello snapshot settimanale utenti (SPEC.md
§11.10) — decide chi entra nello snapshot, senza toccare discord.py
né il database.
"""

from __future__ import annotations


def is_eligible_for_snapshot(
    is_bot: bool,
    member_role_ids: set[int],
    verified_role_id: int | None,
) -> bool:
    """
    True se questo membro va incluso nello snapshot settimanale.

    Un bot non è mai un "utente da ripristinare" — mai incluso.
    Se il server ha un ruolo verificato configurato (Verify Base,
    §4), solo chi lo possiede conta come "verificato" nello spirito
    dello schema. Se il server NON ha configurato Verify Base
    (verified_role_id is None), non esiste un concetto di
    "verificato" da applicare — includiamo chiunque non sia un bot,
    piuttosto che escludere silenziosamente un intero server dal
    backup utenti solo perché non usa quel modulo.

    Chi è bannato o kickato NON compare qui per costruzione: questa
    funzione riceve solo membri ATTUALMENTE presenti nel server
    (guild.members) — chi è stato bannato/kickato non è più un
    membro, quindi non arriva nemmeno a questo controllo.
    """
    if is_bot:
        return False
    if verified_role_id is None:
        return True
    return verified_role_id in member_role_ids
