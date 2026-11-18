"""
core/repositories/alert_gestione_repo.py
========================================
Operazioni comuni a tutti gli avvisi (feed, Twitch, YouTube, Kick, Picarto): modelli di messaggio,
spostamento di canale, elenco con stato e rimozione in blocco. I nomi delle tabelle sono costanti
nel file (mai testo dell'utente); i valori passano sempre da parametri.
Tabelle: quelle dei repository di feed, Twitch, YouTube, Kick e Picarto.
Funzioni coperte: SPEC §10.9, §10.13 (#129 ALR-020, 037, 038, 039)
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

# sigla: (tabella, colonna del modello «in diretta», colonna del modello «fine», colonna «in diretta ora»)
TABELLE: dict[str, tuple[str, str, str | None, str | None]] = {
    "RSS": ("feed_subscriptions", "message_template", None, None),
    "TW": ("twitch_subscriptions", "live_message_template", "offline_message_template", "last_known_live"),
    "YT": ("youtube_subscriptions", "live_message_template", "offline_message_template", "last_known_live"),
    "KK": ("kick_subscriptions", "live_message_template", "offline_message_template", "last_known_live"),
    "PC": ("picarto_subscriptions", "live_message_template", "offline_message_template", "last_known_live"),
}


@dataclass(frozen=True)
class RigaAvviso:
    sigla: str
    id: int
    channel_id: int
    label: str
    in_diretta: bool


class AlertGestioneRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def esiste(self, sigla: str, sub_id: int, guild_id: int) -> bool:
        tabella = TABELLE[sigla][0]
        return bool(await self._pool.fetchval(f"SELECT 1 FROM {tabella} WHERE id = $1 AND guild_id = $2", sub_id, guild_id))

    async def imposta_modello(self, sigla: str, sub_id: int, guild_id: int, quale: str, testo: str) -> bool:
        """`quale`: «inizio» o «fine». False se l'avviso non c'è o se quel tipo non ha il modello di fine."""
        tabella, colonna_inizio, colonna_fine, _ = TABELLE[sigla]
        colonna = colonna_inizio if quale == "inizio" else colonna_fine
        if colonna is None:
            return False
        r = await self._pool.execute(f"UPDATE {tabella} SET {colonna} = $3 WHERE id = $1 AND guild_id = $2", sub_id, guild_id, testo)
        return r.endswith(" 1")

    async def sposta(self, sigla: str, sub_id: int, guild_id: int, channel_id: int) -> bool:
        tabella = TABELLE[sigla][0]
        r = await self._pool.execute(
            f"UPDATE {tabella} SET channel_id = $3 WHERE id = $1 AND guild_id = $2", sub_id, guild_id, channel_id
        )
        return r.endswith(" 1")

    async def elenco(self, guild_id: int, channel_id: int | None = None) -> list[RigaAvviso]:
        """Tutti gli avvisi del server (o di un canale), con lo stato «in diretta ora» dell'ultima lettura."""
        righe: list[RigaAvviso] = []
        for sigla, (tabella, _, _, colonna_live) in TABELLE.items():
            live = colonna_live or "false"
            rows = await self._pool.fetch(
                f"SELECT id, channel_id, label, {live} AS live FROM {tabella} "
                "WHERE guild_id = $1 AND ($2::bigint IS NULL OR channel_id = $2) ORDER BY id",
                guild_id, channel_id,
            )
            righe += [RigaAvviso(sigla, r["id"], r["channel_id"], r["label"], bool(r["live"])) for r in rows]
        return righe

    async def rimuovi_tutti(self, guild_id: int, channel_id: int | None = None) -> int:
        """Cancella gli avvisi del server (o di un canale) con le loro opzioni; restituisce quanti."""
        totale = 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for sigla, (tabella, *_) in TABELLE.items():
                    ids = await conn.fetch(
                        f"DELETE FROM {tabella} WHERE guild_id = $1 AND ($2::bigint IS NULL OR channel_id = $2) RETURNING id",
                        guild_id, channel_id,
                    )
                    totale += len(ids)
                    if ids:
                        await conn.execute(
                            "DELETE FROM alert_options WHERE kind = $1 AND guild_id = $2 AND sub_id = ANY($3::int[])",
                            sigla, guild_id, [r["id"] for r in ids],
                        )
        return totale


def _get_pool():
    from core.database import db

    return db.pool


alert_gestione_repo = AlertGestioneRepository(pool_provider=_get_pool)
