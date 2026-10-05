"""
core/voice_temp_logic.py
===========================
Decisioni pure per i canali vocali temporanei — stesso principio di
core/permissions.py e core/automod_sync.py: solo int/bool/set qui
dentro, niente oggetti discord.py. Il cog (cogs/voice_temp/voice_temp.py)
converte gli oggetti Discord veri (VoiceState, Member) in questi
valori semplici prima di chiamare queste funzioni.
"""

# DA FARE (issue #63, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §7 (Vocali temporanei).

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


# Un canale creato dal pannello nasce vuoto e l'utente entra dopo: la
# pulizia all'avvio (che gira anche a ogni riconnessione) non tocca i
# canali più giovani di così.
STARTUP_CLEANUP_GRACE_SECONDS = 120


def is_old_enough_for_startup_cleanup(age_seconds: float) -> bool:
    """True se il canale è abbastanza vecchio da poter essere ripulito all'avvio."""
    return age_seconds >= STARTUP_CLEANUP_GRACE_SECONDS


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


# Limite hard-coded di Discord: una categoria non può contenere più
# di 50 canali, punto — nessuna configurazione lato server può
# superarlo, quindi va sempre applicato anche se l'admin non ha
# impostato (o ha impostato più alto di) un cap personalizzato.
DISCORD_MAX_CHANNELS_PER_CATEGORY = 50


def effective_category_cap(configured_cap: int | None) -> int:
    """
    SPEC.md §12.8: il cap configurabile per server non può mai
    superare il limite hard di Discord (50 canali per categoria).
    Nessun cap configurato -> si usa direttamente il limite Discord.
    """
    if configured_cap is None:
        return DISCORD_MAX_CHANNELS_PER_CATEGORY
    return min(configured_cap, DISCORD_MAX_CHANNELS_PER_CATEGORY)


def is_category_full(current_channel_count: int, configured_cap: int | None) -> bool:
    """
    True se la categoria ha già raggiunto il cap effettivo (il minore
    tra il cap configurato dal server e il limite hard di Discord) —
    usato per rifiutare la creazione di un nuovo vocale temporaneo
    PRIMA di tentare la chiamata a Discord, invece di scoprirlo solo
    dall'HTTPException che l'API restituirebbe comunque.
    """
    return current_channel_count >= effective_category_cap(configured_cap)
