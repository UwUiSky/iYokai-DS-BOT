"""
core/music_logic.py
======================
Logica pura di Music (SPEC.md §9). Nessuna dipendenza da wavelink o
discord.py qui dentro — solo formattazione e parsing di stringhe.

Decisione presa con l'utente su come collegarsi a Lavalink: nodi
PUBBLICI gratuiti mantenuti dalla community, con più nodi configurati
in fallback, invece di self-hostare un processo Java sulla stessa VM
del bot (che peserebbe centinaia di MB extra su una macchina già
misurata con cura — vedi scripts/load_simulation.py). wavelink.Pool
gestisce da solo la scelta del nodo meno carico e il fallback tra
quelli configurati; qui serve solo interpretare la stringa di
configurazione (LAVALINK_NODES in core/config.py) in oggetti Python.
"""

# Fase F2 (issue #64, D10): nodi per bot, versione minima di Lavalink,
# scelta esplicita del nodo, percorsi locali, titoli tagliati.

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

# Lavalink 4.2.0 o successivo: cifratura vocale DAVE, obbligatoria da
# 01/03/2026 (D10, LIM-54).
MIN_LAVALINK_VERSION = (4, 2, 0)

# Tentativi di collegamento di ogni nodo prima di rinunciare (LIM-41):
# un nodo morto non deve riprovare per sempre né tenere fermi gli altri.
NODE_CONNECT_RETRIES = 3

# Base dell'identificatore del nodo locale/self-hostato. Ogni bot ha il
# suo nodo con identificatore "<base>@<chiave del bot>" (D10).
LOCAL_NODE_BASE = "iyokai-local-node"

EMBED_TITLE_LIMIT = 256  # LIM-21


@dataclass(frozen=True)
class LavalinkNodeConfig:
    uri: str
    password: str



def parse_lavalink_nodes(raw: str) -> list[LavalinkNodeConfig]:
    """
    Formato: "uri1|password1,uri2|password2,...". Un pezzo vuoto o
    senza il separatore "|" (typo dell'utente nel file .env) viene
    ignorato silenziosamente, non fa fallire l'avvio del bot per un
    nodo scritto male mentre altri nodi validi sono configurati
    correttamente accanto.
    """
    if not raw.strip():
        return []

    nodi = []
    for pezzo in raw.split(","):
        pezzo = pezzo.strip()
        if not pezzo or "|" not in pezzo:
            continue
        uri, _, password = pezzo.partition("|")
        uri = uri.strip()
        password = password.strip()
        if not uri:
            continue
        nodi.append(LavalinkNodeConfig(uri=uri, password=password))
    return nodi


def format_duration(milliseconds: int) -> str:
    """
    Millisecondi -> "m:ss", o "h:mm:ss" se supera un'ora (formato
    classico di ogni player musicale, non un'invenzione di questo
    progetto).
    """
    secondi_totali = max(0, milliseconds) // 1000
    ore, resto = divmod(secondi_totali, 3600)
    minuti, secondi = divmod(resto, 60)
    if ore > 0:
        return f"{ore}:{minuti:02d}:{secondi:02d}"
    return f"{minuti}:{secondi:02d}"


def build_queue_display(
    current_title: str | None,
    queued_titles: list[str],
    max_shown: int = 10,
) -> str:
    """
    Testo pronto per un embed — non un oggetto discord.Embed qui
    dentro (questa funzione resta pura, senza discord.py), il
    chiamante lo mette dentro un embed come preferisce.
    """
    righe = []
    if current_title is not None:
        righe.append(f"▶️ **In riproduzione:** {current_title}")
    else:
        righe.append("Nessuna traccia in riproduzione.")

    if not queued_titles:
        righe.append("\nLa coda è vuota.")
        return "\n".join(righe)

    righe.append("\n**In coda:**")
    for indice, titolo in enumerate(queued_titles[:max_shown], start=1):
        righe.append(f"{indice}. {titolo}")

    rimanenti = len(queued_titles) - max_shown
    if rimanenti > 0:
        righe.append(f"...e altre {rimanenti} tracce.")

    return "\n".join(righe)


MAX_PLAYLIST_TRACKS = 750  # SPEC.md §9.4 — richiesto esplicitamente
# dall'utente: un link a UNA playlist enorme (Spotify e altre
# piattaforme ne permettono di migliaia di brani) non deve poter
# riempire la coda di un server all'infinito in un colpo solo. Non è
# un limite tecnico di wavelink/Lavalink, è una scelta di prodotto.


def truncate_playlist_tracks(tracks, limit: int = MAX_PLAYLIST_TRACKS):
    """
    Restituisce solo le prime `limit` tracce di una playlist (§9.4) —
    non tocca l'ordine, taglia semplicemente in coda. `tracks` può
    essere qualunque sequenza indicizzabile (una lista o un
    wavelink.Playlist, che supporta lo slicing) — nessuna dipendenza
    da wavelink qui, resta logica pura testabile con liste semplici.
    """
    return list(tracks[:limit])


