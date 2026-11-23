"""
core/ticket_trascrizioni_logic.py
=================================
Trascrizioni dei ticket conservate cifrate (TKT-072, D111): scelta della chiave, cifratura legata al server e al
ticket (AES-256-GCM di `core/oauth_crypto`), scadenza e filtri di ricerca. Funzioni pure, senza Discord né database.
Il contenuto (testo e immagini ricodificate) esce dal database solo decifrato in memoria, per lo staff del server.
Funzioni coperte: SPEC §13.22 (TKT-072)
Dipende da: core/oauth_crypto.py, core/ticket_transcript_logic.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from cryptography.exceptions import InvalidTag

from core import oauth_crypto

MAX_GIORNI = 90
GIORNI_DI_BASE = 90
RIGHE_PAGINA = 25
MAX_RICERCA = 100


def chiave_da_config(cfg) -> str:
    """La chiave dedicata, altrimenti quella dei token OAuth; vuota = niente conservazione."""
    return (getattr(cfg, "TICKET_TRASCRIZIONI_KEY", "") or getattr(cfg, "OAUTH_ENCRYPTION_KEY", "") or "").strip()


def giorni_validi(valore: object) -> int | None:
    """Da 1 a 90 giorni; qualunque altra cosa è None (mai oltre il massimo)."""
    try:
        n = int(str(valore).strip())
    except (TypeError, ValueError):
        return None
    return n if 1 <= n <= MAX_GIORNI else None


def scadenza(adesso: datetime, giorni: int) -> datetime:
    return adesso + timedelta(days=max(1, min(int(giorni), MAX_GIORNI)))


def _aad(guild_id: int, ticket_id: int) -> bytes:
    return f"ticket-trascrizione:{guild_id}:{ticket_id}".encode("ascii")


def cifra(parti: list[str], guild_id: int, ticket_id: int, chiave: str) -> str:
    """Le pagine HTML della trascrizione, cifrate. Copiate su un'altra riga non si aprono più."""
    corpo = json.dumps({"v": 1, "parti": parti}, ensure_ascii=False)
    return oauth_crypto.encrypt_token(corpo, chiave, aad=_aad(guild_id, ticket_id))


def apri(cifrato: str, guild_id: int, ticket_id: int, chiave: str) -> list[str] | None:
    """Le pagine HTML, o None se il dato è alterato, di un'altra riga o la chiave non c'è più."""
    try:
        dati = json.loads(oauth_crypto.decrypt_token(cifrato, chiave, aad=_aad(guild_id, ticket_id)))
        parti = dati["parti"]
    except (InvalidTag, oauth_crypto.OAuthEncryptionNotConfigured, ValueError, KeyError, TypeError):
        return None
    return [p for p in parti if isinstance(p, str)] or None


@dataclass(frozen=True)
class Filtro:
    utente_id: int | None = None
    panel_id: int | None = None
    voto: int | None = None
    motivo: str = ""


def filtro_da_form(utente: object, pannello: object, voto: object, motivo: object) -> Filtro:
    """Il filtro dai campi della pagina. Valori strani si ignorano, mai un errore: l'utente può digitare di tutto."""
    cifre = "".join(c for c in str(utente or "") if c.isdigit())
    utente_id = int(cifre) if 15 <= len(cifre) <= 20 and int(cifre) < 2**63 else None
    try:
        panel_id = int(str(pannello)) if str(pannello or "").strip() else None
    except ValueError:
        panel_id = None
    if panel_id is not None and not 0 < panel_id < 2**31:
        panel_id = None
    try:
        v = int(str(voto)) if str(voto or "").strip() else None
    except ValueError:
        v = None
    return Filtro(
        utente_id, panel_id, v if v in (1, 2, 3, 4, 5) else None,
        "".join(c for c in str(motivo or "") if c.isprintable()).strip()[:MAX_RICERCA],
    )
