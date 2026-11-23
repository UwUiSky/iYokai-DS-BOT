"""
core/music_settings_logic.py
================================
Impostazioni musicali per server (issue #126: MUS-047 volume massimo,
MUS-044 durata massima, MUS-055 restare a coda finita, MUS-059 canale
vocale permesso, MUS-066 riepilogo, MUS-054 attesa prima di uscire,
MUS-062 parole vietate nei titoli, MUS-064 solo siti conosciuti, MUS-012 fonte di ricerca, MUS-037 coda equa,
MUS-041 playlist di riserva (e MUS-040: continuare da soli dalla playlist scelta), MUS-045 playlist «Oggi»,
MUS-042 coda salvata, MUS-051 DJ, MUS-052 voto per saltare, MUS-053 pausa a canale vuoto, MUS-061 stato del bot, MUS-015 paese delle ricerche, MUS-065 jukebox (prezzo in monete), MUS-057 annunci «ora in riproduzione» accesi/spenti, MUS-058 canale degli annunci).
MUS-063 parole vietate in tutto il bot (elenco dell'owner, `imposta_parole_globali`).
MUS-048 qualità audio per server: non fatta, la qualità si regola sul nodo Lavalink (D85). Stanno nella colonna `settings` di
guild_config (come le altre impostazioni dei cog: cronologia delle
modifiche e cancellazione del server gia' coperte). Un solo punto di
lettura e di scrittura (`load_music_settings`, `save_music_setting`),
usato da comandi, controlli e, piu' avanti, dal pannello (D16).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from core.fun_logic import normalizza_per_filtro
from core.music_jukebox_logic import prezzo_valido
from core.music_logic import format_duration, truncate_title
from core.music_paese_logic import paese_effettivo, paese_valido
from core.music_sources import FONTI, FONTI_DI_RICERCA

MAX_VOLUME = 200
MAX_TRACK_MINUTES = 1440  # un giorno: oltre non ha senso un tetto
MAX_IDLE_MINUTES = 60
MAX_PAROLE_VIETATE = 300  # caratteri

# MUS-064: siti ammessi quando il server sceglie «solo siti conosciuti».
SITI_CONOSCIUTI = (
    "youtube.com", "youtu.be", "soundcloud.com", "spotify.com", "bandcamp.com", "twitch.tv",
    "vimeo.com", "mixcloud.com", "deezer.com", "tidal.com", "music.apple.com",
    "music.yandex.ru", "music.yandex.com", "music.yandex.by", "music.yandex.kz", "music.yandex.uz",
    # MUS-009: i file allegati a /music play arrivano da Discord.
    "cdn.discordapp.com", "media.discordapp.net",
)


SETTING_MAX_VOLUME = "music_max_volume"
SETTING_MAX_TRACK_MINUTES = "music_max_track_minutes"
SETTING_STAY_WHEN_QUEUE_ENDS = "music_stay_when_queue_ends"
SETTING_ALLOWED_CHANNEL = "music_allowed_voice_channel_id"
SETTING_BANNED_WORDS = "music_banned_words"
SETTING_IDLE_MINUTES = "music_idle_minutes"
SETTING_KNOWN_SITES_ONLY = "music_known_sites_only"
SETTING_DEFAULT_SEARCH = "music_default_search"
SETTING_QUEUE_MODE = "music_queue_mode"
SETTING_ANNOUNCE = "music_announce"  # MUS-057
SETTING_FALLBACK_PLAYLIST = "music_fallback_playlist"  # MUS-041/040
SETTING_DAILY_PLAYLIST = "music_daily_playlist"  # MUS-045
SETTING_PERSIST_QUEUE = "music_persist_queue"  # MUS-042
SETTING_ANNOUNCE_CHANNEL = "music_announce_channel_id"  # MUS-058
SETTING_JUKEBOX_PRICE = "music_jukebox_price"  # MUS-065
SETTING_DJ_MODE = "music_dj_mode"  # MUS-051
SETTING_DJ_ROLE = "music_dj_role_id"  # MUS-051
SETTING_SKIP_VOTE = "music_skip_vote_percent"  # MUS-052
SETTING_EMPTY_PAUSE = "music_empty_pause"  # MUS-053
SETTING_BOT_STATUS = "music_bot_status"  # MUS-061
SETTING_SEARCH_COUNTRY = "music_search_country"  # MUS-015
SETTING_AUDIO_ONLY = "music_audio_only"  # MUS-016
QUEUE_MODES = ("normale", "equa")


@dataclass(frozen=True)
class MusicSettings:
    guild_id: int = 0
    max_volume: int = MAX_VOLUME
    max_track_minutes: int = 0  # 0 = nessun limite
    stay_when_queue_ends: bool = False
    allowed_voice_channel_id: int | None = None
    banned_words: str = ""  # separate da virgola
    idle_minutes: int = 0  # 0 = predefinito (5 minuti)
    known_sites_only: bool = False
    queue_mode: str = "normale"  # «equa»: i brani si alternano tra chi li ha messi
    fallback_playlist: str = ""  # MUS-041: playlist del server che parte a coda finita ("" = nessuna)
    daily_playlist: bool = False  # MUS-045: spenta di base (D85)
    persist_queue: bool = False  # MUS-042: spenta di base (D85)
    announce: bool = False  # MUS-057: spento di base (D85), niente messaggi non chiesti
    announce_channel_id: int | None = None  # MUS-058
    jukebox_price: int = 0  # MUS-065: monete per mettere un brano in coda; 0 = spento (D97)
    dj_mode: bool = False  # MUS-051: spenta di base
    dj_role_id: int | None = None  # MUS-051
    skip_vote_percent: int = 50  # MUS-052: percentuale degli ascoltatori umani
    empty_pause: bool = True  # MUS-053: pausa se nel canale non resta nessuno
    bot_status: bool = False  # MUS-061: titolo come stato del bot della flotta, spento di base
    audio_only: bool = False  # MUS-016: nelle ricerche per titolo, prima le versioni senza «video ufficiale»
    default_search: str = ""  # fonte dove cercare un titolo; "" = automatica (YouTube, poi SoundCloud)
    search_country: str = ""  # MUS-015: paese ISO delle ricerche; "" = quello globale dell'owner, di base nessun limite


# MUS-063: le parole vietate dall'owner in tutto il bot (già normalizzate); le imposta il cog dell'owner.
_parole_globali: frozenset[str] = frozenset()


def imposta_parole_globali(parole) -> None:
    """MUS-063: sostituisce l'elenco globale (le parole passano dallo stesso filtro dei temi)."""
    global _parole_globali
    _parole_globali = frozenset(p for p in (normalizza_per_filtro(x) for x in parole) if p)


