"""
core/repositories/greetings_repo.py
======================================
Persistenza di Welcome / Goodbye / Boost messages (SPEC.md
§14.4-14.6). Una sola tabella, tutti e tre i tipi di messaggio
insieme — sono impostazioni dello stesso "pannello" concettuale per
un admin, non serve separarle in tabelle diverse.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import asyncpg

from core.greetings_logic import (
    DEFAULT_BOOST_TEMPLATE,
    DEFAULT_GOODBYE_TEMPLATE,
    DEFAULT_WELCOME_TEMPLATE,
)


@dataclass(frozen=True)
class GreetingsConfig:
    guild_id: int
    welcome_enabled: bool
    welcome_channel_id: int | None
    welcome_message: str
    welcome_dm: bool
    goodbye_enabled: bool
    goodbye_channel_id: int | None
    goodbye_message: str
    boost_enabled: bool
    boost_channel_id: int | None
    boost_message: str
    # D12 / M 10.6: ping di ruolo ammessi solo se chi ha configurato il
    # messaggio aveva "Menziona tutti".
    welcome_ping_ruoli: bool = False
    goodbye_ping_ruoli: bool = False
    boost_ping_ruoli: bool = False
    # NF-11: immagine di benvenuto (colonne di core/migrations/0084_greetings_immagine.sql).
    welcome_image_enabled: bool = False
    welcome_image_template: str = "scuro"
    welcome_image_shape: str = "tondo"
    welcome_image_color: str = "#FFFFFF"
    welcome_image_title: str = "Benvenuto"
    welcome_image_has_background: bool = False
    # RUO-004, 007, 008, 010 (migrazione 0643)
    welcome_image_opacity: int = 65
    welcome_image_text: str = ""
    welcome_image_order: str = "insieme"
    welcome_image_align: str = "sinistra"
    welcome_image_name_color: str = ""
    # RUO-001, 014, 015 (migrazione 0644): nome dell'embed salvato ('' = nessuno)
    welcome_embed: str = ""
    dm_embed: str = ""
    goodbye_embed: str = ""
    # RUO-027 (migrazione 0646): canale degli avvisi «argomento cambiato» (None = spenti)
    topic_notice_channel_id: int | None = None
    # RUO-024 (migrazione 0645): emoji sul primo messaggio di un nuovo membro ('' = spenta)
    first_message_reaction: str = ""
    # RUO-013, 017, 023, 025 (migrazione 0330).
    welcome_dm_message: str = ""
    welcome_variants: list[str] = field(default_factory=list)
    welcome_reactions: list[str] = field(default_factory=list)
    ban_message: str = ""
    # D37: chi esce tra entrambi / solo_ban / solo_addio / nessuno (migrazione 0400).
    leave_mode: str = "entrambi"


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS greetings_config (
            guild_id           BIGINT PRIMARY KEY,
            welcome_enabled    BOOLEAN NOT NULL DEFAULT FALSE,
            welcome_channel_id BIGINT,
            welcome_message    TEXT NOT NULL DEFAULT '',
            welcome_dm         BOOLEAN NOT NULL DEFAULT FALSE,
            goodbye_enabled    BOOLEAN NOT NULL DEFAULT FALSE,
            goodbye_channel_id BIGINT,
            goodbye_message    TEXT NOT NULL DEFAULT '',
            boost_enabled      BOOLEAN NOT NULL DEFAULT FALSE,
            boost_channel_id   BIGINT,
            boost_message      TEXT NOT NULL DEFAULT ''
        );
        """
    )


class GreetingsRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def get_config(self, guild_id: int) -> GreetingsConfig:
        row = await self._pool.fetchrow(
            "SELECT * FROM greetings_config WHERE guild_id = $1", guild_id
        )
        if row is None:
            return GreetingsConfig(
                guild_id=guild_id,
                welcome_enabled=False,
                welcome_channel_id=None,
                welcome_message=DEFAULT_WELCOME_TEMPLATE,
                welcome_dm=False,
                goodbye_enabled=False,
                goodbye_channel_id=None,
                goodbye_message=DEFAULT_GOODBYE_TEMPLATE,
                boost_enabled=False,
                boost_channel_id=None,
                boost_message=DEFAULT_BOOST_TEMPLATE,
            )
        return GreetingsConfig(
            guild_id=row["guild_id"],
            welcome_enabled=row["welcome_enabled"],
            welcome_channel_id=row["welcome_channel_id"],
            welcome_message=row["welcome_message"] or DEFAULT_WELCOME_TEMPLATE,
            welcome_dm=row["welcome_dm"],
            goodbye_enabled=row["goodbye_enabled"],
            goodbye_channel_id=row["goodbye_channel_id"],
            goodbye_message=row["goodbye_message"] or DEFAULT_GOODBYE_TEMPLATE,
            boost_enabled=row["boost_enabled"],
            boost_channel_id=row["boost_channel_id"],
            boost_message=row["boost_message"] or DEFAULT_BOOST_TEMPLATE,
            welcome_ping_ruoli=row["welcome_ping_ruoli"],
            goodbye_ping_ruoli=row["goodbye_ping_ruoli"],
            boost_ping_ruoli=row["boost_ping_ruoli"],
            welcome_image_enabled=row["welcome_image_enabled"],
            welcome_image_template=row["welcome_image_template"],
            welcome_image_shape=row["welcome_image_shape"],
            welcome_image_color=row["welcome_image_color"],
            welcome_image_title=row["welcome_image_title"],
            welcome_image_has_background=row["welcome_image_has_background"],
            first_message_reaction=row["first_message_reaction"],
            topic_notice_channel_id=row["topic_notice_channel_id"],
            welcome_embed=row["welcome_embed"],
            dm_embed=row["dm_embed"],
            goodbye_embed=row["goodbye_embed"],
            welcome_image_opacity=row["welcome_image_opacity"],
            welcome_image_text=row["welcome_image_text"],
            welcome_image_order=row["welcome_image_order"],
            welcome_image_align=row["welcome_image_align"],
            welcome_image_name_color=row["welcome_image_name_color"],
            welcome_dm_message=row["welcome_dm_message"],
            welcome_variants=list(row["welcome_variants"]),
            welcome_reactions=list(row["welcome_reactions"]),
            ban_message=row["ban_message"],
            leave_mode=row["leave_mode"],
        )

    async def set_leave_mode(self, guild_id: int, modo: str) -> None:
        await self._pool.execute(
            """
            INSERT INTO greetings_config (guild_id, leave_mode) VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET leave_mode = EXCLUDED.leave_mode
            """,
            guild_id, modo,
        )

    async def get_grafica(self, guild_id: int, tipo: str):
        """(url, immagine, nome del file) della grafica di ban o addio; None se non c'è."""
        riga = await self._pool.fetchrow(
            "SELECT url, image, filename FROM greetings_graphics WHERE guild_id = $1 AND kind = $2", guild_id, tipo
        )
        return None if riga is None else (riga["url"], riga["image"], riga["filename"])

    async def set_grafica(
        self, guild_id: int, tipo: str, *, url: str | None = None, image: bytes | None = None, filename: str | None = None
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO greetings_graphics (guild_id, kind, url, image, filename) VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (guild_id, kind) DO UPDATE
                SET url = EXCLUDED.url, image = EXCLUDED.image, filename = EXCLUDED.filename, updated_at = now()
            """,
            guild_id, tipo, url, image, filename,
        )

    async def clear_grafica(self, guild_id: int, tipo: str) -> None:
        await self._pool.execute("DELETE FROM greetings_graphics WHERE guild_id = $1 AND kind = $2", guild_id, tipo)

    async def set_welcome_extra(
        self, guild_id: int, dm_message: str, variants: list[str], reactions: list[str], ban_message: str = ""
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO greetings_config (guild_id, welcome_dm_message, welcome_variants, welcome_reactions, ban_message)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (guild_id) DO UPDATE
                SET welcome_dm_message = EXCLUDED.welcome_dm_message,
                    welcome_variants = EXCLUDED.welcome_variants,
                    welcome_reactions = EXCLUDED.welcome_reactions,
                    ban_message = EXCLUDED.ban_message
            """,
            guild_id, dm_message, variants, reactions, ban_message,
        )

    async def set_welcome_image(
        self, guild_id: int, enabled: bool, template: str, shape: str, color: str, title: str
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO greetings_config
                (guild_id, welcome_image_enabled, welcome_image_template, welcome_image_shape,
                 welcome_image_color, welcome_image_title)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (guild_id) DO UPDATE
                SET welcome_image_enabled = EXCLUDED.welcome_image_enabled,
                    welcome_image_template = EXCLUDED.welcome_image_template,
                    welcome_image_shape = EXCLUDED.welcome_image_shape,
                    welcome_image_color = EXCLUDED.welcome_image_color,
                    welcome_image_title = EXCLUDED.welcome_image_title
            """,
            guild_id, enabled, template, shape, color, title,
        )

    async def set_welcome_image_extra(
        self, guild_id: int, opacity: int, text: str, order: str, align: str, name_color: str
    ) -> None:
        """RUO-004, 007, 008, 010: impostazioni in più dell'immagine di benvenuto."""
        await self._pool.execute(
            """
            INSERT INTO greetings_config
                (guild_id, welcome_image_opacity, welcome_image_text, welcome_image_order,
                 welcome_image_align, welcome_image_name_color)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (guild_id) DO UPDATE
                SET welcome_image_opacity = EXCLUDED.welcome_image_opacity,
                    welcome_image_text = EXCLUDED.welcome_image_text,
                    welcome_image_order = EXCLUDED.welcome_image_order,
                    welcome_image_align = EXCLUDED.welcome_image_align,
                    welcome_image_name_color = EXCLUDED.welcome_image_name_color
            """,
            guild_id, opacity, text, order, align, name_color,
        )

    async def set_topic_notice(self, guild_id: int, channel_id: int | None) -> None:
        """RUO-027: il canale degli avvisi sull'argomento dei canali (None li spegne)."""
        await self._pool.execute(
            """
            INSERT INTO greetings_config (guild_id, topic_notice_channel_id) VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET topic_notice_channel_id = EXCLUDED.topic_notice_channel_id
            """,
            guild_id, channel_id,
        )

    async def set_first_reaction(self, guild_id: int, emoji: str) -> None:
        """RUO-024: l'emoji per il primo messaggio dei nuovi membri ('' la spegne)."""
        await self._pool.execute(
            """
            INSERT INTO greetings_config (guild_id, first_message_reaction) VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET first_message_reaction = EXCLUDED.first_message_reaction
            """,
            guild_id, emoji,
        )

    async def set_embed(self, guild_id: int, dove: str, nome: str) -> None:
        """RUO-001, 014, 015: l'embed salvato da usare nel benvenuto, nel DM o nell'addio ('' lo toglie)."""
        colonna = {"benvenuto": "welcome_embed", "dm": "dm_embed", "addio": "goodbye_embed"}.get(dove)
        if colonna is None:
            raise ValueError(f"Posto sconosciuto: {dove}")
        await self._pool.execute(
            f"""
            INSERT INTO greetings_config (guild_id, {colonna}) VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET {colonna} = EXCLUDED.{colonna}
            """,
            guild_id, nome,
        )

    async def get_welcome_background(self, guild_id: int) -> bytes | None:
        return await self._pool.fetchval("SELECT image FROM greetings_background WHERE guild_id = $1", guild_id)

    async def set_welcome_background(self, guild_id: int, image: bytes) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO greetings_background (guild_id, image) VALUES ($1, $2)
                    ON CONFLICT (guild_id) DO UPDATE SET image = EXCLUDED.image, updated_at = now()
                    """,
                    guild_id, image,
                )
                await conn.execute(
                    """
                    INSERT INTO greetings_config (guild_id, welcome_image_has_background) VALUES ($1, TRUE)
                    ON CONFLICT (guild_id) DO UPDATE SET welcome_image_has_background = TRUE
                    """,
                    guild_id,
                )

    async def clear_welcome_background(self, guild_id: int) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM greetings_background WHERE guild_id = $1", guild_id)
                await conn.execute(
                    "UPDATE greetings_config SET welcome_image_has_background = FALSE WHERE guild_id = $1", guild_id
                )

    async def set_welcome(
        self,
        guild_id: int,
        enabled: bool,
        channel_id: int,
        message: str,
        dm: bool,
        ping_ruoli: bool = False,
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO greetings_config (guild_id, welcome_enabled, welcome_channel_id, welcome_message, welcome_dm, welcome_ping_ruoli)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (guild_id) DO UPDATE
                SET welcome_enabled = EXCLUDED.welcome_enabled,
                    welcome_channel_id = EXCLUDED.welcome_channel_id,
                    welcome_message = EXCLUDED.welcome_message,
                    welcome_dm = EXCLUDED.welcome_dm,
                    welcome_ping_ruoli = EXCLUDED.welcome_ping_ruoli
            """,
            guild_id,
            enabled,
            channel_id,
            message,
            dm,
            ping_ruoli,
        )

    async def set_goodbye(
        self,
        guild_id: int,
        enabled: bool,
        channel_id: int,
        message: str,
        ping_ruoli: bool = False,
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO greetings_config (guild_id, goodbye_enabled, goodbye_channel_id, goodbye_message, goodbye_ping_ruoli)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (guild_id) DO UPDATE
                SET goodbye_enabled = EXCLUDED.goodbye_enabled,
                    goodbye_channel_id = EXCLUDED.goodbye_channel_id,
                    goodbye_message = EXCLUDED.goodbye_message,
                    goodbye_ping_ruoli = EXCLUDED.goodbye_ping_ruoli
            """,
            guild_id,
            enabled,
            channel_id,
            message,
            ping_ruoli,
        )

    async def set_boost(
        self,
        guild_id: int,
        enabled: bool,
        channel_id: int,
        message: str,
        ping_ruoli: bool = False,
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO greetings_config (guild_id, boost_enabled, boost_channel_id, boost_message, boost_ping_ruoli)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (guild_id) DO UPDATE
                SET boost_enabled = EXCLUDED.boost_enabled,
                    boost_channel_id = EXCLUDED.boost_channel_id,
                    boost_message = EXCLUDED.boost_message,
                    boost_ping_ruoli = EXCLUDED.boost_ping_ruoli
            """,
            guild_id,
            enabled,
            channel_id,
            message,
            ping_ruoli,
        )


def _get_pool():
    from core.database import db
    return db.pool


greetings_repo = GreetingsRepository(pool_provider=_get_pool)
