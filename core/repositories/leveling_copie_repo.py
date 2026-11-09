"""
core/repositories/leveling_copie_repo.py
========================================
Copie di sicurezza degli XP (30 giorni): l'azzeramento di tutto il server o di una persona scrive
la copia e azzera nella stessa transazione; il ripristino non toglie mai XP a nessuno.
Funzioni coperte: SPEC §15 (LIV-068, 069, 070; catalogo #124)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.leveling_azzera_logic import (
    GIORNI_COPIA,
    MAX_COPIE_ELENCO,
    MAX_COPIE_SERVER,
    MAX_MOTIVO,
)


@dataclass(frozen=True)
class Copia:
    id: int
    guild_id: int
    tipo: str  # "server" o "utente"
    creata_il: datetime
    scade_il: datetime
    autore_id: int | None
    motivo: str
    righe: int


@dataclass(frozen=True)
class EsitoAzzeramento:
    copia_id: int
    utenti: int


_COLONNE = "id, guild_id, tipo, creata_il, scade_il, autore_id, motivo, righe"
_VALIDA = "scade_il > now()"


def _copia(riga) -> Copia:
    return Copia(**{k: riga[k] for k in Copia.__dataclass_fields__})


class LevelingCopieRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self):
        return self._pool_provider()

    @staticmethod
    async def _blocca(conn, guild_id: int) -> None:
        """Un solo azzeramento o ripristino alla volta per server (si libera a fine transazione)."""
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext('leveling_copie'), hashtext($1::text))", str(guild_id)
        )

    async def _scrivi_copia(self, conn, guild_id, tipo, autore_id, motivo, utente_id=None) -> tuple[int, int]:
        """Copia le righe con XP e azzera, nella transazione di chi chiama. (id copia, utenti) o (0, 0)."""
        filtro_utente = "" if utente_id is None else "AND user_id = $2"
        argomenti = (guild_id,) if utente_id is None else (guild_id, utente_id)
        presenti = await conn.fetchval(
            f"SELECT count(*) FROM leveling_totals WHERE guild_id = $1 {filtro_utente} "
            "AND (xp_total > 0 OR level > 0)",
            *argomenti,
        )
        if not presenti:
            return 0, 0
        copia_id = await conn.fetchval(
            "INSERT INTO leveling_copie (guild_id, tipo, scade_il, autore_id, motivo, righe) "
            "VALUES ($1, $2, now() + make_interval(days => $3), $4, $5, $6) RETURNING id",
            guild_id, tipo, GIORNI_COPIA, autore_id, motivo[:MAX_MOTIVO], presenti,
        )
        # Nessun parametro per riga: con 100.000 membri una sola istruzione.
        await conn.execute(
            "INSERT INTO leveling_copie_righe (copia_id, user_id, xp_total, level) "
            f"SELECT {int(copia_id)}, user_id, xp_total, level FROM leveling_totals "
            f"WHERE guild_id = $1 {filtro_utente} AND (xp_total > 0 OR level > 0)",
            *argomenti,
        )
        await conn.execute(
            "UPDATE leveling_totals SET xp_total = 0, level = 0 "
            f"WHERE guild_id = $1 {filtro_utente} AND (xp_total > 0 OR level > 0)",
            *argomenti,
        )
        await self._azzera_attivita(conn, *argomenti)
        return copia_id, presenti

    @staticmethod
    async def _azzera_attivita(conn, guild_id: int, user_id: int | None = None) -> None:
        """Azzera gli XP di mese e settimana (classifiche a periodo); le monete restano."""
        filtro = "" if user_id is None else "AND user_id = $2"
        argomenti = (guild_id,) if user_id is None else (guild_id, user_id)
        await conn.execute(
            f"UPDATE leveling_activity SET xp = 0 WHERE guild_id = $1 {filtro} AND xp > 0", *argomenti
        )

    async def azzera_server(self, guild_id: int, autore_id: int, motivo: str) -> EsitoAzzeramento | None:
        """
        LIV-068/069: copia di sicurezza e azzeramento degli XP di tutto il server (le monete restano).
        None se non c'era niente da azzerare (nessuna copia vuota). Restano le ultime due copie.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._blocca(conn, guild_id)
                copia_id, utenti = await self._scrivi_copia(conn, guild_id, "server", autore_id, motivo)
                if not copia_id:
                    return None
                await conn.execute(
                    "DELETE FROM leveling_copie WHERE guild_id = $1 AND tipo = 'server' AND id NOT IN ("
                    "SELECT id FROM leveling_copie WHERE guild_id = $1 AND tipo = 'server' "
                    "ORDER BY id DESC LIMIT $2)",
                    guild_id, MAX_COPIE_SERVER,
                )
        return EsitoAzzeramento(copia_id, utenti)

    async def azzera_utente(self, guild_id: int, user_id: int, con_copia: bool, motivo: str) -> bool:
        """LIV-070: azzera gli XP di una persona (con copia leggera se richiesto). False = era già a zero."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._blocca(conn, guild_id)
                if con_copia:
                    _, utenti = await self._scrivi_copia(conn, guild_id, "utente", None, motivo, user_id)
                    return bool(utenti)
                esito = await conn.execute(
                    "UPDATE leveling_totals SET xp_total = 0, level = 0 "
                    "WHERE guild_id = $1 AND user_id = $2 AND (xp_total > 0 OR level > 0)",
                    guild_id, user_id,
                )
                await self._azzera_attivita(conn, guild_id, user_id)
                return esito != "UPDATE 0"

    async def elenco(self, guild_id: int) -> list[Copia]:
        """Le copie ancora valide, la più nuova per prima (al massimo 25: un menu non ne mostra di più)."""
        righe = await self._pool.fetch(
            f"SELECT {_COLONNE} FROM leveling_copie WHERE guild_id = $1 AND {_VALIDA} "
            "ORDER BY id DESC LIMIT $2",
            guild_id, MAX_COPIE_ELENCO,
        )
        return [_copia(r) for r in righe]

    async def get(self, guild_id: int, copia_id: int) -> Copia | None:
        riga = await self._pool.fetchrow(
            f"SELECT {_COLONNE} FROM leveling_copie WHERE id = $1 AND guild_id = $2 AND {_VALIDA}",
            copia_id, guild_id,
        )
        return _copia(riga) if riga else None

    async def ripristina(self, guild_id: int, copia_id: int) -> int | None:
        """
        LIV-069: rimette gli XP della copia. Chi ha già di più dopo l'azzeramento tiene i suoi:
        il ripristino non toglie XP a nessuno, quindi si può ripetere. None = copia sparita,
        scaduta o di un altro server; altrimenti quante persone c'erano nella copia.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._blocca(conn, guild_id)
                righe = await conn.fetchval(
                    f"SELECT righe FROM leveling_copie WHERE id = $1 AND guild_id = $2 AND {_VALIDA}",
                    copia_id, guild_id,
                )
                if righe is None:
                    return None
                await conn.execute(
                    "INSERT INTO leveling_totals AS t (guild_id, user_id, xp_total, level) "
                    "SELECT $1, user_id, xp_total, level FROM leveling_copie_righe WHERE copia_id = $2 "
                    "ON CONFLICT (guild_id, user_id) DO UPDATE "
                    "SET xp_total = EXCLUDED.xp_total, level = EXCLUDED.level "
                    "WHERE EXCLUDED.xp_total > t.xp_total",
                    guild_id, copia_id,
                )
        return righe


def _get_pool():
    from core.database import db

    return db.pool


leveling_copie_repo = LevelingCopieRepository(pool_provider=_get_pool)
