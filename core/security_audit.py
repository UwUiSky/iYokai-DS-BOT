"""
core/security_audit.py
======================
Chi ha fatto cosa, letto dal registro di controllo (audit log) di Discord.
Lo usano l'anti-nuke e l'anti-raid: l'autore di un evento non e' mai nel
payload dell'evento gateway, va cercato qui.

Il registro arriva spesso un attimo dopo l'evento: se la voce non c'e'
ancora si riprova, aspettando ogni volta i secondi di `attese`.
"""

from __future__ import annotations

import asyncio

import discord

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
    for attesa in attese:
        if attesa:
            await _aspetta(attesa)
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
