"""
core/repositories/verify_ip_repo.py
===================================
IP della verifica web, già cifrati da `core/verify_ip.py` (tabella `verify_ip`, migrazione 0530, D67), e le
scadenze legate a uscite, kick e ban. Qui non c'è mai un IP in chiaro né la chiave.
Funzioni coperte: SPEC §4.2 (IP solo per il proprietario, D67)
"""

from __future__ import annotations

import asyncpg

GIORNI_USCITA = 30
GIORNI_KICK = 180
GIORNI_DOPO_SBLOCCO = 30


class VerifyIpRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def salva(
        self, guild_id: int, user_id: int, impronta: str, cifrato: str, esito: str, massimo: int
    ) -> None:
        """
        Una riga per (server, persona, impronta dell'IP); oltre `massimo` per persona si tolgono le più vecchie.
        Chi si verifica è nel server: via la scadenza di un'uscita o di uno sblocco (rientro a bot spento).
        """
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                """
                INSERT INTO verify_ip (guild_id, user_id, ip_impronta, ip_cifrato, esito) VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (guild_id, user_id, ip_impronta) DO UPDATE SET
                    esito = EXCLUDED.esito, ultimo_il = now(), ip_cifrato = EXCLUDED.ip_cifrato
                """,
                guild_id, user_id, impronta, cifrato, esito,
            )
            # chi si verifica è nel server: un'uscita o uno sblocco segnati prima non contano più
            await conn.execute(
                "UPDATE verify_ip SET motivo = NULL, scade_il = NULL "
                "WHERE guild_id = $1 AND user_id = $2 AND motivo IN ('uscita', 'sblocco')",
                guild_id, user_id,
            )
            await conn.execute(
                """
                DELETE FROM verify_ip WHERE id IN (
                    SELECT id FROM verify_ip WHERE guild_id = $1 AND user_id = $2
                    ORDER BY ultimo_il DESC, id DESC OFFSET $3
                )
                """,
                guild_id, user_id, massimo,
            )

    async def della_persona(self, user_id: int, massimo: int = 100):
        """Solo per il proprietario del bot."""
        return await self._pool.fetch(
            "SELECT guild_id, ip_cifrato, esito, ultimo_il FROM verify_ip WHERE user_id = $1 "
            "ORDER BY ultimo_il DESC LIMIT $2",
            user_id, massimo,
        )

    async def ha_righe(self, guild_id: int, user_id: int) -> bool:
        return bool(await self._pool.fetchval(
            "SELECT EXISTS (SELECT 1 FROM verify_ip WHERE guild_id = $1 AND user_id = $2)", guild_id, user_id
        ))

    async def persona_uscita(self, guild_id: int, user_id: int, espulsa: bool) -> int:
        """30 giorni (180 dopo un kick). Un ban o un kick già segnati non si toccano con un'uscita semplice."""
        if espulsa:
            giorni, motivo, non_toccare = GIORNI_KICK, "kick", ("ban",)
        else:
            giorni, motivo, non_toccare = GIORNI_USCITA, "uscita", ("ban", "kick")
        return await self._conta(
            """
            UPDATE verify_ip SET motivo = $3, scade_il = now() + make_interval(days => $4)
            WHERE guild_id = $1 AND user_id = $2 AND COALESCE(motivo, '') <> ALL($5::text[])
            """,
            guild_id, user_id, motivo, giorni, list(non_toccare),
        )

    async def persona_tornata(self, guild_id: int, user_id: int) -> None:
        await self._pool.execute(
            "UPDATE verify_ip SET motivo = NULL, scade_il = NULL "
            "WHERE guild_id = $1 AND user_id = $2 AND motivo IN ('uscita', 'sblocco')",
            guild_id, user_id,
        )

    async def persona_bannata(self, guild_id: int, user_id: int) -> None:
        """Il ban vince su tutto: nessuna scadenza finché è attivo."""
        await self._pool.execute(
            "UPDATE verify_ip SET motivo = 'ban', scade_il = NULL WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id,
        )

    async def persona_sbloccata(self, guild_id: int, user_id: int) -> None:
        await self._pool.execute(
            "UPDATE verify_ip SET motivo = 'sblocco', scade_il = now() + make_interval(days => $3) "
            "WHERE guild_id = $1 AND user_id = $2 AND motivo = 'ban'",
            guild_id, user_id, GIORNI_DOPO_SBLOCCO,
        )

    async def _conta(self, sql: str, *args) -> int:
        stato = await self._pool.execute(sql, *args)
        return int(stato.rsplit(" ", 1)[-1])


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


verify_ip_repo = VerifyIpRepository(pool_provider=_get_pool)
