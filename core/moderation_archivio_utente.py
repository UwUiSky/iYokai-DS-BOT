"""
core/moderation_archivio_utente.py
==================================
L'archivio dei messaggi di un utente (LOG-029, D121): a ogni sanzione si copia, legato al caso, ciò che il registro
eventi ha già salvato sui messaggi di quell'utente negli ultimi 3 giorni, su tutti i canali che il server registra
(cancellati e modificati). Nessuna raccolta nuova, nessuna chiamata alla cronologia di Discord. Il registro eventi
non conserva il testo dei messaggi in chiaro: il file dice quando, dove e che cosa è successo. Il TESTO (D122) si copia
CIFRATO dalla finestra di 7 giorni (`core/log_testi_servizio.py`) in `testi_cifrato`: resta finché esiste il caso e si
decifra solo all'apertura dalla pagina del pannello. Si apre solo dallo staff (`/mod-casi caso chat archivio:sì`).
Funzioni coperte: LOG-029 (D121, D122)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from core import log_testi_logic, log_testi_servizio
from core.database import db
from core.repositories.event_log_repo import event_log_repo

logger = logging.getLogger("iyokai.moderation.archivio_utente")

GIORNI = 3
MAX_EVENTI = 500
MAX_BYTE = 1_000_000
TIPI = {"message_delete": "cancellato", "message_edit": "modificato"}


def costruisci(eventi, utente_id: int) -> str:
    """Testo dell'archivio: una riga per evento, dal più vecchio. Solo identificatori, nessun testo di messaggi (il testo sta cifrato a parte, D122)."""
    righe = [
        f"Archivio dei messaggi dell'utente {utente_id}, ultimi {GIORNI} giorni.",
        "Questo file non contiene il testo dei messaggi: restano quando, dove e che cosa è successo. Il testo, cifrato, si apre dal pannello web.",
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
        testi = await _testi(guild_id, case_number, utente_id)  # D122: cifrati, solo con la chiave
        if not eventi and testi is None:
            return 0
        testo = costruisci(eventi, utente_id).encode("utf-8")[:MAX_BYTE].decode("utf-8", errors="ignore")
        await db.pool.execute(
            "INSERT INTO moderation_archivio_utente (guild_id, case_number, user_id, eventi, contenuto, testi_cifrato, testi_messaggi) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7) ON CONFLICT (guild_id, case_number) DO NOTHING",
            guild_id, case_number, utente_id, len(eventi), testo.encode("utf-8"),
            testi[0] if testi else None, testi[1] if testi else 0,
        )
        return len(eventi)
    except Exception:
        logger.warning("Archivio dell'utente non salvato (caso %s).", case_number, exc_info=True)
        return 0


async def _testi(guild_id: int, case_number: int, utente_id: int):
    try:
        return await log_testi_servizio.testi_per_caso(guild_id, case_number, utente_id)
    except Exception:  # noqa: BLE001 - senza testo il resto dell'archivio si salva lo stesso
        logger.warning("Testi dell'archivio non copiati (caso %s).", case_number, exc_info=True)
        return None


async def leggi_testi(guild_id: int, case_number: int):
    """(utente, messaggi) decifrati per la pagina del pannello, o None (non c'è, manca la chiave, dato alterato)."""
    r = await db.pool.fetchrow(
        "SELECT testi_cifrato FROM moderation_archivio_utente WHERE guild_id = $1 AND case_number = $2",
        guild_id, case_number,
    )
    if r is None or not r["testi_cifrato"]:
        return None
    return log_testi_logic.apri_archivio(r["testi_cifrato"], guild_id, case_number, log_testi_servizio.chiave())


async def numero_testi(guild_id: int, case_number: int) -> int:
    """Quanti messaggi con testo cifrato ci sono nell'archivio del caso (0 = nessuno)."""
    return int(await db.pool.fetchval(
        "SELECT testi_messaggi FROM moderation_archivio_utente WHERE guild_id = $1 AND case_number = $2 AND testi_cifrato IS NOT NULL",
        guild_id, case_number,
    ) or 0)


async def leggi(guild_id: int, case_number: int) -> tuple[bytes, int] | None:
    """(contenuto, eventi) oppure None."""
    r = await db.pool.fetchrow(
        "SELECT contenuto, eventi FROM moderation_archivio_utente WHERE guild_id = $1 AND case_number = $2",
        guild_id, case_number,
    )
    return (bytes(r["contenuto"]), r["eventi"]) if r else None
