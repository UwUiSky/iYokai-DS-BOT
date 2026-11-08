"""
core/account_rubato_opzioni.py
==============================
Opzione per server della difesa dagli account rubati (D67): accesa di base. Un solo punto (D16) per il comando
`/admin-automod immagini` e per il pannello.
Funzioni coperte: SPEC §6.20 (D67, #153)
"""

from __future__ import annotations

from core.database import db as _db

SETTING_ATTIVO = "account_rubato_attivo"


async def attivo(guild_id: int, archivio=None) -> bool:
    valore = await (archivio or _db).get_guild_setting(guild_id, SETTING_ATTIVO, True)
    return valore if isinstance(valore, bool) else True


async def imposta(guild_id: int, autore_id: int, valore: bool) -> None:
    await _db.set_guild_setting(guild_id, SETTING_ATTIVO, bool(valore), changed_by=autore_id)
