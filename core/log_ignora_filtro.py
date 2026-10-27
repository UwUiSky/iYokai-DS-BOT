"""
core/log_ignora_filtro.py
=========================
Applica l'elenco di /log ignora (canali, categorie, utenti, ruoli) agli
eventi dei log che non sono messaggi: voce, canali, thread, membri.
Funzioni coperte: SPEC §18.6
"""

from __future__ import annotations

from core.message_log_logic import evento_ignorato
from core.repositories.log_ignora_repo import log_ignora_repo


async def evento_da_ignorare(guild: discord.Guild, canale=None, membro=None, canali_extra=()) -> bool:
    """/log ignora (SPEC §18.6): canali, categorie, utenti e ruoli valgono per tutti i log."""
    ignorati = await log_ignora_repo.carica(guild.id)
    if not (ignorati.canali or ignorati.utenti or ignorati.ruoli):
        return False
    ids = [getattr(c, "id", None) for c in (canale, *canali_extra)]
    ids += [getattr(c, "category_id", None) for c in (canale, *canali_extra)]
    ids.append(getattr(canale, "parent_id", None))
    return evento_ignorato(
        ignorati,
        channel_ids=ids,
        user_id=getattr(membro, "id", None),
        ruoli=[r.id for r in getattr(membro, "roles", [])],
    )
