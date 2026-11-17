"""
core/repositories/music_playlist_repo.py
========================================
Tabella music_playlists: le playlist salvate di ogni utente (al massimo
25, ognuna con al massimo 200 brani), valide in ogni server.
Funzioni coperte: SPEC §23 (NF-19), catalogo MUS-082, MUS-073 crea, MUS-074 aggiungi/MUS-075 togli
(`aggiorna_brani`), MUS-076 senza doppioni, MUS-077 rinomina
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from core.music_playlist_logic import (
    MAX_PLAYLIST_PER_UTENTE,
    BranoSalvato,
    brani_a_json,
    brani_da_json,
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

    async def save(self, user_id: int, nome: str, brani: list[BranoSalvato]) -> bool:
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
                    INSERT INTO music_playlists (user_id, name, tracks)
                    VALUES ($1, $2, $3::jsonb)
                    ON CONFLICT (user_id, name) DO UPDATE SET tracks = $3::jsonb, updated_at = now()
                    """,
                    user_id, nome, brani_a_json(brani),
                )
                return not esiste

    async def crea_vuota(self, user_id: int, nome: str) -> bool:
        """MUS-073: crea una playlist vuota. False se il nome c'è già; solleva LimitePlaylistRaggiunto."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(7170001, $1::int)", user_id % 2**31)
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

    async def delete(self, user_id: int, nome: str) -> bool:
        esito = await self._pool.execute(
            "DELETE FROM music_playlists WHERE user_id = $1 AND name = $2", user_id, nome
        )
        return esito.endswith(" 1")


def _get_pool():
    from core.database import db
    return db.pool


music_playlist_repo = MusicPlaylistRepository(pool_provider=_get_pool)
