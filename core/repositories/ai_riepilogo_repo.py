"""
core/repositories/ai_riepilogo_repo.py
======================================
Scelte del riepilogo del server (canale, ora, frequenza), numeri dalle statistiche già raccolte (bacheca delle stelle,
clan) e parole seguite dalle persone per gli avvisi.
Funzioni coperte: SPEC §25.41, §25.42, §25.43, §25.92 (AI-R-044..046, AI-R-099)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class ConfigRiepilogo:
    guild_id: int
    attivo: bool = False
    canale_id: int | None = None
    ora: int = 9
    frequenza: str = "giorno"
    con_testo: bool = False
    canali_testo: tuple[int, ...] = ()
    ultimo_invio: datetime | None = None
    ultimo_testo: str | None = None


_CAMPI = {"attivo", "canale_id", "ora", "frequenza", "con_testo", "canali_testo"}


def _config(r) -> ConfigRiepilogo:
    return ConfigRiepilogo(
        guild_id=r["guild_id"], attivo=r["attivo"], canale_id=r["canale_id"], ora=r["ora"], frequenza=r["frequenza"],
        con_testo=r["con_testo"], canali_testo=tuple(r["canali_testo"]), ultimo_invio=r["ultimo_invio"], ultimo_testo=r["ultimo_testo"],
    )


class AiRiepilogoRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def config(self, guild_id: int) -> ConfigRiepilogo:
        r = await self._pool.fetchrow("SELECT * FROM ai_riepiloghi WHERE guild_id = $1", guild_id)
        return ConfigRiepilogo(guild_id=guild_id) if r is None else _config(r)

    async def imposta(self, guild_id: int, **campi) -> ConfigRiepilogo:
        """Il solo punto che cambia le scelte del riepilogo (comandi e pannello)."""
        if not campi or set(campi) - _CAMPI:
            raise ValueError(f"Campi del riepilogo non validi: {sorted(set(campi) - _CAMPI)}")
        nomi = list(campi)
        valori = [list(v) if k == "canali_testo" else v for k, v in campi.items()]
        r = await self._pool.fetchrow(
            f"INSERT INTO ai_riepiloghi (guild_id, {', '.join(nomi)}) VALUES ($1, {', '.join(f'${i + 2}' for i in range(len(nomi)))}) "
            f"ON CONFLICT (guild_id) DO UPDATE SET {', '.join(f'{n} = EXCLUDED.{n}' for n in nomi)}, aggiornato_il = now() RETURNING *",
            guild_id, *valori,
        )
        return _config(r)

    async def attivi(self) -> list[ConfigRiepilogo]:
        righe = await self._pool.fetch("SELECT * FROM ai_riepiloghi WHERE attivo AND canale_id IS NOT NULL")
        return [_config(r) for r in righe]

    async def prenota_invio(self, guild_id: int, adesso: datetime, inizio_slot: datetime) -> bool:
        """True a chi arriva per primo: un solo bot pubblica il riepilogo di questo orario."""
        r = await self._pool.fetchval(
            "UPDATE ai_riepiloghi SET ultimo_invio = $2 WHERE guild_id = $1 AND (ultimo_invio IS NULL OR ultimo_invio < $3) RETURNING 1",
            guild_id, adesso, inizio_slot,
        )
        return r == 1

    async def salva_testo(self, guild_id: int, testo: str) -> None:
        await self._pool.execute("UPDATE ai_riepiloghi SET ultimo_testo = $2 WHERE guild_id = $1", guild_id, testo[:4000])

    # ------------------------------------------------------------ numeri
    async def meme_top(self, guild_id: int, dal: datetime) -> tuple[int, int, int, int] | None:
        r = await self._pool.fetchrow(
            "SELECT source_channel_id, source_message_id, stars, author_id FROM starboard_posts "
            "WHERE guild_id = $1 AND created_at >= $2 AND stars > 0 ORDER BY stars DESC LIMIT 1",
            guild_id, dal,
        )
        return None if r is None else (r["source_channel_id"], r["source_message_id"], r["stars"], r["author_id"])

    async def clan_top(self, guild_id: int, dal: datetime) -> tuple[str, int] | None:
        r = await self._pool.fetchrow(
            "SELECT c.name, count(*) AS n FROM clan_members m JOIN clans c ON c.id = m.clan_id "
            "WHERE m.guild_id = $1 AND m.joined_at >= $2 GROUP BY c.id, c.name ORDER BY n DESC LIMIT 1",
            guild_id, dal,
        )
        return None if r is None else (r["name"], int(r["n"]))

    # ------------------------------------------------------------ parole seguite
    async def parole_aggiungi(self, guild_id: int, user_id: int, parola: str, massimo: int) -> str:
        """'ok', 'gia' (c'era) o 'piene' (tetto raggiunto)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1)", user_id % 2147483647)
                if await conn.fetchval("SELECT 1 FROM ai_avvisi_parole WHERE guild_id = $1 AND user_id = $2 AND parola = $3", guild_id, user_id, parola):
                    return "gia"
                if await conn.fetchval("SELECT count(*) FROM ai_avvisi_parole WHERE guild_id = $1 AND user_id = $2", guild_id, user_id) >= massimo:
                    return "piene"
                await conn.execute("INSERT INTO ai_avvisi_parole (guild_id, user_id, parola) VALUES ($1, $2, $3)", guild_id, user_id, parola)
                return "ok"

    async def parole_togli(self, guild_id: int, user_id: int, parola: str) -> bool:
        esito = await self._pool.execute("DELETE FROM ai_avvisi_parole WHERE guild_id = $1 AND user_id = $2 AND parola = $3", guild_id, user_id, parola)
        return esito.endswith(" 1")

    async def parole_di(self, guild_id: int, user_id: int) -> list[str]:
        righe = await self._pool.fetch("SELECT parola FROM ai_avvisi_parole WHERE guild_id = $1 AND user_id = $2 ORDER BY creato_il", guild_id, user_id)
        return [r["parola"] for r in righe]

    async def parole_del_server(self, guild_id: int) -> dict[str, list[int]]:
        """parola -> persone che la seguono."""
        righe = await self._pool.fetch("SELECT parola, user_id FROM ai_avvisi_parole WHERE guild_id = $1", guild_id)
        risultato: dict[str, list[int]] = {}
        for r in righe:
            risultato.setdefault(r["parola"], []).append(r["user_id"])
        return risultato


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


ai_riepilogo_repo = AiRiepilogoRepository(pool_provider=_get_pool)
