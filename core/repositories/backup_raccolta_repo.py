"""
core/repositories/backup_raccolta_repo.py
=========================================
Raccolta pubblica dei modelli di server: proposte in revisione, approvati con voti (uno per persona), modifica
e decisione dell'owner. Un modello non approvato non si legge mai da chi non è l'owner (funzioni `*_pubblic*`).
Funzioni coperte: BKP-022, BKP-023 (D127, D130)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from core.backup_raccolta_logic import MAX_IN_REVISIONE_PER_SERVER


@dataclass(frozen=True)
class ModelloRaccolta:
    id: int
    nome: str
    descrizione: str
    lingua: str
    stato: str
    voti: int
    ruoli: int
    categorie: int
    canali: int
    creato_il: datetime
    guild_id: int = 0


_COLONNE = (
    "m.id, m.nome, m.descrizione, m.lingua, m.stato, m.creato_il, m.guild_id, "
    "(SELECT count(*) FROM backup_raccolta_voti v WHERE v.modello_id = m.id) AS voti, "
    "jsonb_array_length(m.struttura->'ruoli') AS ruoli, jsonb_array_length(m.struttura->'categorie') AS categorie, "
    "jsonb_array_length(m.struttura->'canali') AS canali"
)


def _modello(r) -> ModelloRaccolta:
    return ModelloRaccolta(**{k: r[k] for k in ModelloRaccolta.__dataclass_fields__})


class BackupRaccoltaRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self):
        return self._pool_provider()

    async def proponi(self, guild_id: int, user_id: int, nome: str, descrizione: str, lingua: str, struttura: dict) -> int | None:
        """Id della proposta (stato «revisione»), o None se il server ne ha già troppe in attesa."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext('backup_raccolta'), $1::int)", guild_id % (1 << 31))
            attese = await conn.fetchval(
                "SELECT count(*) FROM backup_raccolta WHERE guild_id = $1 AND stato = 'revisione'", guild_id
            )
            if attese >= MAX_IN_REVISIONE_PER_SERVER:
                return None
            return await conn.fetchval(
                "INSERT INTO backup_raccolta (guild_id, proposto_da, nome, descrizione, lingua, struttura) "
                "VALUES ($1, $2, $3, $4, $5, $6::jsonb) RETURNING id",
                guild_id, user_id, nome, descrizione, lingua, json.dumps(struttura),
            )

    async def elenco_pubblico(
        self, lingua: str | None = None, ricerca: str = "", limite: int = 25, salta: int = 0
    ) -> list[ModelloRaccolta]:
        """Solo i modelli APPROVATI, i più votati in alto."""
        righe = await self._pool.fetch(
            f"SELECT {_COLONNE} FROM backup_raccolta m WHERE m.stato = 'approvato' "
            "AND ($1::text IS NULL OR m.lingua = $1) "
            "AND ($2 = '' OR m.nome ILIKE '%' || $2 || '%' OR m.descrizione ILIKE '%' || $2 || '%') "
            "ORDER BY voti DESC, m.id DESC LIMIT $3 OFFSET $4",
            lingua, ricerca, max(1, min(limite, 100)), max(0, salta),
        )
        return [_modello(r) for r in righe]

    async def leggi_pubblico(self, modello_id: int) -> tuple[ModelloRaccolta, dict] | None:
        """Scheda e struttura di un modello approvato; di uno in revisione o rifiutato: None."""
        r = await self._pool.fetchrow(
            f"SELECT {_COLONNE}, m.struttura FROM backup_raccolta m WHERE m.id = $1 AND m.stato = 'approvato'", modello_id
        )
        return (_modello(r), json.loads(r["struttura"])) if r is not None else None

    async def vota(self, modello_id: int, user_id: int) -> str:
        """«nuovo», «gia» (stesso voto già dato: conta una volta sola) o «assente» (non approvato o non esiste)."""
        async with self._pool.acquire() as conn, conn.transaction():
            if not await conn.fetchval("SELECT 1 FROM backup_raccolta WHERE id = $1 AND stato = 'approvato'", modello_id):
                return "assente"
            fatto = await conn.fetchval(
                "INSERT INTO backup_raccolta_voti (modello_id, user_id) VALUES ($1, $2) "
                "ON CONFLICT DO NOTHING RETURNING 1", modello_id, user_id,
            )
            return "nuovo" if fatto else "gia"

    async def del_server(self, guild_id: int) -> list[ModelloRaccolta]:
        """Le proposte di un server, in ogni stato (le vede solo chi le ha fatte)."""
        righe = await self._pool.fetch(
            f"SELECT {_COLONNE} FROM backup_raccolta m WHERE m.guild_id = $1 ORDER BY m.id DESC LIMIT 25", guild_id
        )
        return [_modello(r) for r in righe]

    # ---- owner del bot ----
    async def da_rivedere(self, stato: str = "revisione", limite: int = 50) -> list[ModelloRaccolta]:
        righe = await self._pool.fetch(
            f"SELECT {_COLONNE} FROM backup_raccolta m WHERE m.stato = $1 ORDER BY m.id LIMIT $2", stato, max(1, min(limite, 100))
        )
        return [_modello(r) for r in righe]

    async def leggi_per_owner(self, modello_id: int) -> tuple[ModelloRaccolta, dict] | None:
        r = await self._pool.fetchrow(f"SELECT {_COLONNE}, m.struttura FROM backup_raccolta m WHERE m.id = $1", modello_id)
        return (_modello(r), json.loads(r["struttura"])) if r is not None else None

    async def decidi(self, modello_id: int, approva: bool, owner_id: int) -> bool:
        """Approva o rifiuta (anche un modello già approvato si può togliere). False se non esiste o è già in quello stato."""
        esito = await self._pool.execute(
            "UPDATE backup_raccolta SET stato = $2, deciso_da = $3, deciso_il = now() WHERE id = $1 AND stato <> $2",
            modello_id, "approvato" if approva else "rifiutato", owner_id,
        )
        return esito.endswith(" 1")

    async def modifica(self, modello_id: int, nome: str, descrizione: str, struttura: dict) -> bool:
        esito = await self._pool.execute(
            "UPDATE backup_raccolta SET nome = $2, descrizione = $3, struttura = $4::jsonb, modificato_il = now() WHERE id = $1",
            modello_id, nome, descrizione, json.dumps(struttura),
        )
        return esito.endswith(" 1")


def _get_pool():
    from core.database import db

    return db.pool


backup_raccolta_repo = BackupRaccoltaRepository(pool_provider=_get_pool)
