"""
core/logging_advanced_logic.py
==================================
Logica pura del Logging Avanzato (SPEC.md §8.6-§8.15, livello
Premium) — nessuna dipendenza da discord.py o dal database, solo
funzioni di diff tra "prima" e "dopo" su dizionari di attributi
semplici. Lo stesso principio già usato in
`cogs/logging/basic_logs.py` (`diff_roles`, `nickname_changed`), qui
esteso a ruoli/canali/server/voce/emoji/sticker/thread.

Ogni funzione riceve SNAPSHOT (dict di valori semplici), non oggetti
discord.py — l'estrazione dei valori dall'oggetto reale vive nel cog
(`cogs/logging/advanced_logs.py`), qui c'è solo la decisione "cosa è
cambiato".
"""

from __future__ import annotations


def diff_attributes(before: dict, after: dict, tracked_keys: tuple[str, ...]) -> dict:
    """
    Confronta due snapshot sugli attributi indicati in
    `tracked_keys`, restituendo SOLO quelli effettivamente cambiati
    (non l'intero prima/dopo) — un ruolo/canale/server ha spesso
    decine di attributi, la maggior parte irrilevanti per un log
    leggibile.
    """
    changes = {}
    for key in tracked_keys:
        prima, dopo = before.get(key), after.get(key)
        if prima != dopo:
            changes[key] = {"before": prima, "after": dopo}
    return changes


ROLE_TRACKED_KEYS = ("name", "color", "hoist", "mentionable", "permissions")
CHANNEL_TRACKED_KEYS = ("name", "category_id", "topic", "nsfw", "slowmode_delay", "position")
GUILD_TRACKED_KEYS = (
    "name", "icon", "verification_level", "afk_channel_id", "system_channel_id",
    "explicit_content_filter",
)
THREAD_TRACKED_KEYS = ("name", "archived", "locked")


def diff_id_sets(before_ids: set[int], after_ids: set[int]) -> tuple[set[int], set[int]]:
    """Stesso principio di `diff_roles` in basic_logs.py, generico:
    quali ID sono spariti e quali sono nuovi tra due istantanee."""
    added = after_ids - before_ids
    removed = before_ids - after_ids
    return added, removed


def diff_named_items(
    before: dict[int, str], after: dict[int, str]
) -> dict[str, list]:
    """
    Confronta due mappe {id: nome} (emoji o sticker di un server) e
    restituisce creati/eliminati/rinominati. Un ID presente in
    entrambe le mappe con un nome diverso è un rename (update), non
    una coppia elimina+crea — distinzione che l'evento gateway
    stesso (`on_guild_emojis_update`/`on_guild_stickers_update`) non
    fa: consegna solo le due liste complete "prima" e "dopo".
    """
    before_ids, after_ids = set(before), set(after)
    added_ids, removed_ids = diff_id_sets(before_ids, after_ids)

    created = [{"id": i, "name": after[i]} for i in added_ids]
    deleted = [{"id": i, "name": before[i]} for i in removed_ids]
    renamed = [
        {"id": i, "before": before[i], "after": after[i]}
        for i in (before_ids & after_ids)
        if before[i] != after[i]
    ]
    return {"created": created, "deleted": deleted, "renamed": renamed}


def classify_voice_state_change(before: dict, after: dict) -> list[str]:
    """
    Un singolo `on_voice_state_update` può contenere più cambiamenti
    insieme (es. mute E cambio canale nello stesso evento) — per
    questo restituisce una LISTA di categorie, non una sola.
    Ordine: movimento di canale prima di mute/deafen, così un log
    letto in sequenza racconta prima "dove", poi "come".
    """
    eventi: list[str] = []

    prima_canale = before.get("channel_id")
    dopo_canale = after.get("channel_id")
    if prima_canale != dopo_canale:
        if prima_canale is None:
            eventi.append("voice_join")
        elif dopo_canale is None:
            eventi.append("voice_leave")
        else:
            eventi.append("voice_move")

    if before.get("mute") != after.get("mute"):
        eventi.append("voice_mute" if after.get("mute") else "voice_unmute")

    if before.get("deaf") != after.get("deaf"):
        eventi.append("voice_deafen" if after.get("deaf") else "voice_undeafen")

    return eventi
