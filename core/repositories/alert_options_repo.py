"""
core/repositories/alert_options_repo.py
=======================================
Opzioni facoltative di ogni sottoscrizione (#129, NF-32) e ruolo «in diretta».
Tabelle: core/migrations/0121_kick_alert_opzioni.sql. Senza riga valgono i
valori predefiniti (`AlertOptions()`): chi non ha mai usato le opzioni non
vede nessun cambiamento. Funzioni coperte: SPEC §10.9, §10.13
"""

from __future__ import annotations

import asyncpg

from core.alert_options_logic import AlertOptions

_CAMPI = ("mention_role_id", "ping_allowed", "notify_end", "delete_on_end", "watch_button",
          "crosspost", "live_member_id", "last_message_id")


class AlertOptionsRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    @staticmethod
    def _opzioni(r) -> AlertOptions:
        return AlertOptions(**{c: r[c] for c in _CAMPI})

    async def get_many(self, kind: str, sub_ids: list[int]) -> dict[int, AlertOptions]:
        """Una sola query per giro del watcher; gli id senza riga non compaiono."""
        if not sub_ids:
            return {}
        rows = await self._pool.fetch(
            "SELECT * FROM alert_options WHERE kind = $1 AND sub_id = ANY($2::int[])", kind, sub_ids
        )
        return {r["sub_id"]: self._opzioni(r) for r in rows}

    async def get(self, kind: str, sub_id: int) -> AlertOptions:
        return (await self.get_many(kind, [sub_id])).get(sub_id, AlertOptions())

    async def set_fields(self, kind: str, sub_id: int, guild_id: int, **campi) -> None:
        """Aggiorna solo i campi indicati (gli altri restano o prendono il valore predefinito)."""
        sconosciuti = set(campi) - set(_CAMPI)
        if sconosciuti:
            raise ValueError(f"Campi non validi: {sorted(sconosciuti)}")
        if not campi:
            return
        colonne = list(campi)
        segnaposto = ", ".join(f"${i + 4}" for i in range(len(colonne)))
        aggiorna = ", ".join(f"{c} = EXCLUDED.{c}" for c in colonne)
        await self._pool.execute(
            f"INSERT INTO alert_options (kind, sub_id, guild_id, {', '.join(colonne)}) "
            f"VALUES ($1, $2, $3, {segnaposto}) "
            f"ON CONFLICT (kind, sub_id) DO UPDATE SET {aggiorna}",
            kind, sub_id, guild_id, *campi.values(),
        )

    async def set_last_message(self, kind: str, sub_id: int, guild_id: int, message_id: int | None) -> None:
        """Solo UPDATE: se la sottoscrizione è stata rimossa nel frattempo non si ricrea la riga delle opzioni."""
        await self._pool.execute(
            "UPDATE alert_options SET last_message_id = $4 WHERE kind = $1 AND sub_id = $2 AND guild_id = $3",
            kind, sub_id, guild_id, message_id,
        )

    async def other_live_for_member(self, guild_id: int, member_id: int, kind: str, sub_id: int) -> bool:
        """True se il membro è collegato a un altro avviso (Twitch, YouTube, Kick) ancora in diretta."""
        return bool(
            await self._pool.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM alert_options o
                    WHERE o.guild_id = $1 AND o.live_member_id = $2 AND NOT (o.kind = $3 AND o.sub_id = $4)
                      AND CASE o.kind
                        WHEN 'TW' THEN EXISTS (SELECT 1 FROM twitch_subscriptions s WHERE s.id = o.sub_id AND s.last_known_live)
                        WHEN 'YT' THEN EXISTS (SELECT 1 FROM youtube_subscriptions s WHERE s.id = o.sub_id AND s.last_known_live)
                        WHEN 'KK' THEN EXISTS (SELECT 1 FROM kick_subscriptions s WHERE s.id = o.sub_id AND s.last_known_live)
                        ELSE false END
                )
                """,
                guild_id, member_id, kind, sub_id,
            )
        )

    async def delete(self, kind: str, sub_id: int, guild_id: int) -> None:
        await self._pool.execute(
            "DELETE FROM alert_options WHERE kind = $1 AND sub_id = $2 AND guild_id = $3", kind, sub_id, guild_id
        )

    # ---------------------------------------------------------- ruolo in diretta
    async def get_live_role(self, guild_id: int) -> int | None:
        return await self._pool.fetchval("SELECT role_id FROM live_role_settings WHERE guild_id = $1", guild_id)

    async def get_live_roles(self, guild_ids: list[int]) -> dict[int, int]:
        rows = await self._pool.fetch(
            "SELECT guild_id, role_id FROM live_role_settings WHERE guild_id = ANY($1::bigint[])", guild_ids
        )
        return {r["guild_id"]: r["role_id"] for r in rows}

    async def set_live_role(self, guild_id: int, role_id: int | None) -> None:
        if role_id is None:
            await self._pool.execute("DELETE FROM live_role_settings WHERE guild_id = $1", guild_id)
            return
        await self._pool.execute(
            "INSERT INTO live_role_settings (guild_id, role_id) VALUES ($1, $2) "
            "ON CONFLICT (guild_id) DO UPDATE SET role_id = EXCLUDED.role_id",
            guild_id, role_id,
        )


def _get_pool():
    from core.database import db

    return db.pool


alert_options_repo = AlertOptionsRepository(pool_provider=_get_pool)
