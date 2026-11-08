"""
core/repositories/verify_vpn_repo.py
====================================
Esito del controllo VPN/proxy nella verifica web (tabella `verify_vpn`, migrazione 0507, D64) e storico
condiviso dei falsi positivi (`verify_vpn_storico`, 0508, D65). Solo metodo, esito e data: mai l'IP (gli IP stanno cifrati in `verify_ip`, D67).
Funzioni coperte: SPEC §4.2 (VPN e proxy, D64, D65)
"""

from __future__ import annotations

import asyncpg

ESITO_BLOCCATO = "bloccato"
ESITO_ECCEZIONE = "eccezione"
ESITO_DA_STORICO = "da_storico"
PAUSA_AVVISO_MINUTI = 60


class VerifyVpnRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def leggi(self, guild_id: int, user_id: int):
        return await self._pool.fetchrow(
            "SELECT metodo, esito, creato_il FROM verify_vpn WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        )

    async def ha_eccezione(self, guild_id: int, user_id: int) -> bool:
        return bool(await self._pool.fetchval(
            "SELECT esito = 'eccezione' FROM verify_vpn WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        ))

    async def registra_blocco(
        self, guild_id: int, user_id: int, metodo: str, minuti: int = PAUSA_AVVISO_MINUTI, esito: str = ESITO_BLOCCATO
    ) -> bool:
        """
        Registra il tentativo. True se va avvisato lo staff: prima volta, o l'ultimo avviso è più vecchio di
        `minuti`. Un'eccezione già data non si tocca mai (e non si avvisa).
        """
        riga = await self._pool.fetchrow(
            """
            INSERT INTO verify_vpn (guild_id, user_id, metodo, esito) VALUES ($1, $2, $3, $5)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET
                metodo = CASE WHEN verify_vpn.esito = 'eccezione' THEN verify_vpn.metodo ELSE EXCLUDED.metodo END,
                esito = CASE WHEN verify_vpn.esito = 'eccezione' THEN 'eccezione' ELSE EXCLUDED.esito END,
                creato_il = CASE WHEN verify_vpn.esito = 'eccezione' THEN verify_vpn.creato_il ELSE now() END,
                avvisato_il = CASE
                    WHEN verify_vpn.esito = 'eccezione' OR verify_vpn.avvisato_il > now() - make_interval(mins => $4)
                    THEN verify_vpn.avvisato_il ELSE now() END
            RETURNING (avvisato_il = now() AND esito <> 'eccezione') AS avvisare
            """,
            guild_id, user_id, metodo[:100], minuti, esito,
        )
        return bool(riga["avvisare"])

    async def lascia_passare(
        self, guild_id: int, user_id: int, founder_id: int | None = None, admin_id: int | None = None
    ) -> bool:
        """
        Eccezione per la persona in questo server, e una riga nello storico condiviso (D65) con il founder del
        server e l'admin che ha premuto (D67: servono alla soglia di 3 approvazioni diverse).
        False se l'eccezione c'era già.
        """
        fatto = await self._pool.fetchval(
            """
            WITH prima AS (SELECT metodo FROM verify_vpn WHERE guild_id = $1 AND user_id = $2),
            ins AS (
                INSERT INTO verify_vpn (guild_id, user_id, metodo, esito)
                VALUES ($1, $2, (SELECT metodo FROM prima), 'eccezione')
                ON CONFLICT (guild_id, user_id) DO UPDATE SET esito = 'eccezione', creato_il = now()
                WHERE verify_vpn.esito <> 'eccezione'
                RETURNING metodo
            ),
            sto AS (
                INSERT INTO verify_vpn_storico (guild_id, user_id, metodo, founder_id, admin_id)
                SELECT $1::bigint, $2::bigint, metodo, $3::bigint, $4::bigint FROM ins
                ON CONFLICT (guild_id, user_id) DO UPDATE SET metodo = EXCLUDED.metodo, creato_il = now(),
                    founder_id = EXCLUDED.founder_id, admin_id = EXCLUDED.admin_id
                RETURNING 1
            )
            SELECT count(*) FROM ins
            """,
            guild_id, user_id, founder_id, admin_id,
        )
        return bool(fatto)

    async def storico_altri(self, guild_id: int, user_id: int, massimo: int = 50):
        """Le volte che altri server hanno lasciato passare la persona, dalla più recente (con founder e admin, D67)."""
        return await self._pool.fetch(
            """
            SELECT guild_id, metodo, creato_il, founder_id, admin_id FROM verify_vpn_storico
            WHERE user_id = $1 AND guild_id <> $2 ORDER BY creato_il DESC LIMIT $3
            """,
            user_id, guild_id, massimo,
        )


    async def storico_completo(self, user_id: int, massimo: int = 200):
        """Solo per il proprietario del bot: tutte le volte che un server ha lasciato passare la persona."""
        return await self._pool.fetch(
            "SELECT guild_id, metodo, creato_il FROM verify_vpn_storico WHERE user_id = $1 ORDER BY creato_il DESC LIMIT $2",
            user_id, massimo,
        )


def _get_pool() -> asyncpg.Pool:
    from core.database import db

    return db.pool


verify_vpn_repo = VerifyVpnRepository(pool_provider=_get_pool)
