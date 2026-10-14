"""
core/premium_code_service.py
============================
Codici premium da riscattare, a tempo o permanenti (CFG-038, #122). L'owner crea un codice (o concede
direttamente) e il server lo riscatta con `/admin premium riscatta`. Un codice sblocca un modulo oppure tutti.
Funzioni coperte: SPEC §3, catalogo #122
Dipende da: core/repositories/premium_code_repo.py, core/migrations/0132_codici_premium.sql
"""

from __future__ import annotations

import hashlib
import secrets
import time
from datetime import datetime, timezone

from core.repositories.guild_premium_repo import guild_premium_repo
from core.repositories.module_subscription_repo import module_subscription_repo
from core.repositories.premium_code_repo import premium_code_repo

TUTTI_I_MODULI = "tutti"
GIORNI_PERMANENTE = 36500  # cento anni
# Senza I, O, 0, 1: non si confondono quando si copia un codice a mano.
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
GRUPPI = 3
LUNGHEZZA_GRUPPO = 4
PREFISSO = "YOKAI"
MAX_TENTATIVI_SBAGLIATI = 5
FINESTRA_SECONDI = 600

_sbagliati: dict[int, list[float]] = {}


class TroppiTentativi(Exception):
    """La persona ha sbagliato troppi codici di fila: deve aspettare."""


def normalizza(codice: str) -> str:
    """Maiuscole, senza spazi: «yokai-abcd-efgh-jkmn » e «YOKAIABCDEFGHJKMN» sono lo stesso codice."""
    return "".join(c for c in codice.upper() if c.isalnum())


def impronta(codice: str) -> str:
    return hashlib.sha256(normalizza(codice).encode("utf-8")).hexdigest()


def nuovo_codice() -> str:
    gruppi = ["".join(secrets.choice(ALFABETO) for _ in range(LUNGHEZZA_GRUPPO)) for _ in range(GRUPPI)]
    return "-".join([PREFISSO, *gruppi])


def _tentativi_recenti(user_id: int, adesso: float) -> list[float]:
    recenti = [t for t in _sbagliati.get(user_id, []) if adesso - t < FINESTRA_SECONDI]
    if recenti:
        _sbagliati[user_id] = recenti
    else:
        _sbagliati.pop(user_id, None)
    return recenti


async def crea_codice(module_name: str | None, giorni: int, created_by: int) -> str:
    """Crea un codice e lo restituisce in chiaro (l'unica volta). `module_name` None = tutti i moduli."""
    if giorni <= 0:
        raise ValueError("giorni deve essere positivo")
    codice = nuovo_codice()
    await premium_code_repo.crea(impronta(codice), codice[-4:], module_name, giorni, created_by)
    return codice


async def applica_sblocco(guild_id: int, module_name: str | None, giorni: int, granted_by: int | None) -> datetime:
    """Sblocca un modulo (o tutti, con None) per `giorni` giorni. Restituisce la nuova scadenza."""
    if module_name is None:
        return await guild_premium_repo.estendi(guild_id, giorni, datetime.now(timezone.utc))
    return await module_subscription_repo.grant(guild_id, module_name, duration_days=giorni, granted_by=granted_by)


async def riscatta_codice(codice: str, user_id: int, guild_id: int, *, adesso: float | None = None):
    """
    Riscatta un codice per il server. Restituisce `(module_name, scadenza)`; `(None, scadenza)` vale per tutti i
    moduli. Codice sconosciuto o già usato: None (e conta come tentativo sbagliato; dopo 5 in 10 minuti
    solleva `TroppiTentativi`).
    """
    ora = time.monotonic() if adesso is None else adesso
    if len(_tentativi_recenti(user_id, ora)) >= MAX_TENTATIVI_SBAGLIATI:
        raise TroppiTentativi()
    chiave = impronta(codice)
    trovato = await premium_code_repo.riscatta(chiave, user_id, guild_id)
    if trovato is None:
        _sbagliati.setdefault(user_id, []).append(ora)
        return None
    try:
        scadenza = await applica_sblocco(guild_id, trovato.module_name, trovato.duration_days, user_id)
    except Exception:
        await premium_code_repo.annulla_riscatto(chiave)  # lo sblocco non è riuscito: il codice resta buono
        raise
    _sbagliati.pop(user_id, None)
    return trovato.module_name, scadenza
