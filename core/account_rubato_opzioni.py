"""
core/account_rubato_opzioni.py
==============================
Opzioni per server della difesa dagli account rubati (D67): accesa o spenta (accesa di base) e minuti di timeout,
60 per lo stesso messaggio in più canali e 1.440 (24 ore) per le immagini malevole. Un solo punto (D16) per il
comando `/admin-automod immagini` e per il pannello.
Funzioni coperte: SPEC §6.20 (D67, #153)
"""

from __future__ import annotations

from core.database import db as _db

SETTING_ATTIVO = "account_rubato_attivo"
SETTING_MINUTI_UGUALI = "account_rubato_minuti_uguali"
SETTING_MINUTI_MALEVOLE = "account_rubato_minuti_malevole"
MINUTI_UGUALI = 60
MINUTI_MALEVOLE = 1_440
MAX_MINUTI = 40_320  # 28 giorni: il massimo del timeout di Discord


async def attivo(guild_id: int, archivio=None) -> bool:
    valore = await (archivio or _db).get_guild_setting(guild_id, SETTING_ATTIVO, True)
    return valore if isinstance(valore, bool) else True


async def imposta(guild_id: int, autore_id: int, valore: bool) -> None:
    await _db.set_guild_setting(guild_id, SETTING_ATTIVO, bool(valore), changed_by=autore_id)


def _minuti_validi(valore, predefinito: int) -> int:
    if isinstance(valore, bool) or not isinstance(valore, int) or not 1 <= valore <= MAX_MINUTI:
        return predefinito
    return valore


async def minuti(guild_id: int, archivio=None) -> tuple[int, int]:
    """(minuti per i messaggi uguali, minuti per le immagini malevole); un valore rotto torna a quello di base."""
    archivio = archivio or _db
    uguali = await archivio.get_guild_setting(guild_id, SETTING_MINUTI_UGUALI, MINUTI_UGUALI)
    malevole = await archivio.get_guild_setting(guild_id, SETTING_MINUTI_MALEVOLE, MINUTI_MALEVOLE)
    return _minuti_validi(uguali, MINUTI_UGUALI), _minuti_validi(malevole, MINUTI_MALEVOLE)


async def timeout_secondi(guild_id: int, malevole: bool) -> int:
    uguali, per_malevole = await minuti(guild_id)
    return (per_malevole if malevole else uguali) * 60


async def imposta_minuti(guild_id: int, autore_id: int, *, uguali: int | None = None, malevole: int | None = None) -> None:
    """ValueError se un valore è fuori da 1–40.320; controlla tutto prima di scrivere, poi scrive solo ciò che è dato."""
    for valore in (uguali, malevole):
        if valore is not None and _minuti_validi(valore, 0) == 0:
            raise ValueError(f"timeout: da 1 a {MAX_MINUTI} minuti.")
    for chiave, valore in ((SETTING_MINUTI_UGUALI, uguali), (SETTING_MINUTI_MALEVOLE, malevole)):
        if valore is not None:
            await _db.set_guild_setting(guild_id, chiave, valore, changed_by=autore_id)
