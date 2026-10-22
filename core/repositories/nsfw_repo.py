"""
core/repositories/nsfw_repo.py
==============================
Dati dell'istanza NSFW: scelte del server, pubblicazione automatica,
registro con l'impronta di ogni immagine e contenuti bloccati.
Tabelle: core/migrations/0240_nsfw.sql.
Funzioni coperte: SPEC §16.10 (NF-23)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class NsfwConfig:
    guild_id: int
    attivo: bool
    tag_permessi: tuple[str, ...]


@dataclass(frozen=True)
class NsfwAutopost:
    guild_id: int
    channel_id: int
    tag: str
    intervallo_minuti: int
    prossimo_il: datetime
    errori: int


@dataclass(frozen=True)
class NsfwInvio:
    guild_id: int
    channel_id: int
    message_id: int | None
    fonte: str
    id_fonte: str
    impronta: str


class NsfwRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ---- scelte del server ----
    async def get_config(self, guild_id: int) -> NsfwConfig | None:
        r = await self._pool.fetchrow(
            "SELECT guild_id, attivo, tag_permessi FROM nsfw_config WHERE guild_id = $1", guild_id
        )
        return None if r is None else NsfwConfig(r["guild_id"], r["attivo"], tuple(r["tag_permessi"]))

    async def imposta_attivo(self, guild_id: int, attivo: bool, da: int) -> None:
        await self._pool.execute(
            """
            INSERT INTO nsfw_config (guild_id, attivo, attivato_da) VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE
                SET attivo = EXCLUDED.attivo, attivato_da = EXCLUDED.attivato_da, aggiornato_il = now()
            """,
            guild_id, attivo, da,
        )

    async def imposta_tag(self, guild_id: int, tag: list[str]) -> None:
        await self._pool.execute(
            """
            INSERT INTO nsfw_config (guild_id, tag_permessi) VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET tag_permessi = EXCLUDED.tag_permessi, aggiornato_il = now()
            """,
            guild_id, tag,
        )

    # ---- pubblicazione automatica ----
    async def salva_autopost(self, guild_id: int, channel_id: int, tag: str, intervallo_minuti: int, da: int) -> None:
        await self._pool.execute(
            """
            INSERT INTO nsfw_autopost (guild_id, channel_id, tag, intervallo_minuti, creato_da)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (guild_id, channel_id) DO UPDATE
                SET tag = EXCLUDED.tag, intervallo_minuti = EXCLUDED.intervallo_minuti,
                    creato_da = EXCLUDED.creato_da, errori = 0, prossimo_il = now()
            """,
            guild_id, channel_id, tag, intervallo_minuti, da,
        )

    async def togli_autopost(self, guild_id: int, channel_id: int | None = None) -> int:
        """Toglie una pubblicazione (o tutte, senza canale). Restituisce quante."""
        esito = await self._pool.execute(
            "DELETE FROM nsfw_autopost WHERE guild_id = $1 AND ($2::bigint IS NULL OR channel_id = $2)",
            guild_id, channel_id,
        )
        return int(esito.split()[-1])

    async def elenco_autopost(self, guild_id: int) -> list[NsfwAutopost]:
        righe = await self._pool.fetch(
            "SELECT guild_id, channel_id, tag, intervallo_minuti, prossimo_il, errori FROM nsfw_autopost "
            "WHERE guild_id = $1 ORDER BY channel_id",
            guild_id,
        )
        return [NsfwAutopost(**dict(r)) for r in righe]

    async def autopost_scaduti(self, limite: int) -> list[NsfwAutopost]:
        righe = await self._pool.fetch(
            "SELECT guild_id, channel_id, tag, intervallo_minuti, prossimo_il, errori FROM nsfw_autopost "
            "WHERE prossimo_il <= now() ORDER BY prossimo_il LIMIT $1",
            limite,
        )
        return [NsfwAutopost(**dict(r)) for r in righe]

    async def rimanda_autopost(self, guild_id: int, channel_id: int, prossimo_il: datetime, errori: int) -> None:
        await self._pool.execute(
            "UPDATE nsfw_autopost SET prossimo_il = $3, errori = $4 WHERE guild_id = $1 AND channel_id = $2",
            guild_id, channel_id, prossimo_il, errori,
        )

    # ---- registro e blocchi ----
    async def registra_invio(
        self, guild_id: int, channel_id: int, message_id: int | None, fonte: str, id_fonte: str, impronta: str
    ) -> None:
        await self._pool.execute(
            "INSERT INTO nsfw_registro (guild_id, channel_id, message_id, fonte, id_fonte, impronta) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            guild_id, channel_id, message_id, fonte, id_fonte, impronta,
        )

    async def gia_inviato(self, guild_id: int, impronta: str) -> bool:
        return bool(
            await self._pool.fetchval(
                "SELECT EXISTS (SELECT 1 FROM nsfw_registro WHERE guild_id = $1 AND impronta = $2)", guild_id, impronta
            )
        )

    async def invio_del_messaggio(self, message_id: int) -> NsfwInvio | None:
        r = await self._pool.fetchrow(
            "SELECT guild_id, channel_id, message_id, fonte, id_fonte, impronta FROM nsfw_registro "
            "WHERE message_id = $1",
            message_id,
        )
        return None if r is None else NsfwInvio(**dict(r))

    async def blocca(
        self, impronta: str, fonte: str, id_fonte: str, motivo: str, guild_id: int | None, da: int | None,
        tetto_server: int | None = None,
    ) -> bool:
        """
        Blocca in tutti i server. Con `tetto_server`: solo se quel server ha fatto meno di
        `tetto_server` blocchi nelle ultime 24 ore (un server non svuota la fonte per tutti).
        True se il contenuto ora è bloccato (anche se lo era già).
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                if tetto_server is not None and guild_id is not None:
                    await conn.execute("SELECT pg_advisory_xact_lock(hashtext('nsfw_blocca'), $1::int)", guild_id % 2**31)
                    fatti = await conn.fetchval(
                        "SELECT count(*) FROM nsfw_bloccati WHERE guild_id = $1 AND creato_il > now() - interval '1 day'",
                        guild_id,
                    )
                    if fatti >= tetto_server:
                        return bool(await conn.fetchval(
                            "SELECT EXISTS (SELECT 1 FROM nsfw_bloccati WHERE impronta = $1)", impronta
                        ))
                await conn.execute(
                    """
                    INSERT INTO nsfw_bloccati (impronta, fonte, id_fonte, motivo, guild_id, segnalato_da)
                    VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (impronta) DO NOTHING
                    """,
                    impronta, fonte, id_fonte, motivo[:500], guild_id, da,
                )
        return True

    async def e_bloccato(self, fonte: str, id_fonte: str, impronta: str | None = None) -> bool:
        return bool(
            await self._pool.fetchval(
                "SELECT EXISTS (SELECT 1 FROM nsfw_bloccati WHERE (fonte = $1 AND id_fonte = $2) OR impronta = $3)",
                fonte, id_fonte, impronta,
            )
        )


    # ---- presenza del bot NSFW (D6) ----
    async def segna_presenza(self, guild_id: int, presente: bool) -> None:
        await self._pool.execute(
            """
            INSERT INTO nsfw_presenza (guild_id, uscito_il) VALUES ($1, CASE WHEN $2 THEN NULL ELSE now() END)
            ON CONFLICT (guild_id) DO UPDATE SET uscito_il =
                CASE WHEN $2 THEN NULL ELSE COALESCE(nsfw_presenza.uscito_il, now()) END
            """,
            guild_id, presente,
        )

    async def sincronizza_presenza(self, guild_ids: set[int]) -> None:
        """I server visti ora sono presenti; quelli con dati NSFW e non visti sono usciti (partono i 90 giorni)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO nsfw_presenza (guild_id) SELECT unnest($1::bigint[])
                    ON CONFLICT (guild_id) DO UPDATE SET uscito_il = NULL
                    """,
                    list(guild_ids),
                )
                await conn.execute(
                    """
                    INSERT INTO nsfw_presenza (guild_id, uscito_il)
                    SELECT guild_id, now() FROM nsfw_config WHERE NOT (guild_id = ANY($1::bigint[]))
                    UNION SELECT guild_id, now() FROM nsfw_registro WHERE NOT (guild_id = ANY($1::bigint[]))
                    ON CONFLICT (guild_id) DO UPDATE SET uscito_il = COALESCE(nsfw_presenza.uscito_il, now())
                    """,
                    list(guild_ids),
                )

    async def cancella_usciti(self, giorni: int) -> list[int]:
        """Dati NSFW dei server da cui il bot NSFW è uscito da più di `giorni` (i blocchi restano)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                righe = await conn.fetch(
                    "SELECT guild_id FROM nsfw_presenza WHERE uscito_il < now() - make_interval(days => $1) "
                    "FOR UPDATE",
                    giorni,
                )
                ids = [r["guild_id"] for r in righe]
                if ids:
                    for tabella in ("nsfw_autopost", "nsfw_registro", "nsfw_config", "nsfw_presenza"):
                        await conn.execute(f"DELETE FROM {tabella} WHERE guild_id = ANY($1::bigint[])", ids)
        return ids


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


nsfw_repo = NsfwRepository(pool_provider=_get_pool)
