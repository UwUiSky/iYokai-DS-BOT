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


@dataclass(frozen=True)
class Config:
    """
    Contenitore immutabile (frozen=True) di tutta la configurazione.
    Immutabile apposta: nessun cog dovrebbe MAI modificare questi
    valori a runtime — se serve un valore che cambia, appartiene al
    database (guild_config), non a questa classe.
    """

    # --- Discord: token -------------------------------------------
    YOKAI_BOT_TOKEN: str
    YOKAI_CREATOR_TOKEN: str
    MUSIC_TOKENS: list[str]  # le 5 istanze music, in ordine
    NSFW_TOKEN: str

    # --- Discord: ID di controllo -----------------------------------
    OWNER_ID: int
    MAIN_GUILD_ID: int

    # --- Database -----------------------------------------------------
    DATABASE_URL: str
    DB_POOL_MIN: int
    DB_POOL_MAX: int

    # --- Ambiente ----------------------------------------------------
    ENVIRONMENT: str
    LOG_LEVEL: str

    # --- Lavalink ------------------------------------------------------
    LAVALINK_HOST: str
    LAVALINK_PORT: int
    LAVALINK_PASSWORD: str

    # --- Memory Guard --------------------------------------------------
    # Soglia oltre la quale il Memory Guard forza una garbage
    # collection e, se il consumo resta alto, avvisa il proprietario
    # in DM (con cooldown — vedi core/memory_guard_logic.py). Ha un
    # default (opzionale), quindi va DOPO tutti i campi obbligatori
    # della dataclass — un default seguito da un campo senza default
    # fa fallire la definizione della classe stessa (regola di
    # dataclass, non specifica di questo progetto).
    MEMORY_ALERT_THRESHOLD_MB: int = field(default=512)

    # --- Web panel (opzionali finché quel modulo non è attivo) -----------
    OAUTH2_CLIENT_ID: str = field(default="")
    OAUTH2_CLIENT_SECRET: str = field(default="")
    OAUTH2_REDIRECT_URI: str = field(default="")
    WEB_PANEL_SECRET_KEY: str = field(default="")

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

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
        ENVIRONMENT=_optional("ENVIRONMENT", "development"),
        LOG_LEVEL=_optional("LOG_LEVEL", "INFO"),
        LAVALINK_HOST=_optional("LAVALINK_HOST", "127.0.0.1"),
        LAVALINK_PORT=_optional_int("LAVALINK_PORT", 2333),
        LAVALINK_PASSWORD=_optional("LAVALINK_PASSWORD", ""),
        MEMORY_ALERT_THRESHOLD_MB=_optional_int("MEMORY_ALERT_THRESHOLD_MB", 512),
        OAUTH2_CLIENT_ID=_optional("OAUTH2_CLIENT_ID"),
        OAUTH2_CLIENT_SECRET=_optional("OAUTH2_CLIENT_SECRET"),
        OAUTH2_REDIRECT_URI=_optional("OAUTH2_REDIRECT_URI"),
        WEB_PANEL_SECRET_KEY=_optional("WEB_PANEL_SECRET_KEY"),
    )


# Istanza unica, condivisa da tutto il progetto.
# Import "from core.config import config" e usala direttamente.
config = _load_config()
