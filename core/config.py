"""
core/config.py
================
Punto UNICO da cui tutto il resto del bot legge la configurazione.

Perché questo file esiste
--------------------------
Invece di sparpagliare `os.getenv("QUALCOSA")` in giro per tutti i cog,
ogni valore passa da qui. Vantaggi concreti:

1. Se manca una variabile obbligatoria, il bot si rifiuta di PARTIRE,
   con un messaggio che dice esattamente quale variabile manca —
   invece di crashare in modo criptico dopo 20 minuti di uptime
   quando finalmente qualcuno prova a usare quella feature.
2. Se in futuro cambi il nome di una variabile d'ambiente, tocchi
   un solo file, non 40 cog diversi.
3. I tipi sono già convertiti (int, bool, ecc.): il resto del codice
   non deve mai fare `int(os.getenv(...))` in giro.

Come si usa altrove nel progetto
----------------------------------
    from core.config import config

    bot_token = config.YOKAI_BOT_TOKEN
    if config.is_production:
        ...
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Carica il file .env nella cartella del progetto.
# Se .env non esiste, load_dotenv non fa nulla di male: semplicemente
# le variabili non vengono trovate e la validazione qui sotto le segnala.
load_dotenv()


def _require(name: str) -> str:
    """
    Legge una variabile d'ambiente OBBLIGATORIA.
    Se manca o è vuota, interrompe l'avvio del bot con un messaggio
    chiaro invece di lasciare che il valore mancante causi un errore
    più avanti, magari dentro un comando usato da un utente.
    """
    value = os.getenv(name, "").strip()
    if not value:
        print(
            f"\n[CONFIG] ERRORE: la variabile d'ambiente '{name}' è "
            f"obbligatoria e non è impostata (o è vuota).\n"
            f"Controlla il tuo file .env — puoi partire da .env.example "
            f"come modello.\n",
            file=sys.stderr,
        )
        sys.exit(1)
    return value


def _optional(name: str, default: str = "") -> str:
    """Legge una variabile d'ambiente opzionale, con un default."""
    return os.getenv(name, default).strip()


def _optional_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(
            f"[CONFIG] ERRORE: '{name}' deve essere un numero intero, "
            f"trovato: '{raw}'",
            file=sys.stderr,
        )
        sys.exit(1)


def _optional_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    print(
        f"[CONFIG] ERRORE: '{name}' deve essere true/false (o 1/0, yes/no, "
        f"on/off), trovato: '{raw}'",
        file=sys.stderr,
    )
    sys.exit(1)


AMBIENTI_AMMESSI = ("development", "production")


def _require_environment() -> str:
    """
    ENVIRONMENT decide i default di ENABLE_EVAL e PREMIUM_ALPHA_UNLOCK_ALL
    (spenti solo in produzione). Un valore sconosciuto ("prod", "live")
    o assente li accenderebbe in silenzio: meglio non partire.
    Maiuscole e spazi intorno non contano.
    """
    valore = os.getenv("ENVIRONMENT", "").strip().lower()
    if valore not in AMBIENTI_AMMESSI:
        print(
            f"\n[CONFIG] ERRORE: la variabile d'ambiente 'ENVIRONMENT' deve valere "
            f"{' oppure '.join(AMBIENTI_AMMESSI)}, trovato: '{valore}'.\n"
            f"Impostala nel file .env (vedi .env.example).\n",
            file=sys.stderr,
        )
        sys.exit(1)
    return valore


