"""
core/repositories/slash_server_repo.py
======================================
Comandi e menu del server che rispondono con un tag, e lo stato della sync con Discord per server (ultima sync, impronta,
creazioni del giorno). I tetti (25 nomi, 25 sotto-comandi, 5 menu per tipo) si controllano sotto blocco per server.
Tabelle: core/migrations/0564_slash_server.sql.
Funzioni coperte: catalogo #128 UTL-045, UTL-046 (D69, B28)
"""

from __future__ import annotations

import json
from datetime import date, datetime

import asyncpg

from core.repositories.tetto_server import tetto_per_server
from core.slash_server_logic import MAX_COMANDI, MAX_MENU, MAX_SOTTO


class SlashServerRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ------------------------------------------------------------ comandi
    async def pubblica(self, guild_id: int, nome: str, sotto: str, tag: str, descrizione: str, creato_da: int) -> str:
        """"ok" (nuovo o aggiornato), "pieno" (25 nomi), "troppi" (25 sotto-comandi) o "conflitto" (stesso nome con e senza sotto-comando)."""
        async with tetto_per_server(self._pool, "comandi_server", guild_id) as conn:
            righe = await conn.fetch("SELECT sotto FROM comandi_server WHERE guild_id = $1 AND nome = $2", guild_id, nome)
            if righe and (sotto == "") != (righe[0]["sotto"] == ""):
                return "conflitto"
            if not righe and await conn.fetchval("SELECT count(DISTINCT nome) FROM comandi_server WHERE guild_id = $1", guild_id) >= MAX_COMANDI:
                return "pieno"
            if sotto and sotto not in {r["sotto"] for r in righe} and len(righe) >= MAX_SOTTO:
                return "troppi"
            await conn.execute(
                "INSERT INTO comandi_server (guild_id, nome, sotto, tag, descrizione, creato_da) VALUES ($1, $2, $3, $4, $5, $6) "
                "ON CONFLICT (guild_id, nome, sotto) DO UPDATE SET tag = EXCLUDED.tag, descrizione = EXCLUDED.descrizione",
                guild_id, nome, sotto, tag, descrizione, creato_da)
        return "ok"

    async def togli(self, guild_id: int, nome: str, sotto: str) -> bool:
        return await self._pool.execute("DELETE FROM comandi_server WHERE guild_id = $1 AND nome = $2 AND sotto = $3", guild_id, nome, sotto) != "DELETE 0"

    async def comandi(self, guild_id: int) -> list[asyncpg.Record]:
        return await self._pool.fetch(
            "SELECT nome, sotto, tag, descrizione FROM comandi_server WHERE guild_id = $1 ORDER BY nome, sotto", guild_id)

    async def comando(self, guild_id: int, nome: str, sotto: str) -> asyncpg.Record | None:
        return await self._pool.fetchrow(
            "SELECT nome, sotto, tag, descrizione FROM comandi_server WHERE guild_id = $1 AND nome = $2 AND sotto = $3", guild_id, nome, sotto)

    async def togli_per_tag(self, guild_id: int, tag: str) -> int:
        """Toglie comandi e menu che rispondono con quel tag; dice quante voci."""
        n = 0
        for tabella in ("comandi_server", "menu_server"):
            n += int((await self._pool.execute(f"DELETE FROM {tabella} WHERE guild_id = $1 AND tag = $2", guild_id, tag)).split()[-1])
        return n

    # ------------------------------------------------------------ menu
    async def aggiungi_menu(self, guild_id: int, nome: str, tipo: str, tag: str, creato_da: int) -> str:
        """"ok" (nuovo o aggiornato) o "pieno" (5 per tipo)."""
        async with tetto_per_server(self._pool, "menu_server", guild_id) as conn:
            esiste = await conn.fetchval("SELECT 1 FROM menu_server WHERE guild_id = $1 AND nome = $2 AND tipo = $3", guild_id, nome, tipo)
            if not esiste and await conn.fetchval("SELECT count(*) FROM menu_server WHERE guild_id = $1 AND tipo = $2", guild_id, tipo) >= MAX_MENU:
                return "pieno"
            await conn.execute(
                "INSERT INTO menu_server (guild_id, nome, tipo, tag, creato_da) VALUES ($1, $2, $3, $4, $5) "
                "ON CONFLICT (guild_id, nome, tipo) DO UPDATE SET tag = EXCLUDED.tag", guild_id, nome, tipo, tag, creato_da)
        return "ok"

    async def togli_menu(self, guild_id: int, nome: str, tipo: str) -> bool:
        return await self._pool.execute("DELETE FROM menu_server WHERE guild_id = $1 AND nome = $2 AND tipo = $3", guild_id, nome, tipo) != "DELETE 0"

    async def menu(self, guild_id: int) -> list[asyncpg.Record]:
        return await self._pool.fetch("SELECT nome, tipo, tag FROM menu_server WHERE guild_id = $1 ORDER BY tipo, nome", guild_id)

    async def una_voce_di_menu(self, guild_id: int, nome: str, tipo: str) -> asyncpg.Record | None:
        return await self._pool.fetchrow("SELECT nome, tipo, tag FROM menu_server WHERE guild_id = $1 AND nome = $2 AND tipo = $3", guild_id, nome, tipo)

    # ------------------------------------------------------------ stato della sync
    async def server_con_voci(self) -> list[int]:
        righe = await self._pool.fetch("SELECT guild_id FROM comandi_server UNION SELECT guild_id FROM menu_server UNION SELECT guild_id FROM slash_server_stato")
        return [r["guild_id"] for r in righe]

    async def stato(self, guild_id: int) -> asyncpg.Record | None:
        return await self._pool.fetchrow(
            "SELECT ultimo_sync, impronta, nomi, giorno, creazioni, in_coda FROM slash_server_stato WHERE guild_id = $1", guild_id)

    async def salva_sync(self, guild_id: int, quando: datetime, impronta: str, nomi: list[str], giorno: date, creazioni: int) -> None:
        await self._pool.execute(
            "INSERT INTO slash_server_stato (guild_id, ultimo_sync, impronta, nomi, giorno, creazioni, in_coda) "
            "VALUES ($1, $2, $3, $4::jsonb, $5, $6, FALSE) ON CONFLICT (guild_id) DO UPDATE SET ultimo_sync = EXCLUDED.ultimo_sync, "
            "impronta = EXCLUDED.impronta, nomi = EXCLUDED.nomi, giorno = EXCLUDED.giorno, creazioni = EXCLUDED.creazioni, in_coda = FALSE",
            guild_id, quando, impronta, json.dumps(nomi), giorno, creazioni)

    async def segna_in_coda(self, guild_id: int, in_coda: bool) -> None:
        await self._pool.execute(
            "INSERT INTO slash_server_stato (guild_id, in_coda) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET in_coda = EXCLUDED.in_coda",
            guild_id, in_coda)


def _get_pool():
    from core.database import db

    return db.pool


slash_server_repo = SlashServerRepository(pool_provider=_get_pool)
