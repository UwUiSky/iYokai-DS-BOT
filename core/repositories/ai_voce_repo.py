"""
core/repositories/ai_voce_repo.py
=================================
Scelte della voce di Yokai per server (accesa, tono, canali dei saluti) e il testo dietro ogni vocale.
Funzioni coperte: SPEC §14.19, §25.102, §25.103, §25.105 (AI-R-109, AI-R-110, AI-R-112)
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from core.voice_profile import tono_valido


@dataclass(frozen=True)
class ConfigVoce:
    guild_id: int
    attiva: bool = False
    tono: str = "scherzosa"
    canali_saluti: tuple[int, ...] = ()


@dataclass(frozen=True)
class Vocale:
    message_id: int
    guild_id: int | None
    channel_id: int
    testo: str
    lingua: str


_CAMPI = {"attiva", "tono", "canali_saluti"}


class AiVoceRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def config(self, guild_id: int) -> ConfigVoce:
        r = await self._pool.fetchrow("SELECT * FROM ai_voce_config WHERE guild_id = $1", guild_id)
        if r is None:
            return ConfigVoce(guild_id=guild_id)
        return ConfigVoce(guild_id, r["attiva"], r["tono"], tuple(r["canali_saluti"]))

    async def imposta(self, guild_id: int, **campi) -> ConfigVoce:
        """Il solo punto che cambia le scelte della voce (comandi e pannello)."""
        if not campi or set(campi) - _CAMPI:
            raise ValueError(f"Campi della voce non validi: {sorted(set(campi) - _CAMPI)}")
        if "tono" in campi and campi["tono"] != tono_valido(campi["tono"]):
            raise ValueError("Tono non valido.")
        nomi = list(campi)
        valori = [list(v) if k == "canali_saluti" else v for k, v in campi.items()]
        await self._pool.execute(
            f"INSERT INTO ai_voce_config (guild_id, {', '.join(nomi)}) VALUES ($1, {', '.join(f'${i + 2}' for i in range(len(nomi)))}) "
            f"ON CONFLICT (guild_id) DO UPDATE SET {', '.join(f'{n} = EXCLUDED.{n}' for n in nomi)}, aggiornato_il = now()",
            guild_id, *valori,
        )
        return await self.config(guild_id)

    async def salva_vocale(self, message_id: int, guild_id: int | None, channel_id: int, testo: str, lingua: str) -> None:
        await self._pool.execute(
            "INSERT INTO ai_vocali (message_id, guild_id, channel_id, testo, lingua) VALUES ($1, $2, $3, $4, $5) "
            "ON CONFLICT (message_id) DO UPDATE SET testo = EXCLUDED.testo, lingua = EXCLUDED.lingua",
            message_id, guild_id, channel_id, testo[:1000], lingua,
        )

    async def vocale(self, message_id: int) -> Vocale | None:
        r = await self._pool.fetchrow("SELECT * FROM ai_vocali WHERE message_id = $1", message_id)
        return None if r is None else Vocale(r["message_id"], r["guild_id"], r["channel_id"], r["testo"], r["lingua"])


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


ai_voce_repo = AiVoceRepository(pool_provider=_get_pool)
