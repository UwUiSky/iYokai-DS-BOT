"""
core/music_settings_logic.py
================================
Impostazioni musicali per server (issue #126: MUS-047 volume massimo,
MUS-044 durata massima, MUS-055 restare a coda finita, MUS-059 canale
vocale permesso, MUS-066 riepilogo, MUS-054 attesa prima di uscire,
MUS-062 parole vietate nei titoli, MUS-064 solo siti conosciuti). Stanno nella colonna `settings` di
guild_config (come le altre impostazioni dei cog: cronologia delle
modifiche e cancellazione del server gia' coperte). Un solo punto di
lettura e di scrittura (`load_music_settings`, `save_music_setting`),
usato da comandi, controlli e, piu' avanti, dal pannello (D16).
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from core.music_logic import format_duration, truncate_title

MAX_VOLUME = 200
MAX_TRACK_MINUTES = 1440  # un giorno: oltre non ha senso un tetto
MAX_IDLE_MINUTES = 60
MAX_PAROLE_VIETATE = 300  # caratteri

# MUS-064: siti ammessi quando il server sceglie «solo siti conosciuti».
SITI_CONOSCIUTI = (
    "youtube.com", "youtu.be", "soundcloud.com", "spotify.com", "bandcamp.com", "twitch.tv",
    "vimeo.com", "mixcloud.com", "deezer.com", "tidal.com", "music.apple.com",
)


SETTING_MAX_VOLUME = "music_max_volume"
SETTING_MAX_TRACK_MINUTES = "music_max_track_minutes"
SETTING_STAY_WHEN_QUEUE_ENDS = "music_stay_when_queue_ends"
SETTING_ALLOWED_CHANNEL = "music_allowed_voice_channel_id"
SETTING_BANNED_WORDS = "music_banned_words"
SETTING_IDLE_MINUTES = "music_idle_minutes"
SETTING_KNOWN_SITES_ONLY = "music_known_sites_only"


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


def title_blocked(titolo: str, settings: MusicSettings) -> bool:
    """MUS-062: vero se il titolo contiene una parola vietata dal server (maiuscole ignorate)."""
    parole = [p.strip().lower() for p in settings.banned_words.split(",") if p.strip()]
    basso = (titolo or "").lower()
    return any(p in basso for p in parole)


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
        f"🌐 Link ammessi: **{'solo siti conosciuti' if settings.known_sites_only else 'tutti i siti sicuri'}**",
    ]


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
    )


async def save_music_setting(database, guild_id: int, key: str, value, changed_by: int) -> None:
    """Scrive UNA impostazione; `None` la toglie (torna il default)."""
    await database.set_guild_setting(guild_id, key, value, changed_by=changed_by)
