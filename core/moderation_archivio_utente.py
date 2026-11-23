"""
core/moderation_archivio_utente.py
==================================
L'archivio dei messaggi di un utente (LOG-029, D121): a ogni sanzione si copia, legato al caso, ciò che il registro
eventi ha già salvato sui messaggi di quell'utente negli ultimi 3 giorni, su tutti i canali che il server registra
(cancellati e modificati). Nessuna raccolta nuova, nessuna chiamata alla cronologia di Discord. Il registro eventi
non conserva il testo dei messaggi (D74): l'archivio dice quando, dove e che cosa è successo, con il collegamento al
messaggio. Resta finché esiste il caso. Si apre solo dallo staff (`/mod-casi caso chat archivio:sì`).
Funzioni coperte: LOG-029
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from core.database import db
from core.repositories.event_log_repo import event_log_repo

logger = logging.getLogger("iyokai.moderation.archivio_utente")

GIORNI = 3
MAX_EVENTI = 500
MAX_BYTE = 1_000_000
TIPI = {"message_delete": "cancellato", "message_edit": "modificato"}


def costruisci(eventi, utente_id: int) -> str:
    """Testo dell'archivio: una riga per evento, dal più vecchio. Solo identificatori, nessun testo di messaggi."""
    righe = [
        f"Archivio dei messaggi dell'utente {utente_id}, ultimi {GIORNI} giorni.",
        "Il registro del bot non conserva il testo dei messaggi: restano quando, dove e che cosa è successo.",
        "",
    ]
    for e in sorted(eventi, key=lambda x: x.created_at):
        quando = e.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        canale = f"<#{e.channel_id}>" if e.channel_id else "canale sconosciuto"
        mid = (e.details or {}).get("message_id")
        righe.append(f"{quando} | messaggio {TIPI.get(e.event_type, e.event_type)} | {canale} | id messaggio {mid}")
    return "\n".join(righe)


async def salva(guild_id: int, case_number: int, utente_id: int) -> int:
    """Salva l'archivio per il caso. Restituisce quanti eventi ci sono; mai solleva (il caso c'è già)."""
    try:
        da = datetime.now(timezone.utc) - timedelta(days=GIORNI)
        eventi = await event_log_repo.get_events_by_user(guild_id, utente_id, limit=MAX_EVENTI, since=da)
        eventi = [e for e in eventi if e.event_type in TIPI]
        if not eventi:
            return 0
        testo = costruisci(eventi, utente_id).encode("utf-8")[:MAX_BYTE].decode("utf-8", errors="ignore")
        await db.pool.execute(
            "INSERT INTO moderation_archivio_utente (guild_id, case_number, user_id, eventi, contenuto) "
            "VALUES ($1, $2, $3, $4, $5) ON CONFLICT (guild_id, case_number) DO NOTHING",
            guild_id, case_number, utente_id, len(eventi), testo.encode("utf-8"),
        )
        return len(eventi)
    except Exception:
        logger.warning("Archivio dell'utente non salvato (caso %s).", case_number, exc_info=True)
        return 0


async def leggi(guild_id: int, case_number: int) -> tuple[bytes, int] | None:
    """(contenuto, eventi) oppure None."""
    r = await db.pool.fetchrow(
        "SELECT contenuto, eventi FROM moderation_archivio_utente WHERE guild_id = $1 AND case_number = $2",
        guild_id, case_number,
    )
    return (bytes(r["contenuto"]), r["eventi"]) if r else None
