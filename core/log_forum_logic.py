"""
core/log_forum_logic.py
=======================
Testi e limiti della vista dei log su un forum (un post per canale o per caso).
Funzioni pure, senza Discord né database.
Funzioni coperte: SPEC §8.17
"""

from __future__ import annotations

import json

DIM_CANALI = "canali"
DIM_CASI = "casi"
DIMENSIONI = (DIM_CANALI, DIM_CASI)

# Un forum con troppi post non si legge più: oltre il tetto i canali o i casi nuovi non hanno un post.
MAX_POST_PER_DIMENSIONE = 200
# Quanti eventi aspettano di essere scritti, in tutto il bot. Oltre, i nuovi si perdono dalla vista
# (restano nel database e nel canale dei log): un raid non deve riempire la memoria.
CODA_MAX = 500
# Dopo un errore di scrittura (permessi tolti, tag obbligatori che non si possono scegliere) la vista
# di quel forum si ferma per un po': un solo avviso nei log, non uno per ogni evento.
PAUSA_DOPO_ERRORE_SECONDI = 600.0
MAX_TITOLO = 100
MAX_DETTAGLI = 600
MAX_DESCRIZIONE = 1500


def titolo_post(dimensione: str, chiave: int, nome: str | None = None) -> str:
    """Il titolo del post (Discord tiene 100 caratteri)."""
    if dimensione == DIM_CASI:
        return f"Caso #{chiave}"
    return f"#{nome or chiave}"[:MAX_TITOLO]


def scegli_tag(tag_disponibili) -> object | None:
    """
    Il tag da mettere a un post nuovo di un forum con tag obbligatori: il primo che chiunque può usare,
    altrimenti il primo (il bot può gestire i thread). None se il forum non ha tag.
    """
    tag = list(tag_disponibili)
    liberi = [t for t in tag if not getattr(t, "moderated", False)]
    return (liberi or tag or [None])[0]


def _dettagli(details: dict | None) -> str:
    if not details:
        return ""
    testo = json.dumps(details, ensure_ascii=False).replace("`", "'")
    if len(testo) > MAX_DETTAGLI:
        testo = testo[: MAX_DETTAGLI - 1] + "…"
    return f"\n`{testo}`"


def descrizione_evento(
    event_type: str,
    *,
    actor_id: int | None = None,
    target_user_id: int | None = None,
    role_id: int | None = None,
    case_number: int | None = None,
    details: dict | None = None,
) -> str:
    """Una riga per l'evento: tipo, chi l'ha fatto, su chi, ruolo, caso e dettagli tagliati."""
    pezzi = [f"**{event_type}**"]
    if actor_id:
        pezzi.append(f"da <@{actor_id}>")
    if target_user_id:
        pezzi.append(f"su <@{target_user_id}>")
    if role_id:
        pezzi.append(f"ruolo <@&{role_id}>")
    if case_number:
        pezzi.append(f"(caso #{case_number})")
    return (" ".join(pezzi) + _dettagli(details))[:MAX_DESCRIZIONE]


def descrizione_caso(
    case_number: int,
    azione: str,
    *,
    user_id: int,
    moderator_id: int,
    motivo: str | None = None,
    revocato_da: int | None = None,
) -> str:
    """Il testo del post di un caso: apertura (con motivo) o revoca."""
    if revocato_da is not None:
        return f"**Caso #{case_number}** revocato da <@{revocato_da}>."
    testo = f"**Caso #{case_number}** · {azione}\nUtente: <@{user_id}> ({user_id})\nModeratore: <@{moderator_id}>"
    if motivo:
        testo += f"\nMotivo: {motivo}"
    return testo[:MAX_DESCRIZIONE]
