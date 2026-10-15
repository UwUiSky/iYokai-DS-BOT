"""
core/log_eventi_logic.py
========================
Interruttori dei singoli eventi di log (LOG-017): ogni interruttore
raccoglie uno o più eventi. Senza scelte del server sono tutti accesi.
Le scelte rapide sono «tutto», «niente» e «predefinito» (tutto tranne
microfono e audio spenti da soli, gli eventi più rumorosi).
Funzioni coperte: SPEC §8.19 (LOG-017)
"""

from __future__ import annotations

# interruttore → (etichetta, eventi). Massimo 25: entrano in un solo menu.
INTERRUTTORI: dict[str, tuple[str, tuple[str, ...]]] = {
    "ingressi": ("Ingressi nel server", ("member_join",)),
    "uscite": ("Uscite ed espulsioni", ("member_remove",)),
    "ban": ("Ban e sban", ("member_ban", "member_unban")),
    "ruoli_membri": ("Ruoli dati e tolti ai membri", ("role_update",)),
    "nickname": ("Nickname", ("nickname_update",)),
    "timeout": ("Timeout", ("timeout_update",)),
    "profilo": ("Nome utente, nome visualizzato, avatar", ("username_update", "display_name_update", "avatar_update")),
    "messaggi_cancellati": ("Messaggi cancellati", ("message_delete", "message_bulk_delete")),
    "messaggi_modificati": ("Messaggi modificati", ("message_edit",)),
    "inviti_scritti": ("Inviti scritti nei messaggi", ("invite_posted",)),
    "fissati": ("Messaggi fissati e tolti", ("message_pin", "message_unpin")),
    "ruoli": ("Ruoli creati, modificati, eliminati", ("role_create", "role_delete", "role_edit")),
    "canali": ("Canali creati, modificati, spostati", ("channel_create", "channel_delete", "channel_update", "channel_move")),
    "inviti": ("Inviti creati, eliminati, usati", ("invite_create", "invite_delete", "invite_use")),
    "webhook": ("Webhook", ("webhook_create", "webhook_update", "webhook_delete")),
    "emoji": ("Emoji e sticker", (
        "emoji_create", "emoji_delete", "emoji_update", "sticker_create", "sticker_delete", "sticker_update",
    )),
    "thread": ("Thread", ("thread_create", "thread_delete", "thread_update")),
    "soundboard": ("Suoni della soundboard", (
        "soundboard_sound_create", "soundboard_sound_update", "soundboard_sound_delete",
    )),
    "server": ("Impostazioni del server", ("guild_update",)),
    "palchi": ("Palchi (stage)", ("voice_stage_create", "voice_stage_update", "voice_stage_delete")),
    "voce": ("Entrate, uscite e cambi di vocale", ("voice_join", "voice_leave", "voice_move")),
    "voce_server": ("Mutati e assordati dal server", ("voice_mute", "voice_unmute", "voice_deafen", "voice_undeafen")),
    "voce_propri": ("Microfono e audio spenti da soli", (
        "voice_self_mute", "voice_self_unmute", "voice_self_deafen", "voice_self_undeafen",
    )),
    "voce_forzati": ("Scollegati o spostati da un moderatore", ("voice_force_disconnect", "voice_force_move")),
}

PREDEFINITO_SPENTI: frozenset[str] = frozenset({"voce_propri"})

_DI_EVENTO = {evento: chiave for chiave, (_, eventi) in INTERRUTTORI.items() for evento in eventi}


def interruttore_di(evento: str) -> str | None:
    """L'interruttore che comanda l'evento, o None se l'evento non ne ha (resta sempre acceso)."""
    return _DI_EVENTO.get(evento)


def acceso(evento: str, spenti: frozenset[str]) -> bool:
    chiave = interruttore_di(evento)
    return chiave is None or chiave not in spenti


def spenti_da_scelta(scelta: str, accesi: list[str] | None = None) -> frozenset[str]:
    """Gli interruttori spenti dopo una scelta: «tutto», «niente», «predefinito» o l'elenco degli accesi."""
    if scelta == "tutto":
        return frozenset()
    if scelta == "niente":
        return frozenset(INTERRUTTORI)
    if scelta == "predefinito":
        return PREDEFINITO_SPENTI
    return frozenset(INTERRUTTORI) - frozenset(accesi or ())
