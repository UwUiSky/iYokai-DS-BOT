"""
core/repositories/log_testi_repo.py
===================================
Righe cifrate del testo dei messaggi (LOG-029, D122): scrittura a lotti, lettura per utente in una finestra di giorni,
potatura per server. Qui entra e esce solo il dato già cifrato; la cifratura sta in `core/log_testi_logic.py`.
Funzioni coperte: SPEC §8.18 (LOG-029)
Dipende da: core/migrations/0900_log_messaggi_testi.sql
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.database import db


@dataclass(frozen=True)
class RigaCifrata:
    guild_id: int
    channel_id: int
    message_id: int
    user_id: int
    evento: str
    cifrato: str
    creato: datetime | None = None


class LogTestiRepository:
    async def inserisci_lotto(self, righe: list[RigaCifrata]) -> None:
        """Un solo invio per tutto il lotto, in transazione."""
        if not righe:
            return
        async with db.pool.acquire() as conn, conn.transaction():
            await conn.executemany(
                "INSERT INTO log_messaggi_testi (guild_id, channel_id, message_id, user_id, evento, cifrato) "
                "VALUES ($1, $2, $3, $4, $5, $6)",
                [(r.guild_id, r.channel_id, r.message_id, r.user_id, r.evento, r.cifrato) for r in righe],
            )

    async def dell_utente(self, guild_id: int, user_id: int, giorni: int, limite: int) -> list[RigaCifrata]:
        """Le righe più recenti dell'utente negli ultimi `giorni` giorni, dalla più vecchia."""
        righe = await db.pool.fetch(
            "SELECT guild_id, channel_id, message_id, user_id, evento, cifrato, creato FROM ("
            "  SELECT * FROM log_messaggi_testi WHERE guild_id = $1 AND user_id = $2 "
            "  AND creato >= now() - make_interval(days => $3) ORDER BY id DESC LIMIT $4) t ORDER BY id",
            guild_id, user_id, giorni, limite,
        )
        return [RigaCifrata(**dict(r)) for r in righe]

    async def pota_per_server(self, massimo: int) -> int:
        """Tiene al massimo `massimo` righe per server (le più recenti). Restituisce quante ne toglie."""
        esito = await db.pool.execute(
            "DELETE FROM log_messaggi_testi WHERE id IN ("
            "  SELECT id FROM (SELECT id, row_number() OVER (PARTITION BY guild_id ORDER BY id DESC) AS n "
            "  FROM log_messaggi_testi) t WHERE n > $1)",
            massimo,
        )
        return int(esito.split()[-1])


log_testi_repo = LogTestiRepository()
