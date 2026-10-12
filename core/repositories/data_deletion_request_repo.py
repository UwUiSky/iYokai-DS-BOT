"""
core/repositories/data_deletion_request_repo.py
===============================================
Richieste di cancellazione dei dati di un utente e loro esito (tabella
`data_deletion_requests`, migrazione 0036). Una sola richiesta in attesa per
utente. L'esito è un rapporto senza dati personali: serve a dimostrare che cosa
è stato fatto.
Funzioni coperte: SPEC §19 (NF-04)
"""

from __future__ import annotations

import json

import asyncpg

STATO_IN_ATTESA = "in_attesa"
STATO_ESEGUITA = "eseguita"
STATO_RIFIUTATA = "rifiutata"
MOTIVO_MAX = 300


class DataDeletionRequestRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def crea(self, user_id: int, motivo: str | None = None) -> tuple[int, bool]:
        """
        Crea la richiesta. Restituisce (id, nuova): se l'utente ne ha già una in
        attesa non ne nasce un'altra e `nuova` è False.
        """
        motivo = motivo[:MOTIVO_MAX] if motivo else None
        riga = await self._pool.fetchrow(
            """
            INSERT INTO data_deletion_requests (user_id, motivo) VALUES ($1, $2)
            ON CONFLICT (user_id) WHERE stato = 'in_attesa' DO NOTHING
            RETURNING id
            """,
            user_id,
            motivo,
        )
        if riga is not None:
            return riga["id"], True
        esistente = await self._pool.fetchval(
            "SELECT id FROM data_deletion_requests WHERE user_id = $1 AND stato = 'in_attesa'",
            user_id,
        )
        return esistente, False

    async def get(self, richiesta_id: int) -> dict | None:
        riga = await self._pool.fetchrow(
            "SELECT * FROM data_deletion_requests WHERE id = $1", richiesta_id
        )
        return _a_dict(riga)

    async def in_attesa(self, limite: int = 100) -> list[dict]:
        righe = await self._pool.fetch(
            "SELECT * FROM data_deletion_requests WHERE stato = 'in_attesa' "
            "ORDER BY richiesta_il LIMIT $1",
            limite,
        )
        return [_a_dict(r) for r in righe]

    async def chiudi(
        self,
        richiesta_id: int,
        stato: str,
        deciso_da: int,
        esito: dict | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> bool:
        """Chiude una richiesta ancora in attesa. False se non esiste o era già chiusa."""
        sql = (
            "UPDATE data_deletion_requests SET stato = $2, deciso_il = now(), deciso_da = $3, "
            "esito = $4::jsonb WHERE id = $1 AND stato = 'in_attesa'"
        )
        argomenti = (richiesta_id, stato, deciso_da, json.dumps(esito) if esito is not None else None)
        esecutore = conn if conn is not None else self._pool
        esito_sql = await esecutore.execute(sql, *argomenti)
        return esito_sql.endswith(" 1")


def _a_dict(riga) -> dict | None:
    if riga is None:
        return None
    dati = dict(riga)
    if isinstance(dati.get("esito"), str):
        dati["esito"] = json.loads(dati["esito"])
    return dati


def _get_pool():
    from core.database import db

    return db.pool


data_deletion_request_repo = DataDeletionRequestRepository(pool_provider=_get_pool)
