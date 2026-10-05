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

# DA FARE (issue #64, fase F2): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §8 (Musica).

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LavalinkNodeConfig:
    uri: str
    password: str


# Nodi pubblici gratuiti verificati con una ricerca (settembre 2026) —
# usati come cascata di DEFAULT quando LAVALINK_NODES non è impostato
# esplicitamente, così Music funziona senza che l'utente debba
# configurare nulla al primo avvio. HeavenCloud per primi (4 nodi
# regionali, dichiara supporto Spotify/Apple Music/Deezer via plugin
# LavaSRC — utile dato che l'utente vuole più sorgenti oltre YouTube),
# poi Serenetia come ulteriore fallback. Elenchi come questo cambiano
# nel tempo (nodi che spariscono, ne nascono di nuovi) — da
# riverificare periodicamente, non è un elenco statico per sempre:
# fonte aggiornata con controllo di qualità settimanale su
# https://lavalink.darrennathanael.com/.
DEFAULT_PUBLIC_LAVALINK_NODES = (
    "https://lavalink.heavencloud.in:443|heavencloud,"
    "https://us.lavalink.heavencloud.in:443|heavencloud,"
    "https://sg.lavalink.heavencloud.in:443|heavencloud,"
    "https://eu.lavalink.heavencloud.in:443|heavencloud,"
    "http://lavalink.serenetia.com:80|https://dsc.gg/ajidevserver"
)


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
    Barra di avanzamento testuale per /nowplaying (SPEC.md §9.4) —
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
