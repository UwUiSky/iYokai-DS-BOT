"""
core/voice_azioni_ruoli.py
==========================
Quali azioni sul proprio canale vocale temporaneo può fare il proprietario, per ruolo (VOC-017). Si guarda al
contrario: per ogni azione l'elenco dei ruoli a cui è tolta. Chi non ha nessun ruolo nell'elenco può tutto, come
prima. Chi ha il permesso «Gestisci canali» non è mai fermato (è lo staff). Un solo punto (D16): `/admin-vocali
opzioni` e il pannello web leggono e scrivono da qui.
Funzioni coperte: VOC-017
Dipende da: core/database.py (impostazioni del server)
"""

from __future__ import annotations

AZIONI = (
    "rename", "limit", "lock", "unlock", "kick", "permit", "deny", "bitrate", "nascondi", "invita", "stato", "transfer",
)
CHIAVE = "voice_azioni_vietate"  # {azione: [id ruolo, ...]}
MAX_RUOLI_PER_AZIONE = 10


class AzioneNonValida(ValueError):
    """L'azione o il ruolo non vanno bene. Il messaggio è la chiave del testo per l'utente."""


def azione_permessa(vietate: dict[str, list[int]], azione: str, ruoli_utente: set[int]) -> bool:
    """Falso se uno dei ruoli di chi agisce è nell'elenco dei vietati per quell'azione."""
    return not (set(vietate.get(azione, ())) & ruoli_utente)


def pulisci(grezzo) -> dict[str, list[int]]:
    """Legge il valore salvato senza fidarsi: solo azioni note, solo numeri interi, mai più di 10 ruoli."""
    if not isinstance(grezzo, dict):
        return {}
    pulito: dict[str, list[int]] = {}
    for azione, ruoli in grezzo.items():
        if azione not in AZIONI or not isinstance(ruoli, list):
            continue
        validi = [r for r in ruoli if isinstance(r, int) and not isinstance(r, bool) and 0 < r < 2**63]
        if validi:
            pulito[azione] = list(dict.fromkeys(validi))[:MAX_RUOLI_PER_AZIONE]
    return pulito


def con_modifica(vietate: dict[str, list[int]], azione: str, ruolo_id: int, consenti: bool) -> dict[str, list[int]]:
    """La mappa nuova dopo «ruolo può / non può fare azione». Non cambia quella data."""
    if azione not in AZIONI:
        raise AzioneNonValida("voicetemp_azione_sconosciuta")
    nuova = {a: list(r) for a, r in vietate.items()}
    attuali = nuova.get(azione, [])
    if consenti:
        attuali = [r for r in attuali if r != ruolo_id]
    elif ruolo_id not in attuali:
        if len(attuali) >= MAX_RUOLI_PER_AZIONE:
            raise AzioneNonValida("voicetemp_troppi_ruoli_vietati")
        attuali = [*attuali, ruolo_id]
    if attuali:
        nuova[azione] = attuali
    else:
        nuova.pop(azione, None)
    return nuova


async def leggi(guild_id: int) -> dict[str, list[int]]:
    from core.database import db

    return pulisci(await db.get_guild_setting(guild_id, CHIAVE, None))


async def imposta(guild_id: int, azione: str, ruolo_id: int, consenti: bool, changed_by: int | None) -> dict[str, list[int]]:
    """Cambia una voce e salva (con lo storico). Una mappa vuota toglie la chiave."""
    from core.database import db

    nuova = con_modifica(await leggi(guild_id), azione, ruolo_id, consenti)
    if nuova:
        await db.set_guild_setting(guild_id, CHIAVE, nuova, changed_by=changed_by)
    elif await db.get_guild_setting(guild_id, CHIAVE, None) is not None:
        await db.remove_guild_setting(guild_id, CHIAVE, changed_by=changed_by)
    return nuova
