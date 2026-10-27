"""
cogs/logging/advanced_logs.py
=================================
Logging Avanzato (SPEC.md §8.6-§8.15) — livello Premium del Logging,
distinto dal Logging semplificato SEMPRE GRATUITO di
`cogs/logging/basic_logs.py` (SPEC.md §8.17). Questi eventi arrivano nella
destinazione scelta con `/log canale` (tipo «server» per canali, inviti,
webhook, emoji, sticker, thread, soundboard e impostazioni; tipo «voce» per
le entrate e uscite dai vocali) solo se il server ha acceso e sbloccato
`MODULE_LOGGING_ADVANCED`. Il controllo sta in `logging_avanzato_attivo`:
ogni listener lo chiama prima di scrivere. Dove scrive lo decide
`core/channel_router.py` (canale di testo o forum).

Copre: 8.6 Role update, 8.7 Channel create/delete/update (gli spostamenti
di posizione arrivano in un solo messaggio; i canali offuscati
`___hidden___` sono ignorati), 8.8 Invite create/delete/use, 8.9 Voice
state (mute e sordità proprie distinte da quelle del server), 8.10
Webhook, 8.11 Emoji, 8.12 Sticker, 8.13 Soundboard (eventi gateway di
discord.py), 8.14 Thread, 8.15 Server update, 8.18 messaggi fissati e
chi scollega o sposta a forza in vocale (LOG-006, LOG-012, dal registro
di controllo). Ogni evento si può spegnere (LOG-017). Ogni evento viene anche
salvato nel log eventi unificato (core/repositories/event_log_repo.py).
I messaggi cancellati e modificati (8.16) stanno in
`cogs/logging/message_logs.py`.

**8.8 "use"**: usa `invite_tracker.resolve_join_invite()`, non
`find_used_invite()`: quest'ultimo muta la propria cache a ogni chiamata,
mentre `resolve_join_invite()` dà la stessa risposta a tutti i moduli per
lo stesso ingresso (vedi core/invite_tracker.py).
"""

from __future__ import annotations

import asyncio
import logging
import time

import discord
from discord.ext import commands

from core import channel_router as router
from core.channel_router import SETTING_LOG_CHANNEL, TIPO_MESSAGGI, TIPO_SERVER, TIPO_VOCE
from core.bounded_cache import BoundedCache
from core.database import db
from core.premium_cache import registra_invalidatore
from core.invite_tracker import invite_tracker
from core.logging_advanced_logic import (
    CHANNEL_TRACKED_KEYS,
    GUILD_TRACKED_KEYS,
    ROLE_TRACKED_KEYS,
    THREAD_TRACKED_KEYS,
    classify_voice_state_change,
    diff_attributes,
    diff_named_items,
    diff_overwrites,
    menzione_bersaglio,
)
from core.testo_limiti import DESCRIZIONE_MAX, tronca
from core.premium import registry
from core.repositories.event_log_repo import event_log_repo
from core.repositories.log_eventi_repo import log_eventi_repo
from core.security_access import premium_sbloccato

logger = logging.getLogger("iyokai.advanced_logs")

MODULE_LOGGING_ADVANCED = "logging_advanced"

# Gli spostamenti di canale fatti insieme (trascinare un canale cambia la
# posizione di molti altri) arrivano in un solo messaggio dopo questa attesa.
SPOSTAMENTI_ATTESA_SECONDI = 5
# Mute e sordità scelti dall'utente si registrano al massimo una volta al minuto
# per utente e tipo: chi attiva e disattiva il microfono non riempie il canale.
VOCE_PROPRIO_ATTESA_SECONDI = 60

