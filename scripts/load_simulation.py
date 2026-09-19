"""
scripts/load_simulation.py
=============================
Simulazione di carico sui percorsi caldi del bot (leveling, spam
trap) — NON è il bot vero connesso a Discord (serve un vero token e
traffico reale, che uno script diagnostico non ha), è l'esecuzione
REALE del codice dei cog contro PostgreSQL vero, con oggetti Discord
finti minimali ma sufficienti a superare i controlli isinstance che
il codice fa davvero.

## Come si usa

Richiede le stesse variabili d'ambiente fittizie di tests/conftest.py
(vedi quel file) più un DATABASE_URL che punti a un Postgres reale
raggiungibile — NON puntarlo mai al database di produzione, questo
script scrive e poi ripulisce dati con guild_id >= 900000001.

    export YOKAI_BOT_TOKEN=test YOKAI_CREATOR_TOKEN=test
    export MUSIC_TOKEN_1=test MUSIC_TOKEN_2=test MUSIC_TOKEN_3=test MUSIC_TOKEN_4=test MUSIC_TOKEN_5=test
    export NSFW_TOKEN=test OWNER_ID=123 MAIN_GUILD_ID=456 ENVIRONMENT=development
    export DATABASE_URL=postgresql://utente:password@host:5432/nome_db
    python3 scripts/load_simulation.py --guilds 100 --messages-per-guild 1000

Per imporre un vero tetto di memoria (cgroup v1, richiede root):

    mkdir -p /sys/fs/cgroup/memory/iyokai_sim
    echo $((3*1024*1024*1024)) > /sys/fs/cgroup/memory/iyokai_sim/memory.limit_in_bytes
    python3 scripts/load_simulation.py --guilds 100 --messages-per-guild 1000 &
    echo $! > /sys/fs/cgroup/memory/iyokai_sim/cgroup.procs
    wait
    rmdir /sys/fs/cgroup/memory/iyokai_sim

## Cosa misura, con psutil (non a stima)
- RSS del processo prima/durante/dopo il carico
- Tempo di CPU consumato (user+system)
- Throughput (eventi/secondo)

## Limiti onesti, da tenere presente leggendo i risultati
- Il numero di CPU e la RAM disponibili dipendono da DOVE gira lo
  script: i numeri assoluti (RSS in MB, msg/s) valgono per QUELLA
  macchina, non sono portabili 1:1 su un'altra — quello che è
  portabile è l'ANDAMENTO (la RSS si stabilizza o cresce senza
  fine? il throughput cala nel tempo o resta costante?).
- Architetture diverse (x86 vs ARM Ampere, per esempio) non hanno lo
  stesso rapporto tempo-CPU/lavoro-svolto — un confronto tra macchine
  diverse va preso come ordine di grandezza, non come previsione
  esatta.
- Un solo processo, nessuna concorrenza reale simulata: eventuali
  colli di bottiglia di lock/contesa sul pool DB sotto vero carico
  concorrente (più richieste Discord in parallelo) non emergono qui.
- Non è un bot connesso a Discord: niente rate limit reali dell'API
  Discord, niente latenza di rete verso i server Discord — solo il
  costo del codice Python + le query verso Postgres.
"""

from __future__ import annotations

import asyncio
import gc
import os
import sys
import time
from datetime import datetime, timezone

import discord
import psutil

# Rende lo script eseguibile da qualunque cartella, indipendentemente
# da dove il repository è clonato — niente path hardcoded.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import Database  # noqa: E402


# ======================================================================
# Oggetti Discord finti — minimi ma reali per gli isinstance che il
# codice controlla davvero (stesso trucco già verificato nei test:
# ereditare da discord.TextChannel senza chiamarne il costruttore).
# ======================================================================
class _FakeTextChannel(discord.TextChannel):
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id
        self._sent = 0

    async def send(self, *args, **kwargs) -> None:
        self._sent += 1


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class _FakeAuthor:
    bot = False

    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.mention = f"<@{user_id}>"


class _FakeMessage:
    def __init__(self, guild: _FakeGuild, channel: _FakeTextChannel, author: _FakeAuthor) -> None:
        self.guild = guild
        self.channel = channel
        self.author = author
        self.id = int(time.time_ns())
        self.created_at = datetime.now(timezone.utc)


