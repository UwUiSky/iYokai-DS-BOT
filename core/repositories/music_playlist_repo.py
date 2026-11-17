"""
core/repositories/music_playlist_repo.py
========================================
Tabella music_playlists: le playlist salvate di ogni utente (al massimo
25, ognuna con al massimo 200 brani), valide in ogni server.
Funzioni coperte: SPEC §23 (NF-19), catalogo MUS-082, MUS-073 crea, MUS-074 aggiungi/MUS-075 togli
(`aggiorna_brani`), MUS-076 senza doppioni, MUS-077 rinomina, MUS-072/083 link di origine,
MUS-084 codice di condivisione, MUS-081 playlist del server, MUS-086 playlist a più mani
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from core.music_playlist_logic import (
    MAX_COLLABORATORI,
    MAX_PLAYLIST_PER_SERVER,
    MAX_PLAYLIST_PER_UTENTE,
    BranoSalvato,
    brani_a_json,
    brani_da_json,
    nuovo_codice,
    togli_doppioni,
)


@dataclass(frozen=True)
class RiassuntoPlaylist:
    nome: str
    numero_brani: int
    durata_ms: int


class LimitePlaylistRaggiunto(Exception):
    """L'utente ha già MAX_PLAYLIST_PER_UTENTE playlist."""


class MusicPlaylistRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def save(
        self, user_id: int, nome: str, brani: list[BranoSalvato], origine: str | None = None
    ) -> bool:
        """
        Salva (o sovrascrive) una playlist. True se era nuova. Solleva
        LimitePlaylistRaggiunto se è nuova e l'utente è già al tetto.
        Conteggio e scrittura nella stessa transazione, con un lock per utente.
        """
        brani, _doppioni = togli_doppioni(brani)  # MUS-076: mai doppioni in una playlist
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(7170001, $1::int)", user_id % 2**31)
                esiste = await conn.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM music_playlists WHERE user_id = $1 AND name = $2)",
                    user_id, nome,
                )
                if not esiste:
                    quante = await conn.fetchval(
                        "SELECT count(*) FROM music_playlists WHERE user_id = $1", user_id
                    )
                    if quante >= MAX_PLAYLIST_PER_UTENTE:
                        raise LimitePlaylistRaggiunto()
                await conn.execute(
                    """
                    INSERT INTO music_playlists (user_id, name, tracks, source_url)
                    VALUES ($1, $2, $3::jsonb, $4)
                    ON CONFLICT (user_id, name) DO UPDATE
                        SET tracks = $3::jsonb, source_url = $4, updated_at = now()
                    """,
                    user_id, nome, brani_a_json(brani), origine,
                )
                return not esiste

    async def crea_vuota(self, user_id: int, nome: str) -> bool:
        """MUS-073: crea una playlist vuota. False se il nome c'è già; solleva LimitePlaylistRaggiunto."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(7170001, $1::int)", user_id % 2**31)
                if await conn.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM music_playlists WHERE user_id = $1 AND name = $2)", user_id, nome
                ):
                    return False
                quante = await conn.fetchval("SELECT count(*) FROM music_playlists WHERE user_id = $1", user_id)
                if quante >= MAX_PLAYLIST_PER_UTENTE:
                    raise LimitePlaylistRaggiunto()
                esito = await conn.execute(
                    "INSERT INTO music_playlists (user_id, name) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    user_id, nome,
                )
                return esito.endswith(" 1")

    async def aggiorna_brani(self, user_id: int, nome: str, trasforma):
        """
        MUS-074/075: legge i brani di una playlist (riga bloccata), li passa a `trasforma(brani)`
        che restituisce (nuovi_brani, risultato), e li riscrive. None se la playlist non c'è.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                valore = await conn.fetchval(
                    "SELECT tracks FROM music_playlists WHERE user_id = $1 AND name = $2 FOR UPDATE",
                    user_id, nome,
                )
                if valore is None:
                    return None
                nuovi, risultato = trasforma(brani_da_json(valore))
                await conn.execute(
                    "UPDATE music_playlists SET tracks = $3::jsonb, updated_at = now() "
                    "WHERE user_id = $1 AND name = $2",
                    user_id, nome, brani_a_json(nuovi),
                )
                return risultato

    async def rinomina(self, user_id: int, vecchio: str, nuovo: str) -> str:
        """MUS-077: «ok», «manca» (non c'è) o «esiste» (il nuovo nome è già preso)."""
        try:
            esito = await self._pool.execute(
                "UPDATE music_playlists SET name = $3, updated_at = now() WHERE user_id = $1 AND name = $2",
                user_id, vecchio, nuovo,
            )
        except asyncpg.UniqueViolationError:
            return "esiste"
        return "ok" if esito.endswith(" 1") else "manca"

    async def get(self, user_id: int, nome: str) -> list[BranoSalvato] | None:
        valore = await self._pool.fetchval(
            "SELECT tracks FROM music_playlists WHERE user_id = $1 AND name = $2", user_id, nome
        )
        return None if valore is None else brani_da_json(valore)

    async def list_for_user(self, user_id: int) -> list[RiassuntoPlaylist]:
        righe = await self._pool.fetch(
            """
            SELECT name,
                   jsonb_array_length(tracks) AS numero,
                   COALESCE((SELECT sum((b->>'length')::bigint) FROM jsonb_array_elements(tracks) b
                             WHERE (b->>'length') ~ '^[0-9]+$'), 0) AS durata
              FROM music_playlists WHERE user_id = $1 ORDER BY name LIMIT $2
            """,
            user_id, MAX_PLAYLIST_PER_UTENTE,
        )
        return [RiassuntoPlaylist(r["name"], r["numero"], int(r["durata"])) for r in righe]

    async def origine(self, user_id: int, nome: str) -> str | None:
        """MUS-083: il link da cui la playlist è stata salvata, se c'è."""
        return await self._pool.fetchval(
            "SELECT source_url FROM music_playlists WHERE user_id = $1 AND name = $2", user_id, nome
        )

    async def nomi(self, user_id: int) -> set[str]:
        righe = await self._pool.fetch("SELECT name FROM music_playlists WHERE user_id = $1", user_id)
        return {r["name"] for r in righe}

    async def codice(self, user_id: int, nome: str, nuovo: bool = False) -> str | None:
        """
        MUS-084: il codice di condivisione (lo crea se manca; `nuovo` ne crea uno nuovo e il
        vecchio smette di valere). None se la playlist non c'è.
        """
        for _ in range(5):  # un urto con un codice già preso è rarissimo
            candidato = nuovo_codice()
            try:
                esito = await self._pool.fetchrow(
                    """
                    UPDATE music_playlists SET share_code = CASE WHEN $4 OR share_code IS NULL THEN $3 ELSE share_code END
                     WHERE user_id = $1 AND name = $2 RETURNING share_code
                    """,
                    user_id, nome, candidato, nuovo,
                )
            except asyncpg.UniqueViolationError:
                continue
            return None if esito is None else esito["share_code"]
        return None

    async def revoca_codice(self, user_id: int, nome: str) -> bool:
        esito = await self._pool.execute(
            "UPDATE music_playlists SET share_code = NULL WHERE user_id = $1 AND name = $2 AND share_code IS NOT NULL",
            user_id, nome,
        )
        return esito.endswith(" 1")

    async def da_codice(self, codice: str) -> tuple[int, str, list[BranoSalvato]] | None:
        """MUS-084: (proprietario, nome, brani) di una playlist condivisa, o None."""
        riga = await self._pool.fetchrow(
            "SELECT user_id, name, tracks FROM music_playlists WHERE share_code = $1", codice
        )
        return None if riga is None else (riga["user_id"], riga["name"], brani_da_json(riga["tracks"]))

    # --- MUS-086: playlist a più mani
    async def aggiungi_collaboratore(self, owner_id: int, nome: str, user_id: int) -> str:
        """«ok», «gia», «manca» (la playlist non c'è) o «pieno» (al massimo MAX_COLLABORATORI)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                esiste = await conn.fetchval(
                    "SELECT 1 FROM music_playlists WHERE user_id = $1 AND name = $2 FOR UPDATE", owner_id, nome
                )
                if not esiste:
                    return "manca"
                presente = await conn.fetchval(
                    "SELECT 1 FROM music_playlist_collabs WHERE owner_id = $1 AND name = $2 AND user_id = $3",
                    owner_id, nome, user_id,
                )
                if presente:
                    return "gia"
                quanti = await conn.fetchval(
                    "SELECT count(*) FROM music_playlist_collabs WHERE owner_id = $1 AND name = $2", owner_id, nome
                )
                if quanti >= MAX_COLLABORATORI:
                    return "pieno"
                await conn.execute(
                    "INSERT INTO music_playlist_collabs (owner_id, name, user_id) VALUES ($1, $2, $3)",
                    owner_id, nome, user_id,
                )
                return "ok"

    async def togli_collaboratore(self, owner_id: int, nome: str, user_id: int) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM music_playlist_collabs WHERE owner_id = $1 AND name = $2 AND user_id = $3",
            owner_id, nome, user_id,
        )
        return esito.endswith(" 1")

    async def collaboratori(self, owner_id: int, nome: str) -> list[int]:
        righe = await self._pool.fetch(
            "SELECT user_id FROM music_playlist_collabs WHERE owner_id = $1 AND name = $2 ORDER BY added_at",
            owner_id, nome,
        )
        return [r["user_id"] for r in righe]

    async def puo_modificare(self, owner_id: int, nome: str, user_id: int) -> bool:
        """Il proprietario, o chi è stato aggiunto come collaboratore."""
        if owner_id == user_id:
            return await self._pool.fetchval(
                "SELECT EXISTS (SELECT 1 FROM music_playlists WHERE user_id = $1 AND name = $2)", owner_id, nome
            )
        return await self._pool.fetchval(
            "SELECT EXISTS (SELECT 1 FROM music_playlist_collabs WHERE owner_id = $1 AND name = $2 AND user_id = $3)",
            owner_id, nome, user_id,
        )

    async def condivise_con(self, user_id: int) -> list[tuple[int, str]]:
        righe = await self._pool.fetch(
            "SELECT owner_id, name FROM music_playlist_collabs WHERE user_id = $1 ORDER BY name LIMIT $2",
            user_id, MAX_PLAYLIST_PER_UTENTE,
        )
        return [(r["owner_id"], r["name"]) for r in righe]

    async def delete(self, user_id: int, nome: str) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM music_playlists WHERE user_id = $1 AND name = $2", user_id, nome
        )
        return esito.endswith(" 1")


class MusicGuildPlaylistRepository:
    """MUS-081: playlist del server (al massimo 25, ognuna con al massimo 200 brani)."""

    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def save(self, guild_id: int, nome: str, brani: list[BranoSalvato], user_id: int) -> bool:
        """Salva o sostituisce. True se era nuova. Solleva LimitePlaylistRaggiunto al tetto del server."""
        brani, _ = togli_doppioni(brani)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(7170002, $1::int)", guild_id % 2**31)
                esiste = await conn.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM music_guild_playlists WHERE guild_id = $1 AND name = $2)",
                    guild_id, nome,
                )
                if not esiste:
                    quante = await conn.fetchval(
                        "SELECT count(*) FROM music_guild_playlists WHERE guild_id = $1", guild_id
                    )
                    if quante >= MAX_PLAYLIST_PER_SERVER:
                        raise LimitePlaylistRaggiunto()
                await conn.execute(
                    """
                    INSERT INTO music_guild_playlists (guild_id, name, tracks, created_by)
                    VALUES ($1, $2, $3::jsonb, $4)
                    ON CONFLICT (guild_id, name) DO UPDATE SET tracks = $3::jsonb, updated_at = now()
                    """,
                    guild_id, nome, brani_a_json(brani), user_id,
                )
                return not esiste

    async def get(self, guild_id: int, nome: str) -> list[BranoSalvato] | None:
        valore = await self._pool.fetchval(
            "SELECT tracks FROM music_guild_playlists WHERE guild_id = $1 AND name = $2", guild_id, nome
        )
        return None if valore is None else brani_da_json(valore)

    async def list_for_guild(self, guild_id: int) -> list[RiassuntoPlaylist]:
        righe = await self._pool.fetch(
            """
            SELECT name, jsonb_array_length(tracks) AS numero,
                   COALESCE((SELECT sum((b->>'length')::bigint) FROM jsonb_array_elements(tracks) b
                             WHERE (b->>'length') ~ '^[0-9]+$'), 0) AS durata
              FROM music_guild_playlists WHERE guild_id = $1 ORDER BY name LIMIT $2
            """,
            guild_id, MAX_PLAYLIST_PER_SERVER,
        )
        return [RiassuntoPlaylist(r["name"], r["numero"], int(r["durata"])) for r in righe]

    async def delete(self, guild_id: int, nome: str) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM music_guild_playlists WHERE guild_id = $1 AND name = $2", guild_id, nome
        )
        return esito.endswith(" 1")


def _get_pool():
    from core.database import db
    return db.pool


music_playlist_repo = MusicPlaylistRepository(pool_provider=_get_pool)
music_guild_playlist_repo = MusicGuildPlaylistRepository(pool_provider=_get_pool)
