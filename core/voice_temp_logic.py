"""
core/voice_temp_logic.py
===========================
Decisioni pure per i canali vocali temporanei — stesso principio di
core/permissions.py e core/automod_sync.py: solo int/bool/set qui
dentro, niente oggetti discord.py. Il cog (cogs/voice_temp/voice_temp.py)
converte gli oggetti Discord veri (VoiceState, Member) in questi
valori semplici prima di chiamare queste funzioni.
"""

from __future__ import annotations


def is_generator_join(
    after_channel_id: int | None, generator_channel_id: int | None
) -> bool:
    """
    True se l'utente è appena entrato ESATTAMENTE nel canale
    generatore configurato per questo server. generator_channel_id
    è None per un server che non ha ancora configurato nulla — in
    quel caso non scatta mai nulla, correttamente.
    """
    if generator_channel_id is None or after_channel_id is None:
        return False
    return after_channel_id == generator_channel_id


def should_delete_after_leave(
    left_channel_id: int | None,
    is_tracked_temp_channel: bool,
    remaining_member_count: int,
) -> bool:
    """
    True se il canale che l'utente ha appena lasciato va eliminato:
    deve essere un canale temporaneo tracciato E deve essere rimasto
    vuoto. Un canale non tracciato (es. un canale vocale normale del
    server, non creato da questo modulo) non viene mai toccato,
    anche se resta vuoto — non è compito di questo modulo gestirlo.
    """
    if left_channel_id is None:
        return False
    if not is_tracked_temp_channel:
        return False
    return remaining_member_count == 0


def can_manage_voice_channel(
    actor_id: int, owner_id: int, actor_has_manage_channels: bool
) -> bool:
    """
    Chi può rinominare/bloccare/espellere da un canale vocale
    temporaneo: il proprietario del canale, oppure chiunque abbia il
    permesso Discord 'Manage Channels' (staff), a prescindere da chi
    lo possiede.
    """
    return actor_id == owner_id or actor_has_manage_channels