PREMIUM_CACHE_TTL_SECONDS = 60
_monotonic = time.monotonic
# guild_id -> (scadenza, sbloccato)
_premium_cache: BoundedCache[int, tuple[float, bool]] = BoundedCache(10_000)
# Sale a ogni invalidazione: un verdetto letto PRIMA di uno sblocco non si scrive DOPO l'invalida
# (stesso schema di `_versione_cache` in core/database.py).
_versione_verdetto = 0
# (guild_id, user_id, evento) -> ultimo istante registrato
_voce_propria_cache: BoundedCache[tuple[int, int, str], float] = BoundedCache(10_000)

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
    "voice_stage_create": ("🎙️ Palco aperto", discord.Color.green()),
    "voice_stage_update": ("🎙️ Palco modificato", discord.Color.blurple()),
    "voice_stage_delete": ("🎙️ Palco chiuso", discord.Color.red()),
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
    "voice_mute": ("🔇 Mutato dal server", discord.Color.orange()),
    "voice_unmute": ("🔊 Smutato dal server", discord.Color.green()),
    "voice_deafen": ("🔇 Assordato dal server", discord.Color.orange()),
    "voice_undeafen": ("🔊 Non più assordato dal server", discord.Color.green()),
    "voice_self_mute": ("🎙️ Si è mutato da solo", discord.Color.light_grey()),
    "voice_self_unmute": ("🎙️ Ha riattivato il microfono", discord.Color.light_grey()),
    "voice_self_deafen": ("🎧 Si è assordato da solo", discord.Color.light_grey()),
    "voice_self_undeafen": ("🎧 Ha riattivato l'audio", discord.Color.light_grey()),
    "channel_move": ("↕️ Canali spostati", discord.Color.blurple()),
    "message_pin": ("📌 Messaggio fissato", discord.Color.blurple()),
    "message_unpin": ("📌 Messaggio tolto dai fissati", discord.Color.light_grey()),
    "voice_force_move": ("🔀 Spostato da un moderatore", discord.Color.orange()),
    "voice_force_disconnect": ("⏏️ Scollegato da un moderatore", discord.Color.orange()),
    "soundboard_sound_create": ("🔔 Suono soundboard creato", discord.Color.green()),
    "soundboard_sound_update": ("🔔 Suono soundboard modificato", discord.Color.blurple()),
    "soundboard_sound_delete": ("🔔 Suono soundboard eliminato", discord.Color.red()),
}

_EVENTI_REGISTRO = {
    discord.AuditLogAction.message_pin: "message_pin",
    discord.AuditLogAction.message_unpin: "message_unpin",
    discord.AuditLogAction.member_move: "voice_force_move",
    discord.AuditLogAction.member_disconnect: "voice_force_disconnect",
}


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


def _overwrites_snapshot(channel) -> dict[str, tuple[int, int]]:
    """Permessi del canale per ruolo e utente: {«ruolo:ID»: (concessi, negati)}."""
    istantanea = {}
    for bersaglio, sovrascrittura in (getattr(channel, "overwrites", None) or {}).items():
        concessi, negati = sovrascrittura.pair()
        genere = "ruolo" if isinstance(bersaglio, discord.Role) else "utente"
        istantanea[f"{genere}:{bersaglio.id}"] = (concessi.value, negati.value)
    return istantanea


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
    # mute/deaf: decisi da un moderatore; self_*: scelti dall'utente.
    return {
        "channel_id": state.channel.id if state.channel is not None else None,
        "mute": bool(state.mute),
        "deaf": bool(state.deaf),
        "self_mute": bool(state.self_mute),
        "self_deaf": bool(state.self_deaf),
    }


async def logging_avanzato_attivo(guild_id: int, bot=None) -> bool:
    """
    True se il server ha acceso il Logging Avanzato E può usarlo.
    Il modulo è premium-capable (M 3.14): quando l'owner lo rende premium,
    un server che non lo ha sbloccato smette di scrivere questi log, anche
    se il modulo risulta acceso. Stesso controllo degli altri moduli
    premium (core/security_access.premium_sbloccato). Ogni listener e il
    servizio soundboard lo chiamano PRIMA di scrivere nel database o in
    un canale.

    Il verdetto sul premium (3 query) si tiene in memoria per
    PREMIUM_CACHE_TTL_SECONDS per server, solo con il modulo premium e
    acceso. Whitelist, cassa, abbonamenti e flag del modulo passano da
    `core.premium_cache.invalida_cache_premium` (#145), che chiama
    `invalida_verdetto_premium`: sblocco e revoca valgono subito. Resta il
    TTL come rete di sicurezza (il boost del server principale non ha un
    punto di scrittura).
    """
    if not await db.is_module_active_for_guild(guild_id, MODULE_LOGGING_ADVANCED):
        return False
    if not registry.is_module_premium(MODULE_LOGGING_ADVANCED):
        return True
    adesso = _monotonic()
    voce = _premium_cache.get(guild_id)
    if voce is not None and voce[0] > adesso:
        return voce[1]
    versione = _versione_verdetto
    sbloccato = await premium_sbloccato(guild_id, MODULE_LOGGING_ADVANCED, bot)
    if versione == _versione_verdetto:  # nessuna invalidazione mentre leggevo
        _premium_cache.set(guild_id, (adesso + PREMIUM_CACHE_TTL_SECONDS, sbloccato))
    return sbloccato


