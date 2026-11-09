"""
core/fun_servizi_logic.py
=========================
Interruttori dei servizi esterni del Divertimento, spenti di base (#131, D70, B10): `/immagini post` (Lemmy)
`/gif cerca` (ricerca libera, solo dove c'è una chiave) e il telefono tra server (B12). Si accendono dalla scheda «fun» del pannello o con
`/admin-giochi servizi`; la scrittura passa da `core/config_impostazioni.py` (con lo storico).
Funzioni coperte: SPEC §16 (FUN-053, FUN-055, FUN-056, FUN-065)
"""

from __future__ import annotations

SETTING_IMMAGINI_POST = "fun_immagini_post"
SETTING_GIF_CERCA = "fun_gif_cerca"
SETTING_TELEFONO = "fun_telefono"
SCHEDA_FUN = "fun"


async def acceso(guild_id: int, chiave: str) -> bool:
    from core.database import db

    return (await db.get_guild_setting(guild_id, chiave, False)) is True