@dataclass(frozen=True)
class Config:
    """
    Contenitore immutabile (frozen=True) di tutta la configurazione.
    Immutabile apposta: nessun cog dovrebbe MAI modificare questi
    valori a runtime — se serve un valore che cambia, appartiene al
    database (guild_config), non a questa classe.
    """

    # --- Discord: token -------------------------------------------
    # SEC-16: repr=False su tutti i campi segreti di questa classe —
    # un `logger.info(config)` o un `print(config)` di debug lasciato
    # per sbaglio non deve stampare token/password/chiavi in chiaro
    # nei log. I valori restano normalmente leggibili accedendo al
    # campo per nome (config.YOKAI_BOT_TOKEN), cambia solo cosa mostra
    # repr()/str() dell'intero oggetto.
    YOKAI_BOT_TOKEN: str = field(repr=False)
    YOKAI_CREATOR_TOKEN: str = field(repr=False)
    MUSIC_TOKENS: list[str] = field(repr=False)  # le 5 istanze music, in ordine
    NSFW_TOKEN: str = field(repr=False)

    # --- Discord: ID di controllo -----------------------------------
    OWNER_ID: int
    MAIN_GUILD_ID: int

    # --- Database -----------------------------------------------------
    # repr=False: la password è dentro l'URL (postgresql://utente:PASSWORD@host/db).
    DATABASE_URL: str = field(repr=False)
    DB_POOL_MIN: int
    DB_POOL_MAX: int

    # --- Ambiente ----------------------------------------------------
    ENVIRONMENT: str
    LOG_LEVEL: str

    # --- Lavalink ------------------------------------------------------
    LAVALINK_HOST: str
    LAVALINK_PORT: int
    LAVALINK_PASSWORD: str = field(repr=False)
    # Nodi pubblici multipli in fallback (SPEC.md §9), invece di
    # self-hostare Lavalink sulla stessa VM del bot (peserebbe
    # centinaia di MB extra — vedi PROGRESS.md, decisione presa con
    # l'utente). Formato: "uri1|password1,uri2|password2,...", vuoto
    # di default — se vuoto, il cog Music usa i tre campi sopra
    # (LAVALINK_HOST/PORT/PASSWORD, comportamento originale invariato
    # per chi preferisce comunque self-hostare un singolo nodo).
    LAVALINK_NODES: str = field(default="", repr=False)

    # Twitch (SPEC.md §10.1/10.2) — opzionali: vuoti finché l'utente
    # non registra un'app su dev.twitch.tv. Il watcher (core/twitch_
    # watcher.py) resta semplicemente inattivo finché non sono
    # compilati, non fa fallire l'avvio del bot.
    TWITCH_CLIENT_ID: str = field(default="")
    TWITCH_CLIENT_SECRET: str = field(default="", repr=False)

    # YouTube Data API (SPEC.md §10.4) — opzionale, stesso principio
    # di TWITCH_CLIENT_ID/SECRET sopra: vuota finché l'utente non crea
    # una API key sulla Google Cloud Console. Il watcher (core/
    # youtube_watcher.py) resta inattivo finché non è compilata, non
    # fa fallire l'avvio del bot. A differenza del feed RSS già usato
    # per "nuovo video" (§10.3, nessuna chiave richiesta), rilevare lo
    # stato LIVE richiede l'endpoint search.list della Data API, che
    # consuma quota — per questo è un metodo di sblocco separato e
    # opzionale, non abilitato di default.
    YOUTUBE_API_KEY: str = field(default="", repr=False)

    # Pixabay (SPEC.md §16.9, ricerca immagini SFW) — opzionale, vuota
    # finché l'utente non crea una API key gratuita su pixabay.com/
    # api/docs/. `/fun search-image` (cogs/fun/entertainment.py)
    # risponde con un messaggio che spiega come attivarla finché è
    # vuota, invece di fallire in modo criptico. Pixabay applica il
    # proprio filtro SFW lato server (`safesearch=true`, impostato
    # sempre da core/image_search_fetcher.py) — non è compito di
    # questo bot rifiltrare i risultati.
    PIXABAY_API_KEY: str = field(default="", repr=False)

    # Radio condivisa del bot principale (SPEC.md §9.11) — cartella
    # locale per gli inediti dell'utente, letta SOLO dal nodo
    # Lavalink locale/self-hostato (i nodi pubblici non hanno accesso
    # al filesystem di questa macchina — verificato prima di
    # progettare questa feature). Vuota di default: gli inediti
    # restano semplicemente non disponibili finché non è impostata.
    MAIN_RADIO_LOCAL_FOLDER: str = field(default="")

    # --- Memory Guard --------------------------------------------------
    # Soglia oltre la quale il Memory Guard forza una garbage
    # collection e, se il consumo resta alto, avvisa il proprietario
    # in DM (con cooldown — vedi core/memory_guard_logic.py). Ha un
    # default (opzionale), quindi va DOPO tutti i campi obbligatori
    # della dataclass — un default seguito da un campo senza default
    # fa fallire la definizione della classe stessa (regola di
    # dataclass, non specifica di questo progetto).
    MEMORY_ALERT_THRESHOLD_MB: int = field(default=512)

    # --- Server web (SEC-14) ---------------------------------------------
    # Indirizzo su cui ascoltano TUTTI i piccoli server web del progetto
    # (callback OAuth2 del restore, webhook custom in ricezione — sotto).
    # Default "127.0.0.1": solo localhost, non tutte le interfacce di
    # rete. Chi vuole esporli davvero mette un reverse proxy con HTTPS
    # davanti e lo fa puntare a questo indirizzo/porta, invece di
    # cambiare questo valore in "0.0.0.0" (che li espone in HTTP semplice
    # su tutta la rete).
    WEB_BIND_HOST: str = field(default="127.0.0.1")

    # --- Web panel (opzionali finché quel modulo non è attivo) -----------
    OAUTH2_CLIENT_ID: str = field(default="")
    OAUTH2_CLIENT_SECRET: str = field(default="", repr=False)
    OAUTH2_REDIRECT_URI: str = field(default="")
    WEB_PANEL_SECRET_KEY: str = field(default="", repr=False)

    # --- Restore utenti via OAuth2 (SPEC.md §11.11) ---------------------
    # Chiave di cifratura (AES-256-GCM) dei token OAuth altrui salvati
    # per il restore massivo — MAI in chiaro nel DB (core/oauth_crypto.
    # py). Va generata una volta con Fernet.generate_key() o 32 byte
    # casuali in base64 e non deve MAI cambiare senza prima decifrare
    # e ricifrare tutti i token esistenti (altrimenti diventano
    # illeggibili per sempre). Vuota finché il modulo non è configurato
    # — in quel caso il restore via OAuth resta disattivato (nessun
    # crash, il chiamante lo controlla esplicitamente).
    OAUTH_ENCRYPTION_KEY: str = field(default="", repr=False)
    # Porta su cui core/restore_web_server.py ascolta le callback
    # OAuth2 di Discord dopo che un utente autorizza il restore
    # (indirizzo: WEB_BIND_HOST, condiviso con il server webhook sotto).
    RESTORE_WEB_PORT: int = field(default=8420)

    # --- Webhook custom in ricezione (SPEC.md §10.8) --------------------
    # Porta su cui core/custom_webhook_server.py ascolta i webhook PUSH
    # di servizi terzi — a differenza del server restore sopra, questo
    # parte solo se esiste già almeno un webhook configurato (SEC-14):
    # niente motivo di tenere una porta in ascolto per una funzione mai
    # usata. Porta di default diversa da RESTORE_WEB_PORT apposta, così
    # i due server possono girare insieme senza scontrarsi.
    ALERTS_WEBHOOK_PORT: int = field(default=8421)
    # URL pubblico base (dominio/reverse proxy dell'utente, es.
    # "https://webhooks.miobot.tld") usato per costruire il link da dare
    # a servizi terzi — core.custom_webhook_logic.build_webhook_url.
    # Vuota finché l'utente non configura un dominio/reverse proxy
    # davanti a questa porta: il comando di creazione webhook lo dice
    # esplicitamente invece di mostrare un URL http://0.0.0.0 inutile.
    ALERTS_WEBHOOK_PUBLIC_BASE_URL: str = field(default="")

    # --- Premium (SPEC.md §3) ---------------------------------------
    # Override temporaneo di fase ALPHA: quando True, `core.premium.
    # guild_has_premium_access` restituisce sempre True per QUALUNQUE
    # server e modulo, a prescindere da whitelist/boost/abbonamento —
    # richiesto esplicitamente dall'utente ("tutte le feature premium
    # sbloccate per tutti" durante l'alpha). #41: default calcolato da
    # ENVIRONMENT in _load_config() (non qui: un default statico non
    # potrebbe dipendere da un'altra variabile, stesso motivo di
    # ENABLE_EVAL/SEC-13) — False in produzione (l'alpha va accesa
    # esplicitamente lì, non lasciata accesa per dimenticanza), True
    # altrove (comodo in sviluppo/test). Sempre sovrascrivibile con
    # PREMIUM_ALPHA_UNLOCK_ALL=true/false in .env; se resta true
    # all'avvio, main.py logga un WARNING (non solo un INFO).
    PREMIUM_ALPHA_UNLOCK_ALL: bool = field(default=True)

    # --- Sicurezza (SEC-13, decisione owner D7) ----------------------
    # /owner eval, /owner shell e /owner cog-load eseguono codice
    # arbitrario sulla macchina che ospita il bot — chi compromette
    # l'account Discord dell'owner compromette anche il server.
    # Spento di default in produzione (default calcolato da
    # ENVIRONMENT in _load_config, non qui: un default statico non
    # potrebbe dipendere da un'altra variabile), acceso di default
    # altrove (comodo in sviluppo/test). L'owner può comunque forzare
    # il valore con ENABLE_EVAL=true/false in .env.
    ENABLE_EVAL: bool = field(default=True)

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        return not self.is_production