def parole_globali() -> frozenset[str]:
    return _parole_globali


def title_blocked(titolo: str, settings: MusicSettings) -> bool:
    """MUS-062: vero se il titolo contiene una parola vietata dal server.

    Titolo e parole passano dallo stesso filtro dei temi (`normalizza_per_filtro`):
    maiuscole, accenti, lettere larghe o somiglianti e lettere staccate non aggirano il divieto.
    """
    parole = [normalizza_per_filtro(p) for p in settings.banned_words.split(",")]
    normale = normalizza_per_filtro(titolo or "")
    return any(p and p in normale for p in [*parole, *_parole_globali])


# MUS-016: espressioni che dicono «video» nel titolo (parole intere: «videogame» non conta).
_VIDEO = re.compile(
    r"\b(official (music )?video|music video|video ufficiale|videoclip|video clip|lyric video|official mv)\b", re.IGNORECASE
)
_AUDIO = re.compile(r"\b(audio|solo audio|official audio|audio only|topic)\b", re.IGNORECASE)


def preferisci_solo_audio(tracce):
    """MUS-016: stesso elenco, ma i titoli da «video musicale» in fondo (ordine stabile). Se sono tutti video, non cambia.

    Un titolo che dice anche «audio» conta come audio. Un valore che non è un elenco torna com'è (playlist, link)."""
    if not isinstance(tracce, list) or not tracce:
        return tracce

    def e_video(t) -> bool:
        titolo = getattr(t, "title", "") or ""
        return bool(_VIDEO.search(titolo)) and not _AUDIO.search(titolo)

    if all(e_video(t) for t in tracce):
        return tracce
    return [t for t in tracce if not e_video(t)] + [t for t in tracce if e_video(t)]


