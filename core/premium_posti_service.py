"""
core/premium_posti_service.py
=============================
Posti premium legati a una persona (CFG-034, CFG-035, #122). L'owner concede N posti a una persona (`concedi_posti`,
dopo aver incassato fuori dal bot); la persona li assegna ai server che amministra (`assegna`) e li toglie (`togli`).
Un server con un posto attivo ha il premium, come per un abbonamento (`posto_attivo`, letto da `guild_has_premium_access`).
Regole, tutte controllate qui sul server e mai dal lato utente:
- un server ha un solo posto; i posti usati non superano quelli concessi; un posto scaduto non vale;
- assegnare e togliere sono atomici (una transazione con la riga della persona bloccata);
- al massimo un cambio all'ora per persona, così i posti non si "prestano" a rotazione;
- chi toglie può togliere solo un posto suo.
Funzioni coperte: SPEC §3 (NF-22), catalogo #122
Dipende da: core/migrations/0720_premium_posti.sql, core/premium_cache.py
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from core.premium_cache import invalida_cache_premium

MAX_POSTI = 10
ATTESA_TRA_CAMBI = timedelta(hours=1)
GIORNI_AMMESSI = (30, 365, None)  # mensile, annuale, permanente (come `/owner premium grant`)


class PostoNonValido(ValueError):
    """Valore rifiutato (posti o durata fuori dai limiti)."""


class Esito(enum.Enum):
    FATTO = "fatto"
    GIA_SUO = "gia_suo"
    OCCUPATO = "occupato"  # il server ha già il posto di un'altra persona
    NESSUN_ABBONAMENTO = "nessun_abbonamento"  # niente posti, o scaduti
    NESSUN_POSTO_LIBERO = "nessun_posto_libero"
    DA_ATTENDERE = "da_attendere"
    NON_SUO = "non_suo"  # `togli` su un server che non ha un suo posto


@dataclass(frozen=True)
class StatoPosti:
    posti: int
    usati: int
    scade_il: datetime | None
    server: tuple[int, ...]

    @property
    def liberi(self) -> int:
        return max(self.posti - self.usati, 0)


def _pool():
    from core.database import db

    return db.pool


async def concedi_posti(user_id: int, posti: int, giorni: int | None, concesso_da: int) -> datetime | None:
    """
    Dà `posti` posti alla persona per `giorni` giorni (None = permanenti); `posti` 0 li toglie tutti.
    Sostituisce quelli di prima. Se i posti scendono, i server assegnati per ultimi li perdono.
    Restituisce la scadenza (None = permanente).
    """
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise PostoNonValido("utente")
    if not isinstance(posti, int) or isinstance(posti, bool) or not 0 <= posti <= MAX_POSTI:
        raise PostoNonValido("posti")
    if giorni not in GIORNI_AMMESSI:
        raise PostoNonValido("giorni")
    scade = None if giorni is None else datetime.now(timezone.utc) + timedelta(days=giorni)
    async with _pool().acquire() as conn, conn.transaction():
        if posti == 0:
            tolti = await conn.fetch("DELETE FROM premium_posti_server WHERE user_id = $1 RETURNING guild_id", user_id)
            await conn.execute("DELETE FROM premium_posti_utente WHERE user_id = $1", user_id)
        else:
            await conn.execute(
                """
                INSERT INTO premium_posti_utente (user_id, posti, scade_il, concesso_da)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id) DO UPDATE
                    SET posti = EXCLUDED.posti, scade_il = EXCLUDED.scade_il, concesso_da = EXCLUDED.concesso_da
                """,
                user_id, posti, scade, concesso_da,
            )
            tolti = await conn.fetch(
                """
                DELETE FROM premium_posti_server WHERE guild_id IN (
                    SELECT guild_id FROM premium_posti_server WHERE user_id = $1
                    ORDER BY assegnato_il ASC, guild_id OFFSET $2
                ) RETURNING guild_id
                """,
                user_id, posti,
            )
    for riga in tolti:
        invalida_cache_premium(riga["guild_id"])
    return scade if posti else None


async def assegna(user_id: int, guild_id: int) -> Esito:
    """Mette un posto della persona su un server."""
    adesso = datetime.now(timezone.utc)
    async with _pool().acquire() as conn, conn.transaction():
        sub = await conn.fetchrow(
            "SELECT posti, scade_il, ultimo_cambio FROM premium_posti_utente WHERE user_id = $1 FOR UPDATE", user_id
        )
        if sub is None or (sub["scade_il"] is not None and sub["scade_il"] <= adesso):
            return Esito.NESSUN_ABBONAMENTO
        attuale = await conn.fetchval("SELECT user_id FROM premium_posti_server WHERE guild_id = $1", guild_id)
        if attuale == user_id:
            return Esito.GIA_SUO
        if attuale is not None:
            return Esito.OCCUPATO
        if sub["ultimo_cambio"] is not None and adesso - sub["ultimo_cambio"] < ATTESA_TRA_CAMBI:
            return Esito.DA_ATTENDERE
        usati = await conn.fetchval("SELECT count(*) FROM premium_posti_server WHERE user_id = $1", user_id)
        if usati >= sub["posti"]:
            return Esito.NESSUN_POSTO_LIBERO
        await conn.execute("INSERT INTO premium_posti_server (guild_id, user_id) VALUES ($1, $2)", guild_id, user_id)
        await conn.execute("UPDATE premium_posti_utente SET ultimo_cambio = $2 WHERE user_id = $1", user_id, adesso)
    invalida_cache_premium(guild_id)
    return Esito.FATTO


async def togli(user_id: int, guild_id: int) -> Esito:
    """Toglie il posto della persona da un server. Un posto di un'altra persona non si tocca."""
    adesso = datetime.now(timezone.utc)
    async with _pool().acquire() as conn, conn.transaction():
        await conn.fetchrow("SELECT 1 FROM premium_posti_utente WHERE user_id = $1 FOR UPDATE", user_id)
        tolto = await conn.fetchval(
            "DELETE FROM premium_posti_server WHERE guild_id = $1 AND user_id = $2 RETURNING guild_id", guild_id, user_id
        )
        if tolto is None:
            return Esito.NON_SUO
        await conn.execute("UPDATE premium_posti_utente SET ultimo_cambio = $2 WHERE user_id = $1", user_id, adesso)
    invalida_cache_premium(guild_id)
    return Esito.FATTO