def _load_config() -> Config:
    """
    Costruisce la configurazione leggendo e validando l'ambiente.
    Viene chiamata UNA volta sola, all'importazione del modulo
    (vedi `config = _load_config()` in fondo al file).
    """

    # I 5 token music sono tutti obbligatori: se ne manca anche solo
    # uno, meglio saperlo subito che scoprirlo quando la quinta
    # istanza music non parte in un momento a caso.
    music_tokens = [
        _require(f"MUSIC_TOKEN_{i}") for i in range(1, 6)
    ]

    # Letto PRIMA del resto: ENABLE_EVAL (SEC-13/D7) e
    # PREMIUM_ALPHA_UNLOCK_ALL (#41) ne calcolano il default — entrambi
    # spenti di default in produzione, accesi in sviluppo.
    environment = _require_environment()
    in_sviluppo = environment == "development"

    return Config(
        YOKAI_BOT_TOKEN=_require("YOKAI_BOT_TOKEN"),
        YOKAI_CREATOR_TOKEN=_require("YOKAI_CREATOR_TOKEN"),
        MUSIC_TOKENS=music_tokens,
        NSFW_TOKEN=_require("NSFW_TOKEN"),
        OWNER_ID=int(_require("OWNER_ID")),
        MAIN_GUILD_ID=int(_require("MAIN_GUILD_ID")),
        DATABASE_URL=_require("DATABASE_URL"),
        DB_POOL_MIN=_optional_int("DB_POOL_MIN", 5),
        DB_POOL_MAX=_optional_int("DB_POOL_MAX", 10),
        ENVIRONMENT=environment,
        LOG_LEVEL=_optional("LOG_LEVEL", "INFO"),
        LAVALINK_HOST=_optional("LAVALINK_HOST", "127.0.0.1"),
        LAVALINK_PORT=_optional_int("LAVALINK_PORT", 2333),
        LAVALINK_PASSWORD=_optional("LAVALINK_PASSWORD", ""),
        LAVALINK_NODES=_optional("LAVALINK_NODES", ""),
        TWITCH_CLIENT_ID=_optional("TWITCH_CLIENT_ID", ""),
        TWITCH_CLIENT_SECRET=_optional("TWITCH_CLIENT_SECRET", ""),
        YOUTUBE_API_KEY=_optional("YOUTUBE_API_KEY", ""),
        PIXABAY_API_KEY=_optional("PIXABAY_API_KEY", ""),
        MAIN_RADIO_LOCAL_FOLDER=_optional("MAIN_RADIO_LOCAL_FOLDER", ""),
        MEMORY_ALERT_THRESHOLD_MB=_optional_int("MEMORY_ALERT_THRESHOLD_MB", 512),
        WEB_BIND_HOST=_optional("WEB_BIND_HOST", "127.0.0.1"),
        OAUTH2_CLIENT_ID=_optional("OAUTH2_CLIENT_ID"),
        OAUTH2_CLIENT_SECRET=_optional("OAUTH2_CLIENT_SECRET"),
        OAUTH2_REDIRECT_URI=_optional("OAUTH2_REDIRECT_URI"),
        WEB_PANEL_SECRET_KEY=_optional("WEB_PANEL_SECRET_KEY"),
        OAUTH_ENCRYPTION_KEY=_optional("OAUTH_ENCRYPTION_KEY", ""),
        RESTORE_WEB_PORT=_optional_int("RESTORE_WEB_PORT", 8420),
        ALERTS_WEBHOOK_PORT=_optional_int("ALERTS_WEBHOOK_PORT", 8421),
        ALERTS_WEBHOOK_PUBLIC_BASE_URL=_optional("ALERTS_WEBHOOK_PUBLIC_BASE_URL", ""),
        PREMIUM_ALPHA_UNLOCK_ALL=_optional_bool("PREMIUM_ALPHA_UNLOCK_ALL", in_sviluppo),
        ENABLE_EVAL=_optional_bool("ENABLE_EVAL", in_sviluppo),
    )


# Istanza unica, condivisa da tutto il progetto.
# Import "from core.config import config" e usala direttamente.
config = _load_config()
