"""
core/repositories/ruoli_collegati_repo.py
=========================================
Collegamenti Twitch per i ruoli collegati di Discord (tabella `ruoli_collegati_twitch`, migrazione 0753).
I token arrivano già cifrati: qui non si cifra né si decifra niente.
Funzioni coperte: SPEC §24.9 (ALR-049, issue #129)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class Collegamento:
    user_id: int
    twitch_id: str
    twitch_login: str
    tipo: str
    collegato_il: datetime | None


class RuoliCollegatiRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def salva_twitch(
        self, user_id: int, twitch_id: str, login: str, tipo: str, token: str, refresh: str | None, scade_il: datetime | None
    ) -> None:
        """Primo passo: i dati di Twitch (e il tipo di canale); il collegamento con Discord si azzera finché non si finisce."""
        await self._pool.execute(
            "INSERT INTO ruoli_collegati_twitch (user_id, twitch_id, twitch_login, tipo, twitch_token, twitch_refresh, twitch_scade_il) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7) ON CONFLICT (user_id) DO UPDATE SET twitch_id = EXCLUDED.twitch_id, "
            "twitch_login = EXCLUDED.twitch_login, tipo = EXCLUDED.tipo, twitch_token = EXCLUDED.twitch_token, "
            "twitch_refresh = EXCLUDED.twitch_refresh, twitch_scade_il = EXCLUDED.twitch_scade_il, "
            "discord_token = NULL, discord_refresh = NULL, discord_scade_il = NULL, collegato_il = NULL",
            user_id, twitch_id, login, tipo, token, refresh, scade_il,
        )

    async def leggi_twitch(self, user_id: int) -> tuple[str, str, str] | None:
        """(id Twitch, login, tipo) del primo passo, se c'è."""
        riga = await self._pool.fetchrow(
            "SELECT twitch_id, twitch_login, tipo FROM ruoli_collegati_twitch WHERE user_id = $1", user_id
        )
        return (riga["twitch_id"], riga["twitch_login"], riga["tipo"]) if riga else None

    async def segna_collegato(self, user_id: int, token: str, refresh: str | None, scade_il: datetime | None) -> bool:
        esito = await self._pool.execute(
            "UPDATE ruoli_collegati_twitch SET discord_token = $2, discord_refresh = $3, discord_scade_il = $4, "
            "collegato_il = now() WHERE user_id = $1",
            user_id, token, refresh, scade_il,
        )
        return esito.endswith(" 1")

    async def stato(self, user_id: int) -> Collegamento | None:
        """Il collegamento finito (con Discord); un primo passo a metà non conta."""
        riga = await self._pool.fetchrow(
            "SELECT user_id, twitch_id, twitch_login, tipo, collegato_il FROM ruoli_collegati_twitch "
            "WHERE user_id = $1 AND collegato_il IS NOT NULL",
            user_id,
        )
        return Collegamento(**dict(riga)) if riga else None

    async def leggi_token_discord(self, user_id: int) -> str | None:
        return await self._pool.fetchval("SELECT discord_token FROM ruoli_collegati_twitch WHERE user_id = $1", user_id)

    async def da_aggiornare(self, limite: int, ore: int = 11) -> list[dict]:
        """Collegamenti finiti non aggiornati da `ore` ore (prima i mai aggiornati), con i token cifrati."""
        righe = await self._pool.fetch(
            "SELECT user_id, twitch_id, twitch_login, tipo, twitch_token, twitch_refresh, twitch_scade_il, "
            "discord_token, discord_refresh, discord_scade_il, errori FROM ruoli_collegati_twitch "
            "WHERE collegato_il IS NOT NULL AND (aggiornato_il IS NULL OR aggiornato_il < now() - make_interval(hours => $2)) "
            "ORDER BY aggiornato_il NULLS FIRST, user_id LIMIT $1",
            limite, ore,
        )
        return [dict(r) for r in righe]

    async def aggiorna_canale(self, user_id: int, login: str, tipo: str) -> None:
        await self._pool.execute(
            "UPDATE ruoli_collegati_twitch SET twitch_login = $2, tipo = $3 WHERE user_id = $1", user_id, login[:40], tipo
        )

    async def aggiorna_token_twitch(self, user_id: int, token: str, refresh: str | None, scade_il: datetime | None) -> None:
        await self._pool.execute(
            "UPDATE ruoli_collegati_twitch SET twitch_token = $2, twitch_refresh = $3, twitch_scade_il = $4 WHERE user_id = $1",
            user_id, token, refresh, scade_il,
        )

    async def aggiorna_token_discord(self, user_id: int, token: str, refresh: str | None, scade_il: datetime | None) -> None:
        await self._pool.execute(
            "UPDATE ruoli_collegati_twitch SET discord_token = $2, discord_refresh = $3, discord_scade_il = $4 WHERE user_id = $1",
            user_id, token, refresh, scade_il,
        )

    async def segna_giro(self, user_id: int, *, riuscito: bool) -> None:
        """Giro riuscito: azzera gli errori e ricomincia il conto; andato male per un guasto passeggero: se ne tiene il conto."""
        if riuscito:
            await self._pool.execute("UPDATE ruoli_collegati_twitch SET aggiornato_il = now(), errori = 0 WHERE user_id = $1", user_id)
        else:
            await self._pool.execute(
                "UPDATE ruoli_collegati_twitch SET errori = LEAST(errori + 1, 100) WHERE user_id = $1", user_id
            )

    async def elimina(self, user_id: int) -> bool:
        esito = await self._pool.execute("DELETE FROM ruoli_collegati_twitch WHERE user_id = $1", user_id)
        return esito.endswith(" 1")


def _get_pool():
    from core.database import db

    return db.pool


ruoli_collegati_repo = RuoliCollegatiRepository(pool_provider=_get_pool)
