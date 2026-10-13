"""
core/repositories/form_repo.py
==============================
Moduli e risposte (NF-34). Tabelle: core/migrations/0096_forms.sql.
Funzioni coperte: SPEC §23 (NF-34)
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import asyncpg

from core.form_logic import MAX_MODULI, PENDING, Domanda


@dataclass(frozen=True)
class Form:
    id: int
    guild_id: int
    name: str
    title: str
    review_channel_id: int
    accept_role_id: int | None
    domande: list[Domanda]


@dataclass(frozen=True)
class FormResponse:
    id: int
    form_id: int
    guild_id: int
    user_id: int
    risposte: list[str]
    status: str
    review_message_id: int | None
    decided_by: int | None


def _json(v):
    return json.loads(v) if isinstance(v, str) else v


def _form(r) -> Form:
    return Form(
        id=r["id"], guild_id=r["guild_id"], name=r["name"], title=r["title"],
        review_channel_id=r["review_channel_id"], accept_role_id=r["accept_role_id"],
        domande=[Domanda.da_dict(d) for d in _json(r["questions"])],
    )


def _risposta(r) -> FormResponse:
    return FormResponse(
        id=r["id"], form_id=r["form_id"], guild_id=r["guild_id"], user_id=r["user_id"],
        risposte=list(_json(r["answers"])), status=r["status"],
        review_message_id=r["review_message_id"], decided_by=r["decided_by"],
    )


class FormRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def create_form(
        self, guild_id: int, name: str, title: str, review_channel_id: int,
        accept_role_id: int | None, domande: list[Domanda], created_by: int,
    ) -> str:
        """"ok", "esiste" o "pieno"; tetto e scrittura nella stessa query."""
        riga = await self._pool.fetchrow(
            """
            INSERT INTO forms (guild_id, name, title, review_channel_id, accept_role_id, questions, created_by)
            SELECT $1, $2, $3, $4, $5, $6::jsonb, $7
            WHERE (SELECT count(*) FROM forms WHERE guild_id = $1) < $8
            ON CONFLICT (guild_id, name) DO NOTHING
            RETURNING id
            """,
            guild_id, name.lower(), title, review_channel_id, accept_role_id,
            json.dumps([d.a_dict() for d in domande]), created_by, MAX_MODULI,
        )
        if riga is not None:
            return "ok"
        esiste = await self._pool.fetchval(
            "SELECT 1 FROM forms WHERE guild_id = $1 AND name = $2", guild_id, name.lower()
        )
        return "esiste" if esiste else "pieno"

    async def get_form(self, guild_id: int, name: str) -> Form | None:
        r = await self._pool.fetchrow("SELECT * FROM forms WHERE guild_id = $1 AND name = $2", guild_id, name.lower())
        return None if r is None else _form(r)

    async def get_form_by_id(self, form_id: int) -> Form | None:
        r = await self._pool.fetchrow("SELECT * FROM forms WHERE id = $1", form_id)
        return None if r is None else _form(r)

    async def list_forms(self, guild_id: int) -> list[Form]:
        return [_form(r) for r in await self._pool.fetch("SELECT * FROM forms WHERE guild_id = $1 ORDER BY name", guild_id)]

    async def delete_form(self, guild_id: int, name: str) -> bool:
        esito = await self._pool.execute("DELETE FROM forms WHERE guild_id = $1 AND name = $2", guild_id, name.lower())
        return esito.endswith(" 1")

    async def add_response(self, form: Form, user_id: int, risposte: list[str]) -> int | None:
        """None se la persona ha già una candidatura in attesa per questo modulo."""
        return await self._pool.fetchval(
            """
            INSERT INTO form_responses (form_id, guild_id, user_id, answers) VALUES ($1, $2, $3, $4::jsonb)
            ON CONFLICT (form_id, user_id) WHERE status = 'pending' DO NOTHING
            RETURNING id
            """,
            form.id, form.guild_id, user_id, json.dumps(risposte),
        )

    async def set_review_message(self, response_id: int, message_id: int) -> None:
        await self._pool.execute("UPDATE form_responses SET review_message_id = $2 WHERE id = $1", response_id, message_id)

    async def delete_response(self, response_id: int) -> None:
        await self._pool.execute("DELETE FROM form_responses WHERE id = $1", response_id)

    async def get_response(self, response_id: int) -> FormResponse | None:
        r = await self._pool.fetchrow("SELECT * FROM form_responses WHERE id = $1", response_id)
        return None if r is None else _risposta(r)

    async def decide(self, response_id: int, status: str, decided_by: int) -> bool:
        """Solo se è ancora in attesa: due clic insieme non decidono due volte."""
        riga = await self._pool.fetchval(
            "UPDATE form_responses SET status = $2, decided_by = $3 WHERE id = $1 AND status = $4 RETURNING id",
            response_id, status, decided_by, PENDING,
        )
        return riga is not None

    async def list_pending(self) -> list[FormResponse]:
        righe = await self._pool.fetch(
            "SELECT * FROM form_responses WHERE status = 'pending' AND review_message_id IS NOT NULL"
        )
        return [_risposta(r) for r in righe]


def _get_pool():
    from core.database import db
    return db.pool


form_repo = FormRepository(pool_provider=_get_pool)
