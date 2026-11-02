"""
core/immagini_opzioni.py
========================
Impostazioni del filtro immagini sospette (D62), in un solo punto (D16): acceso (spento di base),
azione (cancella, avvisa, timeout), minuti del timeout e canale del log. Le usano il cog del filtro
e, dopo l'unione con il filone AutoMod, il comando «immagini» del gruppo admin-automod e il pannello.
Funzioni coperte: SPEC §6 (D62)
"""

from __future__ import annotations

from dataclasses import dataclass

from core.database import db as _db

SETTING_ATTIVO = "immagini_filtro_attivo"
SETTING_AZIONE = "immagini_azione"
SETTING_TIMEOUT_MINUTI = "immagini_timeout_minuti"
SETTING_CANALE_LOG = "immagini_canale_log_id"

AZIONI = ("cancella", "avvisa", "timeout")
AZIONE_PREDEFINITA = "cancella"
TIMEOUT_PREDEFINITO = 10
MAX_TIMEOUT_MINUTI = 40320  # 28 giorni: il massimo di Discord


@dataclass(frozen=True)
class OpzioniImmagini:
    attivo: bool = False
    azione: str = AZIONE_PREDEFINITA
    timeout_minuti: int = TIMEOUT_PREDEFINITO
    canale_log_id: int | None = None


def _intero(valore, minimo: int, massimo: int, predefinito: int) -> int:
    if isinstance(valore, int) and not isinstance(valore, bool) and minimo <= valore <= massimo:
        return valore
    return predefinito


async def leggi(guild_id: int, archivio=None) -> OpzioniImmagini:
    db = archivio or _db
    attivo = await db.get_guild_setting(guild_id, SETTING_ATTIVO, False)
    azione = await db.get_guild_setting(guild_id, SETTING_AZIONE, AZIONE_PREDEFINITA)
    canale = await db.get_guild_setting(guild_id, SETTING_CANALE_LOG, None)
    return OpzioniImmagini(
        attivo=attivo if isinstance(attivo, bool) else False,
        azione=azione if azione in AZIONI else AZIONE_PREDEFINITA,
        timeout_minuti=_intero(
            await db.get_guild_setting(guild_id, SETTING_TIMEOUT_MINUTI, TIMEOUT_PREDEFINITO), 1, MAX_TIMEOUT_MINUTI, TIMEOUT_PREDEFINITO
        ),
        canale_log_id=_intero(canale, 1, 2**63 - 1, 0) or None,
    )


async def imposta(
    guild_id: int,
    autore_id: int,
    *,
    attivo: bool | None = None,
    azione: str | None = None,
    timeout_minuti: int | None = None,
    canale_log_id: int | None = None,
    togli_canale: bool = False,
) -> None:
    """ValueError se un valore e' fuori dai limiti. Scrive solo quello che e' dato."""
    if azione is not None and azione not in AZIONI:
        raise ValueError(f"azione: {', '.join(AZIONI)}.")
    if timeout_minuti is not None and not 1 <= timeout_minuti <= MAX_TIMEOUT_MINUTI:
        raise ValueError(f"timeout: da 1 a {MAX_TIMEOUT_MINUTI} minuti.")
    if canale_log_id is not None and not 0 < canale_log_id < 2**63:
        raise ValueError("canale non valido.")
    if attivo is not None:
        await _db.set_guild_setting(guild_id, SETTING_ATTIVO, attivo, changed_by=autore_id)
    if azione is not None:
        await _db.set_guild_setting(guild_id, SETTING_AZIONE, azione, changed_by=autore_id)
    if timeout_minuti is not None:
        await _db.set_guild_setting(guild_id, SETTING_TIMEOUT_MINUTI, timeout_minuti, changed_by=autore_id)
    if canale_log_id is not None:
        await _db.set_guild_setting(guild_id, SETTING_CANALE_LOG, canale_log_id, changed_by=autore_id)
    elif togli_canale:
        await _db.set_guild_setting(guild_id, SETTING_CANALE_LOG, None, changed_by=autore_id)
