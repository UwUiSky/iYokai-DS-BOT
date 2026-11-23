"""
core/voto_logic.py
==================
Regole pure del modulo «voto»: verifica del segreto o della firma di un sito di elenchi di bot (top.gg), lettura del
voto dal corpo JSON, durata del bonus XP. Nessun accesso a Discord né al database.
Funzioni coperte: LIV-019, ECO-048, ECO-049, CFG-039
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass

SITO_TOPGG = "topgg"
TOLLERANZA_FIRMA = 300  # secondi: una firma più vecchia non vale (nessun rinvio di una richiesta rubata)
MAX_BYTE_CORPO = 16 * 1024
GIORNI_PER_RISCATTARE = 7  # un voto non riscattato dopo 7 giorni si perde
ORE_TRA_DUE_VOTI = 11  # un sito fa votare ogni 12 ore: due voti più vicini sono lo stesso voto rinviato
MAX_ID = 2**63 - 1


@dataclass(frozen=True)
class Voto:
    user_id: int
    peso: int = 1  # il fine settimana alcuni siti contano doppio: qui conta sempre come un voto solo (un premio per voto)


def segreto_valido(segreto: str) -> bool:
    """Una chiave troppo corta o fatta di spazi vale come «non messa»: il modulo resta spento."""
    return len(segreto.strip()) >= 8


def verifica(segreto: str, autorizzazione: str | None, firma: str | None, corpo: bytes, adesso: float | None = None) -> bool:
    """
    Vera se la richiesta è del sito: o l'intestazione Authorization è uguale al segreto, o la firma
    `t=<secondi>,v1=<hmac-sha256 di "t.corpo">` torna. Confronti a tempo costante. Senza segreto valido, mai.
    """
    if not segreto_valido(segreto):
        return False
    chiave = segreto.strip().encode()
    if autorizzazione and hmac.compare_digest(autorizzazione.strip().encode(), chiave):
        return True
    if not firma:
        return False
    parti = dict(p.split("=", 1) for p in firma.split(",") if "=" in p)
    try:
        t = int(parti.get("t", ""))
    except ValueError:
        return False
    if abs((time.time() if adesso is None else adesso) - t) > TOLLERANZA_FIRMA:
        return False
    atteso = hmac.new(chiave, f"{t}.".encode() + corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(parti.get("v1", "").encode(), atteso.encode())


def leggi_voto(corpo: bytes) -> Voto | None:
    """
    L'utente che ha votato. Due forme: la vecchia `{"user": "123", "type": "upvote"}` e la nuova
    `{"type": "vote.create", "data": {"user": {"platform_id": "123"}}}`. I voti di prova e ogni forma
    sconosciuta danno None (la richiesta si accetta senza premio).
    """
    if len(corpo) > MAX_BYTE_CORPO:
        return None
    try:
        dati = json.loads(corpo)
    except ValueError:
        return None
    if not isinstance(dati, dict):
        return None
    tipo = dati.get("type")
    if tipo == "upvote":
        grezzo = dati.get("user")
    elif tipo == "vote.create" and isinstance(dati.get("data"), dict) and isinstance(dati["data"].get("user"), dict):
        grezzo = dati["data"]["user"].get("platform_id")
    else:
        return None
    if isinstance(grezzo, bool) or not isinstance(grezzo, (str, int)):
        return None
    testo = str(grezzo).strip()
    if not testo.isascii() or not testo.isdigit() or not 0 < int(testo) <= MAX_ID:
        return None
    return Voto(int(testo))
