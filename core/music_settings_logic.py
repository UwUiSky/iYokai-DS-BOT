"""
core/music_settings_logic.py
================================
Impostazioni musicali per server (issue #126: MUS-047 volume massimo,
MUS-044 durata massima, MUS-055 restare a coda finita, MUS-059 canale
vocale permesso, MUS-066 riepilogo). Stanno nella colonna `settings` di
guild_config (come le altre impostazioni dei cog: cronologia delle
modifiche e cancellazione del server gia' coperte). Un solo punto di
lettura e di scrittura (`load_music_settings`, `save_music_setting`),
usato da comandi, controlli e, piu' avanti, dal pannello (D16).
"""

from __future__ import annotations

from dataclasses import dataclass

from core.music_logic import format_duration, truncate_title

MAX_VOLUME = 200
MAX_TRACK_MINUTES = 1440  # un giorno: oltre non ha senso un tetto


KEY_MAX_VOLUME = "music_max_volume"
KEY_MAX_TRACK_MINUTES = "music_max_track_minutes"
KEY_STAY_WHEN_QUEUE_ENDS = "music_stay_when_queue_ends"
KEY_ALLOWED_CHANNEL = "music_allowed_voice_channel_id"


@dataclass(frozen=True)
class MusicSettings:
    guild_id: int = 0
    max_volume: int = MAX_VOLUME
    max_track_minutes: int = 0  # 0 = nessun limite
    stay_when_queue_ends: bool = False
    allowed_voice_channel_id: int | None = None


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
    ]


async def load_music_settings(database, guild_id: int) -> MusicSettings:
    """Legge le impostazioni del server; ciò che manca vale il default."""
    get = database.get_guild_setting
    return MusicSettings(
        guild_id=guild_id,
        max_volume=max(0, min(MAX_VOLUME, int(await get(guild_id, KEY_MAX_VOLUME, MAX_VOLUME)))),
        max_track_minutes=max(
            0, min(MAX_TRACK_MINUTES, int(await get(guild_id, KEY_MAX_TRACK_MINUTES, 0)))
        ),
        stay_when_queue_ends=bool(await get(guild_id, KEY_STAY_WHEN_QUEUE_ENDS, False)),
        allowed_voice_channel_id=await get(guild_id, KEY_ALLOWED_CHANNEL, None),
    )


async def save_music_setting(database, guild_id: int, key: str, value, changed_by: int) -> None:
    """Scrive UNA impostazione; `None` la toglie (torna il default)."""
    await database.set_guild_setting(guild_id, key, value, changed_by=changed_by)
