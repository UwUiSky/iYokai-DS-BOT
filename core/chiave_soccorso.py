"""
core/chiave_soccorso.py
=======================
La chiave di soccorso dell'owner (SIC-021, D121): un codice per riprendere il controllo del bot se l'owner perde il
suo account. Si mostra una volta sola, nel database resta solo l'impronta (scrypt con sale). La verifica non passa
da Discord (chi ha perso l'account non può usare `/owner`): si fa a mano sul server con
`scripts/chiave_soccorso.py`, dopo 5 errori la chiave si blocca. Cambiare `OWNER_ID` resta un gesto manuale.
Funzioni coperte: SIC-021
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from core.database import db

MAX_ERRORI = 5
_N, _R, _P = 2**14, 8, 1


class GiaPresente(Exception):
    """C'è già una chiave: per cambiarla serve sostituire di proposito."""


@dataclass(frozen=True)
class Stato:
    presente: bool
    creata_at: datetime | None = None
    ultimo_uso: datetime | None = None
    bloccata: bool = False


def _normalizza(codice: str) -> str:
    return re.sub(r"[^A-Z2-7]", "", codice.upper())


def _impronta(codice: str, sale: bytes) -> bytes:
    return hashlib.scrypt(_normalizza(codice).encode(), salt=sale, n=_N, r=_R, p=_P, dklen=32)


def _nuovo_codice() -> str:
    grezzo = base64.b32encode(secrets.token_bytes(25)).decode().rstrip("=")  # 40 caratteri, 200 bit
    return "-".join(grezzo[i:i + 5] for i in range(0, len(grezzo), 5))


async def crea(sostituisci: bool = False) -> str:
    """Crea la chiave e restituisce il codice (l'unica volta in cui esiste in chiaro)."""
    if (await stato()).presente and not sostituisci:
        raise GiaPresente()
    codice = _nuovo_codice()
    sale = os.urandom(16)
    await db.pool.execute(
        "INSERT INTO owner_chiave_soccorso (id, sale, impronta) VALUES (1, $1, $2) "
        "ON CONFLICT (id) DO UPDATE SET sale = EXCLUDED.sale, impronta = EXCLUDED.impronta, creata_at = now(), "
        "errori = 0, ultimo_errore = NULL, ultimo_uso = NULL",
        sale, _impronta(codice, sale),
    )
    return codice


async def stato() -> Stato:
    r = await db.pool.fetchrow("SELECT creata_at, ultimo_uso, errori FROM owner_chiave_soccorso WHERE id = 1")
    if r is None:
        return Stato(False)
    return Stato(True, r["creata_at"], r["ultimo_uso"], r["errori"] >= MAX_ERRORI)


async def revoca() -> bool:
    return (await db.pool.execute("DELETE FROM owner_chiave_soccorso WHERE id = 1")).endswith(" 1")


async def verifica(codice: str) -> bool:
    """Vero se il codice è quello giusto. Dopo MAX_ERRORI errori risponde sempre falso (si sblocca ricreando la chiave)."""
    r = await db.pool.fetchrow("SELECT sale, impronta, errori FROM owner_chiave_soccorso WHERE id = 1")
    if r is None or r["errori"] >= MAX_ERRORI:
        return False
    if hmac.compare_digest(_impronta(codice, bytes(r["sale"])), bytes(r["impronta"])):
        await db.pool.execute("UPDATE owner_chiave_soccorso SET ultimo_uso = $1, errori = 0 WHERE id = 1", datetime.now(timezone.utc))
        return True
    await db.pool.execute("UPDATE owner_chiave_soccorso SET errori = errori + 1, ultimo_errore = now() WHERE id = 1")
    return False