async def posto_attivo(guild_id: int) -> bool:
    """True se il server ha il posto di una persona il cui abbonamento non è scaduto."""
    return bool(
        await _pool().fetchval(
            """
            SELECT 1 FROM premium_posti_server s JOIN premium_posti_utente u ON u.user_id = s.user_id
            WHERE s.guild_id = $1 AND (u.scade_il IS NULL OR u.scade_il > now())
            """,
            guild_id,
        )
    )


async def stato_utente(user_id: int) -> StatoPosti | None:
    sub = await _pool().fetchrow("SELECT posti, scade_il FROM premium_posti_utente WHERE user_id = $1", user_id)
    if sub is None or (sub["scade_il"] is not None and sub["scade_il"] <= datetime.now(timezone.utc)):
        return None
    server = await _pool().fetch(
        "SELECT guild_id FROM premium_posti_server WHERE user_id = $1 ORDER BY assegnato_il, guild_id", user_id
    )
    return StatoPosti(sub["posti"], len(server), sub["scade_il"], tuple(r["guild_id"] for r in server))


async def posto_del_server(guild_id: int) -> int | None:
    """Chi ha messo un posto su questo server (None = nessuno, o posto scaduto)."""
    return await _pool().fetchval(
        """
        SELECT s.user_id FROM premium_posti_server s JOIN premium_posti_utente u ON u.user_id = s.user_id
        WHERE s.guild_id = $1 AND (u.scade_il IS NULL OR u.scade_il > now())
        """,
        guild_id,
    )
