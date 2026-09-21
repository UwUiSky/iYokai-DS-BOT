"""
main.py
========
Punto di avvio di iYokai Main — include anche le 5 istanze Music
worker (SPEC.md §9.1), avviate come task concorrenti nello STESSO
processo (non 6 processi separati — vedi la nota nel corpo di
main() per il perché). Restano fuori da qui il Creator e l'NSFW,
applicazioni Discord del tutto scollegate dal resto, con il proprio
entry point separato.

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
from logging.handlers import RotatingFileHandler
from pathlib import Path

import discord
from discord.ext import commands

from core.config import config
from core.database import db
from core.cog_manager import load_all_cogs
from core.scheduler import scheduler
from core.memory_guard import memory_guard
from core.event_log_retention import event_log_retention
from core.feed_watcher import feed_watcher
from core.twitch_watcher import twitch_watcher
from core.music_fleet import MusicFleet
from core.music_worker_bot import MusicWorkerBot
from core.blacklist_tree import BlacklistAwareCommandTree
from core.repositories.blacklist_repo import blacklist_repo
from core.premium import handle_app_command_error
from core.error_handler_logic import should_alert_owner
from core.json_log_formatter import JSONFormatter
from core.welcome_logic import choose_welcome_target


def setup_logging() -> None:
    """
    Due destinazioni contemporanee per ogni riga di log, non una in
    sostituzione dell'altra:
    - stdout, formato testuale leggibile — quello che `journalctl`
      cattura se il bot gira sotto systemd, comodo per un controllo
      rapido dal terminale
    - `logs/iyokai.log`, formato JSON strutturato con rotazione
      (`core/json_log_formatter.py`) — interrogabile da strumenti
      (grep su un campo specifico, un futuro dashboard), con la
      dimensione tenuta sotto controllo dalla rotazione invece di
      crescere all'infinito
    """
    level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "iyokai.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB per file
        backupCount=5,               # fino a 5 file precedenti conservati
        encoding="utf-8",
    )
    file_handler.setFormatter(JSONFormatter())

    logging.basicConfig(level=level, handlers=[console_handler, file_handler], force=True)


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
            # CommandTree personalizzata (SPEC.md §17.4/17.5): blocca
            # globalmente le interazioni di utenti/server in
            # blacklist prima che qualunque comando venga eseguito —
            # vedi core/blacklist_tree.py per il perché va passata
            # qui e non assegnata dopo (CommandTree.__init__ solleva
            # se il client ha già un tree associato).
            tree_cls=BlacklistAwareCommandTree,
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

        # Retention del log eventi unificato (BACKLOG.md §3): pulizia
        # una volta al giorno, soglia diversa per server in base allo
        # stato Free/Premium. Stesso pattern di Memory Guard.
        event_log_retention.start(self)

        # Feed watcher (SPEC.md §10.3/10.7/10.8): polling ogni 5
        # minuti dei feed RSS/Atom sottoscritti (YouTube, Reddit,
        # RSS qualsiasi) — stesso pattern di Memory Guard/Retention.
        feed_watcher.start(self)

        # Twitch live/offline (SPEC.md §10.1/10.2): resta inattivo
        # finché TWITCH_CLIENT_ID/SECRET non sono configurati.
        twitch_watcher.start(self)

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
        configurazione, PRIMA che qualsiasi comando venga usato lì,
        e prova a mandare un messaggio di benvenuto con la catena di
        fallback decisa in core/welcome_logic.py: canale di sistema
        → primo canale scrivibile → DM al proprietario.

        Un server in blacklist (SPEC.md §17.5) viene lasciato SUBITO,
        prima di ensure_guild_exists e del messaggio di benvenuto —
        non ha senso configurare o dare il benvenuto a un server che
        il bot deve comunque abbandonare.
        """
        if await blacklist_repo.is_guild_blacklisted(guild.id):
            logger.info(
                "Server %s (ID: %s) è in blacklist — esco immediatamente.",
                guild.name,
                guild.id,
            )
            await guild.leave()
            return

        await db.ensure_guild_exists(guild.id)
        logger.info("Nuovo server: %s (ID: %s)", guild.name, guild.id)
        await self._send_welcome_message(guild)

    async def _send_welcome_message(self, guild: discord.Guild) -> None:
        embed = discord.Embed(
            title="👋 Thanks for adding iYokai!",
            description=(
                "Run `/setup` to choose which modules you want active on "
                "this server. Everything starts disabled until you turn it on."
            ),
            color=discord.Color.blurple(),
        )
        await self._send_embed_with_fallback(guild, embed, contesto="messaggio di benvenuto")

    async def _send_embed_with_fallback(
        self, guild: discord.Guild, embed: discord.Embed, contesto: str = "messaggio"
    ) -> bool:
        """
        Catena di fallback GENERICA (estratta da _send_welcome_message
        quando è servita una seconda volta, per /owner announce —
        SPEC.md §17.7): system_channel → primo canale scrivibile → DM
        al proprietario. `contesto` è solo per i log, non cambia il
        comportamento — permette di distinguere nei log "benvenuto
        fallito" da "annuncio fallito" senza duplicare la logica.

        Restituisce True se l'invio è riuscito con QUALCHE metodo,
        False se tutti e tre hanno fallito — /owner announce lo usa
        per contare quanti server ha effettivamente raggiunto.
        """
        can_send_system = (
            guild.system_channel is not None
            and guild.system_channel.permissions_for(guild.me).send_messages
        )

        # Cerchiamo comunque il primo canale scrivibile anche se il
        # system_channel va bene, così choose_welcome_target riceve
        # entrambe le informazioni indipendentemente da quale delle
        # due verrà usata — la decisione resta nella funzione pura,
        # non sparsa qui con degli if impliciti.
        #
        # ESCLUDIAMO ESPLICITAMENTE guild.system_channel da questa
        # ricerca: se non lo facessimo, e l'invio sul system_channel
        # fallisse più sotto, il fallback "primo canale scrivibile"
        # potrebbe ritrovare ESATTAMENTE LO STESSO CANALE (il
        # system_channel è quasi sempre incluso in guild.text_channels)
        # e ritentarlo inutilmente invece di passare a uno
        # genuinamente diverso — bug reale, trovato scrivendo il test
        # di questo stesso file (non ipotizzato a tavolino).
        first_writable = next(
            (
                channel
                for channel in guild.text_channels
                if channel != guild.system_channel
                and channel.permissions_for(guild.me).send_messages
            ),
            None,
        )

        target = choose_welcome_target(
            can_send_in_system_channel=can_send_system,
            has_any_writable_channel=first_writable is not None,
        )

        if target == "system_channel":
            try:
                await guild.system_channel.send(embed=embed)
                return True
            except discord.HTTPException:
                logger.warning(
                    "Invio del %s fallito sul system_channel del "
                    "server %s nonostante i permessi risultassero ok — "
                    "provo il canale scrivibile.",
                    contesto,
                    guild.id,
                )
                # Non torniamo subito: proviamo comunque il prossimo
                # anello della catena invece di arrenderci qui.
                target = "first_writable_channel" if first_writable else "dm_owner"

        if target == "first_writable_channel" and first_writable is not None:
            try:
                await first_writable.send(embed=embed)
                return True
            except discord.HTTPException:
                logger.warning(
                    "Invio del %s fallito anche sul primo canale "
                    "scrivibile del server %s — provo il DM al proprietario.",
                    contesto,
                    guild.id,
                )

        # Ultima risorsa: DM al proprietario. guild.owner può essere
        # None se non ancora in cache — in quel caso lo recuperiamo
        # esplicitamente prima di arrenderci.
        owner = guild.owner
        if owner is None:
            try:
                owner = await guild.fetch_member(guild.owner_id)
            except discord.HTTPException:
                owner = None

        if owner is not None:
            try:
                await owner.send(embed=embed)
                return True
            except discord.HTTPException:
                pass

        logger.warning(
            "Impossibile inviare il %s nel server %s "
            "con nessuno dei tre metodi (system_channel, canale "
            "scrivibile, DM proprietario).",
            contesto,
            guild.id,
        )
        return False


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

    # Le 5 istanze Music worker (SPEC.md §9.1) girano nello STESSO
    # processo del bot principale, come task asyncio concorrenti —
    # non 6 processi separati. Decisione presa per due motivi: (1)
    # il bot principale deve poter instradare /play verso il worker
    # giusto con una semplice chiamata Python (self.bot.music_fleet),
    # non con una comunicazione tra processi che aggiungerebbe
    # latenza; (2) 6 processi separati moltiplicherebbero 6 volte
    # l'overhead di interprete Python su una VM già misurata con
    # cura (scripts/load_simulation.py). Restano applicazioni Discord
    # DISTINTE (5 token separati, 5 bot visti come entità diverse
    # dagli utenti) — solo il processo che le ospita è condiviso.
    worker_bots = [MusicWorkerBot(worker_index=i) for i in range(1, 6)]
    bot.music_fleet = MusicFleet(worker_bots)

    try:
        await asyncio.gather(
            bot.start(config.YOKAI_BOT_TOKEN),
            *[
                worker.start(token)
                for worker, token in zip(worker_bots, config.MUSIC_TOKENS)
            ],
        )
    finally:
        # Se bot.start() termina (crash o spegnimento pulito),
        # chiudiamo comunque il pool in modo ordinato.
        await db.close()
        logger.info("Database disconnesso. Arresto completato.")


if __name__ == "__main__":
    asyncio.run(main())
