"""
core/moderation_casi_logic.py
=============================
Regole dei casi di moderazione che non hanno bisogno di Discord: durata nuova di un caso,
testo dell'esportazione dei casi di un membro.
Funzioni coperte: SPEC §5.3 (MOD-012, MOD-043)
"""

from __future__ import annotations

from datetime import datetime

# Tipi di caso che hanno una fine e quindi una durata da cambiare.
TIPI_CON_DURATA = ("tempban", "timeout", "mute_role")
MAX_TIMEOUT_S = 28 * 86400  # limite di Discord per il timeout


def errore_durata_caso(tipo: str, attivo: bool, secondi: int) -> str | None:
    """None se si può cambiare la durata, altrimenti il motivo (in italiano)."""
    if tipo not in TIPI_CON_DURATA:
        return "Questo tipo di caso non ha una durata: si cambia solo per tempban, timeout e mute."
    if not attivo:
        return "Il caso è già finito o è stato revocato."
    if tipo == "timeout" and secondi > MAX_TIMEOUT_S:
        return "Il timeout di Discord dura al massimo 28 giorni."
    return None


def _data(valore: datetime | None) -> str:
    return valore.strftime("%d/%m/%Y %H:%M") if valore else "-"


def testo_esportazione(utente_id: int, casi, note) -> str:
    """Testo semplice con tutti i casi e le note di un membro, dal più vecchio."""
    righe = [f"Casi di moderazione dell'utente {utente_id}", f"Casi: {len(casi)} - Note: {len(note)}", ""]
    for c in casi:
        stato = "attivo" if c.active else "finito/revocato"
        durata = f", durata {c.duration_seconds} s" if c.duration_seconds else ""
        righe.append(
            f"Caso #{c.case_number} - {c.action_type} - {_data(c.created_at)} - "
            f"moderatore {c.moderator_id} - {stato}{durata}"
        )
        righe.append(f"  Motivo: {c.reason or 'nessuno'}")
    if note:
        righe += ["", "Note"]
        for n in note:
            righe.append(f"Nota #{n.id} - {_data(n.created_at)} - moderatore {n.moderator_id}")
            righe.append(f"  {n.note}")
    return "\n".join(righe) + "\n"