def build_progress_bar(elapsed_ms: int, total_ms: int, bar_length: int = 20) -> str:
    """
    Barra di avanzamento testuale per /music nowplaying (SPEC.md §9.4) —
    un pallino 🔘 posizionato lungo una linea di trattini ▬, in base
    a quanto della traccia (o della playlist, il chiamante decide
    cosa passare come total_ms) è già trascorso.

    `total_ms <= 0` (stream live, Lavalink riporta length=0 quando
    la durata non è nota) restituisce un indicatore fisso invece di
    dividere per zero. `elapsed_ms` viene sempre ristretto a
    [0, total_ms] prima di calcolare la posizione — un piccolo scarto
    di sincronizzazione con Lavalink (o un valore appena oltre la
    fine, un istante prima del cambio traccia) non deve mai far
    sforare la barra a un indice fuori dagli slot disponibili.
    """
    if total_ms <= 0:
        return "🔴 LIVE"

    elapsed_ms = max(0, min(elapsed_ms, total_ms))
    frazione = elapsed_ms / total_ms
    posizione = min(bar_length - 1, int(frazione * bar_length))

    return "▬" * posizione + "🔘" + "▬" * (bar_length - posizione - 1)


def is_spotify_query(query: str) -> bool:
    """
    Vero se `query` punta a Spotify (URL open.spotify.com o URI
    spotify:...) — usato per decidere quando tentare il fallback sul
    nodo locale/self-hostato se i nodi pubblici non risolvono
    (SPEC.md §9.5): Spotify richiede il plugin LavaSrc, non
    verificabile sui nodi pubblici di terzi senza controllarli
    direttamente, quindi solo le query Spotify hanno bisogno di
    questo fallback speciale — YouTube/SoundCloud/URL funzionano già
    su qualunque nodo pubblico.
    """
    query_pulita = query.strip().lower()
    return query_pulita.startswith("spotify:") or "open.spotify.com" in query_pulita


# ----------------------------------------------------------------
# Nodi per bot, versione, scelta (F2, D10)
# ----------------------------------------------------------------
_SEMVER = re.compile(r"^\s*v?(\d+)\.(\d+)(?:\.(\d+))?")


def parse_semver(testo: str | None) -> tuple[int, int, int] | None:
    """'4.2.0', 'v4.1.1-beta' o '4.2' -> (maggiore, minore, patch). None se illeggibile."""
    if not testo:
        return None
    m = _SEMVER.match(str(testo))
    if m is None:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def is_supported_lavalink(versione: str | None) -> bool:
    """Vero se la versione è almeno MIN_LAVALINK_VERSION. Illeggibile = no."""
    v = parse_semver(versione)
    return v is not None and v >= MIN_LAVALINK_VERSION


def node_identifier(base: str, client_key: str) -> str:
    """Identificatore del nodo di UN bot (il Pool ne tiene uno per identificatore)."""
    return f"{base}@{client_key}"


def public_node_base(uri: str) -> str:
    """Base dell'identificatore di un nodo pubblico: 'pub-<host>-<porta>'."""
    parsed = urlparse(uri if "//" in uri else f"//{uri}")
    host = parsed.hostname or uri
    porta = parsed.port
    return f"pub-{host}" + (f"-{porta}" if porta else "")


def is_local_node(identifier: str) -> bool:
    return identifier.startswith(LOCAL_NODE_BASE)


def _stato_connesso(nodo) -> bool:
    stato = getattr(nodo, "status", None)
    return str(getattr(stato, "name", stato)).upper() == "CONNECTED"


def order_nodes(nodi) -> list:
    """
    LIM-42: solo i nodi CONNESSI; i pubblici per primi (meno carichi
    davanti), il locale per ultimo. Il chiamante cerca sul primo e
    passa al successivo solo se serve.
    """
    connessi = [n for n in nodi if _stato_connesso(n)]
    return sorted(
        connessi,
        key=lambda n: (is_local_node(n.identifier), len(getattr(n, "players", {}) or {})),
    )


def choose_node(nodi):
    """Il nodo scelto per cercare o per creare un player; None se nessuno è connesso."""
    ordinati = order_nodes(nodi)
    return ordinati[0] if ordinati else None


# ----------------------------------------------------------------
# Brani locali della radio (BUG-10, LIM-43)
# ----------------------------------------------------------------
LOCAL_PREFIX = "local:"


def is_safe_local_filename(nome: str) -> bool:
    """Un nome di file semplice: niente cartelle, niente '..', niente caratteri di controllo."""
    if not nome or nome != nome.strip() or len(nome) > 255:
        return False
    if nome in (".", "..") or "/" in nome or "\\" in nome:
        return False
    return not any(ord(c) < 32 for c in nome)


def local_path_for_node(radice: str, nome: str) -> str:
    """
    Il percorso del file COME LO VEDE IL NODO Lavalink (con Docker non
    coincide con quello del bot: `LAVALINK_LOCAL_ROOT`, es. /audio/local).
    """
    return f"{radice.rstrip('/')}/{nome}"


