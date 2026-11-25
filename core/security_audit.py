"""
core/security_audit.py
======================
Chi ha fatto cosa, letto dal registro di controllo (audit log) di Discord.
Lo usano l'anti-nuke e l'anti-raid: l'autore di un evento non e' mai nel
payload dell'evento gateway, va cercato qui.

Il registro arriva spesso un attimo dopo l'evento: se la voce non c'e'
ancora si riprova, aspettando ogni volta i secondi di `attese`.

Le voci arrivano anche da sole, con l'evento `on_audit_log_entry_create`: `registra_voce`
le tiene in memoria per qualche decina di secondi e `resolve_voce` guarda prima lì. In un
nuke con decine di cancellazioni in pochi secondi così non si fanno decine di letture del
registro (Discord le limita) e non restano cancellazioni senza autore.
"""

from __future__ import annotations

import asyncio
import time

import discord

from core.bounded_cache import BoundedCache

# Finestra di ricerca nell'audit log: l'evento gateway e la riga di
# audit log corrispondente arrivano quasi sempre entro pochi secondi
# l'uno dall'altro, ma non sono garantiti nello stesso istante.
LOOKBACK_REGISTRO_SECONDI = 10

# Secondi di attesa prima di ogni lettura del registro di controllo:
# subito, poi altre due volte. Per le uscite dal server (quasi sempre
# volontarie, senza voce nel registro) basta una sola rilettura.
ATTESE_REGISTRO = (0, 1, 1)
ATTESE_REGISTRO_USCITA = (0, 1.5)


async def _aspetta(secondi: float) -> None:
    await asyncio.sleep(secondi)


# (server, azione, oggetto) -> (autore, momento). Per ogni azione c'è anche la chiave con oggetto None: l'ultima.
_RECENTI: BoundedCache[tuple[int, int, int | None], tuple[int, float]] = BoundedCache(max_size=5000)


def registra_voce(entry: discord.AuditLogEntry) -> None:
    """Un evento `on_audit_log_entry_create`: si tiene chi ha fatto cosa, per `resolve_voce`."""
    guild = getattr(entry, "guild", None)
    autore = getattr(entry, "user_id", None)
    if guild is None or autore is None:
        return
    oggetto = getattr(getattr(entry, "target", None), "id", None)
    ora = time.monotonic()
    azione = entry.action.value if hasattr(entry.action, "value") else int(entry.action)
    _RECENTI.set((guild.id, azione, oggetto), (autore, ora))
    _RECENTI.set((guild.id, azione, None), (autore, ora))


def _voce_in_memoria(guild_id: int, action, target_id: int | None) -> tuple[int, int | None] | None:
    azione = action.value if hasattr(action, "value") else int(action)
    trovata = _RECENTI.get((guild_id, azione, target_id))
    if trovata is None or time.monotonic() - trovata[1] > LOOKBACK_REGISTRO_SECONDI:
        return None
    return trovata[0], target_id


async def resolve_voce(
    guild: discord.Guild,
    action: discord.AuditLogAction,
    target_id: int | None = None,
    attese: tuple[float, ...] = ATTESE_REGISTRO,
) -> tuple[int, int | None] | None:
    """
    Cerca nel registro di controllo chi ha fatto questa azione
    (se `target_id` e' dato, solo la voce che riguarda quell'oggetto).
    Restituisce (autore, oggetto dell'azione). None se non si trova o
    se Discord non lascia leggere il registro: mai un'eccezione che
    blocchi l'evento.
    """
    now = discord.utils.utcnow()
    for tentativo, attesa in enumerate(attese):
        if attesa:
            await _aspetta(attesa)
        in_memoria = _voce_in_memoria(guild.id, action, target_id)
        if in_memoria is not None:
            return in_memoria
        if tentativo == 0 and len(attese) > 1:
            continue  # il primo giro guarda solo in memoria: la voce arriva da sola, di solito entro un secondo
        try:
            async for entry in guild.audit_logs(action=action, limit=10):
                if (now - entry.created_at).total_seconds() > LOOKBACK_REGISTRO_SECONDI:
                    break
                oggetto = getattr(entry.target, "id", None)
                if target_id is not None and oggetto != target_id:
                    continue
                return entry.user_id, oggetto
        except discord.HTTPException:
            return None
    return None
