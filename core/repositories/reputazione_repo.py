"""
core/repositories/reputazione_repo.py
=====================================
Reputazione tra membri: punti, pausa, tetto giornaliero, registro, classifica, ruoli per soglia, impostazioni.
Dare o togliere un punto è una transazione sola con un blocco per chi lo dà: pausa, tetto e punti si scrivono
insieme, quindi due comandi contemporanei non superano il limite. Mai a se stessi né ai bot (il controllo sui bot
sta nel cog, che vede il membro); chi ha bloccato chi dà non riceve nulla.
Funzioni coperte: LIV-076…LIV-088
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

MAX_PREMI = 10
CAMPI_IMPOSTAZIONI = frozenset({
    "attiva", "nome", "pausa_secondi", "massimo_per_comando", "tetto_giornaliero", "ruolo_togliere",
    "ruolo_dare_richiesto", "ruolo_dare_escluso", "ruolo_ricevere_richiesto", "ruolo_ricevere_escluso",
    "grazie_attivo", "grazie_canali",
})
PUNTI_MASSIMI = 1_000_000


@dataclass(frozen=True)
class Esito:
    """stato: ok | spenta | se_stessi | bloccato | pausa | tetto | massimo."""

    stato: str
    punti: int = 0  # punti nuovi del ricevente (se ok)
    attesa: int = 0  # secondi alla fine della pausa (se pausa)


class ReputazioneRepository:
    def __init__(self, pool_provider) -> None:
        self._pool_provider = pool_provider

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._pool_provider()

    # ---------------------------------------------------------------- impostazioni
    async def impostazioni(self, guild_id: int) -> asyncpg.Record:
        async with self._pool.acquire() as conn:
            await conn.execute("INSERT INTO reputazione_impostazioni (guild_id) VALUES ($1) ON CONFLICT DO NOTHING", guild_id)
            return await conn.fetchrow("SELECT * FROM reputazione_impostazioni WHERE guild_id = $1", guild_id)

    async def imposta(self, guild_id: int, **campi) -> None:
        if not campi or not set(campi) <= CAMPI_IMPOSTAZIONI:
            raise ValueError("Campo non valido.")
        nomi = list(campi)
        assegna = ", ".join(f"{n} = ${i + 2}" for i, n in enumerate(nomi))  # nomi dalla lista bianca
        async with self._pool.acquire() as conn:
            await conn.execute("INSERT INTO reputazione_impostazioni (guild_id) VALUES ($1) ON CONFLICT DO NOTHING", guild_id)
            await conn.execute(f"UPDATE reputazione_impostazioni SET {assegna} WHERE guild_id = $1", guild_id, *campi.values())

    # ---------------------------------------------------------------- dare e togliere
    async def muovi(self, guild_id: int, da_id: int, a_id: int, delta: int, *, fonte: str = "utente", motivo: str = "") -> Esito:
        """Un punto (o più, fino al massimo per comando) da `da_id` a `a_id`; delta negativo = toglie."""
        if da_id == a_id:
            return Esito("se_stessi")
        if delta == 0 or fonte not in ("utente", "grazie"):
            raise ValueError("Movimento non valido.")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("INSERT INTO reputazione_impostazioni (guild_id) VALUES ($1) ON CONFLICT DO NOTHING", guild_id)
                i = await conn.fetchrow("SELECT attiva, pausa_secondi, massimo_per_comando, tetto_giornaliero FROM reputazione_impostazioni WHERE guild_id = $1", guild_id)
                if not i["attiva"]:
                    return Esito("spenta")
                if abs(delta) > i["massimo_per_comando"]:
                    return Esito("massimo")
                await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", f"rep:{guild_id}:{da_id}")
                if await conn.fetchval("SELECT 1 FROM economia_blocchi WHERE user_id = $1 AND bloccato_id = $2", a_id, da_id):
                    return Esito("bloccato")
                usato = await conn.fetchval(
                    "SELECT COALESCE(sum(abs(delta)), 0) FROM reputazione_registro WHERE guild_id = $1 AND da_id = $2 AND fonte <> 'staff' "
                    "AND creato > now() - interval '24 hours'", guild_id, da_id,
                )
                if usato + abs(delta) > i["tetto_giornaliero"]:
                    return Esito("tetto")
                preso = await conn.fetchval(
                    "INSERT INTO reputazione_pausa (guild_id, user_id) VALUES ($1, $2) "
                    "ON CONFLICT (guild_id, user_id) DO UPDATE SET ultimo = now() "
                    "WHERE reputazione_pausa.ultimo <= now() - make_interval(secs => $3) RETURNING 1",
                    guild_id, da_id, float(i["pausa_secondi"]),
                )
                if not preso:
                    attesa = await conn.fetchval(
                        "SELECT GREATEST(1, ceil(extract(epoch FROM ultimo + make_interval(secs => $3) - now())))::int "
                        "FROM reputazione_pausa WHERE guild_id = $1 AND user_id = $2", guild_id, da_id, float(i["pausa_secondi"]),
                    )
                    return Esito("pausa", attesa=attesa or 1)
                punti = await conn.fetchval(
                    "INSERT INTO reputazione_punti (guild_id, user_id, punti) VALUES ($1, $2, $3) "
                    "ON CONFLICT (guild_id, user_id) DO UPDATE SET punti = reputazione_punti.punti + $3 RETURNING punti",
                    guild_id, a_id, delta,
                )
                await conn.execute(
                    "INSERT INTO reputazione_registro (guild_id, da_id, a_id, delta, fonte, motivo) VALUES ($1, $2, $3, $4, $5, $6)",
                    guild_id, da_id, a_id, delta, fonte, motivo[:200],
                )
                return Esito("ok", punti=punti)

    # ---------------------------------------------------------------- staff
    async def imposta_punti(self, guild_id: int, user_id: int, punti: int, staff_id: int) -> int:
        """Lo staff fissa i punti (anche negativi). Restituisce la variazione."""
        punti = max(-PUNTI_MASSIMI, min(PUNTI_MASSIMI, punti))
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", f"repu:{guild_id}:{user_id}")
                prima = await conn.fetchval("SELECT punti FROM reputazione_punti WHERE guild_id = $1 AND user_id = $2", guild_id, user_id) or 0
                await conn.execute(
                    "INSERT INTO reputazione_punti (guild_id, user_id, punti) VALUES ($1, $2, $3) "
                    "ON CONFLICT (guild_id, user_id) DO UPDATE SET punti = $3", guild_id, user_id, punti,
                )
                if punti != prima:
                    await conn.execute(
                        "INSERT INTO reputazione_registro (guild_id, da_id, a_id, delta, fonte) VALUES ($1, $2, $3, $4, 'staff')",
                        guild_id, staff_id, user_id, punti - prima,
                    )
                return punti - prima

    async def cancella(self, guild_id: int, user_id: int, staff_id: int) -> int:
        """Porta a zero i punti di un utente. Restituisce quelli che aveva."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", f"repu:{guild_id}:{user_id}")
                prima = await conn.fetchval("DELETE FROM reputazione_punti WHERE guild_id = $1 AND user_id = $2 RETURNING punti", guild_id, user_id) or 0
                if prima:
                    await conn.execute(
                        "INSERT INTO reputazione_registro (guild_id, da_id, a_id, delta, fonte) VALUES ($1, $2, $3, $4, 'staff')",
                        guild_id, staff_id, user_id, -prima,
                    )
                return prima

    async def azzera_server(self, guild_id: int) -> int:
        """Punti, registro e pause di tutto il server, insieme. Restituisce quanti membri avevano punti."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", f"repg:{guild_id}")
                n = await conn.fetchval("WITH d AS (DELETE FROM reputazione_punti WHERE guild_id = $1 RETURNING 1) SELECT count(*) FROM d", guild_id)
                await conn.execute("DELETE FROM reputazione_registro WHERE guild_id = $1", guild_id)
                await conn.execute("DELETE FROM reputazione_pausa WHERE guild_id = $1", guild_id)
                return n

    # ---------------------------------------------------------------- lettura
    async def punti_e_posizione(self, guild_id: int, user_id: int) -> tuple[int, int | None]:
        async with self._pool.acquire() as conn:
            r = await conn.fetchrow(
                "SELECT punti, (SELECT count(*) + 1 FROM reputazione_punti p2 WHERE p2.guild_id = $1 AND p2.punti > p.punti) AS pos "
                "FROM reputazione_punti p WHERE guild_id = $1 AND user_id = $2", guild_id, user_id,
            )
        return (r["punti"], r["pos"]) if r else (0, None)

    async def classifica(self, guild_id: int) -> list[tuple[int, int]]:
        """Fino a 1000 righe (utente, punti) dal più alto; l'elenco si sfoglia a pagine nel cog."""
        async with self._pool.acquire() as conn:
            righe = await conn.fetch(
                "SELECT user_id, punti FROM reputazione_punti WHERE guild_id = $1 AND punti <> 0 ORDER BY punti DESC, user_id LIMIT 1000", guild_id
            )
        return [(r["user_id"], r["punti"]) for r in righe]

    async def registro(self, guild_id: int, user_id: int, limite: int = 25) -> list[asyncpg.Record]:
        async with self._pool.acquire() as conn:
            return await conn.fetch(
                "SELECT da_id, a_id, delta, fonte, motivo, creato FROM reputazione_registro "
                "WHERE guild_id = $1 AND (a_id = $2 OR da_id = $2) ORDER BY creato DESC, id DESC LIMIT $3", guild_id, user_id, min(limite, 50),
            )

    # ---------------------------------------------------------------- ruoli per soglia (LIV-086)
    async def premi(self, guild_id: int) -> list[tuple[int, int]]:
        async with self._pool.acquire() as conn:
            righe = await conn.fetch("SELECT soglia, role_id FROM reputazione_premi WHERE guild_id = $1 ORDER BY soglia", guild_id)
        return [(r["soglia"], r["role_id"]) for r in righe]

    async def metti_premio(self, guild_id: int, soglia: int, role_id: int) -> str:
        """«ok» o «pieno» (al massimo 10 per server)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", f"repp:{guild_id}")
                gia = await conn.fetchval("SELECT 1 FROM reputazione_premi WHERE guild_id = $1 AND soglia = $2", guild_id, soglia)
                if not gia and await conn.fetchval("SELECT count(*) FROM reputazione_premi WHERE guild_id = $1", guild_id) >= MAX_PREMI:
                    return "pieno"
                await conn.execute(
                    "INSERT INTO reputazione_premi (guild_id, soglia, role_id) VALUES ($1, $2, $3) "
                    "ON CONFLICT (guild_id, soglia) DO UPDATE SET role_id = $3", guild_id, soglia, role_id,
                )
                return "ok"

    async def togli_premio(self, guild_id: int, soglia: int) -> bool:
        async with self._pool.acquire() as conn:
            return bool(await conn.fetchval("DELETE FROM reputazione_premi WHERE guild_id = $1 AND soglia = $2 RETURNING 1", guild_id, soglia))


def _get_pool():
    from core.database import db

    return db.pool


reputazione_repo = ReputazioneRepository(pool_provider=_get_pool)
