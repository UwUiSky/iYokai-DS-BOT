"""
core/repositories/backup_struttura_repo.py
==========================================
Copie datate della struttura (al massimo 10 per server), modelli con codice,
stato dei caricamenti con annullo e registro di chi usa il backup (365 giorni).
Funzioni coperte: SPEC §11.15, §11.16, M 12.17, NF-39, BKP-009, BKP-010, BKP-019
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime

MAX_COPIE_PER_SERVER = 10
# Un caricamento senza notizie da tanto è morto con il bot: non blocca il prossimo.
MINUTI_CARICAMENTO_MORTO = 30


@dataclass(frozen=True)
class CopiaStruttura:
    id: int
    nome: str
    creato_il: datetime
    codice_modello: str | None


@dataclass(frozen=True)
class StatoCaricamento:
    id: int
    fonte: str
    stato: str
    passo: str
    fatti: int
    totale: int
    annulla: bool
    creato_il: datetime


class BackupStrutturaRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self):
        return self._pool_provider()

    # copie ------------------------------------------------------------
    async def salva_struttura(self, guild_id: int, nome: str, created_by: int, dati: dict) -> int | None:
        """Id della copia nuova, o None se il server ha già 10 copie."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext('backup_strutture'), $1::int)", guild_id % (1 << 31))
            quante = await conn.fetchval("SELECT count(*) FROM backup_strutture WHERE guild_id = $1", guild_id)
            if quante >= MAX_COPIE_PER_SERVER:
                return None
            return await conn.fetchval(
                "INSERT INTO backup_strutture (guild_id, nome, created_by, dati) VALUES ($1, $2, $3, $4::jsonb) RETURNING id",
                guild_id, nome[:50], created_by, json.dumps(dati, ensure_ascii=False),
            )

    async def lista_strutture(self, guild_id: int) -> list[CopiaStruttura]:
        righe = await self._pool.fetch(
            "SELECT id, nome, creato_il, codice_modello FROM backup_strutture "
            "WHERE guild_id = $1 ORDER BY creato_il DESC LIMIT $2",
            guild_id, MAX_COPIE_PER_SERVER,
        )
        return [CopiaStruttura(**dict(r)) for r in righe]

    async def leggi_struttura(self, guild_id: int, copia_id: int) -> dict | None:
        dati = await self._pool.fetchval(
            "SELECT dati FROM backup_strutture WHERE guild_id = $1 AND id = $2", guild_id, copia_id
        )
        return json.loads(dati) if dati is not None else None

    async def elimina_struttura(self, guild_id: int, copia_id: int) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM backup_strutture WHERE guild_id = $1 AND id = $2", guild_id, copia_id
        )
        return esito.endswith(" 1")

    # modelli (NF-39) --------------------------------------------------
    async def pubblica_modello(self, guild_id: int, copia_id: int) -> str | None:
        """Dà alla copia un codice condivisibile (lo stesso se lo ha già). None se la copia non c'è."""
        codice = secrets.token_urlsafe(9)
        return await self._pool.fetchval(
            "UPDATE backup_strutture SET codice_modello = COALESCE(codice_modello, $3) "
            "WHERE guild_id = $1 AND id = $2 RETURNING codice_modello",
            guild_id, copia_id, codice,
        )

    async def ritira_modello(self, guild_id: int, copia_id: int) -> bool:
        esito = await self._pool.execute(
            "UPDATE backup_strutture SET codice_modello = NULL "
            "WHERE guild_id = $1 AND id = $2 AND codice_modello IS NOT NULL",
            guild_id, copia_id,
        )
        return esito.endswith(" 1")

    async def leggi_modello(self, codice: str) -> tuple[str, dict] | None:
        riga = await self._pool.fetchrow(
            "SELECT nome, dati FROM backup_strutture WHERE codice_modello = $1", codice
        )
        return (riga["nome"], json.loads(riga["dati"])) if riga is not None else None

    # caricamenti (BKP-009/010) ----------------------------------------
    async def avvia_caricamento(self, guild_id: int, created_by: int, fonte: str, totale: int) -> int | None:
        """Id del caricamento, o None se ce n'è già uno in corso nel server."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "UPDATE backup_caricamenti SET stato = 'fallito', aggiornato_il = now() "
                "WHERE guild_id = $1 AND stato = 'in_corso' "
                "AND aggiornato_il < now() - make_interval(mins => $2)",
                guild_id, MINUTI_CARICAMENTO_MORTO,
            )
            return await conn.fetchval(
                "INSERT INTO backup_caricamenti (guild_id, created_by, fonte, totale) VALUES ($1, $2, $3, $4) "
                "ON CONFLICT (guild_id) WHERE stato = 'in_corso' DO NOTHING RETURNING id",
                guild_id, created_by, fonte[:100], totale,
            )

    async def aggiorna_caricamento(self, caricamento_id: int, passo: str, fatti: int, totale: int) -> bool:
        """Salva il passo; restituisce True se qualcuno ha chiesto di annullare."""
        return bool(await self._pool.fetchval(
            "UPDATE backup_caricamenti SET passo = $2, fatti = $3, totale = $4, aggiornato_il = now() "
            "WHERE id = $1 RETURNING annulla",
            caricamento_id, passo, fatti, totale,
        ))

    async def chiudi_caricamento(self, caricamento_id: int, stato: str) -> None:
        await self._pool.execute(
            "UPDATE backup_caricamenti SET stato = $2, aggiornato_il = now() WHERE id = $1",
            caricamento_id, stato,
        )

    async def chiedi_annullo(self, guild_id: int) -> bool:
        esito = await self._pool.execute(
            "UPDATE backup_caricamenti SET annulla = true WHERE guild_id = $1 AND stato = 'in_corso'", guild_id
        )
        return esito.endswith(" 1")

    async def ultimo_caricamento(self, guild_id: int) -> StatoCaricamento | None:
        riga = await self._pool.fetchrow(
            "SELECT id, fonte, stato, passo, fatti, totale, annulla, creato_il FROM backup_caricamenti "
            "WHERE guild_id = $1 ORDER BY creato_il DESC LIMIT 1",
            guild_id,
        )
        return StatoCaricamento(**dict(riga)) if riga is not None else None

    # registro (BKP-019) -----------------------------------------------
    async def registra(self, guild_id: int, user_id: int, azione: str, dettaglio: str = "") -> None:
        await self._pool.execute(
            "INSERT INTO backup_registro (guild_id, user_id, azione, dettaglio) VALUES ($1, $2, $3, $4)",
            guild_id, user_id, azione[:40], dettaglio[:200],
        )

    async def leggi_registro(self, guild_id: int, limite: int = 20) -> list[dict]:
        righe = await self._pool.fetch(
            "SELECT user_id, azione, dettaglio, creato_il FROM backup_registro "
            "WHERE guild_id = $1 ORDER BY creato_il DESC LIMIT $2",
            guild_id, limite,
        )
        return [dict(r) for r in righe]


def _get_pool():
    from core.database import db

    return db.pool


backup_struttura_repo = BackupStrutturaRepository(pool_provider=_get_pool)
