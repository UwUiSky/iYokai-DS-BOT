"""
core/lavalink_yml.py
====================
Genera `application.yml` di Lavalink dalle fonti accese (MUSIC_SOURCES_ENABLED) e
dalle chiavi presenti. Nel file ci sono solo segnaposto ${VARIABILE}: i valori
restano nell'.env di Lavalink. Nessuna chiave presente = fonte spenta.
Funzioni coperte: SPEC §9.5, issue #126 (B1), D73
Dipende da: core.music_sources
"""

from __future__ import annotations

from core import music_sources as ms

INTESTAZIONE = """\
# Configurazione Lavalink 4 per iYokai (issue #47, #48, #126).
# FILE GENERATO da scripts/genera_lavalink_yml.py dalle fonti accese: non modificarlo a mano.
# NESSUN SEGRETO QUI: i valori ${...} arrivano dall'ambiente (docker-compose.yml).
#   - password: LAVALINK_PASSWORD
#   - Spotify: SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET (solo metadati; l'audio arriva da un'altra fonte)
#   - Apple Music: APPLE_MUSIC_TOKEN (solo metadati)
# Una fonte senza chiavi resta spenta: con chiavi vuote LavaSrc puo' non avviarsi.
# Deezer non si usa con la chiave di decifrazione (D73).
# Versioni dei plugin: https://github.com/lavalink-devs/youtube-source/releases
#                      https://github.com/topi314/LavaSrc/releases
"""


def _vero(nome: str, accese: set[str]) -> bool:
    return nome in accese and ms.chiavi_presenti(nome)


def _booleano(valore: bool) -> str:
    return "true" if valore else "false"


def genera_application_yml() -> str:
    accese = ms.fonti_accese_dall_owner()
    youtube = _vero("youtube", accese)
    soundcloud = _vero("soundcloud", accese)
    spotify = _vero("spotify", accese)
    apple = _vero("applemusic", accese)

    providers = []
    if youtube:
        providers += ["""      - 'ytsearch:"%ISRC%"'""", '      - "ytsearch:%QUERY%"']
    if soundcloud:
        providers.append('      - "scsearch:%QUERY%"')
    if not providers:
        providers.append('      - "scsearch:%QUERY%"')

    righe = [
        INTESTAZIONE,
        "server:",
        "  port: 2333",
        "  address: 0.0.0.0   # dentro il container; fuori e' legato a 127.0.0.1 dal compose",
        "",
        "lavalink:",
        "  plugins:",
        '    - dependency: "dev.lavalink.youtube:youtube-plugin:1.13.3"',
        '      repository: "https://maven.lavalink.dev/releases"',
        '    - dependency: "com.github.topi314.lavasrc:lavasrc-plugin:4.8.3"',
        '      repository: "https://maven.lavalink.dev/releases"',
        "  server:",
        '    password: "CAMBIA_CON_LAVALINK_PASSWORD"',
        "    sources:",
        "      youtube: false      # lo fa il plugin, non il modulo integrato",
        f"      soundcloud: {_booleano(soundcloud)}",
        f"      bandcamp: {_booleano(_vero('bandcamp', accese))}",
        f"      twitch: {_booleano(_vero('twitch', accese))}",
        f"      vimeo: {_booleano(_vero('vimeo', accese))}",
        "      # http serve per i link diretti a un file audio (SPEC 9.5 \"URL\"). Il bot",
        "      # rifiuta prima gli indirizzi interni (core/safe_http.url_e_sicuro), ma non",
        "      # vede i redirect: sull'host di Lavalink blocca comunque in uscita le reti",
        "      # private e 169.254.169.254 (vedi README, \"Rete\").",
        f"      http: {_booleano(_vero('http', accese))}",
        "      local: true         # serve per gli inediti della radio (/audio/local)",
        "    bufferDurationMs: 400",
        "    frameBufferDurationMs: 5000",
        "    playerUpdateInterval: 5",
        "",
        "plugins:",
        "  youtube:",
        f"    enabled: {_booleano(youtube)}",
        "    allowSearch: true",
        "    allowDirectVideoIds: true",
        "    allowDirectPlaylistIds: true",
        "  lavasrc:",
        "    providers:",
        *providers,
        "    sources:",
        f"      spotify: {_booleano(spotify)}",
        f"      applemusic: {_booleano(apple)}",
        "      deezer: false       # mai con la chiave di decifrazione (D73)",
    ]
    # Le sezioni ci sono sempre (solo segnaposto): è il flag `sources` che accende la fonte.
    righe += [
        "    spotify:",
        '      clientId: "${SPOTIFY_CLIENT_ID}"',
        '      clientSecret: "${SPOTIFY_CLIENT_SECRET}"',
        '      countryCode: "IT"',
        "    applemusic:",
        '      mediaAPIToken: "${APPLE_MUSIC_TOKEN}"',
        '      countryCode: "IT"',
    ]
    righe += ["", "logging:", "  level:", "    root: INFO", "    lavalink: INFO", ""]
    return "\n".join(righe)