async def run_simulation(
    num_guilds: int, messages_per_guild: int, sample_every: int = 500
) -> None:
    process = psutil.Process(os.getpid())
    database = Database()
    await database.connect()

    try:
        await database.run_migrations()

        # Import DOPO connect(): i cog leggono core.database.db come
        # singleton globale, dobbiamo puntarlo al DB di questa sessione
        # prima di istanziare i cog — stesso schema usato nei test.
        import core.database as database_module
        database_module.db._pool = database._pool

        from cogs.leveling.leveling import LevelingCog, MODULE_LEVELING
        from cogs.security.spam_trap import SpamTrapCog, MODULE_SPAM_TRAP

        guild_ids = list(range(900_000_001, 900_000_001 + num_guilds))

        print(f"Setup: {num_guilds} server simulati, moduli attivati...")
        for gid in guild_ids:
            await database.set_module_active_for_guild(gid, MODULE_LEVELING, True)
            await database.set_module_active_for_guild(gid, MODULE_SPAM_TRAP, True)

        leveling_cog = LevelingCog(bot=None)
        spam_trap_cog = SpamTrapCog(bot=None)

        gc.collect()
        rss_start = process.memory_info().rss
        cpu_start = process.cpu_times()
        wall_start = time.monotonic()

        totale_eventi = 0
        campioni_rss = []

        for gid in guild_ids:
            guild = _FakeGuild(gid)
            channel = _FakeTextChannel(channel_id=gid * 1000 + 1)
            for i in range(messages_per_guild):
                author = _FakeAuthor(user_id=(i % 50) + 1)  # 50 utenti distinti per server, realistico
                message = _FakeMessage(guild, channel, author)

                await leveling_cog.on_message(message)
                await spam_trap_cog.on_message(message)

                totale_eventi += 1
                if totale_eventi % sample_every == 0:
                    campioni_rss.append((totale_eventi, process.memory_info().rss))

        wall_elapsed = time.monotonic() - wall_start
        cpu_end = process.cpu_times()
        gc.collect()
        rss_end = process.memory_info().rss

        cpu_used = (cpu_end.user - cpu_start.user) + (cpu_end.system - cpu_start.system)

        print("\n=== RISULTATI ===")
        print(f"Eventi totali simulati (on_message x2 cog): {totale_eventi * 2}")
        print(f"Tempo reale (wall clock):    {wall_elapsed:.2f}s")
        print(f"Tempo CPU consumato:         {cpu_used:.2f}s")
        print(f"Throughput:                  {totale_eventi / wall_elapsed:.1f} messaggi/s (1 core)")
        print(f"RSS iniziale:                {rss_start / 1024 / 1024:.1f} MB")
        print(f"RSS finale:                  {rss_end / 1024 / 1024:.1f} MB")
        print(f"Crescita RSS:                {(rss_end - rss_start) / 1024 / 1024:.1f} MB")
        print("\nAndamento RSS nel tempo (evento -> MB):")
        for evento, rss in campioni_rss:
            print(f"  {evento:>6}  ->  {rss / 1024 / 1024:.1f} MB")

        pool = database.pool
        print(f"\nPool DB: size={pool.get_size()} idle={pool.get_idle_size()} "
              f"min={pool.get_min_size()} max={pool.get_max_size()}")

        # Pulizia dei dati di simulazione.
        await database.pool.execute(
            "DELETE FROM guild_config WHERE guild_id >= 900000001 AND guild_id < 900001000"
        )
        await database.pool.execute(
            "DELETE FROM spam_trap_message_index WHERE guild_id >= 900000001 AND guild_id < 900001000"
        )
        await database.pool.execute(
            "DELETE FROM leveling_totals WHERE guild_id >= 900000001 AND guild_id < 900001000"
        )
        await database.pool.execute(
            "DELETE FROM leveling_activity WHERE guild_id >= 900000001 AND guild_id < 900001000"
        )
    finally:
        await database.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--guilds", type=int, default=50)
    parser.add_argument("--messages-per-guild", type=int, default=200)
    args = parser.parse_args()

    asyncio.run(run_simulation(args.guilds, args.messages_per_guild))
