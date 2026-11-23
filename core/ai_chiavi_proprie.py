"""
core/ai_chiavi_proprie.py
=========================
Chiave API propria (AI-003, D59, D127): un server o una persona mette la chiave di un servizio AI e usa quella al
posto delle chiavi dell'owner. Avere almeno una chiave dà il livello VIP a chi l'ha messa (e al suo server).
Regole: la chiave si salva solo cifrata (AES-GCM con OAUTH_ENCRYPTION_KEY, legata ad ambito, id e servizio),
si legge in chiaro solo in `chiave_per` (per il router AI, mai nei log né nelle risposte), vale solo per chi l'ha
messa e si toglie con `togli`. Senza chiave di cifratura non si salva niente.
Funzioni coperte: AI-003, D59, D127
Dipende da: core/oauth_crypto.py, core/migrations/0911_ai_chiavi_proprie.sql
"""

from __future__ import annotations

import re

AMBITI = ("utente", "server")
SERVIZIO_RE = re.compile(r"^[a-z0-9_]{1,40}$")
MIN_CHIAVE, MAX_CHIAVE = 8, 400


class ChiaveNonValida(ValueError):
    """Ambito, servizio o chiave fuori misura."""


class CifraturaNonConfigurata(RuntimeError):
    """OAUTH_ENCRYPTION_KEY manca: la chiave non si salva."""


def _pool():
    from core.database import db

    return db.pool


def _chiave_cifratura() -> str:
    from core.config import config

    valore = getattr(config, "OAUTH_ENCRYPTION_KEY", "")
    if not valore:
        raise CifraturaNonConfigurata("OAUTH_ENCRYPTION_KEY vuota")
    return valore


def _aad(ambito: str, ambito_id: int, servizio: str) -> bytes:
    return f"ai-chiave:{ambito}:{ambito_id}:{servizio}".encode()


def _controlla(ambito: str, ambito_id: int, servizio: str) -> None:
    if ambito not in AMBITI:
        raise ChiaveNonValida("ambito")
    if not isinstance(ambito_id, int) or isinstance(ambito_id, bool) or ambito_id <= 0:
        raise ChiaveNonValida("id")
    if not SERVIZIO_RE.match(servizio or ""):
        raise ChiaveNonValida("servizio")


async def salva(ambito: str, ambito_id: int, servizio: str, chiave: str, messa_da: int) -> None:
    """Salva (o sostituisce) la chiave, cifrata."""
    from core.oauth_crypto import encrypt_token

    _controlla(ambito, ambito_id, servizio)
    chiave = (chiave or "").strip()
    if not MIN_CHIAVE <= len(chiave) <= MAX_CHIAVE or any(c.isspace() for c in chiave):
        raise ChiaveNonValida("chiave")
    cifrata = encrypt_token(chiave, _chiave_cifratura(), aad=_aad(ambito, ambito_id, servizio))
    await _pool().execute(
        "INSERT INTO ai_chiavi_proprie (ambito, ambito_id, servizio, chiave_cifrata, messa_da) VALUES ($1,$2,$3,$4,$5) "
        "ON CONFLICT (ambito, ambito_id, servizio) DO UPDATE SET chiave_cifrata = EXCLUDED.chiave_cifrata, "
        "messa_da = EXCLUDED.messa_da, creato_il = now()",
        ambito, ambito_id, servizio, cifrata, messa_da,
    )


async def togli(ambito: str, ambito_id: int, servizio: str | None = None) -> int:
    """Toglie la chiave di un servizio (o tutte). Restituisce quante."""
    _controlla(ambito, ambito_id, servizio or "x")
    righe = await _pool().fetch(
        "DELETE FROM ai_chiavi_proprie WHERE ambito = $1 AND ambito_id = $2 AND ($3::text IS NULL OR servizio = $3) RETURNING 1",
        ambito, ambito_id, servizio,
    )
    return len(righe)


async def servizi_con_chiave(ambito: str, ambito_id: int) -> list[str]:
    """I nomi dei servizi con chiave propria (mai le chiavi)."""
    righe = await _pool().fetch(
        "SELECT servizio FROM ai_chiavi_proprie WHERE ambito = $1 AND ambito_id = $2 ORDER BY servizio", ambito, ambito_id
    )
    return [r["servizio"] for r in righe]


async def ha_chiave(ambito: str, ambito_id: int) -> bool:
    return bool(await _pool().fetchval("SELECT 1 FROM ai_chiavi_proprie WHERE ambito = $1 AND ambito_id = $2 LIMIT 1", ambito, ambito_id))


async def chiave_per(servizio: str, *, guild_id: int | None = None, user_id: int | None = None) -> str | None:
    """
    La chiave in chiaro da usare per questa richiesta: prima quella dell'utente, poi quella del server; None se
    nessuno ne ha messa una (allora vale la chiave dell'owner). Solo per il router AI: non va mai scritta nei log.
    """
    from core.oauth_crypto import decrypt_token

    for ambito, ambito_id in (("utente", user_id), ("server", guild_id)):
        if not ambito_id:
            continue
        cifrata = await _pool().fetchval(
            "SELECT chiave_cifrata FROM ai_chiavi_proprie WHERE ambito = $1 AND ambito_id = $2 AND servizio = $3",
            ambito, ambito_id, servizio,
        )
        if cifrata:
            try:
                return decrypt_token(cifrata, _chiave_cifratura(), aad=_aad(ambito, ambito_id, servizio))
            except Exception:  # chiave di cifratura cambiata o riga alterata: come se non ci fosse
                return None
    return None