def site_not_allowed(query: str, settings: MusicSettings) -> str | None:
    """MUS-064: il messaggio di rifiuto se il link è di un sito non ammesso; None altrimenti."""
    if not settings.known_sites_only:
        return None
    testo = query.strip()
    if not testo.lower().startswith(("http://", "https://")):
        return None  # una ricerca per titolo non è un sito
    host = (urlparse(testo).hostname or "").lower()
    if any(host == s or host.endswith("." + s) for s in SITI_CONOSCIUTI):
        return None
    return "Questo server accetta solo link di siti conosciuti (YouTube, SoundCloud, Spotify, Bandcamp…)."


def idle_seconds(settings: MusicSettings) -> int | None:
    """MUS-054: secondi di attesa a coda finita; None = lascia il predefinito della libreria."""
    return settings.idle_minutes * 60 if settings.idle_minutes > 0 else None


def clamp_volume(volume: int, settings: MusicSettings) -> int:
    """Il volume richiesto, tenuto tra 0 e il massimo scelto dal server."""
    return max(0, min(volume, settings.max_volume))


def track_too_long(length_ms: int, settings: MusicSettings, is_stream: bool = False) -> bool:
    """Vero se il brano supera la durata massima. Le dirette (durata ignota) non contano."""
    if settings.max_track_minutes <= 0 or is_stream or length_ms <= 0:
        return False
    return length_ms > settings.max_track_minutes * 60_000


def msg_brano_troppo_lungo(titolo: str, length_ms: int, settings: MusicSettings) -> str:
    return (
        f"**{truncate_title(titolo, 150)}** dura {format_duration(length_ms)}: "
        f"questo server accetta brani fino a {settings.max_track_minutes} minuti."
    )


def channel_not_allowed(channel_id: int, settings: MusicSettings) -> str | None:
    """Il messaggio da mostrare se la musica è permessa in un solo canale e non è questo."""
    permesso = settings.allowed_voice_channel_id
    if permesso is None or permesso == channel_id:
        return None
    return f"La musica su questo server è permessa solo nel canale vocale <#{permesso}>."


def summary_lines(settings: MusicSettings) -> list[str]:
    """Il riepilogo di tutte le impostazioni (MUS-066), una riga ciascuna."""
    canale = (
        f"<#{settings.allowed_voice_channel_id}>"
        if settings.allowed_voice_channel_id
        else "tutti i canali vocali"
    )
    durata = f"{settings.max_track_minutes} minuti" if settings.max_track_minutes else "nessun limite"
    return [
        f"🔊 Volume massimo: **{settings.max_volume}**",
        f"⏱️ Durata massima di un brano: **{durata}**",
        f"🏠 A coda finita il bot: **{'resta nel canale' if settings.stay_when_queue_ends else 'esce dopo un po'}**",
        f"🎙️ Canale vocale permesso: **{canale}**",
        f"⏳ Attesa prima di uscire: **{f'{settings.idle_minutes} minuti' if settings.idle_minutes else 'predefinita (5 minuti)'}**",
        f"🚫 Parole vietate nei titoli: **{settings.banned_words or 'nessuna'}**",
        f"🔎 Ricerca di un titolo: **{FONTI[settings.default_search].etichetta if settings.default_search in FONTI else 'automatica (YouTube, poi SoundCloud)'}**",
        f"🌍 Paese delle ricerche: **{paese_effettivo(settings.search_country) or 'nessun limite (ascoltabili in tutto il mondo)'}**",
        f"⚖️ Ordine della coda: **{'equa (a giro tra gli utenti)' if settings.queue_mode == 'equa' else 'normale (come arrivano)'}**",
        f"📢 Annunci «ora in riproduzione»: **{(f'nel canale <#{settings.announce_channel_id}>' if settings.announce_channel_id else 'accesi, ma serve un canale') if settings.announce else 'spenti'}**",
        f"📻 Playlist di riserva a coda finita: **{settings.fallback_playlist or 'nessuna'}**",
        f"📅 Playlist «Oggi» automatica: **{'accesa' if settings.daily_playlist else 'spenta'}**",
        f"💾 Coda salvata per i riavvii: **{'accesa' if settings.persist_queue else 'spenta'}**",
        f"🪙 Jukebox: **{f'{settings.jukebox_price} monete per richiesta' if settings.jukebox_price else 'spento'}**",
        f"🎧 Modalità DJ: **{'accesa' if settings.dj_mode else 'spenta'}** (ruolo DJ: {f'<@&{settings.dj_role_id}>' if settings.dj_role_id else 'nessuno'})",
        f"🗳️ Voto per saltare: **{settings.skip_vote_percent}%** degli ascoltatori",
        f"⏸️ Pausa a canale vuoto: **{'accesa' if settings.empty_pause else 'spenta'}**",
        f"🎧 Ricerche: **{'prima le versioni solo audio' if settings.audio_only else 'come arrivano'}**",
        f"🏷️ Titolo come stato dei music bot: **{'acceso' if settings.bot_status else 'spento'}**",
        f"🌐 Link ammessi: **{'solo siti conosciuti' if settings.known_sites_only else 'tutti i siti sicuri'}**",
    ]


