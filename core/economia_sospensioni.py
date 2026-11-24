"""
core/economia_sospensioni.py
============================
La sospensione dal gioco (ECO-160, D121): lo staff del server ferma una persona dai comandi di gioco (`/monete`,
`/giochi`, `/monete-clan`) per sempre o per un tempo (al massimo 365 giorni), con un motivo. La persona può chiedere una
revisione una volta sola: la richiesta arriva allo staff (canale dei casi di moderazione) e lo staff accoglie (la
sospensione cade) o respinge (resta, senza una seconda richiesta). Il resto del bot funziona. Un punto solo, usato da
`/admin-giochi sospensione`, dal controllo comune dei comandi e dal futuro pannello (D16).
Funzioni coperte: ECO-160
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.database import db

RADICI_DI_GIOCO = frozenset({"monete", "giochi", "clan"})
MAX_MOTIVO = 200
MAX_APPELLO = 500
MAX_DURATA = timedelta(days=365)
MAX_ELENCO = 25


def e_di_gioco(percorso: str) -> bool:
    """Vero se il comando (percorso come «monete work») è un comando di gioco: solo questi si fermano."""
    return percorso.split(" ", 1)[0] in RADICI_DI_GIOCO


async def sospendi(guild_id: int, user_id: int, motivo: str, durata: timedelta | None, da: int) -> None:
    fino_a = datetime.now(timezone.utc) + min(durata, MAX_DURATA) if durata is not None else None
    await db.pool.execute(
        "INSERT INTO economia_sospensioni (guild_id, user_id, motivo, fino_a, sospeso_da) VALUES ($1, $2, $3, $4, $5) "
        "ON CONFLICT (guild_id, user_id) DO UPDATE SET motivo = EXCLUDED.motivo, fino_a = EXCLUDED.fino_a, "
        "sospeso_da = EXCLUDED.sospeso_da, creato_at = now(), appello = NULL, appello_stato = 'nessuno', "
        "appello_at = NULL, deciso_da = NULL",
        guild_id, user_id, motivo.strip()[:MAX_MOTIVO], fino_a, da,
    )


async def riabilita(guild_id: int, user_id: int) -> bool:
    return (await db.pool.execute(
        "DELETE FROM economia_sospensioni WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
    )).endswith(" 1")


async def attiva(guild_id: int, user_id: int):
    """La sospensione in corso (riga) o None. Una scaduta non conta."""
    return await db.pool.fetchrow(
        "SELECT * FROM economia_sospensioni WHERE guild_id = $1 AND user_id = $2 AND (fino_a IS NULL OR fino_a > now())",
        guild_id, user_id,
    )


async def apri_appello(guild_id: int, user_id: int, testo: str) -> bool:
    """Registra la richiesta di revisione. Falso se non è sospeso o l'ha già chiesta (aperta o respinta)."""
    esito = await db.pool.execute(
        "UPDATE economia_sospensioni SET appello = $3, appello_stato = 'aperto', appello_at = now() "
        "WHERE guild_id = $1 AND user_id = $2 AND appello_stato = 'nessuno' AND (fino_a IS NULL OR fino_a > now())",
        guild_id, user_id, testo.strip()[:MAX_APPELLO],
    )
    return esito.endswith(" 1")


async def decidi(guild_id: int, user_id: int, *, accogli: bool, da: int) -> bool:
    """Lo staff decide su una richiesta aperta. Falso se non ce n'è una."""
    if accogli:
        esito = await db.pool.execute(
            "DELETE FROM economia_sospensioni WHERE guild_id = $1 AND user_id = $2 AND appello_stato = 'aperto'",
            guild_id, user_id,
        )
    else:
        esito = await db.pool.execute(
            "UPDATE economia_sospensioni SET appello_stato = 'respinto', deciso_da = $3 "
            "WHERE guild_id = $1 AND user_id = $2 AND appello_stato = 'aperto'",
            guild_id, user_id, da,
        )
    return esito.endswith(" 1")


async def elenco(guild_id: int):
    return await db.pool.fetch(
        "SELECT * FROM economia_sospensioni WHERE guild_id = $1 AND (fino_a IS NULL OR fino_a > now()) "
        "ORDER BY (appello_stato = 'aperto') DESC, creato_at LIMIT $2",
        guild_id, MAX_ELENCO,
    )
