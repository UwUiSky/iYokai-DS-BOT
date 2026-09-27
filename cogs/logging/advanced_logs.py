"""
cogs/logging/advanced_logs.py
=================================
Logging Avanzato (SPEC.md §8.6-§8.15) — livello Premium del Logging,
distinto dal Logging semplificato SEMPRE GRATUITO di
`cogs/logging/basic_logs.py` (SPEC.md §8.17, "Distinzione log
semplificato [Free] vs completo [Premium]"). Stesso canale di log già
configurato con `/logs-setup` (SETTING_LOG_CHANNEL, riusato — non
serve un secondo comando di setup per un secondo canale), ma questi
eventi arrivano lì SOLO se il server ha sbloccato/attivato anche
`MODULE_LOGGING_ADVANCED`.

Copre: 8.6 Role update, 8.7 Channel create/delete/update, 8.8 Invite
create/delete/use, 8.9 Voice state, 8.10 Webhook, 8.11 Emoji, 8.12
Sticker, 8.14 Thread, 8.15 Server update. Ogni evento viene anche
salvato nel log eventi unificato (core/repositories/event_log_repo.py),
stesso principio di basic_logs.py.

**8.8 "use"**: usa `invite_tracker.resolve_join_invite()`, non
`find_used_invite()` direttamente — quest'ultimo MUTA la propria
cache ad ogni chiamata (aggiorna l'istantanea per il prossimo
confronto), quindi chiamarlo da qui E da Spam Trap sullo STESSO
evento di join avrebbe fatto sì che la seconda chiamata vedesse il
diff già "consumato" dalla prima, restituendo `None` in modo
imprevedibile. `resolve_join_invite()` (vedi la nota architetturale
in core/invite_tracker.py) risolve questo con un lock + cache per
coppia (server, membro): la prima chiamata per un dato join fa il
lavoro reale, ogni altra chiamata per lo stesso join — da qualunque
modulo, in qualunque ordine — riceve la stessa risposta.

**8.13 Soundboard — coperto, ma non da un listener di questo file**:
la prima analisi (Fase 70) concludeva erroneamente che fosse
bloccato — vero solo per gli eventi GATEWAY (`on_webhooks_update` e
simili non esistono per il soundboard). L'AUDIT LOG del server SI
registra `soundboard_sound_create/update/delete`
(`discord.AuditLogAction`, verificato leggendo l'enum reale
installata), quindi è recuperabile — solo non via un evento push,
via polling periodico. Costruito come servizio a parte,
`core/soundboard_log_service.py` (stesso pattern di
`core/event_log_retention.py`: un `tasks.loop`, non un listener),
perché un Cog di questo file reagisce a eventi che Discord manda da
solo — l'audit log va invece INTERROGATO a intervalli. Le funzioni
`advanced_log_channel`/`send_event_embed`/`EVENT_TITLES` di questo
file sono condivise (non più `_private`) apposta per essere riusate
da quel servizio, invece di duplicarle.

**8.16 Message delete/edit resta fuori per scelta esplicita** (serve
il Message Content Intent, vedi § Decisioni in SPEC.md) — non
toccato da questo file.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from cogs.logging.basic_logs import SETTING_LOG_CHANNEL
from core.database import db
from core.invite_tracker import invite_tracker
from core.logging_advanced_logic import (
    CHANNEL_TRACKED_KEYS,
    GUILD_TRACKED_KEYS,
    ROLE_TRACKED_KEYS,
    THREAD_TRACKED_KEYS,
    classify_voice_state_change,
    diff_attributes,
    diff_named_items,
)
from core.repositories.event_log_repo import event_log_repo

logger = logging.getLogger("iyokai.advanced_logs")

MODULE_LOGGING_ADVANCED = "logging_advanced"

# Stessa finestra di tolleranza già usata in cogs/security/anti_nuke.py
# per risolvere l'autore di un evento via audit log (l'evento gateway
# stesso non lo include mai).
_AUDIT_LOG_LOOKBACK_SECONDS = 10

_WEBHOOK_ACTIONS = {
    discord.AuditLogAction.webhook_create: "webhook_create",
    discord.AuditLogAction.webhook_update: "webhook_update",
    discord.AuditLogAction.webhook_delete: "webhook_delete",
}

EVENT_TITLES = {
    "role_edit": ("🎨 Ruolo modificato", discord.Color.blurple()),
    "channel_create": ("➕ Canale creato", discord.Color.green()),
    "channel_delete": ("➖ Canale eliminato", discord.Color.red()),
    "channel_update": ("✏️ Canale modificato", discord.Color.blurple()),
    "invite_create": ("🔗 Invito creato", discord.Color.green()),
    "invite_delete": ("🔗 Invito eliminato", discord.Color.red()),
    "invite_use": ("🔗 Invito usato", discord.Color.blurple()),
    "webhook_create": ("🪝 Webhook creato", discord.Color.green()),
    "webhook_update": ("🪝 Webhook modificato", discord.Color.blurple()),
    "webhook_delete": ("🪝 Webhook eliminato", discord.Color.red()),
    "emoji_create": ("😀 Emoji creata", discord.Color.green()),
    "emoji_delete": ("😀 Emoji eliminata", discord.Color.red()),
    "emoji_update": ("😀 Emoji rinominata", discord.Color.blurple()),
    "sticker_create": ("🏷️ Sticker creato", discord.Color.green()),
    "sticker_delete": ("🏷️ Sticker eliminato", discord.Color.red()),
    "sticker_update": ("🏷️ Sticker rinominato", discord.Color.blurple()),
    "thread_create": ("🧵 Thread creato", discord.Color.green()),
    "thread_delete": ("🧵 Thread eliminato", discord.Color.red()),
    "thread_update": ("🧵 Thread modificato", discord.Color.blurple()),
    "guild_update": ("⚙️ Impostazioni server modificate", discord.Color.blurple()),
    "voice_join": ("🔊 Entrato in un canale vocale", discord.Color.green()),
    "voice_leave": ("🔈 Uscito da un canale vocale", discord.Color.orange()),
    "voice_move": ("🔀 Spostato di canale vocale", discord.Color.blurple()),
    "voice_mute": ("🔇 Mutato (server)", discord.Color.orange()),
    "voice_unmute": ("🔊 Smutato (server)", discord.Color.green()),
    "voice_deafen": ("🔇 Assordato (server)", discord.Color.orange()),
    "voice_undeafen": ("🔊 Non più assordato (server)", discord.Color.green()),
    "soundboard_sound_create": ("🔔 Suono soundboard creato", discord.Color.green()),
    "soundboard_sound_update": ("🔔 Suono soundboard modificato", discord.Color.blurple()),
    "soundboard_sound_delete": ("🔔 Suono soundboard eliminato", discord.Color.red()),
}

# Guild setting generico (stesso meccanismo di SETTING_LOG_CHANNEL)
# dove core/soundboard_log_service.py salva il "watermark" — il
# timestamp dell'ultima voce di audit log soundboard già processata,
# per non ri-loggare la stessa voce al prossimo giro di polling né,
# alla primissima attivazione, riversare tutto lo storico esistente.
SETTING_SOUNDBOARD_WATERMARK = "logging_soundboard_watermark"


def _role_snapshot(role: discord.Role) -> dict:
    return {
        "name": role.name,
        "color": role.color.value,
        "hoist": role.hoist,
        "mentionable": role.mentionable,
        "permissions": role.permissions.value,
    }


def _channel_snapshot(channel) -> dict:
    return {
        "name": getattr(channel, "name", None),
        "category_id": getattr(channel, "category_id", None),
        "topic": getattr(channel, "topic", None),
        "nsfw": getattr(channel, "nsfw", False),
        "slowmode_delay": getattr(channel, "slowmode_delay", 0),
        "position": getattr(channel, "position", 0),
    }


def _guild_snapshot(guild: discord.Guild) -> dict:
    return {
        "name": guild.name,
        "icon": guild.icon.key if guild.icon else None,
        "verification_level": str(guild.verification_level),
        "afk_channel_id": guild.afk_channel.id if guild.afk_channel else None,
        "system_channel_id": guild.system_channel.id if guild.system_channel else None,
        "explicit_content_filter": str(guild.explicit_content_filter),
    }


def _thread_snapshot(thread: discord.Thread) -> dict:
    return {"name": thread.name, "archived": thread.archived, "locked": thread.locked}


def _voice_state_snapshot(state: discord.VoiceState) -> dict:
    # Semplificazione dichiarata: "mute"/"deaf" qui è lo stato
    # EFFETTIVO (server-mute/deafen OPPURE self-mute/self-deafen), non
    # le quattro variabili distinte di discord.py — un log leggibile
    # si chiede "è muto?", non "chi/come l'ha mutato".
    return {
        "channel_id": state.channel.id if state.channel is not None else None,
        "mute": bool(state.mute or state.self_mute),
        "deaf": bool(state.deaf or state.self_deaf),
    }


async def advanced_log_channel(guild: discord.Guild) -> discord.TextChannel | None:
    enabled = await db.is_module_active_for_guild(guild.id, MODULE_LOGGING_ADVANCED)
    if not enabled:
        return None
    channel_id = await db.get_guild_setting(guild.id, SETTING_LOG_CHANNEL)
    if channel_id is None:
        return None
    channel = guild.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        return None
    return channel


async def send_event_embed(
    guild: discord.Guild, event_type: str, description: str
) -> None:
    channel = await advanced_log_channel(guild)
    if channel is None:
        return
    title, color = EVENT_TITLES.get(event_type, (event_type, discord.Color.default()))
    embed = discord.Embed(
        title=title, description=description, color=color, timestamp=discord.utils.utcnow()
    )
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass


async def _resolve_webhook_change(
    channel: discord.abc.GuildChannel,
) -> tuple[str, int | None] | None:
    """
    L'evento gateway `on_webhooks_update` avvisa solo che "qualcosa"
    è cambiato nei webhook di un canale — nessuna distinzione
    create/update/delete, nessun autore. Risolto via audit log,
    stesso principio di `_resolve_actor` in cogs/security/anti_nuke.py:
    tre azioni possibili, si tiene la più recente entro la finestra
    di tolleranza.
    """
    now = discord.utils.utcnow()
    candidati = []
    for action, event_type in _WEBHOOK_ACTIONS.items():
        try:
            async for entry in channel.guild.audit_logs(action=action, limit=1):
                if (now - entry.created_at).total_seconds() <= _AUDIT_LOG_LOOKBACK_SECONDS:
                    candidati.append((entry.created_at, event_type, entry.user_id))
        except discord.Forbidden:
            continue
    if not candidati:
        return None
    candidati.sort(key=lambda c: c[0], reverse=True)
    _, event_type, actor_id = candidati[0]
    return event_type, actor_id


class AdvancedLogsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ================================================================
    # 8.6 Ruoli — modifica (creazione/eliminazione già in basic_logs)
    # ================================================================
    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        if not await db.is_module_active_for_guild(after.guild.id, MODULE_LOGGING_ADVANCED):
            return
        changes = diff_attributes(_role_snapshot(before), _role_snapshot(after), ROLE_TRACKED_KEYS)
        if not changes:
            return
        await event_log_repo.log_event(
            after.guild.id, "role_edit", role_id=after.id, details=changes
        )
        await send_event_embed(
            after.guild, "role_edit", f"{after.mention}\n" + ", ".join(changes.keys())
        )

    # ================================================================
    # 8.7 Canali
    # ================================================================
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        if not await db.is_module_active_for_guild(channel.guild.id, MODULE_LOGGING_ADVANCED):
            return
        await event_log_repo.log_event(
            channel.guild.id, "channel_create", channel_id=channel.id, details={"name": channel.name}
        )
        await send_event_embed(channel.guild, "channel_create", f"`#{channel.name}` ({channel.id})")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if not await db.is_module_active_for_guild(channel.guild.id, MODULE_LOGGING_ADVANCED):
            return
        await event_log_repo.log_event(
            channel.guild.id, "channel_delete", channel_id=channel.id, details={"name": channel.name}
        )
        await send_event_embed(channel.guild, "channel_delete", f"`#{channel.name}` ({channel.id})")

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ) -> None:
        if not await db.is_module_active_for_guild(after.guild.id, MODULE_LOGGING_ADVANCED):
            return
        changes = diff_attributes(_channel_snapshot(before), _channel_snapshot(after), CHANNEL_TRACKED_KEYS)
        if not changes:
            return
        await event_log_repo.log_event(
            after.guild.id, "channel_update", channel_id=after.id, details=changes
        )
        await send_event_embed(
            after.guild, "channel_update", f"<#{after.id}>\n" + ", ".join(changes.keys())
        )

    # ================================================================
    # 8.8 Inviti (create/delete/use — "use" via resolve_join_invite,
    # vedi nota in cima al file)
    # ================================================================
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not await db.is_module_active_for_guild(member.guild.id, MODULE_LOGGING_ADVANCED):
            return
        risultato = await invite_tracker.resolve_join_invite(member.guild, member.id)
        if risultato is None:
            return
        codice, creator_id = risultato
        await event_log_repo.log_event(
            member.guild.id,
            "invite_use",
            actor_id=creator_id,
            target_user_id=member.id,
            details={"code": codice},
        )
        descrizione = f"{member.mention} tramite `{codice}`"
        if creator_id is not None:
            descrizione += f" (creato da <@{creator_id}>)"
        await send_event_embed(member.guild, "invite_use", descrizione)


    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        guild = invite.guild
        if guild is None or not await db.is_module_active_for_guild(guild.id, MODULE_LOGGING_ADVANCED):
            return
        await event_log_repo.log_event(
            guild.id,
            "invite_create",
            actor_id=invite.inviter.id if invite.inviter else None,
            channel_id=invite.channel.id if invite.channel else None,
            details={"code": invite.code},
        )
        await send_event_embed(guild, "invite_create", f"`{invite.code}`")

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        guild = invite.guild
        if guild is None or not await db.is_module_active_for_guild(guild.id, MODULE_LOGGING_ADVANCED):
            return
        await event_log_repo.log_event(
            guild.id,
            "invite_delete",
            channel_id=invite.channel.id if invite.channel else None,
            details={"code": invite.code},
        )
        await send_event_embed(guild, "invite_delete", f"`{invite.code}`")

    # ================================================================
    # 8.9 Voice state
    # ================================================================
    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        if not await db.is_module_active_for_guild(member.guild.id, MODULE_LOGGING_ADVANCED):
            return
        eventi = classify_voice_state_change(_voice_state_snapshot(before), _voice_state_snapshot(after))
        for event_type in eventi:
            canale_rilevante = after.channel or before.channel
            await event_log_repo.log_event(
                member.guild.id,
                event_type,
                target_user_id=member.id,
                channel_id=canale_rilevante.id if canale_rilevante is not None else None,
            )
            await send_event_embed(member.guild, event_type, f"{member.mention}")

    # ================================================================
    # 8.10 Webhook
    # ================================================================
    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel) -> None:
        if not await db.is_module_active_for_guild(channel.guild.id, MODULE_LOGGING_ADVANCED):
            return
        risultato = await _resolve_webhook_change(channel)
        if risultato is None:
            return
        event_type, actor_id = risultato
        await event_log_repo.log_event(
            channel.guild.id, event_type, actor_id=actor_id, channel_id=channel.id
        )
        descrizione = f"<#{channel.id}>" + (f" — <@{actor_id}>" if actor_id else "")
        await send_event_embed(channel.guild, event_type, descrizione)

    # ================================================================
    # 8.11 Emoji
    # ================================================================
    @commands.Cog.listener()
    async def on_guild_emojis_update(
        self, guild: discord.Guild, before: list, after: list
    ) -> None:
        if not await db.is_module_active_for_guild(guild.id, MODULE_LOGGING_ADVANCED):
            return
        diff = diff_named_items({e.id: e.name for e in before}, {e.id: e.name for e in after})
        for item in diff["created"]:
            await event_log_repo.log_event(guild.id, "emoji_create", details=item)
            await send_event_embed(guild, "emoji_create", f"`{item['name']}`")
        for item in diff["deleted"]:
            await event_log_repo.log_event(guild.id, "emoji_delete", details=item)
            await send_event_embed(guild, "emoji_delete", f"`{item['name']}`")
        for item in diff["renamed"]:
            await event_log_repo.log_event(guild.id, "emoji_update", details=item)
            await send_event_embed(guild, "emoji_update", f"`{item['before']}` → `{item['after']}`")

    # ================================================================
    # 8.12 Sticker
    # ================================================================
    @commands.Cog.listener()
    async def on_guild_stickers_update(
        self, guild: discord.Guild, before: list, after: list
    ) -> None:
        if not await db.is_module_active_for_guild(guild.id, MODULE_LOGGING_ADVANCED):
            return
        diff = diff_named_items({s.id: s.name for s in before}, {s.id: s.name for s in after})
        for item in diff["created"]:
            await event_log_repo.log_event(guild.id, "sticker_create", details=item)
            await send_event_embed(guild, "sticker_create", f"`{item['name']}`")
        for item in diff["deleted"]:
            await event_log_repo.log_event(guild.id, "sticker_delete", details=item)
            await send_event_embed(guild, "sticker_delete", f"`{item['name']}`")
        for item in diff["renamed"]:
            await event_log_repo.log_event(guild.id, "sticker_update", details=item)
            await send_event_embed(guild, "sticker_update", f"`{item['before']}` → `{item['after']}`")

    # ================================================================
    # 8.14 Thread
    # ================================================================
    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        if not await db.is_module_active_for_guild(thread.guild.id, MODULE_LOGGING_ADVANCED):
            return
        await event_log_repo.log_event(
            thread.guild.id, "thread_create", channel_id=thread.id, details={"name": thread.name}
        )
        await send_event_embed(thread.guild, "thread_create", f"`{thread.name}`")

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread) -> None:
        if not await db.is_module_active_for_guild(thread.guild.id, MODULE_LOGGING_ADVANCED):
            return
        await event_log_repo.log_event(
            thread.guild.id, "thread_delete", channel_id=thread.id, details={"name": thread.name}
        )
        await send_event_embed(thread.guild, "thread_delete", f"`{thread.name}`")

    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread) -> None:
        if not await db.is_module_active_for_guild(after.guild.id, MODULE_LOGGING_ADVANCED):
            return
        changes = diff_attributes(_thread_snapshot(before), _thread_snapshot(after), THREAD_TRACKED_KEYS)
        if not changes:
            return
        await event_log_repo.log_event(
            after.guild.id, "thread_update", channel_id=after.id, details=changes
        )
        await send_event_embed(after.guild, "thread_update", f"`{after.name}`\n" + ", ".join(changes.keys()))

    # ================================================================
    # 8.15 Server (impostazioni guild)
    # ================================================================
    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        if not await db.is_module_active_for_guild(after.id, MODULE_LOGGING_ADVANCED):
            return
        changes = diff_attributes(_guild_snapshot(before), _guild_snapshot(after), GUILD_TRACKED_KEYS)
        if not changes:
            return
        await event_log_repo.log_event(after.id, "guild_update", details=changes)
        await send_event_embed(after, "guild_update", ", ".join(changes.keys()))


async def setup(bot: commands.Bot) -> None:
    from core.premium import PremiumModule, registry

    registry.register(
        PremiumModule(
            name=MODULE_LOGGING_ADVANCED,
            display_name="Logging Avanzato",
            description=(
                "Log completo: ruoli, canali, inviti, voce, webhook, emoji, "
                "sticker, thread e impostazioni server (livello Premium del Logging)."
            ),
            premium_capable=True,
        )
    )
    await bot.add_cog(AdvancedLogsCog(bot))
