"""
core/repositories/ticket_opzioni_repo.py
========================================
Opzioni dei pannelli dei ticket e regole del server per aprirli (catalogo #120):
opzioni per pannello, regole di accesso, lista nera, sospensione, pausa azzerata,
staff reperibile.
Funzioni coperte: SPEC §13.15–§13.19
Tabelle: migrazione 0220.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime

import asyncpg

from core.ticket_opzioni_logic import (
    MAX_LISTA_NERA,
    MAX_REGOLE_ACCESSO,
    MAX_REPERIBILI,
    Opzioni,
    Situazione,
)

_COLONNE = tuple(f.name for f in fields(Opzioni) if f.name != "panel_id")
_LISTE = {
    "ruoli_esenti", "categorie_riserva", "ping_ruoli", "permessi_negati",
    "ruoli_osservatori", "ruoli_durante", "ruoli_staff",
}


class TroppeRegole(Exception):
    """Il pannello ha già 25 regole di accesso, oppure il server 500 voci in lista nera."""


def _opzioni(r) -> Opzioni:
    valori = {c: (tuple(r[c]) if c in _LISTE else r[c]) for c in _COLONNE}
    return Opzioni(panel_id=r["panel_id"], **valori)


class TicketOpzioniRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ------------------------------------------------------------ opzioni del pannello
    async def opzioni(self, panel_id: int) -> Opzioni:
        r = await self._pool.fetchrow("SELECT * FROM ticket_panel_opzioni WHERE panel_id = $1", panel_id)
        return _opzioni(r) if r else Opzioni(panel_id=panel_id)

    async def imposta(self, panel_id: int, **valori) -> Opzioni:
        """Cambia solo le opzioni date (D16: unico punto, usato dai comandi e dal pannello web)."""
        sconosciute = set(valori) - set(_COLONNE)
        if sconosciute:
            raise KeyError(f"Opzioni sconosciute: {sorted(sconosciute)}")
        if not valori:
            return await self.opzioni(panel_id)
        nomi = list(valori)
        dati = [list(valori[n]) if n in _LISTE else valori[n] for n in nomi]
        colonne = ", ".join(nomi)
        segnaposti = ", ".join(f"${i + 2}" for i in range(len(nomi)))
        aggiorna = ", ".join(f"{n} = EXCLUDED.{n}" for n in nomi)
        r = await self._pool.fetchrow(
            f"INSERT INTO ticket_panel_opzioni (panel_id, {colonne}) VALUES ($1, {segnaposti}) "
            f"ON CONFLICT (panel_id) DO UPDATE SET {aggiorna} RETURNING *",
            panel_id, *dati,
        )
        return _opzioni(r)

    # ------------------------------------------------------------ TKT-020 regole di accesso
    async def regole_accesso(self, panel_id: int) -> list[tuple[int, bool]]:
        righe = await self._pool.fetch(
            "SELECT role_id, permetti FROM ticket_panel_accesso WHERE panel_id = $1 ORDER BY posizione", panel_id
        )
        return [(r["role_id"], r["permetti"]) for r in righe]

    async def imposta_regola(self, panel_id: int, role_id: int, permetti: bool | None) -> list[tuple[int, bool]]:
        """Una regola nuova va in fondo; una esistente cambia sul posto; None la toglie. Le posizioni restano 1..N."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1, $2)", 8420, panel_id)
                regole = [
                    (r["role_id"], r["permetti"])
                    for r in await conn.fetch(
                        "SELECT role_id, permetti FROM ticket_panel_accesso WHERE panel_id = $1 ORDER BY posizione",
                        panel_id,
                    )
                ]
                indice = next((i for i, (rid, _) in enumerate(regole) if rid == role_id), None)
                if permetti is None:
                    if indice is not None:
                        regole.pop(indice)
                elif indice is not None:
                    regole[indice] = (role_id, permetti)
                else:
                    if len(regole) >= MAX_REGOLE_ACCESSO:
                        raise TroppeRegole()
                    regole.append((role_id, permetti))
                await conn.execute("DELETE FROM ticket_panel_accesso WHERE panel_id = $1", panel_id)
                await conn.executemany(
                    "INSERT INTO ticket_panel_accesso (panel_id, posizione, role_id, permetti) VALUES ($1, $2, $3, $4)",
                    [(panel_id, i + 1, rid, p) for i, (rid, p) in enumerate(regole)],
                )
        return regole

    # ------------------------------------------------------------ TKT-021 lista nera
    async def blocca(self, guild_id: int, target_id: int, is_role: bool, motivo: str | None, by: int) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1, $2)", 8421, guild_id % 2**31)
                quante = await conn.fetchval("SELECT count(*) FROM ticket_blacklist WHERE guild_id = $1", guild_id)
                gia = await conn.fetchval(
                    "SELECT 1 FROM ticket_blacklist WHERE guild_id = $1 AND target_id = $2", guild_id, target_id
                )
                if not gia and quante >= MAX_LISTA_NERA:
                    raise TroppeRegole()
                await conn.execute(
                    """
                    INSERT INTO ticket_blacklist (guild_id, target_id, is_role, motivo, added_by)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (guild_id, target_id) DO UPDATE
                        SET is_role = EXCLUDED.is_role, motivo = EXCLUDED.motivo, added_by = EXCLUDED.added_by
                    """,
                    guild_id, target_id, is_role, motivo, by,
                )

    async def sblocca(self, guild_id: int, target_id: int) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM ticket_blacklist WHERE guild_id = $1 AND target_id = $2", guild_id, target_id
        )
        return esito.endswith(" 1")

    async def lista_nera(self, guild_id: int, limite: int = 25) -> list[tuple[int, bool, str | None]]:
        righe = await self._pool.fetch(
            "SELECT target_id, is_role, motivo FROM ticket_blacklist WHERE guild_id = $1 ORDER BY created_at DESC LIMIT $2",
            guild_id, limite,
        )
        return [(r["target_id"], r["is_role"], r["motivo"]) for r in righe]

    # ------------------------------------------------------------ TKT-024 sospensione
    async def sospendi(self, guild_id: int, motivo: str, fino_a: datetime | None, by: int) -> None:
        await self._pool.execute(
            """
            INSERT INTO ticket_sospensioni (guild_id, fino_a, motivo, set_by) VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id) DO UPDATE SET fino_a = EXCLUDED.fino_a, motivo = EXCLUDED.motivo, set_by = EXCLUDED.set_by
            """,
            guild_id, fino_a, motivo, by,
        )

    async def riprendi(self, guild_id: int) -> bool:
        esito = await self._pool.execute("DELETE FROM ticket_sospensioni WHERE guild_id = $1", guild_id)
        return esito.endswith(" 1")

    # ------------------------------------------------------------ TKT-019 pausa
    async def azzera_pausa(self, guild_id: int, user_id: int) -> None:
        await self._pool.execute(
            """
            INSERT INTO ticket_pause_azzerate (guild_id, user_id) VALUES ($1, $2)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET azzerata_at = now()
            """,
            guild_id, user_id,
        )

    # ------------------------------------------------------------ TKT-033 reperibili
    async def reperibili(self, guild_id: int) -> list[int]:
        righe = await self._pool.fetch(
            "SELECT user_id FROM ticket_reperibili WHERE guild_id = $1 ORDER BY user_id LIMIT $2", guild_id, MAX_REPERIBILI
        )
        return [r["user_id"] for r in righe]

    async def cambia_reperibile(self, guild_id: int, user_id: int) -> bool | None:
        """True = ora reperibile, False = non più; None se il server ha già 10 reperibili."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1, $2)", 8422, guild_id % 2**31)
                tolto = await conn.execute(
                    "DELETE FROM ticket_reperibili WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
                )
                if tolto.endswith(" 1"):
                    return False
                quanti = await conn.fetchval("SELECT count(*) FROM ticket_reperibili WHERE guild_id = $1", guild_id)
                if quanti >= MAX_REPERIBILI:
                    return None
                await conn.execute(
                    "INSERT INTO ticket_reperibili (guild_id, user_id) VALUES ($1, $2)", guild_id, user_id
                )
        return True

    # ------------------------------------------------------------ tutto ciò che serve per decidere
    async def situazione(
        self, guild_id: int, user_id: int, role_ids: list[int], panel_id: int | None
    ) -> Situazione:
        """Lista nera, sospensione, regole, aperti nel pannello e pausa, in una connessione."""
        async with self._pool.acquire() as conn:
            nera = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM ticket_blacklist WHERE guild_id = $1 AND target_id = ANY($2::bigint[]))",
                guild_id, [user_id, *role_ids],
            )
            sosp = await conn.fetchrow(
                "SELECT motivo, fino_a FROM ticket_sospensioni WHERE guild_id = $1 AND (fino_a IS NULL OR fino_a > now())",
                guild_id,
            )
            s = Situazione(
                in_lista_nera=bool(nera),
                sospesa_motivo=sosp["motivo"] if sosp else None,
                sospesa_fino=sosp["fino_a"] if sosp else None,
            )
            if panel_id is None:
                return s
            r = await conn.fetchrow("SELECT * FROM ticket_panel_opzioni WHERE panel_id = $1", panel_id)
            s.opzioni = _opzioni(r) if r else Opzioni(panel_id=panel_id)
            s.regole_accesso = [
                (x["role_id"], x["permetti"])
                for x in await conn.fetch(
                    "SELECT role_id, permetti FROM ticket_panel_accesso WHERE panel_id = $1 ORDER BY posizione", panel_id
                )
            ]
            s.aperti_nel_pannello = await conn.fetchval(
                "SELECT count(*) FROM tickets WHERE panel_id = $1 AND status = 'open'", panel_id
            )
            s.ultima_apertura = await conn.fetchval(
                "SELECT max(created_at) FROM tickets WHERE guild_id = $1 AND user_id = $2 AND panel_id = $3",
                guild_id, user_id, panel_id,
            )
            s.azzerata_at = await conn.fetchval(
                "SELECT azzerata_at FROM ticket_pause_azzerate WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
            )
        return s


def _get_pool():
    from core.database import db
    return db.pool


ticket_opzioni_repo = TicketOpzioniRepository(pool_provider=_get_pool)
