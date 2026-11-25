"""
core/secondo_fattore.py
=======================
Il secondo fattore dei comandi che eseguono codice sulla macchina del bot (`/owner eval`, `/owner shell`,
`/owner cog load`, aggiornamento a caldo): un codice TOTP a 6 cifre (RFC 6238, SHA-1, 30 secondi) da un'app di
autenticazione, con il segreto in `OWNER_TOTP_SECRET` (base32). Senza segreto questi comandi si rifiutano: si fanno
solo da console. Un codice vale una volta sola (niente replay) e si confronta a tempo costante.
Funzioni coperte: blocco A (voce 12)
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import struct
import time

PASSO_SECONDI = 30
CIFRE = 6
FINESTRA_PASSI = 1  # si accetta anche il passo prima e quello dopo (orologi leggermente diversi)

_ultimo_passo_usato = 0  # un passo già accettato non vale una seconda volta


def _chiave(segreto_base32: str) -> bytes | None:
    pulito = (segreto_base32 or "").replace(" ", "").replace("-", "").upper()
    if len(pulito) < 16:  # meno di 80 bit non è un segreto
        return None
    try:
        return base64.b32decode(pulito + "=" * (-len(pulito) % 8))
    except (binascii.Error, ValueError):
        return None


def codice_al_passo(segreto_base32: str, passo: int) -> str | None:
    """Il codice di un passo di 30 secondi (RFC 4226 con contatore = passo). None se il segreto non è valido."""
    chiave = _chiave(segreto_base32)
    if chiave is None:
        return None
    firma = hmac.new(chiave, struct.pack(">Q", passo), hashlib.sha1).digest()
    scarto = firma[-1] & 0x0F
    numero = (struct.unpack(">I", firma[scarto:scarto + 4])[0] & 0x7FFFFFFF) % (10 ** CIFRE)
    return str(numero).zfill(CIFRE)


def verifica_codice(segreto_base32: str, codice: str | None, *, adesso: float | None = None) -> bool:
    """
    True se il codice è giusto per questo momento (o il passo accanto) e non è già stato usato. Un codice giusto
    si consuma: il passo (e i precedenti) non valgono più. Segreto assente o storto, codice non di 6 cifre = False.
    """
    global _ultimo_passo_usato

    testo = (codice or "").strip()
    if not (testo.isascii() and testo.isdigit() and len(testo) == CIFRE) or _chiave(segreto_base32) is None:
        return False
    centro = int((adesso if adesso is not None else time.time()) // PASSO_SECONDI)
    trovato = None
    for passo in range(centro - FINESTRA_PASSI, centro + FINESTRA_PASSI + 1):  # tutti i passi: tempo di calcolo costante
        atteso = codice_al_passo(segreto_base32, passo)
        if atteso is not None and hmac.compare_digest(atteso.encode(), testo.encode()) and passo > _ultimo_passo_usato:
            trovato = passo
    if trovato is None:
        return False
    _ultimo_passo_usato = trovato
    return True
