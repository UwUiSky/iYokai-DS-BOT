"""
core/repositories/custom_command_repo.py
========================================
Comandi personalizzati del server (NF-09) e prefisso per usarli
(guild_config.prefix, M 10.15). Tabella: core/migrations/0082_custom_commands.sql.
Funzioni coperte: SPEC §22 (NF-09)
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from core.repositories.tetto_server import tetto_per_server

from core.custom_command_logic import MAX_TAG


@dataclass(frozen=True)
class CustomCommand:
    guild_id: int
    name: str
    response: str
    use_embed: bool
    role_id: int | None
    role_action: str
    cooldown_seconds: int
    ping_ruoli: bool
    uses: int


_COLONNE = "guild_id, name, response, use_embed, role_id, role_action, cooldown_seconds, ping_ruoli, uses"
_MODIFICABILI = {"response", "use_embed", "role_id", "role_action", "cooldown_seconds", "ping_ruoli"}


class CustomCommandRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def create_tag(
        self,
        guild_id: int,
        name: str,
        *,
        response: str,
        use_embed: bool,
        role_id: int | None,
        role_action: str,
        cooldown_seconds: int,
        ping_ruoli: bool,
        created_by: int,
    ) -> str:
        """"ok", "esiste" (nome già preso) o "pieno" (tetto per server). Controllo e scrittura in una query."""
        async with tetto_per_server(self._pool, "custom_commands", guild_id) as conn:
            riga = await conn.fetchrow(
                """
                INSERT INTO custom_commands
                    (guild_id, name, response, use_embed, role_id, role_action, cooldown_seconds, ping_ruoli, created_by)
                SELECT $1, $2, $3, $4, $5, $6, $7, $8, $9
                WHERE (SELECT count(*) FROM custom_commands WHERE guild_id = $1) < $10
                ON CONFLICT (guild_id, name) DO NOTHING
                RETURNING name
                """,
                guild_id, name, response, use_embed, role_id, role_action, cooldown_seconds, ping_ruoli,
                created_by, MAX_TAG,
            )
            if riga is not None:
                return "ok"
            esiste = await conn.fetchval(
                "SELECT 1 FROM custom_commands WHERE guild_id = $1 AND name = $2", guild_id, name
            )
            return "esiste" if esiste else "pieno"

    async def get_tag(self, guild_id: int, name: str) -> CustomCommand | None:
        r = await self._pool.fetchrow(
            f"SELECT {_COLONNE} FROM custom_commands WHERE guild_id = $1 AND name = $2", guild_id, name
        )
        return None if r is None else CustomCommand(**dict(r))

    async def list_tags(self, guild_id: int) -> list[CustomCommand]:
        righe = await self._pool.fetch(
            f"SELECT {_COLONNE} FROM custom_commands WHERE guild_id = $1 ORDER BY name", guild_id
        )
        return [CustomCommand(**dict(r)) for r in righe]

    async def search_names(self, guild_id: int, parte: str, limite: int = 25) -> list[str]:
        """Per il completamento automatico: al massimo `limite` nomi che contengono `parte`."""
        pulita = parte.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        righe = await self._pool.fetch(
            "SELECT name FROM custom_commands WHERE guild_id = $1 AND name LIKE $2 ORDER BY name LIMIT $3",
            guild_id, f"%{pulita}%", limite,
        )
        return [r["name"] for r in righe]

    async def update_tag(self, guild_id: int, name: str, **campi) -> bool:
        """Cambia solo i campi dati (nomi presi da un elenco fisso, valori sempre come parametri)."""
        if not campi or not set(campi) <= _MODIFICABILI:
            raise ValueError(f"Campi non modificabili: {sorted(set(campi) - _MODIFICABILI)}")
        impostazioni = ", ".join(f"{col} = ${i}" for i, col in enumerate(campi, start=3))
        esito = await self._pool.execute(
            f"UPDATE custom_commands SET {impostazioni} WHERE guild_id = $1 AND name = $2",
            guild_id, name, *campi.values(),
        )
        return esito.endswith(" 1")

    async def delete_tag(self, guild_id: int, name: str) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM custom_commands WHERE guild_id = $1 AND name = $2", guild_id, name
        )
        return esito.endswith(" 1")

    async def add_use(self, guild_id: int, name: str) -> None:
        await self._pool.execute(
            "UPDATE custom_commands SET uses = uses + 1 WHERE guild_id = $1 AND name = $2", guild_id, name
        )

    async def get_prefix(self, guild_id: int) -> str | None:
        return await self._pool.fetchval("SELECT prefix FROM guild_config WHERE guild_id = $1", guild_id)

    async def set_prefix(self, guild_id: int, prefix: str | None) -> None:
        await self._pool.execute(
            """
            INSERT INTO guild_config (guild_id, prefix) VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET prefix = EXCLUDED.prefix, updated_at = now()
            """,
            guild_id, prefix,
        )


def _get_pool():
    from core.database import db
    return db.pool


custom_command_repo = CustomCommandRepository(pool_provider=_get_pool)
