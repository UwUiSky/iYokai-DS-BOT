"""
main.py
========
Punto di avvio di iYokai Main (l'applicazione principale — non i bot
music, non il Creator, non l'NSFW: quelli hanno ciascuno il proprio
entry point separato, in coerenza con la scelta di applicazioni
Discord distinte).

Ordine di avvio, e perché è in questo ordine:
  1. Logging — così anche gli errori dei passi successivi si vedono
  2. Config — già validata all'import di core.config (vedi quel file:
     se manca qualcosa, il processo termina qui, PRIMA di provare
     a connettersi a Discord o al database)
  3. Database — deve essere pronto prima che arrivino eventi Discord
     che lo interrogano (es. on_guild_join chiama ensure_guild_exists)
  4. Cog — caricati dopo che bot e database esistono, perché molti
     cog li usano già nel loro setup()
  5. Connessione a Discord — per ultima, perché tutto il resto deve
     essere pronto PRIMA che arrivino eventi dal gateway
"""

from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from core.config import config
from core.database import db
from core.cog_manager import load_all_cogs


def setup_logging() -> None:
    """
    Log strutturato su stdout. Su Oracle, se il bot gira sotto
    systemd, questi finiscono automaticamente in `journalctl`.
    """
    level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


logger = logging.getLogger("iyokai.main")


class IYokaiBot(commands.AutoShardedBot):
    """
    AutoShardedBot invece di Bot: anche se oggi (pochi server) non
    servono più shard di uno, usare fin da subito la classe
    "sharded" significa che il giorno in cui Discord assegnerà più
    shard (superata la soglia interna, circa 2500 server) il codice
    non cambia — discord.py gestisce lo sharding in modo trasparente.
    Iniziare con la classe "normale" e migrare dopo è molto più
    lavoro che partire già con quella giusta.
    """

    def __init__(self) -> None:
        # Intents: si richiede SOLO quello che serve davvero.
        # members e message_content sono "privileged" e vanno
        # abilitati anche nel Developer Portal, non solo qui.
        intents = discord.Intents.default()
        intents.members = True          # necessario per verify, log join/leave
        intents.message_content = False  # vedi nota sotto

        # NOTA sul message_content: parte disattivato. Verrà acceso
        # SOLO quando un modulo specifico lo richiederà davvero
        # (es. logging dei messaggi cancellati) — non di default,
        # perché è un privileged intent soggetto a review separata
        # in fase di verifica del bot, e più cose lo richiedono
        # inutilmente, più complicata è la review.

        super().__init__(
            command_prefix=commands.when_mentioned,  # niente prefisso testuale
            intents=intents,
        )

    async def setup_hook(self) -> None:
        """
        Chiamato automaticamente da discord.py una volta sola,
        dopo il login ma PRIMA che il bot inizi a ricevere eventi.
        È il posto corretto per caricare i cog e sincronizzare gli
        slash command.
        """
        await load_all_cogs(self)

        # Sincronizza gli slash command con Discord. In sviluppo,
        # sincronizzare su una singola guild è istantaneo; la sync
        # globale può richiedere fino a un'ora per propagarsi.
        if config.is_development and config.MAIN_GUILD_ID:
            guild = discord.Object(id=config.MAIN_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info("Slash command sincronizzati sulla guild di sviluppo.")
        else:
            await self.tree.sync()
            logger.info("Slash command sincronizzati globalmente.")

    async def on_ready(self) -> None:
        logger.info(
            "iYokai Main online come %s (ID: %s) — %d server, %d shard",
            self.user,
            self.user.id if self.user else "?",
            len(self.guilds),
            self.shard_count or 1,
        )

    async def on_guild_join(self, guild: discord.Guild) -> None:
        """
        Assicura che ogni nuovo server abbia una riga di
        configurazione, PRIMA che qualsiasi comando venga usato lì.
        Il vero pannello di setup interattivo arriverà in un cog
        dedicato (cogs/utility/setup.py) — qui c'è solo la garanzia
        che il record esista.
        """
        await db.ensure_guild_exists(guild.id)
        logger.info("Nuovo server: %s (ID: %s)", guild.name, guild.id)


async def main() -> None:
    setup_logging()
    logger.info("Avvio iYokai Main in modalità: %s", config.ENVIRONMENT)

    # Il database va connesso PRIMA del bot, perché setup_hook()
    # (chiamato durante bot.start()) già presuppone che db.pool
    # esista.
    await db.connect()
    await db.run_migrations()
    logger.info("Database connesso e migrazioni applicate.")

    bot = IYokaiBot()

    try:
        await bot.start(config.YOKAI_BOT_TOKEN)
    finally:
        # Se bot.start() termina (crash o spegnimento pulito),
        # chiudiamo comunque il pool in modo ordinato.
        await db.close()
        logger.info("Database disconnesso. Arresto completato.")


if __name__ == "__main__":
    asyncio.run(main())
