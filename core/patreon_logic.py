"""
core/patreon_logic.py
=====================
Regole pure di Patreon (CFG-036): il modulo è acceso solo con le tre chiavi nel .env, la firma del webhook
(HMAC-MD5 del corpo, come la manda Patreon) si controlla a tempo costante, il corpo JSON:API diventa un
evento semplice, i livelli Patreon diventano livelli del bot. Nessun Discord, nessun database, nessuna rete.
Funzioni coperte: CFG-036
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone

MAX_BYTE_CORPO = 256 * 1024
EVENTI_AMMESSI = (
    "members:create", "members:update", "members:delete",
    "members:pledge:create", "members:pledge:update", "members:pledge:delete",
)
STATO_ATTIVO = "active_patron"


def chiavi_presenti(client_id: str, client_secret: str, webhook_secret: str) -> bool:
    """Il modulo lavora solo con tutte e tre le chiavi: senza, niente rotte e niente errori."""
    return bool(client_id.strip()) and len(client_secret.strip()) >= 8 and len(webhook_secret.strip()) >= 8


def firma_valida(segreto: str, corpo: bytes, firma: str | None) -> bool:
    """`X-Patreon-Signature` è l'HMAC-MD5 esadecimale del corpo con il segreto del webhook. Confronto a tempo costante."""
    if len(segreto.strip()) < 8 or not firma:
        return False
    atteso = hmac.new(segreto.strip().encode(), corpo, hashlib.md5).hexdigest()  # noqa: S324 - lo impone Patreon
    return hmac.compare_digest(atteso.encode(), firma.strip().lower().encode())


def impronta_corpo(corpo: bytes) -> str:
    return hashlib.sha256(corpo).hexdigest()


@dataclass(frozen=True)
class EventoPatreon:
    tipo: str
    member_id: str
    patreon_id: str
    attivo: bool
    tiers: tuple[str, ...]
    ultima_carica: datetime | None = None  # data dell'ultimo addebito scritta nell'evento: serve a scartare quelli vecchi


class DaConfermare(Exception):
    """L'account Patreon è già collegato a un'altra persona: la persona che torna da Patreon deve confermare lo spostamento."""

    def __init__(self, discord_user_id: int) -> None:
        super().__init__("conferma")
        self.discord_user_id = discord_user_id


def _data(valore) -> datetime | None:
    """Una data ISO di Patreon (con fuso); qualsiasi altra cosa è «nessuna data»."""
    if not isinstance(valore, str) or len(valore) > 40:
        return None
    try:
        data = datetime.fromisoformat(valore.replace("Z", "+00:00"))
    except ValueError:
        return None
    return data if data.tzinfo else data.replace(tzinfo=timezone.utc)


def _id(valore) -> str:
    return str(valore)[:40] if isinstance(valore, (str, int)) and str(valore).isalnum() else ""


def leggi_evento(tipo: str | None, corpo: bytes) -> EventoPatreon | None:
    """Il corpo JSON:API del webhook. None se il tipo non ci interessa o il corpo non ha le parti che servono."""
    if tipo not in EVENTI_AMMESSI or len(corpo) > MAX_BYTE_CORPO:
        return None
    try:
        radice = json.loads(corpo)
        dati = radice["data"]
        relazioni = dati.get("relationships", {})
        utente = _id(relazioni["user"]["data"]["id"])
        tiers = tuple(i for i in (_id(t.get("id")) for t in relazioni.get("currently_entitled_tiers", {}).get("data", [])) if i)
        stato = dati.get("attributes", {}).get("patron_status")
        member_id = _id(dati.get("id"))
        carica = _data(dati.get("attributes", {}).get("last_charge_date"))
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    if not utente:
        return None
    eliminato = tipo.endswith(":delete")
    return EventoPatreon(tipo, member_id, utente, attivo=(stato == STATO_ATTIVO) and not eliminato, tiers=() if eliminato else tiers,
                         ultima_carica=carica)


def livello_da_tiers(tiers, mappa: dict[str, str]) -> str | None:
    """Il livello più alto tra i livelli Patreon associati; None se nessuno è associato."""
    from core import piani

    trovati = [mappa[t] for t in tiers if t in mappa]
    return piani.livello_massimo(*trovati) if trovati else None