def _fonte_valida(valore) -> str:
    """Una fonte di ricerca nota, altrimenti «automatica» (stringa vuota)."""
    return valore if isinstance(valore, str) and valore in FONTI_DI_RICERCA else ""


def _modo_coda_valido(valore) -> str:
    """Un modo coda noto, altrimenti «normale»."""
    return valore if isinstance(valore, str) and valore in QUEUE_MODES else "normale"


def _id_valido(valore) -> int | None:
    """Un id di canale (intero positivo) oppure None."""
    return valore if isinstance(valore, int) and not isinstance(valore, bool) and valore > 0 else None


def _percentuale_valida(valore) -> int:
    """Una percentuale da 1 a 100, altrimenti il 50 di base."""
    if isinstance(valore, bool) or not isinstance(valore, int) or not 1 <= valore <= 100:
        return 50
    return valore


async def load_music_settings(database, guild_id: int) -> MusicSettings:
    """Legge le impostazioni del server; ciò che manca vale il default."""
    get = database.get_guild_setting
    return MusicSettings(
        guild_id=guild_id,
        max_volume=max(0, min(MAX_VOLUME, int(await get(guild_id, SETTING_MAX_VOLUME, MAX_VOLUME)))),
        max_track_minutes=max(
            0, min(MAX_TRACK_MINUTES, int(await get(guild_id, SETTING_MAX_TRACK_MINUTES, 0)))
        ),
        stay_when_queue_ends=bool(await get(guild_id, SETTING_STAY_WHEN_QUEUE_ENDS, False)),
        allowed_voice_channel_id=await get(guild_id, SETTING_ALLOWED_CHANNEL, None),
        banned_words=str(await get(guild_id, SETTING_BANNED_WORDS, "") or "")[:MAX_PAROLE_VIETATE],
        idle_minutes=max(0, min(MAX_IDLE_MINUTES, int(await get(guild_id, SETTING_IDLE_MINUTES, 0)))),
        known_sites_only=bool(await get(guild_id, SETTING_KNOWN_SITES_ONLY, False)),
        default_search=_fonte_valida(await get(guild_id, SETTING_DEFAULT_SEARCH, "")),
        queue_mode=_modo_coda_valido(await get(guild_id, SETTING_QUEUE_MODE, "normale")),
        announce=bool(await get(guild_id, SETTING_ANNOUNCE, False)),
        fallback_playlist=str(await get(guild_id, SETTING_FALLBACK_PLAYLIST, "") or "")[:50],
        daily_playlist=bool(await get(guild_id, SETTING_DAILY_PLAYLIST, False)),
        persist_queue=bool(await get(guild_id, SETTING_PERSIST_QUEUE, False)),
        announce_channel_id=_id_valido(await get(guild_id, SETTING_ANNOUNCE_CHANNEL, None)),
        jukebox_price=prezzo_valido(await get(guild_id, SETTING_JUKEBOX_PRICE, 0)),
        dj_mode=bool(await get(guild_id, SETTING_DJ_MODE, False)),
        dj_role_id=_id_valido(await get(guild_id, SETTING_DJ_ROLE, None)),
        skip_vote_percent=_percentuale_valida(await get(guild_id, SETTING_SKIP_VOTE, 50)),
        empty_pause=bool(await get(guild_id, SETTING_EMPTY_PAUSE, True)),
        bot_status=bool(await get(guild_id, SETTING_BOT_STATUS, False)),
        search_country=paese_valido(await get(guild_id, SETTING_SEARCH_COUNTRY, "")) or "",
        audio_only=bool(await get(guild_id, SETTING_AUDIO_ONLY, False)),
    )


async def save_music_setting(database, guild_id: int, key: str, value, changed_by: int) -> None:
    """Scrive UNA impostazione; `None` la toglie (torna il default)."""
    await database.set_guild_setting(guild_id, key, value, changed_by=changed_by)
