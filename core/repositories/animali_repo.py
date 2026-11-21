"""
core/repositories/animali_repo.py
=================================
Animali da accudire, posti in più, attività e pesca. Ogni azione è una transazione: la pausa si prende con
una UPDATE/UPSERT condizionata (`... <= now() - intervallo`), il costo con `spend_coins_in`, il premio con
`add_coins_in`; il deposito dei pesci si svuota con DELETE ... RETURNING quindi si vende una volta sola.
Funzioni coperte: ECO-122, ECO-123, ECO-124, ECO-130, ECO-131, ECO-132, ECO-133, ECO-134, ECO-138
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import asyncpg

from core.animali_logic import (
    COSTO_CURA, COSTO_POSTO, MAX_PESCI_DEPOSITO, PAUSA_ATTIVITA, PAUSA_CURA, PESCI, POSTI_BASE, SPECIE, XP_CURA,
    bonus_percentuale, costo_posto, livello, nome_valido, salute, valore_pesci,
)
from core.repositories.guild_chest_repo import deposit_in
from core.repositories.leveling_repo import add_coins_in, spend_coins_in

REASON_ANIMALI = "animali"
_COLONNA = {"fame": "fame_at", "igiene": "igiene_at", "gioco": "gioco_at"}


class AnimaliRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    async def elenco(self, guild_id: int, user_id: int) -> list[asyncpg.Record]:
        return await self._pool.fetch(
            "SELECT id, specie, nome, nato_at, fame_at, igiene_at, gioco_at, xp FROM economia_animali "
            "WHERE guild_id = $1 AND user_id = $2 ORDER BY id LIMIT 5",
            guild_id, user_id,
        )

    async def compra(self, guild_id: int, user_id: int, specie: str, nome: str) -> str:
        """Compra un animale. Restituisce «ok», «pieno» (posti finiti) o «poche» (monete)."""
        if specie not in SPECIE:
            raise ValueError(f"Specie sconosciuta: {specie}")
        nome = nome_valido(nome)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", f"animali:{guild_id}:{user_id}")
                extra = await conn.fetchval(
                    "SELECT extra FROM economia_animali_posti WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
                )
                avuti = await conn.fetchval(
                    "SELECT count(*) FROM economia_animali WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
                )
                if avuti >= POSTI_BASE + int(extra or 0):
                    return "pieno"
                prezzo = SPECIE[specie][0]
                if not await spend_coins_in(conn, guild_id, user_id, prezzo):
                    return "poche"
                await deposit_in(conn, guild_id, prezzo, REASON_ANIMALI)
                await conn.execute(
                    "INSERT INTO economia_animali (guild_id, user_id, specie, nome) VALUES ($1, $2, $3, $4)",
                    guild_id, user_id, specie, nome,
                )
                return "ok"

    async def compra_posto(self, guild_id: int, user_id: int) -> tuple[str, int]:
        """Un posto in più (massimo 2). («ok», costo), («massimo», 0) o («poche», costo)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO economia_animali_posti (guild_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", guild_id, user_id
                )
                extra = await conn.fetchval(
                    "SELECT extra FROM economia_animali_posti WHERE guild_id = $1 AND user_id = $2 FOR UPDATE", guild_id, user_id
                )
                costo = costo_posto(extra)
                if costo is None:
                    return "massimo", 0
                if not await spend_coins_in(conn, guild_id, user_id, costo):
                    return "poche", costo
                await deposit_in(conn, guild_id, costo, REASON_ANIMALI)
                await conn.execute(
                    "UPDATE economia_animali_posti SET extra = extra + 1 WHERE guild_id = $1 AND user_id = $2 AND extra = $3",
                    guild_id, user_id, extra,
                )
                return "ok", costo

    async def cura(self, guild_id: int, user_id: int, animale_id: int, tipo: str) -> str:
        """Nutre, pulisce o fa giocare un animale (una volta all'ora per tipo). «ok», «pausa», «poche» o «non_tuo»."""
        if tipo not in _COLONNA:
            raise ValueError(f"Tipo sconosciuto: {tipo}")
        try:
            return await self._cura(guild_id, user_id, animale_id, tipo)
        except _Pausa:  # la transazione è annullata, anche il costo del cibo
            return "pausa"

    async def _cura(self, guild_id: int, user_id: int, animale_id: int, tipo: str) -> str:
        col = _COLONNA[tipo]  # nome di colonna da una tabella fissa, mai testo dell'utente
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                if not await conn.fetchval(
                    "SELECT 1 FROM economia_animali WHERE id = $1 AND guild_id = $2 AND user_id = $3 FOR UPDATE",
                    animale_id, guild_id, user_id,
                ):
                    return "non_tuo"
                costo = COSTO_CURA[tipo]
                if costo and not await spend_coins_in(conn, guild_id, user_id, costo):
                    return "poche"
                fatto = await conn.fetchval(
                    f"UPDATE economia_animali SET {col} = now(), xp = xp + $2 WHERE id = $1 "
                    f"AND {col} <= now() - make_interval(secs => $3) RETURNING 1",
                    animale_id, XP_CURA, float(PAUSA_CURA),
                )
                if fatto is None:
                    raise _Pausa()
                if costo:
                    await deposit_in(conn, guild_id, costo, REASON_ANIMALI)
                return "ok"

    async def attivita(self, guild_id: int, user_id: int, animale_id: int, monete: int, salute_minima_ok: bool) -> int | None:
        """Un'attività con l'animale (ogni 2 ore): None se in pausa, non è suo o sta troppo male."""
        if not salute_minima_ok or monete <= 0:
            return None
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                fatto = await conn.fetchval(
                    "UPDATE economia_animali SET attivita_at = now(), xp = xp + $4 WHERE id = $1 AND guild_id = $2 AND user_id = $3 "
                    "AND (attivita_at IS NULL OR attivita_at <= now() - make_interval(secs => $5)) RETURNING 1",
                    animale_id, guild_id, user_id, XP_CURA, float(PAUSA_ATTIVITA),
                )
                if fatto is None:
                    return None
                return await add_coins_in(conn, guild_id, user_id, monete)

    async def bonus(self, guild_id: int, user_id: int, tipo: str) -> int:
        """ECO-131: bonus % di lavoro o premio dato dagli animali ben tenuti."""
        adesso = datetime.now(timezone.utc)
        righe = await self.elenco(guild_id, user_id)
        return bonus_percentuale(
            [(r["specie"], salute(r["fame_at"], r["igiene_at"], r["gioco_at"], adesso), livello(r["xp"])) for r in righe], tipo
        )

    # ---------------------------------------------------------------- pesca
    async def pesca(self, guild_id: int, user_id: int, oggi: date, specie: str | None, pausa_s: int) -> bool | None:
        """
        Registra una lanciata: pausa, pesce nel deposito, specie vista e punti del giorno nella stessa transazione.
        Restituisce True se ha preso un pesce, False se niente, None se in pausa o deposito pieno.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                tot = await conn.fetchval(
                    "SELECT COALESCE(SUM(quantita), 0) FROM economia_pesci WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
                )
                if specie and tot >= MAX_PESCI_DEPOSITO:
                    return None
                preso = await conn.fetchval(
                    "INSERT INTO economia_pause (guild_id, user_id, chiave, ultima_at) VALUES ($1, $2, 'pesca', now()) "
                    "ON CONFLICT (guild_id, user_id, chiave) DO UPDATE SET ultima_at = now() "
                    "WHERE economia_pause.ultima_at <= now() - make_interval(secs => $3) RETURNING 1",
                    guild_id, user_id, float(pausa_s),
                )
                if preso is None:
                    return None
                if specie is None:
                    return False
                if specie not in PESCI:
                    raise ValueError(f"Specie sconosciuta: {specie}")
                await conn.execute(
                    "INSERT INTO economia_pesci (guild_id, user_id, specie, quantita) VALUES ($1, $2, $3, 1) "
                    "ON CONFLICT (guild_id, user_id, specie) DO UPDATE SET quantita = economia_pesci.quantita + 1",
                    guild_id, user_id, specie,
                )
                await conn.execute(
                    "INSERT INTO economia_pesci_visti (guild_id, user_id, specie) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                    guild_id, user_id, specie,
                )
                await conn.execute(
                    "INSERT INTO economia_pesca_giorno (guild_id, giorno, user_id, punti) VALUES ($1, $2, $3, $4) "
                    "ON CONFLICT (guild_id, giorno, user_id) DO UPDATE SET punti = economia_pesca_giorno.punti + $4",
                    guild_id, oggi, user_id, PESCI[specie][0],
                )
                return True

    async def deposito(self, guild_id: int, user_id: int) -> dict[str, int]:
        righe = await self._pool.fetch(
            "SELECT specie, quantita FROM economia_pesci WHERE guild_id = $1 AND user_id = $2 AND quantita > 0", guild_id, user_id
        )
        return {r["specie"]: r["quantita"] for r in righe}

    async def vendi_pesci(self, guild_id: int, user_id: int) -> tuple[int, int]:
        """Vende tutto il deposito: (pesci, monete). Si svuota con DELETE ... RETURNING: una volta sola."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                righe = await conn.fetch(
                    "DELETE FROM economia_pesci WHERE guild_id = $1 AND user_id = $2 RETURNING specie, quantita", guild_id, user_id
                )
                quantita = {r["specie"]: r["quantita"] for r in righe}
                monete = valore_pesci(quantita)
                n = sum(quantita.values())
                if monete > 0:
                    await add_coins_in(conn, guild_id, user_id, monete)
                return n, monete

    async def visti(self, guild_id: int, user_id: int) -> set[str]:
        return {r["specie"] for r in await self._pool.fetch(
            "SELECT specie FROM economia_pesci_visti WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)}

    async def classifica_giorno(self, guild_id: int, giorno: date, limite: int = 10) -> list[asyncpg.Record]:
        return await self._pool.fetch(
            "SELECT user_id, punti FROM economia_pesca_giorno WHERE guild_id = $1 AND giorno = $2 AND punti > 0 "
            "ORDER BY punti DESC, user_id LIMIT $3",
            guild_id, giorno, min(max(1, limite), 10),
        )


class _Pausa(Exception):
    pass


def _get_pool():
    from core.database import db

    return db.pool


animali_repo = AnimaliRepository(pool_provider=_get_pool)
