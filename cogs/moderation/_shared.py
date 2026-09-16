"""
cogs/moderation/_shared.py
=============================
Helper condivisi da tutti i cog del modulo moderazione. Il nome
inizia con "_" apposta: core/cog_manager.py salta i file che
iniziano con underscore (non sono cog, sono supporto — vedi
discover_cog_modules in quel file).

Qui vivono le tre costanti dei nomi modulo (usate sia per il
controllo "è attivo su questo server?" sia per la registrazione
premium) e le funzioni che altrimenti si ripeterebbero identiche in
ogni singolo file di comandi.
"""

from __future__ import annotations

import discord

from core.database import db
from core.permissions import ModerationActor, can_moderate

# Nomi dei tre moduli premium-differenziabili di moderazione, come
# da schema di progetto:
#   - le azioni base (warn/kick/ban/timeout...) restano SEMPRE gratis
#   - il case system avanzato (storico, note) è candidato premium
#   - il clear con filtri è candidato premium
MODULE_ACTIONS = "moderation_actions"
MODULE_CASE_SYSTEM = "moderation_case_system"
MODULE_CLEAR = "moderation_clear"
MODULE_CHANNEL_CONTROL = "moderation_channel_control"
MODULE_REPORT = "moderation_report"


async def ensure_module_enabled(
    interaction: discord.Interaction, module_name: str
) -> bool:
    """
    Controlla se il modulo è attivo su questo server. Se non lo è,
    risponde all'utente e restituisce False — il chiamante deve
    fare `if not await ensure_module_enabled(...): return` come
    prima riga del comando.
    """
    if interaction.guild is None:
        await interaction.response.send_message(
            "Questo comando è disponibile solo dentro un server.",
            ephemeral=True,
        )
        return False

    enabled = await db.is_module_active_for_guild(interaction.guild.id, module_name)
    if not enabled:
        await interaction.response.send_message(
            "Questo modulo non è attivo su questo server. "
            "Un amministratore può attivarlo con /setup.",
            ephemeral=True,
        )
        return False
    return True


def actor_from_member(member: discord.Member) -> ModerationActor:
    """
    Converte un discord.Member vero nei soli dati semplici che
    core.permissions.can_moderate() si aspetta. Questa è la
    conversione di cui parla il commento in cima a core/permissions.py:
    la logica di decisione è lì, testata in isolamento; qui c'è solo
    l'estrazione dei valori dall'oggetto Discord reale.
    """
    return ModerationActor(
        user_id=member.id,
        top_role_position=member.top_role.position,
        is_guild_owner=(member.id == member.guild.owner_id),
        is_bot_itself=member.bot and member.id == member.guild.me.id,
    )


async def check_can_moderate(
    interaction: discord.Interaction,
    target: discord.Member,
) -> bool:
    """
    Verifica se chi ha lanciato il comando può moderare `target` in
    questo server. Se non può, risponde con il motivo e restituisce
    False. Il bersaglio del bot stesso, il proprietario del server,
    ruoli pari o superiori, ecc. — tutta la logica reale è in
    core/permissions.py, qui c'è solo il collegamento con l'oggetto
    Interaction per rispondere all'utente.
    """
    guild = interaction.guild
    assert guild is not None  # già controllato da ensure_module_enabled

    moderator = guild.get_member(interaction.user.id)
    if moderator is None:
        await interaction.response.send_message(
            "Non riesco a verificare i tuoi permessi in questo server.",
            ephemeral=True,
        )
        return False

    actor = actor_from_member(moderator)
    target_actor = actor_from_member(target)

    allowed, reason = can_moderate(
        actor, target_actor, bot_top_role_position=guild.me.top_role.position
    )
    if not allowed:
        await interaction.response.send_message(reason, ephemeral=True)
        return False
    return True


async def try_dm(user: discord.abc.Snowflake, embed: discord.Embed) -> bool:
    """
    Prova a mandare un DM. Restituisce True/False invece di
    sollevare un'eccezione: un utente con i DM chiusi non deve far
    fallire l'intero comando di moderazione, solo far sapere al
    moderatore che la notifica non è arrivata.
    """
    try:
        # user qui è sempre un discord.Member/discord.User vero
        # (Snowflake nel type hint solo per generalità); .send()
        # esiste su entrambi.
        await user.send(embed=embed)  # type: ignore[attr-defined]
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


def format_duration(seconds: int) -> str:
    """Converte un numero di secondi in una stringa leggibile in italiano."""
    if seconds < 60:
        return f"{seconds} secondi"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minuti"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} ore"
    days = hours // 24
    return f"{days} giorni"


_DURATION_UNITS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
}


def parse_duration(text: str) -> int:
    """
    Converte una durata scritta come "30m", "12h", "7d", "2w" in
    secondi. Solleva ValueError con un messaggio comprensibile se il
    formato non è valido — il chiamante lo intercetta e lo mostra
    all'utente così com'è, non serve tradurlo di nuovo.

    Formato accettato: un numero intero positivo seguito da UNA
    lettera tra s/m/h/d/w (secondi/minuti/ore/giorni/settimane).
    Niente numeri decimali, niente combinazioni tipo "1h30m": tenerlo
    semplice riduce gli errori di parsing e copre comunque il 99%
    dei casi d'uso reali di moderazione.
    """
    text = text.strip().lower()
    if len(text) < 2:
        raise ValueError(
            "Formato durata non valido. Esempi validi: 30m, 12h, 7d, 2w"
        )

    unit = text[-1]
    number_part = text[:-1]

    if unit not in _DURATION_UNITS:
        raise ValueError(
            f"Unità di tempo '{unit}' non riconosciuta. "
            f"Usa: s (secondi), m (minuti), h (ore), d (giorni), w (settimane)"
        )

    if not number_part.isdigit():
        raise ValueError(
            "La durata deve essere un numero intero positivo seguito "
            "dall'unità, es. 30m, 12h, 7d"
        )

    value = int(number_part)
    if value <= 0:
        raise ValueError("La durata deve essere maggiore di zero.")

    return value * _DURATION_UNITS[unit]
