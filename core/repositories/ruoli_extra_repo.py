"""
core/repositories/ruoli_extra_repo.py
=====================================
Archivio delle funzioni in più dei ruoli: ruoli in più per opzione, gruppi di menu, tavolozza dei colori,
immagine del menu, ruoli personali, immagini proprie del benvenuto.
Funzioni coperte: SPEC RUO-012, RUO-045, RUO-046, RUO-053, RUO-069, RUO-083
"""

from __future__ import annotations

from datetime import datetime

import asyncpg

from core.ruoli_extra_logic import MAX_IMMAGINI_BENVENUTO, MAX_MENU_PER_GRUPPO, TETTO_RUOLI_PERSONALI


class RuoliExtraRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ------------------------------------------------------------ RUO-083: ruoli in più
    async def extra_del_menu(self, menu_id: int) -> dict[int, tuple[int, ...]]:
        righe = await self._pool.fetch(
            "SELECT role_id, extra_role_id FROM role_menu_option_roles WHERE menu_id = $1 ORDER BY extra_role_id", menu_id
        )
        fuori: dict[int, list[int]] = {}
        for r in righe:
            fuori.setdefault(r["role_id"], []).append(r["extra_role_id"])
        return {k: tuple(v) for k, v in fuori.items()}

    async def aggiungi_extra(self, menu_id: int, role_id: int, extra_role_id: int) -> None:
        await self._pool.execute(
            "INSERT INTO role_menu_option_roles (menu_id, role_id, extra_role_id) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
            menu_id, role_id, extra_role_id,
        )

    async def togli_extra(self, menu_id: int, role_id: int, extra_role_id: int) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM role_menu_option_roles WHERE menu_id = $1 AND role_id = $2 AND extra_role_id = $3",
            menu_id, role_id, extra_role_id,
        )
        return esito.endswith(" 1")

    # ------------------------------------------------------------ RUO-069: gruppi
    async def imposta_gruppo(self, menu_id: int, guild_id: int, nome: str | None) -> str | None:
        """Mette il menu nel gruppo (o lo toglie con None). Torna il motivo del rifiuto o None. Il tetto si controlla nella stessa transazione."""
        async with self._pool.acquire() as conn, conn.transaction():
            if nome is not None:
                await conn.execute("SELECT pg_advisory_xact_lock($1)", guild_id)
                gia = await conn.fetchval(
                    "SELECT count(*) FROM role_menus WHERE guild_id = $1 AND gruppo = $2 AND id <> $3", guild_id, nome, menu_id
                )
                if gia >= MAX_MENU_PER_GRUPPO:
                    return f"Un gruppo ha al massimo {MAX_MENU_PER_GRUPPO} menu."
            await conn.execute("UPDATE role_menus SET gruppo = $2 WHERE id = $1 AND guild_id = $3", menu_id, nome, guild_id)
        return None

    async def ruoli_del_gruppo(self, guild_id: int, gruppo: str) -> frozenset[int]:
        """Tutti i ruoli dei menu del gruppo: quelli delle opzioni e i loro ruoli in più."""
        righe = await self._pool.fetch(
            """
            SELECT o.role_id AS r FROM role_menu_options o JOIN role_menus m ON m.id = o.menu_id
             WHERE m.guild_id = $1 AND m.gruppo = $2
            UNION
            SELECT x.extra_role_id FROM role_menu_option_roles x JOIN role_menus m ON m.id = x.menu_id
             WHERE m.guild_id = $1 AND m.gruppo = $2
            """,
            guild_id, gruppo,
        )
        return frozenset(r["r"] for r in righe)

    # ------------------------------------------------------------ RUO-046: tavolozza dei colori
    async def imposta_colori(self, menu_id: int, guild_id: int, attivo: bool) -> None:
        await self._pool.execute("UPDATE role_menus SET colori = $3 WHERE id = $1 AND guild_id = $2", menu_id, guild_id, attivo)

    async def ruoli_colore(self, guild_id: int) -> list[tuple[int, str, tuple[int, ...], tuple[int, ...]]]:
        """(ruolo, etichetta, ruoli ammessi, ruoli esclusi) di ogni opzione dei menu «colori» aperti, senza doppioni."""
        righe = await self._pool.fetch(
            """
            SELECT DISTINCT ON (o.role_id) o.role_id, COALESCE(o.label, '') AS label,
                   m.allowed_role_ids, m.excluded_role_ids
              FROM role_menu_options o JOIN role_menus m ON m.id = o.menu_id
             WHERE m.guild_id = $1 AND m.colori AND m.behavior <> 'lock' ORDER BY o.role_id, o.position
            """,
            guild_id,
        )
        return [(r["role_id"], r["label"], tuple(r["allowed_role_ids"]), tuple(r["excluded_role_ids"])) for r in righe]

    # ------------------------------------------------------------ RUO-053: immagine del menu
    async def imposta_immagine_menu(self, menu_id: int, immagine: bytes) -> None:
        await self._pool.execute(
            """
            INSERT INTO role_menu_images (menu_id, image) VALUES ($1, $2)
            ON CONFLICT (menu_id) DO UPDATE SET image = EXCLUDED.image, updated_at = now()
            """,
            menu_id, immagine,
        )

    async def immagine_menu(self, menu_id: int) -> bytes | None:
        return await self._pool.fetchval("SELECT image FROM role_menu_images WHERE menu_id = $1", menu_id)

    async def togli_immagine_menu(self, menu_id: int) -> bool:
        return (await self._pool.execute("DELETE FROM role_menu_images WHERE menu_id = $1", menu_id)).endswith(" 1")

    # ------------------------------------------------------------ RUO-045: ruoli personali
    async def concedi_ruolo_personale(self, guild_id: int, user_id: int, concesso_da: int) -> str | None:
        """Concede il permesso. Torna il motivo del rifiuto (tetto 250) o None."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", guild_id)
            if await conn.fetchval("SELECT 1 FROM ruoli_personali WHERE guild_id = $1 AND user_id = $2", guild_id, user_id):
                return None
            totale = await conn.fetchval("SELECT count(*) FROM ruoli_personali WHERE guild_id = $1", guild_id)
            if totale >= TETTO_RUOLI_PERSONALI:
                return "Il server ha già il massimo di ruoli personali."
            await conn.execute(
                "INSERT INTO ruoli_personali (guild_id, user_id, concesso_da) VALUES ($1, $2, $3)", guild_id, user_id, concesso_da
            )
        return None

    async def ruolo_personale(self, guild_id: int, user_id: int):
        return await self._pool.fetchrow("SELECT * FROM ruoli_personali WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)

    async def segna_ruolo_personale(self, guild_id: int, user_id: int, role_id: int, quando: datetime) -> None:
        await self._pool.execute(
            "UPDATE ruoli_personali SET role_id = $3, ultima_modifica = $4 WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id, role_id, quando,
        )

    async def prenota_modifica(self, guild_id: int, user_id: int, ora: datetime, pausa_secondi: int) -> bool:
        """Prende il turno per una modifica: vero solo se è passata la pausa (un solo passaggio alla volta per persona)."""
        esito = await self._pool.execute(
            """
            UPDATE ruoli_personali SET ultima_modifica = $3::timestamptz
             WHERE guild_id = $1 AND user_id = $2
               AND (ultima_modifica IS NULL OR ultima_modifica <= $3::timestamptz - make_interval(secs => $4::double precision))
            """,
            guild_id, user_id, ora, float(pausa_secondi),
        )
        return esito.endswith(" 1")

    async def revoca_ruolo_personale(self, guild_id: int, user_id: int) -> int | None:
        """Toglie il permesso. Torna l'ID del ruolo da cancellare (se c'era)."""
        riga = await self._pool.fetchrow(
            "DELETE FROM ruoli_personali WHERE guild_id = $1 AND user_id = $2 RETURNING role_id", guild_id, user_id
        )
        return riga["role_id"] if riga else None

    async def conta_ruoli_personali(self, guild_id: int) -> int:
        return await self._pool.fetchval("SELECT count(*) FROM ruoli_personali WHERE guild_id = $1 AND role_id IS NOT NULL", guild_id)

    # ------------------------------------------------------------ RUO-012: immagini del benvenuto
    async def aggiungi_immagine_benvenuto(self, guild_id: int, immagine: bytes, autore: int) -> int | None:
        """Salva la copia ricodificata. None se il server ha già 10 immagini (controllo nella stessa transazione)."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", guild_id)
            if await conn.fetchval("SELECT count(*) FROM greetings_images WHERE guild_id = $1", guild_id) >= MAX_IMMAGINI_BENVENUTO:
                return None
            return await conn.fetchval(
                "INSERT INTO greetings_images (guild_id, image, added_by) VALUES ($1, $2, $3) RETURNING id", guild_id, immagine, autore
            )

    async def id_immagini_benvenuto(self, guild_id: int) -> list[int]:
        return [r["id"] for r in await self._pool.fetch("SELECT id FROM greetings_images WHERE guild_id = $1 ORDER BY id", guild_id)]

    async def immagine_benvenuto(self, guild_id: int, immagine_id: int) -> bytes | None:
        return await self._pool.fetchval("SELECT image FROM greetings_images WHERE guild_id = $1 AND id = $2", guild_id, immagine_id)

    async def togli_immagine_benvenuto(self, guild_id: int, immagine_id: int) -> bool:
        esito = await self._pool.execute("DELETE FROM greetings_images WHERE guild_id = $1 AND id = $2", guild_id, immagine_id)
        return esito.endswith(" 1")


def _get_pool():
    from core.database import db

    return db.pool


ruoli_extra_repo = RuoliExtraRepository(_get_pool)
