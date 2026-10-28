"""
core/odio_opzioni.py
====================
Impostazioni della difesa dalle parole d'odio (D35), in un solo punto (D16):
blocco preventivo con l'AutoMod nativo (acceso, testo del banner) e richiami
(quanti, in quanti minuti, quanto dura il timeout).
Funzioni coperte: SPEC §6 (D35)
"""

from __future__ import annotations

from dataclasses import dataclass

from core.database import db as _db

SETTING_BLOCCO = "odio_blocco_attivo"
SETTING_BLOCCO_MESSAGGIO = "odio_blocco_messaggio"
SETTING_RICHIAMI_SOGLIA = "odio_richiami_soglia"
SETTING_RICHIAMI_MINUTI = "odio_richiami_minuti"
SETTING_TIMEOUT_MINUTI = "odio_timeout_minuti"

MESSAGGIO_PREDEFINITO = "Primo richiamo: la tua affermazione risulta razzista. Rispetta le regole del server."
MAX_MESSAGGIO = 150  # limite di Discord per il testo del blocco (LIMITI.md 1.7)
SOGLIA_PREDEFINITA = 3
MINUTI_PREDEFINITI = 60
TIMEOUT_PREDEFINITO = 60
MAX_SOGLIA = 20
MAX_MINUTI = 1440  # un giorno
MAX_TIMEOUT_MINUTI = 40320  # 28 giorni: il massimo di Discord


@dataclass(frozen=True)
class OpzioniOdio:
    blocco: bool = False
    messaggio: str = MESSAGGIO_PREDEFINITO
    soglia: int = SOGLIA_PREDEFINITA
    minuti: int = MINUTI_PREDEFINITI
    timeout_minuti: int = TIMEOUT_PREDEFINITO


def _intero(valore, minimo: int, massimo: int, predefinito: int) -> int:
    if isinstance(valore, int) and not isinstance(valore, bool) and minimo <= valore <= massimo:
        return valore
    return predefinito


def messaggio_valido(testo: str | None) -> str:
    """Il testo del banner: quello scritto (tagliato a 150) oppure quello predefinito."""
    testo = (testo or "").strip()
    return testo[:MAX_MESSAGGIO] if testo else MESSAGGIO_PREDEFINITO


async def leggi(guild_id: int, archivio=None) -> OpzioniOdio:
    db = archivio or _db
    blocco = await db.get_guild_setting(guild_id, SETTING_BLOCCO, False)
    messaggio = await db.get_guild_setting(guild_id, SETTING_BLOCCO_MESSAGGIO, MESSAGGIO_PREDEFINITO)
    return OpzioniOdio(
        blocco=blocco if isinstance(blocco, bool) else False,
        messaggio=messaggio_valido(messaggio if isinstance(messaggio, str) else None),
        soglia=_intero(await db.get_guild_setting(guild_id, SETTING_RICHIAMI_SOGLIA, SOGLIA_PREDEFINITA), 1, MAX_SOGLIA, SOGLIA_PREDEFINITA),
        minuti=_intero(await db.get_guild_setting(guild_id, SETTING_RICHIAMI_MINUTI, MINUTI_PREDEFINITI), 1, MAX_MINUTI, MINUTI_PREDEFINITI),
        timeout_minuti=_intero(
            await db.get_guild_setting(guild_id, SETTING_TIMEOUT_MINUTI, TIMEOUT_PREDEFINITO), 1, MAX_TIMEOUT_MINUTI, TIMEOUT_PREDEFINITO
        ),
    )


async def imposta_blocco(guild_id: int, attivo: bool | None, messaggio: str | None, autore_id: int) -> None:
    """Accende o spegne il blocco e/o cambia il testo del banner (vuoto = quello predefinito)."""
    if attivo is not None:
        await _db.set_guild_setting(guild_id, SETTING_BLOCCO, attivo, changed_by=autore_id)
    if messaggio is not None:
        await _db.set_guild_setting(guild_id, SETTING_BLOCCO_MESSAGGIO, messaggio_valido(messaggio), changed_by=autore_id)


async def imposta_richiami(
    guild_id: int, soglia: int | None, minuti: int | None, timeout_minuti: int | None, autore_id: int
) -> None:
    """ValueError se un valore e' fuori dai limiti."""
    for valore, massimo, nome in ((soglia, MAX_SOGLIA, "richiami"), (minuti, MAX_MINUTI, "minuti"), (timeout_minuti, MAX_TIMEOUT_MINUTI, "timeout")):
        if valore is not None and not 1 <= valore <= massimo:
            raise ValueError(f"{nome}: da 1 a {massimo}.")
    if soglia is not None:
        await _db.set_guild_setting(guild_id, SETTING_RICHIAMI_SOGLIA, soglia, changed_by=autore_id)
    if minuti is not None:
        await _db.set_guild_setting(guild_id, SETTING_RICHIAMI_MINUTI, minuti, changed_by=autore_id)
    if timeout_minuti is not None:
        await _db.set_guild_setting(guild_id, SETTING_TIMEOUT_MINUTI, timeout_minuti, changed_by=autore_id)
