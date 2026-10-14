"""
core/repositories/lockdown_repo.py
==================================
Tabelle lockdown_config, lockdown_stato, lockdown_canali (migrazione 0110):
le scelte del server, il blocco in corso e i permessi di prima di ogni canale.
Funzioni coperte: SPEC §23 (NF-29)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

import asyncpg


@dataclass(frozen=True)
class ConfigBlocco:
    categorie_escluse: tuple[int, ...] = ()
    ruoli_avviso: tuple[int, ...] = ()
    sblocco_auto_minuti: int = 0  # 0 = niente sblocco automatico
    solo_proprietario: bool = True  # in panico: solo proprietario e fidati usano /mod e /modban
    automatico: bool = False  # il panico parte da solo (anti-nuke, anti-raid)


@dataclass(frozen=True)
class StatoBlocco:
    guild_id: int
    tipo: str
    stato: str
    avviato_da: int
    avviato_il: datetime
    finisce_il: datetime | None
    motivo: str
    verifica_prima: str | None
    inviti_chiusi_da_noi: bool
    solo_proprietario: bool


@dataclass(frozen=True)
class CanaleBloccato:
    channel_id: int
    prima: dict[str, bool | None] = field(default_factory=dict)


def _stato(r) -> StatoBlocco:
    return StatoBlocco(
        guild_id=r["guild_id"], tipo=r["tipo"], stato=r["stato"], avviato_da=r["avviato_da"],
        avviato_il=r["avviato_il"], finisce_il=r["finisce_il"], motivo=r["motivo"],
        verifica_prima=r["verifica_prima"], inviti_chiusi_da_noi=r["inviti_chiusi_da_noi"],
        solo_proprietario=r["solo_proprietario"],
    )


class LockdownRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ------------------------------------------------------------ scelte
    async def get_config(self, guild_id: int) -> ConfigBlocco:
        r = await self._pool.fetchrow("SELECT * FROM lockdown_config WHERE guild_id = $1", guild_id)
        if r is None:
            return ConfigBlocco()
        return ConfigBlocco(
            categorie_escluse=tuple(r["categorie_escluse"]), ruoli_avviso=tuple(r["ruoli_avviso"]),
            sblocco_auto_minuti=r["sblocco_auto_minuti"], solo_proprietario=r["solo_proprietario"],
            automatico=r["automatico"],
        )

    async def save_config(self, guild_id: int, c: ConfigBlocco) -> None:
        await self._pool.execute(
            """
            INSERT INTO lockdown_config
                (guild_id, categorie_escluse, ruoli_avviso, sblocco_auto_minuti, solo_proprietario, automatico)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (guild_id) DO UPDATE SET
                categorie_escluse = EXCLUDED.categorie_escluse, ruoli_avviso = EXCLUDED.ruoli_avviso,
                sblocco_auto_minuti = EXCLUDED.sblocco_auto_minuti,
                solo_proprietario = EXCLUDED.solo_proprietario, automatico = EXCLUDED.automatico
            """,
            guild_id, list(c.categorie_escluse), list(c.ruoli_avviso), c.sblocco_auto_minuti,
            c.solo_proprietario, c.automatico,
        )

    # ------------------------------------------------------------ stato
    async def get_stato(self, guild_id: int) -> StatoBlocco | None:
        r = await self._pool.fetchrow("SELECT * FROM lockdown_stato WHERE guild_id = $1", guild_id)
        return _stato(r) if r else None

    async def crea_stato(
        self, guild_id: int, *, tipo: str, avviato_da: int, motivo: str,
        finisce_il: datetime | None, solo_proprietario: bool,
    ) -> bool:
        """True se il blocco e' nuovo; False se ce n'e' gia' uno (anche a meta')."""
        esito = await self._pool.execute(
            """
            INSERT INTO lockdown_stato (guild_id, tipo, avviato_da, motivo, finisce_il, solo_proprietario)
            VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (guild_id) DO NOTHING
            """,
            guild_id, tipo, avviato_da, motivo, finisce_il, solo_proprietario,
        )
        return esito.endswith(" 1")

    async def imposta_stato(self, guild_id: int, stato: str) -> None:
        await self._pool.execute("UPDATE lockdown_stato SET stato = $2 WHERE guild_id = $1", guild_id, stato)

    async def salva_server(
        self, guild_id: int, *, verifica_prima: str | None, inviti_chiusi_da_noi: bool
    ) -> None:
        await self._pool.execute(
            "UPDATE lockdown_stato SET verifica_prima = $2, inviti_chiusi_da_noi = $3 WHERE guild_id = $1",
            guild_id, verifica_prima, inviti_chiusi_da_noi,
        )

    async def scaduti(self, adesso: datetime) -> list[int]:
        righe = await self._pool.fetch(
            "SELECT guild_id FROM lockdown_stato WHERE finisce_il IS NOT NULL AND finisce_il <= $1 "
            "AND stato IN ('attivo', 'in_riapertura')",
            adesso,
        )
        return [r["guild_id"] for r in righe]

    async def panici_attivi(self) -> list[StatoBlocco]:
        righe = await self._pool.fetch("SELECT * FROM lockdown_stato WHERE tipo = 'panico'")
        return [_stato(r) for r in righe]

    async def elimina_blocco(self, guild_id: int) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM lockdown_canali WHERE guild_id = $1", guild_id)
                await conn.execute("DELETE FROM lockdown_stato WHERE guild_id = $1", guild_id)

    # ------------------------------------------------------------ canali
    async def salva_canale(self, guild_id: int, channel_id: int, prima: dict[str, bool | None]) -> None:
        await self._pool.execute(
            """
            INSERT INTO lockdown_canali (guild_id, channel_id, prima) VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, channel_id) DO NOTHING
            """,
            guild_id, channel_id, json.dumps(prima),
        )

    async def canali_da_ripristinare(self, guild_id: int) -> list[CanaleBloccato]:
        righe = await self._pool.fetch(
            "SELECT channel_id, prima FROM lockdown_canali WHERE guild_id = $1 AND NOT ripristinato "
            "ORDER BY channel_id",
            guild_id,
        )
        return [CanaleBloccato(r["channel_id"], json.loads(r["prima"])) for r in righe]

    async def segna_ripristinato(self, guild_id: int, channel_id: int) -> None:
        await self._pool.execute(
            "UPDATE lockdown_canali SET ripristinato = TRUE WHERE guild_id = $1 AND channel_id = $2",
            guild_id, channel_id,
        )


def _get_pool():
    from core.database import db
    return db.pool


lockdown_repo = LockdownRepository(pool_provider=_get_pool)
