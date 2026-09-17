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
from datetime import datetime, timezone

import discord
from discord.ext import commands

from core.config import config
from core.database import db
from core.cog_manager import load_all_cogs
from core.scheduler import scheduler
from core.memory_guard import memory_guard
from core.premium import handle_app_command_error
from core.error_handler_logic import should_alert_owner


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


# Il nome della classe usa la "i" minuscola di proposito (branding
# "iYokai", stesso stile di "iPhone"): è una deviazione intenzionale
# dalla convenzione PEP8 (le classi normalmente iniziano maiuscole),
# non un refuso — non "correggerla" in futuro.
class iYokaiBot(commands.AutoShardedBot):
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

        # Error handler globale per i comandi slash: gestisce in
        # particolare gli errori sollevati da @requires_module
        # (core/premium.py), rispondendo con un messaggio coerente
        # invece di lasciare che l'eccezione sparisca in silenzio.
        # Registrato qui nel costruttore, non in setup_hook, perché
        # non dipende dal caricamento dei cog.
        self.tree.error(handle_app_command_error)

        # Cooldown per gli alert DM di on_error, UNO per ogni
        # event_method distinto (es. "on_message", "on_member_join")
        # — così un errore ripetuto in un evento non silenzia gli
        # alert per un errore diverso in un altro. Dizionario semplice,
        # non BoundedCache: il numero di event_method possibili è
        # fisso e piccolo (poche decine al massimo), non cresce con
        # server/utenti.
        self._last_error_alert_at: dict[str, datetime] = {}

    async def setup_hook(self) -> None:
        """
        Chiamato automaticamente da discord.py una volta sola,
        dopo il login ma PRIMA che il bot inizi a ricevere eventi.
        È il posto corretto per caricare i cog e sincronizzare gli
        slash command.
        """
        await load_all_cogs(self)

        # Avvia il loop dello scheduler (tempban, unmute automatico,
        # ecc.) SOLO dopo che i cog hanno avuto modo di registrare i
        # propri handler nel loro setup(). Se lo start() avvenisse
        # prima, il primo giro del loop (che parte comunque solo
        # dopo wait_until_ready) troverebbe comunque gli handler già
        # registrati — l'ordine qui è per chiarezza, non per un bug
        # reale da evitare.
        scheduler.start(self)

        # Memory Guard: monitoraggio RAM, GC forzato, alert DM,
        # pulizia VoiceClient inattivi. Stesso pattern dello
        # scheduler — un servizio bot-wide, non legato a un cog.
        memory_guard.start(self)

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

    async def on_error(self, event_method: str, /, *args, **kwargs) -> None:
        """
        Handler globale per le eccezioni non catturate nei LISTENER
        di eventi (on_message, on_member_join, ecc. — diverso
        dall'error handler dei comandi slash, già gestito da
        handle_app_command_error). discord.py 2.x logga già di
        default tramite il proprio logger interno (non solo su
        stderr come nelle versioni precedenti) — il processo NON
        crasha già oggi. Quello che mancava: passare dal logger di
        QUESTO progetto (stesso formato/gestione delle altre righe di
        log) e avvisare l'owner in DM, con un cooldown per non
        spammarlo se lo stesso evento fallisce ripetutamente in poco
        tempo (es. durante un raid, on_message potrebbe fallire
        decine di volte al minuto).

        logger.exception() va chiamato da QUI (non passando l'errore
        come parametro) perché discord.py chiama on_error dall'interno
        del blocco except che ha catturato l'eccezione originale:
        sys.exc_info() resta valido attraverso la chiamata, esattamente
        come fa l'implementazione di default della libreria stessa.
        """
        logger.exception("Errore non gestito nell'evento '%s'", event_method)

        now = datetime.now(timezone.utc)
        last_alert = self._last_error_alert_at.get(event_method)
        if not should_alert_owner(last_alert, now):
            return

        self._last_error_alert_at[event_method] = now
        try:
            owner = await self.fetch_user(config.OWNER_ID)
            await owner.send(
                f"⚠️ Unhandled error in event `{event_method}`. "
                f"Check the server logs for the full traceback."
            )
        except discord.HTTPException:
            logger.warning("Impossibile avvisare l'owner in DM dell'errore non gestito.")

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

    bot = iYokaiBot()

    try:
        await bot.start(config.YOKAI_BOT_TOKEN)
    finally:
        # Se bot.start() termina (crash o spegnimento pulito),
        # chiudiamo comunque il pool in modo ordinato.
        await db.close()
        logger.info("Database disconnesso. Arresto completato.")


if __name__ == "__main__":
    asyncio.run(main())
