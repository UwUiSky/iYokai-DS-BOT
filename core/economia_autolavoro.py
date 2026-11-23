"""
core/economia_autolavoro.py
===========================
Il lavoro automatico (ECO-050, D121): chi lo accende (premium del server) lavora da solo ogni 4 ore con la stessa
paga di `/monete work`. Un giro ogni 5 minuti prende i turni scaduti e li sposta di 4 ore nella stessa istruzione:
un secondo giro, o un riavvio, non paga due volte. Se l'attesa del lavoro manuale non è finita, il turno salta.
Senza premium, o con il modulo livelli spento, la riga si toglie. Nessun messaggio: il movimento è nello storico.
Funzioni coperte: ECO-050
Dipende da: core/premium.py, core/repositories/leveling_repo.py
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

from discord.ext import commands, tasks

from core import premium as premium_mod
from core.bot_ready import attendi_bot_pronto
from core.database import db
from core.leveling_logic import attesa_work_secondi, con_potenziamento
from core.repositories.animali_repo import animali_repo
from core.repositories.leveling_repo import leveling_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.mondo_repo import mondo_repo
from core.repositories.potenziamenti_repo import potenziamenti_repo
from core.repositories.rischio_repo import rischio_repo
from core.repositories.sociale_repo import BONUS_PRESTIGIO, sociale_repo
from core.rischio_logic import lavoro_per_turni, paga_con_lavoro

logger = logging.getLogger("iyokai.economia_autolavoro")

MODULO_AUTOLAVORO = "autolavoro"
ORE_TRA_TURNI = 4
TICK_SECONDS = 300
MAX_PER_GIRO = 200


async def paga_lavoro(guild_id: int, user_id: int, impostazioni, rng: random.Random | None = None) -> int:
    """La paga di un turno (punto unico: la usano `/monete work` e il lavoro automatico)."""
    scelta = (rng or random).randint(impostazioni.work_min, impostazioni.work_max)
    turni = await rischio_repo.turni(guild_id, user_id)  # ECO-029
    guadagno = max(scelta if scelta == 0 else 1, paga_con_lavoro(scelta, lavoro_per_turni(turni)[2]))
    guadagno = con_potenziamento(guadagno, (await potenziamenti_repo.livelli(guild_id, user_id))["lavoro"])  # ECO-081
    bonus = (  # ECO-131, ECO-148, ECO-056/144
        await animali_repo.bonus(guild_id, user_id, "lavoro")
        + BONUS_PRESTIGIO * await sociale_repo.livello_prestigio(guild_id, user_id)
        + await mondo_repo.bonus_percento(guild_id, user_id)
    )
    return guadagno + guadagno * bonus // 100


async def accendi(guild_id: int, user_id: int, bot=None) -> bool:
    """Accende il lavoro automatico. False se il server non ha il premium."""
    if not await premium_mod.guild_has_premium_access(guild_id, MODULO_AUTOLAVORO, bot=bot):
        return False
    await db.pool.execute(
        "INSERT INTO economia_autolavoro (guild_id, user_id, prossimo_at) VALUES ($1, $2, now()) "
        "ON CONFLICT (guild_id, user_id) DO NOTHING",
        guild_id, user_id,
    )
    return True


async def spegni(guild_id: int, user_id: int) -> bool:
    return (await db.pool.execute(
        "DELETE FROM economia_autolavoro WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
    )).endswith(" 1")


async def acceso(guild_id: int, user_id: int) -> bool:
    return bool(await db.pool.fetchval(
        "SELECT 1 FROM economia_autolavoro WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
    ))


async def tick(bot: commands.Bot | None = None, rng: random.Random | None = None) -> int:
    """Un giro. Restituisce quanti turni sono stati pagati."""
    prese = await db.pool.fetch(
        """
        UPDATE economia_autolavoro SET prossimo_at = now() + make_interval(hours => $2)
        WHERE (guild_id, user_id) IN (
            SELECT guild_id, user_id FROM economia_autolavoro WHERE prossimo_at <= now()
            ORDER BY prossimo_at LIMIT $1 FOR UPDATE SKIP LOCKED
        ) RETURNING guild_id, user_id
        """,
        MAX_PER_GIRO, ORE_TRA_TURNI,
    )
    pagati = 0
    for r in prese:
        try:
            if await _turno(bot, r["guild_id"], r["user_id"], rng):
                pagati += 1
        except Exception:
            logger.exception("Lavoro automatico non riuscito (server %s).", r["guild_id"])
    return pagati


async def _turno(bot, guild_id: int, user_id: int, rng) -> bool:
    if not await premium_mod.guild_has_premium_access(guild_id, MODULO_AUTOLAVORO, bot=bot) or not (
        await db.is_module_active_for_guild(guild_id, "leveling")
    ):
        await spegni(guild_id, user_id)
        return False
    impostazioni = (await leveling_settings_repo.get_config(guild_id)).impostazioni
    guadagno = await paga_lavoro(guild_id, user_id, impostazioni, rng)
    riscosso = await leveling_repo.claim_work(
        guild_id, user_id, guadagno, attesa_work_secondi(impostazioni), datetime.now(timezone.utc)
    )
    if riscosso:
        await rischio_repo.segna_turno(guild_id, user_id)
    return bool(riscosso)


_loop_task: tasks.Loop | None = None


def start(bot: commands.Bot) -> None:
    global _loop_task
    if _loop_task is not None:
        return

    @tasks.loop(seconds=TICK_SECONDS)
    async def _loop():
        await tick(bot)

    @_loop.before_loop
    async def _before():
        await attendi_bot_pronto(bot)

    _loop_task = _loop
    _loop.start()