def invalida_verdetto_premium(guild_id: int | None = None) -> None:
    """
    Dimentica il verdetto premium in memoria (di un server o di tutti): chi
    cambia whitelist, cassa o abbonamenti può chiamarla per far valere
    subito lo sblocco o la revoca, senza aspettare il TTL.
    """
    global _versione_verdetto
    _versione_verdetto += 1
    if guild_id is None:
        _premium_cache.clear()
    else:
        _premium_cache.delete(guild_id)


# #145: punto unico in core/premium_cache.py. Whitelist, cassa, abbonamenti e
# flag del modulo chiamano `invalida_cache_premium` e arrivano qui.
registra_invalidatore(invalida_verdetto_premium)


async def advanced_log_channel(guild: discord.Guild, tipo: str = TIPO_SERVER):
    """Destinazione (canale o post di un forum) del log avanzato `tipo`, o None."""
    enabled = await db.is_module_active_for_guild(guild.id, MODULE_LOGGING_ADVANCED)
    if not enabled:
        return None
    predefinito = await db.get_guild_setting(guild.id, SETTING_LOG_CHANNEL)
    return await router.destinazione(guild, tipo, predefinito)


async def send_event_embed(
    guild: discord.Guild, event_type: str, description: str, tipo: str | None = None
) -> None:
    if not await log_eventi_repo.evento_acceso(guild.id, event_type):
        return
    if tipo is None:
        tipo = TIPO_VOCE if event_type.startswith("voice_") else TIPO_SERVER
    channel = await advanced_log_channel(guild, tipo)
    if channel is None:
        return
    title, color = EVENT_TITLES.get(event_type, (event_type, discord.Color.default()))
    embed = discord.Embed(
        title=title,
        description=tronca(description, DESCRIZIONE_MAX),
        color=color,
        timestamp=discord.utils.utcnow(),
    )
    await router.invia_a(channel, guild, tipo, embed=embed)


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
        # guild_id -> canali spostati in attesa del messaggio unico
        self._spostamenti: dict[int, list[tuple[int, int, int]]] = {}
        self._invii_spostamenti: set[asyncio.Task] = set()

    def cog_unload(self) -> None:
        for compito in self._invii_spostamenti:
            compito.cancel()

    async def _accoda_spostamento(self, guild: discord.Guild, channel_id: int, da: int, a: int) -> None:
        in_attesa = guild.id in self._spostamenti
        self._spostamenti.setdefault(guild.id, []).append((channel_id, da, a))
        if in_attesa:
            return
        compito = asyncio.create_task(self._scarica_spostamenti(guild))
        self._invii_spostamenti.add(compito)
        compito.add_done_callback(self._invii_spostamenti.discard)

    async def _scarica_spostamenti(self, guild: discord.Guild) -> None:
        await asyncio.sleep(SPOSTAMENTI_ATTESA_SECONDI)
        spostati = self._spostamenti.pop(guild.id, [])
        if not spostati:
            return
        righe = [f"<#{c}>: posizione {da} → {a}" for c, da, a in spostati]
        testo = f"**{len(spostati)}** canali spostati\n" + "\n".join(righe)
        await send_event_embed(guild, "channel_move", testo)

    # ================================================================
    # 8.6 Ruoli — modifica (creazione/eliminazione già in basic_logs)
    # ================================================================
    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        if not await logging_avanzato_attivo(after.guild.id, self.bot):
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
        if router.canale_nascosto(channel):
            return
        if not await logging_avanzato_attivo(channel.guild.id, self.bot):
            return
        await event_log_repo.log_event(
            channel.guild.id, "channel_create", channel_id=channel.id, details={"name": channel.name}
        )
        await send_event_embed(channel.guild, "channel_create", f"`#{channel.name}` ({channel.id})")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if router.canale_nascosto(channel):
            return
        if not await logging_avanzato_attivo(channel.guild.id, self.bot):
            return
        await event_log_repo.log_event(
            channel.guild.id, "channel_delete", channel_id=channel.id, details={"name": channel.name}
        )
        await send_event_embed(channel.guild, "channel_delete", f"`#{channel.name}` ({channel.id})")

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ) -> None:
        # LIM-38: quando il bot perde o prende accesso a un canale cambia solo il nome finto.
        if router.canale_nascosto(before) or router.canale_nascosto(after):
            return
        if not await logging_avanzato_attivo(after.guild.id, self.bot):
            return
        changes = diff_attributes(_channel_snapshot(before), _channel_snapshot(after), CHANNEL_TRACKED_KEYS)
        permessi = diff_overwrites(_overwrites_snapshot(before), _overwrites_snapshot(after))
        if permessi:
            changes["permessi"] = permessi
        if not changes:
            return
        await event_log_repo.log_event(
            after.guild.id, "channel_update", channel_id=after.id, details=changes
        )
        if set(changes) == {"position"}:
            await self._accoda_spostamento(
                after.guild, after.id, changes["position"]["before"], changes["position"]["after"]
            )
            return
        testo = f"<#{after.id}>\n" + ", ".join(changes.keys())
        for gruppo, voci in permessi.items():
            testo += f"\nPermessi {gruppo}: " + ", ".join(menzione_bersaglio(v) for v in voci)
        await send_event_embed(after.guild, "channel_update", testo)

    # ================================================================
    # 8.8 Inviti (create/delete/use — "use" via resolve_join_invite,
    # vedi nota in cima al file)
    # ================================================================
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not await logging_avanzato_attivo(member.guild.id, self.bot):
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
        if guild is None or not await logging_avanzato_attivo(guild.id, self.bot):
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
        if guild is None or not await logging_avanzato_attivo(guild.id, self.bot):
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
        if not await logging_avanzato_attivo(member.guild.id, self.bot):
            return
        eventi = classify_voice_state_change(_voice_state_snapshot(before), _voice_state_snapshot(after))
        for event_type in eventi:
            if event_type.startswith("voice_self_") and self._troppo_presto(member, event_type):
                continue
            canale_rilevante = after.channel or before.channel
            await event_log_repo.log_event(
                member.guild.id,
                event_type,
                target_user_id=member.id,
                channel_id=canale_rilevante.id if canale_rilevante is not None else None,
            )
            await send_event_embed(member.guild, event_type, f"{member.mention}")

    @staticmethod
    def _troppo_presto(member: discord.Member, event_type: str) -> bool:
        chiave = (member.guild.id, member.id, event_type)
        adesso = _monotonic()
        ultimo = _voce_propria_cache.get(chiave)
        if ultimo is not None and adesso - ultimo < VOCE_PROPRIO_ATTESA_SECONDI:
            return True
        _voce_propria_cache.set(chiave, adesso)
        return False

    # ================================================================
    # 8.10 Webhook
    # ================================================================
    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel) -> None:
        if not await logging_avanzato_attivo(channel.guild.id, self.bot):
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
        if not await logging_avanzato_attivo(guild.id, self.bot):
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
        if not await logging_avanzato_attivo(guild.id, self.bot):
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
    # 8.13 Soundboard (eventi gateway di discord.py)
    # ================================================================
    async def _log_soundboard(self, sound, event_type: str, attore: int | None) -> None:
        guild = getattr(sound, "guild", None)
        if guild is None or not await logging_avanzato_attivo(guild.id, self.bot):
            return
        await event_log_repo.log_event(
            guild.id, event_type, actor_id=attore, details={"name": sound.name}
        )
        descrizione = f"`{sound.name}`" + (f" — <@{attore}>" if attore else "")
        await send_event_embed(guild, event_type, descrizione)

    @commands.Cog.listener()
    async def on_soundboard_sound_create(self, sound) -> None:
        utente = getattr(sound, "user", None)
        await self._log_soundboard(sound, "soundboard_sound_create", utente.id if utente else None)

    @commands.Cog.listener()
    async def on_soundboard_sound_update(self, before, after) -> None:
        await self._log_soundboard(after, "soundboard_sound_update", None)

    @commands.Cog.listener()
    async def on_soundboard_sound_delete(self, sound) -> None:
        await self._log_soundboard(sound, "soundboard_sound_delete", None)

    # ================================================================
    # 8.14 Thread
    # ================================================================
    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        if not await logging_avanzato_attivo(thread.guild.id, self.bot):
            return
        await event_log_repo.log_event(
            thread.guild.id, "thread_create", channel_id=thread.id, details={"name": thread.name}
        )
        await send_event_embed(thread.guild, "thread_create", f"`{thread.name}`")

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread) -> None:
        if not await logging_avanzato_attivo(thread.guild.id, self.bot):
            return
        await event_log_repo.log_event(
            thread.guild.id, "thread_delete", channel_id=thread.id, details={"name": thread.name}
        )
        await send_event_embed(thread.guild, "thread_delete", f"`{thread.name}`")

    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread) -> None:
        if not await logging_avanzato_attivo(after.guild.id, self.bot):
            return
        changes = diff_attributes(_thread_snapshot(before), _thread_snapshot(after), THREAD_TRACKED_KEYS)
        if not changes:
            return
        await event_log_repo.log_event(
            after.guild.id, "thread_update", channel_id=after.id, details=changes
        )
        await send_event_embed(after.guild, "thread_update", f"`{after.name}`\n" + ", ".join(changes.keys()))

    # ================================================================
    # LOG-013 Palchi (stage): apertura, modifica, chiusura. Tipo «voce».
    # ================================================================
    @commands.Cog.listener()
    async def on_stage_instance_create(self, stage: discord.StageInstance) -> None:
        await self._log_stage(stage, "voice_stage_create", f"`{stage.topic}` in <#{stage.channel_id}>")

    @commands.Cog.listener()
    async def on_stage_instance_delete(self, stage: discord.StageInstance) -> None:
        await self._log_stage(stage, "voice_stage_delete", f"`{stage.topic}` in <#{stage.channel_id}>")

    @commands.Cog.listener()
    async def on_stage_instance_update(self, before: discord.StageInstance, after: discord.StageInstance) -> None:
        if before.topic == after.topic and before.privacy_level == after.privacy_level:
            return
        await self._log_stage(
            after, "voice_stage_update", f"<#{after.channel_id}>\n`{before.topic}` → `{after.topic}`"
        )

    async def _log_stage(self, stage: discord.StageInstance, event_type: str, descrizione: str) -> None:
        guild = stage.guild
        if guild is None or not await logging_avanzato_attivo(guild.id, self.bot):
            return
        await event_log_repo.log_event(
            guild.id, event_type, channel_id=stage.channel_id, details={"topic": stage.topic}
        )
        await send_event_embed(guild, event_type, descrizione)

    # ================================================================
    # LOG-006 messaggi fissati e tolti; LOG-012 chi scollega o sposta a forza
    # in vocale. Dal registro di controllo (serve «Visualizzare il registro»).
    # Discord unisce gli spostamenti ripetuti dello stesso moderatore in una
    # voce sola: si scrive solo la prima.
    # ================================================================
    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry) -> None:
        evento = _EVENTI_REGISTRO.get(entry.action)
        if evento is None or not await logging_avanzato_attivo(entry.guild.id, self.bot):
            return
        canale = getattr(entry.extra, "channel", None)
        if canale is not None and router.canale_nascosto(canale):
            return
        canale_id = getattr(canale, "id", None)
        autore = f"<@{entry.user_id}>" if entry.user_id else "qualcuno"
        bersaglio = getattr(entry.target, "id", None)
        if evento in ("message_pin", "message_unpin"):
            descrizione = (
                f"{autore} in <#{canale_id}>: messaggio `{getattr(entry.extra, 'message_id', '?')}`"
                + (f" di <@{bersaglio}>" if bersaglio else "")
            )
            tipo = TIPO_MESSAGGI
        elif evento == "voice_force_move":
            descrizione = f"{autore} ha spostato un membro in <#{canale_id}>"
            tipo = TIPO_VOCE
        else:
            descrizione = f"{autore} ha scollegato un membro da un canale vocale"
            tipo = TIPO_VOCE
        await event_log_repo.log_event(
            entry.guild.id, evento, actor_id=entry.user_id, target_user_id=bersaglio, channel_id=canale_id,
            details={"message_id": getattr(entry.extra, "message_id", None)},
        )
        await send_event_embed(entry.guild, evento, descrizione, tipo=tipo)

    # ================================================================
    # 8.15 Server (impostazioni guild)
    # ================================================================
    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        if not await logging_avanzato_attivo(after.id, self.bot):
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
            category="logging",
            description=(
                "Log completo: ruoli, canali, inviti, voce, webhook, emoji, "
                "sticker, thread e impostazioni server (livello Premium del Logging)."
            ),
            premium_capable=True,
        )
    )
    await bot.add_cog(AdvancedLogsCog(bot))
