"""
core/repositories/role_menu_repo.py
======================================
Persistenza dei Role Menu (SPEC.md §14.1-14.3). Due tabelle: il menu
(canale, messaggio, modalità, impostazioni) e le sue opzioni (ruolo,
emoji, etichetta).
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg


@dataclass(frozen=True)
class RoleMenu:
    id: int
    guild_id: int
    channel_id: int
    message_id: int | None
    mode: str  # "reaction" | "button" | "select"
    toggle: bool
    max_selectable: int | None
    title: str
    description: str


@dataclass(frozen=True)
class RoleMenuOption:
    id: int
    menu_id: int
    role_id: int
    emoji: str | None
    label: str | None
    position: int


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS role_menus (
            id             SERIAL PRIMARY KEY,
            guild_id       BIGINT NOT NULL,
            channel_id     BIGINT NOT NULL,
            message_id     BIGINT,
            mode           TEXT NOT NULL,
            toggle         BOOLEAN NOT NULL DEFAULT TRUE,
            max_selectable INTEGER,
            title          TEXT NOT NULL,
            description    TEXT NOT NULL DEFAULT ''
        );

        -- Interrogata da on_raw_reaction_add/remove ad ogni reazione
        -- su QUALUNQUE messaggio del server: deve essere veloce.
        CREATE INDEX IF NOT EXISTS idx_role_menus_message
            ON role_menus (guild_id, message_id);

        CREATE TABLE IF NOT EXISTS role_menu_options (
            id       SERIAL PRIMARY KEY,
            menu_id  INTEGER NOT NULL REFERENCES role_menus(id) ON DELETE CASCADE,
            role_id  BIGINT NOT NULL,
            emoji    TEXT,
            label    TEXT,
            position INTEGER NOT NULL DEFAULT 0,
            UNIQUE (menu_id, role_id)
        );

        CREATE INDEX IF NOT EXISTS idx_role_menu_options_menu
            ON role_menu_options (menu_id, position);
        """
    )


class RoleMenuRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    def _row_to_menu(self, row) -> RoleMenu:
        return RoleMenu(
            id=row["id"],
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            message_id=row["message_id"],
            mode=row["mode"],
            toggle=row["toggle"],
            max_selectable=row["max_selectable"],
            title=row["title"],
            description=row["description"],
        )

    async def create_menu(
        self,
        guild_id: int,
        channel_id: int,
        mode: str,
        toggle: bool,
        max_selectable: int | None,
        title: str,
        description: str,
    ) -> int:
        row = await self._pool.fetchrow(
            """
            INSERT INTO role_menus
                (guild_id, channel_id, mode, toggle, max_selectable, title, description)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
            """,
            guild_id,
            channel_id,
            mode,
            toggle,
            max_selectable,
            title,
            description,
        )
        return row["id"]

    async def set_menu_message(self, menu_id: int, message_id: int) -> None:
        await self._pool.execute(
            "UPDATE role_menus SET message_id = $2 WHERE id = $1", menu_id, message_id
        )

    async def get_menu(self, menu_id: int) -> RoleMenu | None:
        row = await self._pool.fetchrow("SELECT * FROM role_menus WHERE id = $1", menu_id)
        return self._row_to_menu(row) if row else None

    async def get_menu_by_message(self, guild_id: int, message_id: int) -> RoleMenu | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM role_menus WHERE guild_id = $1 AND message_id = $2",
            guild_id,
            message_id,
        )
        return self._row_to_menu(row) if row else None

    async def list_menus_by_mode(self, mode: str) -> list[RoleMenu]:
        """
        Usata all'avvio del bot per ricostruire le View dinamiche
        persistenti di tutti i menu bottone/select esistenti (vedi
        cogs/utility/role_menus.py) — serve QUALUNQUE server, non
        filtrata per guild_id.
        """
        rows = await self._pool.fetch(
            "SELECT * FROM role_menus WHERE mode = $1 AND message_id IS NOT NULL", mode
        )
        return [self._row_to_menu(r) for r in rows]

    async def delete_menu(self, menu_id: int) -> None:
        await self._pool.execute("DELETE FROM role_menus WHERE id = $1", menu_id)

    async def add_option(
        self, menu_id: int, role_id: int, emoji: str | None, label: str | None
    ) -> int:
        posizione = await self._pool.fetchval(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM role_menu_options WHERE menu_id = $1",
            menu_id,
        )
        row = await self._pool.fetchrow(
            """
            INSERT INTO role_menu_options (menu_id, role_id, emoji, label, position)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (menu_id, role_id) DO UPDATE
                SET emoji = EXCLUDED.emoji, label = EXCLUDED.label
            RETURNING id
            """,
            menu_id,
            role_id,
            emoji,
            label,
            posizione,
        )
        return row["id"]

    async def remove_option(self, menu_id: int, role_id: int) -> bool:
        result = await self._pool.execute(
            "DELETE FROM role_menu_options WHERE menu_id = $1 AND role_id = $2",
            menu_id,
            role_id,
        )
        return result.endswith(" 1")

    async def get_options(self, menu_id: int) -> list[RoleMenuOption]:
        rows = await self._pool.fetch(
            "SELECT * FROM role_menu_options WHERE menu_id = $1 ORDER BY position",
            menu_id,
        )
        return [
            RoleMenuOption(
                id=r["id"],
                menu_id=r["menu_id"],
                role_id=r["role_id"],
                emoji=r["emoji"],
                label=r["label"],
                position=r["position"],
            )
            for r in rows
        ]

    async def count_options(self, menu_id: int) -> int:
        return await self._pool.fetchval(
            "SELECT COUNT(*) FROM role_menu_options WHERE menu_id = $1", menu_id
        )

    async def get_option_by_emoji(self, menu_id: int, emoji: str) -> RoleMenuOption | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM role_menu_options WHERE menu_id = $1 AND emoji = $2",
            menu_id,
            emoji,
        )
        if row is None:
            return None
        return RoleMenuOption(
            id=row["id"],
            menu_id=row["menu_id"],
            role_id=row["role_id"],
            emoji=row["emoji"],
            label=row["label"],
            position=row["position"],
        )


def _get_pool():
    from core.database import db
    return db.pool


role_menu_repo = RoleMenuRepository(pool_provider=_get_pool)
