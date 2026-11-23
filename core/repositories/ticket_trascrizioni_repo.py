"""
core/repositories/ticket_trascrizioni_repo.py
=============================================
Trascrizioni dei ticket conservate cifrate (TKT-072, D111) e le opzioni del server (accesa/spenta, giorni).
Qui si salva solo il dato già cifrato; la cifratura sta in `core/ticket_trascrizioni_logic.py`.
Voto, motivo di chiusura e nome del pannello si leggono dal ticket, non si copiano.
Funzioni coperte: SPEC §13.22 (TKT-072)
Dipende da: core/migrations/0774_ticket_trascrizioni.sql
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg

from core.ticket_trascrizioni_logic import GIORNI_DI_BASE, MAX_GIORNI, Filtro


@dataclass(frozen=True)
class Opzioni:
    attiva: bool = True
    giorni: int = GIORNI_DI_BASE


@dataclass(frozen=True)
class Riga:
    id: int
    guild_id: int
    ticket_id: int
    ticket_number: int
    user_id: int
    panel_id: int | None
    nome_pannello: str | None
    voto: int | None
    motivo: str | None
    creata_il: datetime
    scade_il: datetime
    peso: int


_RIGA = """
    SELECT t.id, t.guild_id, t.ticket_id, t.ticket_number, t.user_id, t.panel_id, p.name AS nome_pannello,
           k.rating AS voto, k.close_reason AS motivo, t.creata_il, t.scade_il, t.peso
    FROM ticket_trascrizioni t
    LEFT JOIN tickets k ON k.id = t.ticket_id
    LEFT JOIN ticket_panels p ON p.id = t.panel_id
"""


def _riga(r) -> Riga:
    return Riga(**{k: r[k] for k in Riga.__dataclass_fields__})


def _come(testo: str) -> str:
    """Il testo da cercare come parte di una frase: % e _ valgono come lettere."""
    return "%" + testo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class TicketTrascrizioniRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def opzioni(self, guild_id: int) -> Opzioni:
        r = await self._pool.fetchrow("SELECT attiva, giorni FROM ticket_trascrizioni_opzioni WHERE guild_id=$1", guild_id)
        return Opzioni(r["attiva"], r["giorni"]) if r else Opzioni()

    async def imposta_opzioni(self, guild_id: int, attiva: bool, giorni: int) -> Opzioni:
        giorni = max(1, min(int(giorni), MAX_GIORNI))
        await self._pool.execute(
            "INSERT INTO ticket_trascrizioni_opzioni (guild_id, attiva, giorni) VALUES ($1, $2, $3) "
            "ON CONFLICT (guild_id) DO UPDATE SET attiva = EXCLUDED.attiva, giorni = EXCLUDED.giorni",
            guild_id, attiva, giorni,
        )
        return Opzioni(attiva, giorni)

    async def salva(
        self, guild_id: int, ticket_id: int, ticket_number: int, user_id: int, panel_id: int | None,
        cifrato: str, scade_il: datetime,
    ) -> int:
        """Una trascrizione per ticket: una seconda chiusura sostituisce la prima."""
        return await self._pool.fetchval(
            "INSERT INTO ticket_trascrizioni (guild_id, ticket_id, ticket_number, user_id, panel_id, cifrato, peso, scade_il) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT (guild_id, ticket_id) DO UPDATE SET "
            "cifrato = EXCLUDED.cifrato, peso = EXCLUDED.peso, scade_il = EXCLUDED.scade_il, creata_il = now() "
            "RETURNING id",
            guild_id, ticket_id, ticket_number, user_id, panel_id, cifrato, len(cifrato), scade_il,
        )

    async def elenco(self, guild_id: int, filtro: Filtro, limite: int, pagina: int = 0) -> list[Riga]:
        dove, args = ["t.guild_id = $1", "t.scade_il > now()"], [guild_id]
        if filtro.utente_id is not None:
            args.append(filtro.utente_id)
            dove.append(f"t.user_id = ${len(args)}")
        if filtro.panel_id is not None:
            args.append(filtro.panel_id)
            dove.append(f"t.panel_id = ${len(args)}")
        if filtro.voto is not None:
            args.append(filtro.voto)
            dove.append(f"k.rating = ${len(args)}")
        if filtro.motivo:
            args.append(_come(filtro.motivo))
            dove.append(f"k.close_reason ILIKE ${len(args)} ESCAPE '\\'")
        args += [limite + 1, max(0, pagina) * limite]
        righe = await self._pool.fetch(
            f"{_RIGA} WHERE {' AND '.join(dove)} ORDER BY t.creata_il DESC, t.id DESC "
            f"LIMIT ${len(args) - 1} OFFSET ${len(args)}",
            *args,
        )
        return [_riga(r) for r in righe]

    async def pannelli(self, guild_id: int) -> list[tuple[int, str]]:
        righe = await self._pool.fetch(
            "SELECT DISTINCT p.id, p.name FROM ticket_trascrizioni t JOIN ticket_panels p ON p.id = t.panel_id "
            "WHERE t.guild_id = $1 AND t.scade_il > now() ORDER BY p.name LIMIT 50", guild_id,
        )
        return [(r["id"], r["name"]) for r in righe]

    async def leggi(self, guild_id: int, trascrizione_id: int) -> tuple[Riga, str] | None:
        """La riga e il dato cifrato, solo se è di questo server e non è scaduta."""
        r = await self._pool.fetchrow(
            f"SELECT x.*, t.cifrato FROM ({_RIGA}) x JOIN ticket_trascrizioni t ON t.id = x.id "
            "WHERE t.id = $1 AND t.guild_id = $2 AND t.scade_il > now()",
            trascrizione_id, guild_id,
        )
        return (_riga(r), r["cifrato"]) if r else None

    async def pulisci_scadute(self) -> int:
        """Toglie le scadute. Lo fa anche il giro della conservazione dei dati (registro), questo serve ai test e a chi vuole subito."""
        stato = await self._pool.execute("DELETE FROM ticket_trascrizioni WHERE scade_il <= now()")
        return int(stato.rsplit(" ", 1)[-1])


def _get_pool():
    from core.database import db

    return db.pool


ticket_trascrizioni_repo = TicketTrascrizioniRepository(pool_provider=_get_pool)