def local_identifier(percorso: str) -> str:
    return f"{LOCAL_PREFIX}{percorso}"


def local_path_from_identifier(identificatore: str) -> str | None:
    """'local:/audio/local/a.mp3' -> '/audio/local/a.mp3'; None se non è locale."""
    if not identificatore.startswith(LOCAL_PREFIX):
        return None
    return identificatore[len(LOCAL_PREFIX):]


QUERY_URL = "url"
QUERY_SPOTIFY = "spotify"
QUERY_TESTO = "testo"
QUERY_RIFIUTATA = "rifiutata"
MSG_QUERY_RIFIUTATA = (
    "Questa ricerca non è valida: scrivi un titolo oppure un link http(s) "
    "(non percorsi di file né indirizzi particolari)."
)
_SPOTIFY_URI = re.compile(
    r"^spotify:(track|album|playlist|artist|show|episode):[A-Za-z0-9]+$", re.IGNORECASE
)
_PERCORSO_WINDOWS = re.compile(r"^[a-z]:[\\/]", re.IGNORECASE)


def classify_query(query: str) -> str:
    """
    Cosa e' una ricerca scritta da un utente (mai query grezze, BUG-10):
    - URL http(s) con un host -> QUERY_URL (passa cosi' com'e')
    - URI Spotify completo -> QUERY_SPOTIFY
    - percorsi (con barra iniziale, doppia barra, backslash, lettera di unità, `~`), `local:`, `file:`, ogni altro
      `://` o `spotify:` malformato -> QUERY_RIFIUTATA
    - il resto -> QUERY_TESTO: il chiamante aggiunge SEMPRE il prefisso di ricerca.
    I percorsi locali della radio non passano di qui (`local_path_from_identifier`).
    """
    t = query.strip()
    if not t:
        return QUERY_RIFIUTATA
    low = t.lower()
    if low.startswith(("http://", "https://")):
        return QUERY_URL if urlparse(t).hostname else QUERY_RIFIUTATA
    if _SPOTIFY_URI.match(t):
        return QUERY_SPOTIFY
    if (
        t.startswith(("/", "\\", "~"))
        or low.startswith(("local:", "file:", "spotify:"))
        or _PERCORSO_WINDOWS.match(t)
        or "://" in t
        or any(ord(c) < 32 for c in t)
    ):
        return QUERY_RIFIUTATA
    return QUERY_TESTO


def truncate_title(titolo: str, limite: int = EMBED_TITLE_LIMIT) -> str:
    """Titolo dell'embed entro il limite di Discord (LIM-21), con i puntini."""
    if len(titolo) <= limite:
        return titolo
    return titolo[: limite - 1].rstrip() + "…"


# ----------------------------------------------------------------
# Pagine e messaggi di ingresso in vocale (LIM-21, LIM-34)
# ----------------------------------------------------------------
EMBED_DESCRIPTION_LIMIT = 4096


def paginate_lines(righe: list[str], max_chars: int = 3500, max_lines: int = 25) -> list[str]:
    """
    Divide un elenco in pagine che stanno in una descrizione di embed
    (4096): al massimo `max_lines` righe e `max_chars` caratteri per
    pagina. Una riga più lunga del tetto viene tagliata. Sempre almeno
    una pagina.
    """
    pagine: list[str] = []
    corrente: list[str] = []
    lunghezza = 0
    for riga in righe:
        riga = truncate_title(riga, max_chars)
        extra = len(riga) + 1
        if corrente and (len(corrente) >= max_lines or lunghezza + extra > max_chars):
            pagine.append("\n".join(corrente))
            corrente, lunghezza = [], 0
        corrente.append(riga)
        lunghezza += extra
    pagine.append("\n".join(corrente))
    return pagine


MSG_CANALE_PALCO = (
    "Questo è un canale palco: i music bot non possono suonarci. "
    "Usa un canale vocale normale."
)
MSG_TEMPO_SCADUTO = (
    "Il music bot non è riuscito a entrare nel canale vocale in tempo "
    "(Discord non ha risposto). Riprova tra poco."
)


def msg_canale_pieno(presenti: int, limite: int) -> str:
    return (
        f"Il canale vocale è pieno ({presenti}/{limite}): il music bot non può "
        "entrare. Libera un posto o alza il limite del canale."
    )


def voice_join_problem(
    *, is_stage: bool, user_limit: int, presenti: int, puo_superare_limite: bool
) -> str | None:
    """
    LIM-34: il messaggio da mostrare PRIMA di provare a entrare, o None
    se si può provare. Canale palco e canale pieno (a meno che il bot
    abbia Muovi membri/Amministratore, che aggira il limite).
    """
    if is_stage:
        return MSG_CANALE_PALCO
    if user_limit and presenti >= user_limit and not puo_superare_limite:
        return msg_canale_pieno(presenti, user_limit)
    return None
