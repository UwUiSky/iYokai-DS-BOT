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
from core.duration_logic import format_duration, parse_duration  # noqa: F401 — re-export
from core.moderation_validation_logic import is_valid_reason
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

# Chiave in guild_config.settings per il canale mod-log dedicato
# (SPEC.md §5.10) — stesso meccanismo generico già usato da
# cogs/moderation/report.py per il proprio canale, non una nuova
# colonna dedicata.
SETTING_MOD_LOG_CHANNEL = "mod_log_channel_id"


async def validate_reason(interaction: discord.Interaction, reason: str) -> bool:
    """
    Controlla che il motivo fornito sia valido (SPEC.md §5.9, "reason
    obbligatorio"). Se non lo è, risponde all'utente e restituisce
    False — stesso pattern di ensure_module_enabled: il chiamante fa
    `if not await validate_reason(...): return`.
    """
    if not is_valid_reason(reason):
        await interaction.response.send_message(
            "Il motivo deve avere almeno 3 caratteri significativi.",
            ephemeral=True,
        )
        return False
    return True


async def post_to_mod_log(guild: discord.Guild, embed: discord.Embed) -> None:
    """
    Pubblica una copia dell'embed di un caso nel canale mod-log
    dedicato, se configurato (SPEC.md §5.10). Non fa nulla (non
    solleva, non blocca il comando) se il canale non è configurato o
    non è più raggiungibile — il log dedicato è un'aggiunta, non deve
    mai far fallire l'azione di moderazione vera.
    """
    channel_id = await db.get_guild_setting(guild.id, SETTING_MOD_LOG_CHANNEL)
    if channel_id is None:
        return
    channel = guild.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        return
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass


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
