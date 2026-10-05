"""
cogs/moderation/_shared.py
=============================
Helper condivisi da tutti i cog del modulo moderazione. Il nome
inizia con "_" apposta: core/cog_manager.py salta i file che
iniziano con underscore (non sono cog, sono supporto — vedi
discover_cog_modules in quel file).

Qui vivono le costanti dei nomi modulo (usate sia per il controllo
"è attivo su questo server?" sia per la registrazione premium), i
limiti di Discord che valgono per tutta la moderazione (motivo 512,
campo 1024, elenchi entro 4000) e le funzioni che altrimenti si
ripeterebbero identiche in ogni singolo file di comandi.
Funzioni coperte: SPEC §5
"""

# DA FARE (issue #57, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §1 (Moderazione).

from __future__ import annotations

import discord
from discord import app_commands

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

# Il registro di controllo di Discord accetta un motivo di 512
# caratteri al massimo (LIM-8). Dichiararlo sull'opzione fa rifiutare
# il testo troppo lungo a Discord, prima che arrivi al bot.
MAX_REASON_LENGTH = 512
Reason = app_commands.Range[str, 3, MAX_REASON_LENGTH]


def audit_reason(text: str) -> str:
    """
    Taglia a 512 caratteri un motivo destinato al registro di
    controllo. Serve quando il bot aggiunge un prefisso al motivo
    scritto dal moderatore (es. "Softban: …").
    """
    if len(text) <= MAX_REASON_LENGTH:
        return text
    return text[: MAX_REASON_LENGTH - 1] + "…"


# Limiti di un embed (LIM-8): la descrizione tiene 4096 caratteri, un
# campo 1024. Gli elenchi si fermano a 4000 per lasciare posto alla
# riga "…e altri N".
MAX_LIST_LENGTH = 4000
MAX_FIELD_LENGTH = 1024
MAX_LINE_TEXT_LENGTH = 300


def truncate_text(text: str, limit: int) -> str:
    """Taglia il testo a `limit` caratteri, con "…" in fondo se tagliato."""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def join_within_limit(
    lines: list[str], left_out_text: str, limit: int = MAX_LIST_LENGTH
) -> str:
    """
    Unisce le righe (separate da una riga vuota) finché stanno in
    `limit` caratteri. Se qualcuna resta fuori aggiunge
    `left_out_text`, dove "{n}" diventa il numero delle escluse
    (es. "…e altri {n} casi.").
    """
    shown: list[str] = []
    length = 0
    for line in lines:
        length += len(line) + 2  # 2 = la riga vuota che separa le voci
        if length > limit:
            break
        shown.append(line)

    text = "\n\n".join(shown)
    left_out = len(lines) - len(shown)
    if left_out:
        text += "\n\n" + left_out_text.format(n=left_out)
    return text


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
