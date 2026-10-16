"""
core/repositories/voice_temp_repo.py
=======================================
Persistenza per i vocali temporanei:
- configurazione per server (canale generatore, categoria di
  destinazione)
- canali temporanei attivi, con il loro proprietario (per i comandi
  di gestione — rename/limit/lock/kick — vedi
  core/voice_temp_logic.py per chi può usarli)
- opzioni del server: modello del nome, canali che nascono bloccati,
  canale di registro; numero di ogni canale nella sequenza (#127)
- stato del blocco (/voice lock) con il valore di «Connetti» di prima,
  che resta anche dopo un riavvio del bot (#144)
Funzioni coperte: SPEC §12
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg


@dataclass(frozen=True)
class VoiceTempConfig:
    guild_id: int
    generator_channel_id: int | None
    category_id: int | None
    category_cap: int | None = None
    role_pc_id: int | None = None
    role_console_id: int | None = None
    role_mobile_id: int | None = None
    nome_modello: str | None = None
    nasce_bloccato: bool = False
    canale_registro_id: int | None = None


@dataclass(frozen=True)
class TrackedVoiceChannel:
    """Un vocale temporaneo registrato, con la sua età in secondi."""

    channel_id: int
    guild_id: int
    owner_id: int
    age_seconds: float


async def run_migrations(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS voice_temp_config (
            guild_id             BIGINT PRIMARY KEY,
            generator_channel_id BIGINT,
            category_id          BIGINT
        );

        CREATE TABLE IF NOT EXISTS voice_temp_channels (
            channel_id BIGINT PRIMARY KEY,
            guild_id   BIGINT NOT NULL,
            owner_id   BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        -- ADD COLUMN IF NOT EXISTS (idempotente): voice_temp_config
        -- esisteva già senza queste colonne — SPEC.md §12.5 (ruoli
        -- piattaforma, solo informativi) e §12.8 (cap configurabile
        -- per categoria, sempre <= limite hard Discord di 50).
        ALTER TABLE voice_temp_config ADD COLUMN IF NOT EXISTS category_cap INTEGER;
        ALTER TABLE voice_temp_config ADD COLUMN IF NOT EXISTS role_pc_id BIGINT;
        ALTER TABLE voice_temp_config ADD COLUMN IF NOT EXISTS role_console_id BIGINT;
        ALTER TABLE voice_temp_config ADD COLUMN IF NOT EXISTS role_mobile_id BIGINT;
        """
    )


class VoiceTempRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def get_config(self, guild_id: int) -> VoiceTempConfig:
        row = await self._pool.fetchrow(
            """
            SELECT generator_channel_id, category_id, category_cap,
                   role_pc_id, role_console_id, role_mobile_id,
                   nome_modello, nasce_bloccato, canale_registro_id
            FROM voice_temp_config WHERE guild_id = $1
            """,
            guild_id,
        )
        if row is None:
            return VoiceTempConfig(guild_id=guild_id, generator_channel_id=None, category_id=None)
        return VoiceTempConfig(
            guild_id=guild_id,
            generator_channel_id=row["generator_channel_id"],
            category_id=row["category_id"],
            category_cap=row["category_cap"],
            role_pc_id=row["role_pc_id"],
            role_console_id=row["role_console_id"],
            role_mobile_id=row["role_mobile_id"],
            nome_modello=row["nome_modello"],
            nasce_bloccato=row["nasce_bloccato"],
            canale_registro_id=row["canale_registro_id"],
        )

    async def set_config(
        self, guild_id: int, generator_channel_id: int, category_id: int
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO voice_temp_config (guild_id, generator_channel_id, category_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE
                SET generator_channel_id = EXCLUDED.generator_channel_id,
                    category_id = EXCLUDED.category_id
            """,
            guild_id,
            generator_channel_id,
            category_id,
        )

    async def set_category_cap(self, guild_id: int, cap: int | None) -> None:
        """
        SPEC.md §12.8. Richiede che la riga esista già (creata da
        set_config) — un cap senza generatore/categoria configurati
        non avrebbe senso, quindi non facciamo qui un UPSERT che
        creerebbe una riga "orfana".
        """
        await self._pool.execute(
            "UPDATE voice_temp_config SET category_cap = $2 WHERE guild_id = $1",
            guild_id,
            cap,
        )

    async def set_platform_roles(
        self,
        guild_id: int,
        role_pc_id: int | None,
        role_console_id: int | None,
        role_mobile_id: int | None,
    ) -> None:
        """SPEC.md §12.5 — ruoli piattaforma, solo informativi."""
        await self._pool.execute(
            """
            UPDATE voice_temp_config
            SET role_pc_id = $2, role_console_id = $3, role_mobile_id = $4
            WHERE guild_id = $1
            """,
            guild_id,
            role_pc_id,
            role_console_id,
            role_mobile_id,
        )

    async def set_opzioni(
        self,
        guild_id: int,
        nome_modello: str | None,
        nasce_bloccato: bool,
        canale_registro_id: int | None,
    ) -> None:
        """#127 VOC-011/012/015/018. Come il cap: la riga esiste già (setup)."""
        await self._pool.execute(
            """
            UPDATE voice_temp_config
            SET nome_modello = $2, nasce_bloccato = $3, canale_registro_id = $4
            WHERE guild_id = $1
            """,
            guild_id,
            nome_modello,
            nasce_bloccato,
            canale_registro_id,
        )

    async def numeri_usati(self, guild_id: int) -> list[int]:
        """Numeri dei vocali temporanei aperti nel server (VOC-012)."""
        righe = await self._pool.fetch(
            "SELECT numero FROM voice_temp_channels WHERE guild_id = $1 AND numero IS NOT NULL",
            guild_id,
        )
        return [r["numero"] for r in righe]

    async def register_channel(
        self, channel_id: int, guild_id: int, owner_id: int, numero: int | None = None
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO voice_temp_channels (channel_id, guild_id, owner_id, numero)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (channel_id) DO UPDATE SET owner_id = EXCLUDED.owner_id
            """,
            channel_id,
            guild_id,
            owner_id,
            numero,
        )

    async def get_owner(self, channel_id: int) -> int | None:
        """
        Restituisce il proprietario del canale, oppure None se questo
        channel_id non è (o non è più) un canale temporaneo tracciato
        — usato anche come test "è un nostro canale?" prima di agire.
        """
        return await self._pool.fetchval(
            "SELECT owner_id FROM voice_temp_channels WHERE channel_id = $1",
            channel_id,
        )

    async def cambia_proprietario(self, channel_id: int, vecchio_id: int | None, nuovo_id: int) -> bool:
        """Passa la proprietà solo se è ancora di `vecchio_id`: due richieste insieme, vince una sola."""
        result = await self._pool.execute(
            "UPDATE voice_temp_channels SET owner_id = $3 WHERE channel_id = $1 AND owner_id IS NOT DISTINCT FROM $2",
            channel_id,
            vecchio_id,
            nuovo_id,
        )
        return result.endswith(" 1")

    async def segna_bloccato(self, channel_id: int, connect_prima: bool | None) -> None:
        """
        /voice lock: ricorda il valore di «Connetti» di @everyone prima
        del blocco. Solo al primo lock: un secondo vedrebbe già False.
        """
        await self._pool.execute(
            """
            UPDATE voice_temp_channels SET bloccato = true, connect_prima = $2
            WHERE channel_id = $1 AND NOT bloccato
            """,
            channel_id,
            connect_prima,
        )

    async def togli_blocco(self, channel_id: int) -> tuple[bool, bool | None]:
        """
        /voice unlock: restituisce (era bloccato, valore di «Connetti»
        salvato dal lock) e cancella il ricordo, in una sola istruzione.
        Canale non bloccato o non tracciato: (False, None).
        """
        riga = await self._pool.fetchrow(
            """
            UPDATE voice_temp_channels AS c
            SET bloccato = false, connect_prima = NULL
            FROM (
                SELECT channel_id, connect_prima FROM voice_temp_channels
                WHERE channel_id = $1 AND bloccato FOR UPDATE
            ) AS prima
            WHERE c.channel_id = prima.channel_id
            RETURNING prima.connect_prima
            """,
            channel_id,
        )
        return (False, None) if riga is None else (True, riga["connect_prima"])

    async def list_channels(self) -> list[TrackedVoiceChannel]:
        """
        Tutti i vocali temporanei registrati, in ogni server. Serve
        alla pulizia all'avvio: sono pochi (uno per canale aperto).
        """
        rows = await self._pool.fetch(
            """
            SELECT channel_id, guild_id, owner_id,
                   extract(epoch FROM now() - created_at) AS age_seconds
            FROM voice_temp_channels
            ORDER BY channel_id
            """
        )
        return [
            TrackedVoiceChannel(
                channel_id=row["channel_id"],
                guild_id=row["guild_id"],
                owner_id=row["owner_id"],
                age_seconds=float(row["age_seconds"]),
            )
            for row in rows
        ]

    async def unregister_channel(self, channel_id: int) -> None:
        await self._pool.execute(
            "DELETE FROM voice_temp_channels WHERE channel_id = $1", channel_id
        )


def _get_pool():
    from core.database import db
    return db.pool


voice_temp_repo = VoiceTempRepository(pool_provider=_get_pool)
