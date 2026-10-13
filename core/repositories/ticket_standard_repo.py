"""
core/repositories/ticket_standard_repo.py
=========================================
Risposte standard dei ticket: proposte dal bot, approvate dallo staff, usate nei
ticket successivi. Restano nel server dove sono nate (D19).
Funzioni coperte: SPEC §25.97
Tabella: migrazione 0102 (`ticket_standard_replies`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class RispostaStandard:
    id: int
    guild_id: int
    panel_id: int
    title: str
    keywords: str
    body: str
    attachments: list[dict]  # [{"filename": ..., "url": ...}]
    status: str  # "proposed" | "approved"
    source_ticket_number: int | None
    approved_by: int | None
    proposal_message_id: int | None
    use_count: int
    created_at: datetime


def _risposta(r) -> RispostaStandard:
    allegati = r["attachments"]
    if isinstance(allegati, str):
        allegati = json.loads(allegati)
    return RispostaStandard(
        id=r["id"], guild_id=r["guild_id"], panel_id=r["panel_id"], title=r["title"],
        keywords=r["keywords"], body=r["body"], attachments=list(allegati or []),
        status=r["status"], source_ticket_number=r["source_ticket_number"],
        approved_by=r["approved_by"], proposal_message_id=r["proposal_message_id"],
        use_count=r["use_count"], created_at=r["created_at"],
    )


class TicketStandardRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def conta(self, guild_id: int) -> int:
        return await self._pool.fetchval(
            "SELECT count(*) FROM ticket_standard_replies WHERE guild_id = $1", guild_id
        )

    async def crea_proposta(
        self, guild_id: int, panel_id: int, title: str, keywords: str, body: str,
        source_ticket_number: int | None,
    ) -> RispostaStandard:
        riga = await self._pool.fetchrow(
            """
            INSERT INTO ticket_standard_replies
                (guild_id, panel_id, title, keywords, body, source_ticket_number)
            VALUES ($1, $2, $3, $4, $5, $6) RETURNING *
            """,
            guild_id, panel_id, title, keywords, body, source_ticket_number,
        )
        return _risposta(riga)

    async def imposta_messaggio(self, reply_id: int, message_id: int, allegati: list[dict]) -> None:
        await self._pool.execute(
            "UPDATE ticket_standard_replies SET proposal_message_id = $2, attachments = $3::jsonb WHERE id = $1",
            reply_id, message_id, json.dumps(allegati),
        )

    async def per_id(self, reply_id: int) -> RispostaStandard | None:
        riga = await self._pool.fetchrow("SELECT * FROM ticket_standard_replies WHERE id = $1", reply_id)
        return _risposta(riga) if riga else None

    async def elenca(self, guild_id: int, stato: str | None = None, limite: int = 25) -> list[RispostaStandard]:
        righe = await self._pool.fetch(
            """
            SELECT * FROM ticket_standard_replies
            WHERE guild_id = $1 AND ($2::text IS NULL OR status = $2)
            ORDER BY id DESC LIMIT $3
            """,
            guild_id, stato, limite,
        )
        return [_risposta(r) for r in righe]

    async def tutte_del_pannello(self, guild_id: int, panel_id: int) -> list[RispostaStandard]:
        """Approvate e proposte: serve a non riproporre una risposta già coperta."""
        righe = await self._pool.fetch(
            "SELECT * FROM ticket_standard_replies WHERE guild_id = $1 AND panel_id = $2", guild_id, panel_id
        )
        return [_risposta(r) for r in righe]

    async def approvate(self, guild_id: int, panel_id: int) -> list[RispostaStandard]:
        righe = await self._pool.fetch(
            "SELECT * FROM ticket_standard_replies WHERE guild_id = $1 AND panel_id = $2 AND status = 'approved'",
            guild_id, panel_id,
        )
        return [_risposta(r) for r in righe]

    async def approva(self, reply_id: int, by: int) -> bool:
        """True solo se era ancora una proposta (due clic insieme: uno solo vince)."""
        esito = await self._pool.execute(
            """
            UPDATE ticket_standard_replies
            SET status = 'approved', approved_by = $2, approved_at = now()
            WHERE id = $1 AND status = 'proposed'
            """,
            reply_id, by,
        )
        return esito.endswith(" 1")

    async def aggiorna(self, reply_id: int, title: str, keywords: str, body: str) -> bool:
        esito = await self._pool.execute(
            "UPDATE ticket_standard_replies SET title = $2, keywords = $3, body = $4 WHERE id = $1",
            reply_id, title, keywords, body,
        )
        return esito.endswith(" 1")

    async def elimina(self, guild_id: int, reply_id: int) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM ticket_standard_replies WHERE id = $1 AND guild_id = $2", reply_id, guild_id
        )
        return esito.endswith(" 1")

    async def usata(self, reply_id: int) -> None:
        await self._pool.execute(
            "UPDATE ticket_standard_replies SET use_count = use_count + 1 WHERE id = $1", reply_id
        )


def _get_pool():
    from core.database import db
    return db.pool


ticket_standard_repo = TicketStandardRepository(pool_provider=_get_pool)
