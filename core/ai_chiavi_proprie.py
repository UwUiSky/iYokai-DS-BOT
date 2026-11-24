"""
core/ai_chiavi_proprie.py
=========================
Chiave API propria (AI-003, D59, D127): un server o una persona mette la chiave di un servizio AI e usa quella al
posto delle chiavi dell'owner. Avere almeno una chiave verificata dà il livello VIP a chi l'ha messa (e al suo server).
Al salvataggio la chiave si prova presso il servizio (solo servizi della tabella dei fornitori, chiamata che non
consuma token); se il servizio poi la rifiuta (401/403) si segna non valida e il VIP decade.
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


class ServizioSconosciuto(ChiaveNonValida):
    """Il servizio non è nella tabella dei fornitori AI."""


class ChiaveRifiutata(ChiaveNonValida):
    """Il servizio non ha accettato la chiave (o non risponde)."""


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


async def verifica_e_salva(
    ambito: str, ambito_id: int, servizio: str, chiave: str, messa_da: int, *, fornitori=None, trasporto=None
) -> None:
    """Prova la chiave presso il servizio e, solo se risponde, la salva come verificata."""
    from dataclasses import replace

    from core import ai_providers

    _controlla(ambito, ambito_id, servizio)
    chiave = (chiave or "").strip()
    if not MIN_CHIAVE <= len(chiave) <= MAX_CHIAVE or any(c.isspace() for c in chiave):
        raise ChiaveNonValida("chiave")
    if fornitori is None:
        fornitori, _ = ai_providers.leggi_fornitori(ai_providers.env_con_file())
    noto = next((f for f in fornitori if f.nome == servizio), None)
    if noto is None:
        raise ServizioSconosciuto(servizio)
    _chiave_cifratura()  # senza cifratura non si fa nemmeno la prova in rete
    proprio = trasporto is None
    trasporto = trasporto or ai_providers.TrasportoHTTP()
    try:
        ok = bool(await trasporto.controlla(replace(noto, chiave=chiave)))
    except Exception:
        ok = False
    finally:
        if proprio:
            await trasporto.chiudi()
    if not ok:
        raise ChiaveRifiutata(servizio)
    await salva(ambito, ambito_id, servizio, chiave, messa_da, verificata=True)


async def salva(ambito: str, ambito_id: int, servizio: str, chiave: str, messa_da: int, *, verificata: bool = False) -> None:
    """Salva (o sostituisce) la chiave, cifrata. Dà il VIP solo se `verificata` (vedi `verifica_e_salva`)."""
    from core.oauth_crypto import encrypt_token

    _controlla(ambito, ambito_id, servizio)
    chiave = (chiave or "").strip()
    if not MIN_CHIAVE <= len(chiave) <= MAX_CHIAVE or any(c.isspace() for c in chiave):
        raise ChiaveNonValida("chiave")
    cifrata = encrypt_token(chiave, _chiave_cifratura(), aad=_aad(ambito, ambito_id, servizio))
    await _pool().execute(
        "INSERT INTO ai_chiavi_proprie (ambito, ambito_id, servizio, chiave_cifrata, messa_da, verificata) VALUES ($1,$2,$3,$4,$5,$6) "
        "ON CONFLICT (ambito, ambito_id, servizio) DO UPDATE SET chiave_cifrata = EXCLUDED.chiave_cifrata, "
        "messa_da = EXCLUDED.messa_da, verificata = EXCLUDED.verificata, creato_il = now()",
        ambito, ambito_id, servizio, cifrata, messa_da, verificata,
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
    """Almeno una chiave verificata: le altre non danno il VIP."""
    return bool(await _pool().fetchval(
        "SELECT 1 FROM ai_chiavi_proprie WHERE ambito = $1 AND ambito_id = $2 AND verificata LIMIT 1", ambito, ambito_id
    ))


async def segna_non_valida(servizio: str, *, guild_id: int | None = None, user_id: int | None = None) -> None:
    """Il servizio ha rifiutato la chiave (401/403): quella che `chiave_per` ha scelto smette di valere (e il VIP decade)."""
    for ambito, ambito_id in (("utente", user_id), ("server", guild_id)):
        if not ambito_id:
            continue
        righe = await _pool().fetch(
            "UPDATE ai_chiavi_proprie SET verificata = false WHERE ambito = $1 AND ambito_id = $2 AND servizio = $3 "
            "AND verificata RETURNING 1", ambito, ambito_id, servizio,
        )
        if righe:
            return


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
            "SELECT chiave_cifrata FROM ai_chiavi_proprie WHERE ambito = $1 AND ambito_id = $2 AND servizio = $3 AND verificata",
            ambito, ambito_id, servizio,
        )
        if cifrata:
            try:
                return decrypt_token(cifrata, _chiave_cifratura(), aad=_aad(ambito, ambito_id, servizio))
            except Exception:  # chiave di cifratura cambiata o riga alterata: come se non ci fosse
                return None
    return None
