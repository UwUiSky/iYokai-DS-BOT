"""
cogs/utility/snipe.py
========================
Snipe (ultimo messaggio cancellato) ed Editsnipe (ultima modifica) in un
canale, Reactionsnipe (ultima reazione tolta) e Ghost ping detection
(menzione e poi cancellazione). Tutto in memoria, mai su disco: i
messaggi si ricordano 5 minuti e solo nei server che accendono il modulo
`snipe` (privacy). Il ghost ping non scatta se un moderatore ha cancellato
il messaggio (registro di controllo).
Funzioni coperte: SPEC §14.9-§14.12 (NF-03, M 5.9)
Dipende da: core/snipe_logic.py, core/channel_router.py
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import discord
from discord.ext import commands

from core import channel_router as router
from core.bounded_cache import BoundedCache
from core.channel_router import SETTING_LOG_CHANNEL, TIPO_MESSAGGI
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.premium import PremiumModule, registry
from core.message_log_logic import da_ignorare
from core.repositories.log_ignora_repo import log_ignora_repo
from core.testo_limiti import CAMPO_MAX
from core.snipe_logic import (
    RicordiSnipe,
    VoceRegistro,
    cancellato_da_altri,
    is_ghost_ping_candidate,
    testo_snipe,
)

logger = logging.getLogger("iyokai.snipe")

MODULE_SNIPE = "snipe"
MODULE_REACTIONSNIPE = "reactionsnipe"
MODULE_GHOST_PING = "ghost_ping_detection"

_CACHE_MAX_SIZE = 2000
# Il registro di controllo arriva in ritardo: si aspetta un attimo prima di leggerlo.
AUDIT_ATTESA_SECONDI = 1.5


@dataclass(frozen=True)
class _MessaggioCancellato:
    author_id: int
    author_nome: str
    content: str
    allegati: tuple[str, ...]
    quando: datetime
    guild_id: int = 0


@dataclass(frozen=True)
class _MessaggioModificato:
    author_id: int
    author_nome: str
    prima: str
    dopo: str
    jump_url: str
    quando: datetime
    guild_id: int = 0


@dataclass(frozen=True)
class _RemovedReaction:
    emoji: str
    user_id: int
    message_id: int
    removed_at: datetime


@dataclass(frozen=True)
class _TrackedMention:
    author_id: int
    mentioned_user_ids: tuple[int, ...]
    mentions_everyone: bool
    channel_id: int
    created_at: datetime


class SnipeCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Chiave: channel_id -> ultima reazione rimossa in quel canale.
        self._last_removed_reaction: BoundedCache[int, _RemovedReaction] = BoundedCache(_CACHE_MAX_SIZE)
        # Chiave: message_id -> messaggio candidato ghost ping, in
        # attesa di essere cancellato (o mai, se resta lì finché la
        # cache non lo scarta per LRU).
        self._tracked_mentions: BoundedCache[int, _TrackedMention] = BoundedCache(_CACHE_MAX_SIZE)
        # Chiave: channel_id -> ultimo messaggio cancellato / ultima modifica.
        self._ultimo_cancellato = RicordiSnipe()
        self._ultima_modifica = RicordiSnipe()
        # Voci del registro di controllo già viste (id voce -> conteggio).
        self._voci_viste: dict[int, int] = {}

    # ================================================================
    # SPEC.md §14.9 / §14.10 — Snipe ed Editsnipe
    # ================================================================
    async def _ignorato(self, guild: discord.Guild, channel_id: int, message: discord.Message) -> bool:
        """Canali, utenti e prefissi di /log ignora valgono anche per snipe."""
        canale = guild.get_channel_or_thread(channel_id)
        return da_ignorare(
            await log_ignora_repo.carica(guild.id),
            channel_id=channel_id,
            author_id=message.author.id,
            testo=message.content,
            category_id=getattr(canale, "category_id", None),
            thread_parent_id=getattr(canale, "parent_id", None),
        )

    async def _vuole_snipe(self, payload: discord.RawMessageDeleteEvent, guild: discord.Guild) -> bool:
        """Il messaggio cancellato va ricordato per /utility snipe (modulo acceso, non ignorato)."""
        messaggio = payload.cached_message
        if messaggio is None or messaggio.author.bot:
            return False
        if not await db.is_module_active_for_guild(payload.guild_id, MODULE_SNIPE):
            return False
        return not await self._ignorato(guild, payload.channel_id, messaggio)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if after.guild is None or after.author.bot or before.content == after.content:
            return
        if not await db.is_module_active_for_guild(after.guild.id, MODULE_SNIPE):
            return
        if await self._ignorato(after.guild, after.channel.id, after):
            return
        self._ultima_modifica.set(
            after.channel.id,
            _MessaggioModificato(
                author_id=after.author.id,
                author_nome=after.author.display_name,
                prima=before.content,
                dopo=after.content,
                jump_url=after.jump_url,
                quando=datetime.now(timezone.utc),
                guild_id=after.guild.id,
            ),
        )

    async def _ricordato(self, interaction: discord.Interaction, cache: RicordiSnipe):
        """La voce ancora valida del canale, oppure None dopo aver risposto all'utente."""
        if interaction.guild is None or interaction.channel is None:
            return None
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_SNIPE):
            await interaction.response.send_message(
                "Snipe non è attivo su questo server: un amministratore lo accende con /admin setup attiva.",
                ephemeral=True,
            )
            return None
        voce = cache.get(interaction.channel.id)
        if voce is None:
            await interaction.response.send_message(
                "Nessun messaggio da mostrare in questo canale (li ricordo per 5 minuti).",
                ephemeral=True,
            )
        return voce

    @comando_di_gruppo(
        "utility", nome="snipe", descrizione="Mostra l'ultimo messaggio cancellato in questo canale."
    )
    async def snipe(self, interaction: discord.Interaction) -> None:
        voce = await self._ricordato(interaction, self._ultimo_cancellato)
        if voce is None:
            return
        embed = discord.Embed(
            title="🎯 Snipe",
            description=testo_snipe(voce.content, list(voce.allegati)),
            color=discord.Color.red(),
            timestamp=voce.quando,
        )
        embed.set_footer(text=f"Scritto da {voce.author_nome}")
        await interaction.response.send_message(
            embed=embed, allowed_mentions=discord.AllowedMentions.none()
        )

    @comando_di_gruppo(
        "utility", nome="editsnipe", descrizione="Mostra l'ultimo messaggio modificato in questo canale."
    )
    async def editsnipe(self, interaction: discord.Interaction) -> None:
        voce = await self._ricordato(interaction, self._ultima_modifica)
        if voce is None:
            return
        embed = discord.Embed(
            title="🎯 Editsnipe",
            description=f"[Vai al messaggio]({voce.jump_url})",
            color=discord.Color.orange(),
            timestamp=voce.quando,
        )
        embed.add_field(name="Prima", value=testo_snipe(voce.prima, [], CAMPO_MAX), inline=False)
        embed.add_field(name="Dopo", value=testo_snipe(voce.dopo, [], CAMPO_MAX), inline=False)
        embed.set_footer(text=f"Scritto da {voce.author_nome}")
        await interaction.response.send_message(
            embed=embed, allowed_mentions=discord.AllowedMentions.none()
        )

    # ================================================================
    # SPEC.md §14.11 — Reactionsnipe
    # ================================================================
    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None:
            return
        if not await db.is_module_active_for_guild(payload.guild_id, MODULE_REACTIONSNIPE):
            return

        self._last_removed_reaction.set(
            payload.channel_id,
            _RemovedReaction(
                emoji=str(payload.emoji),
                user_id=payload.user_id,
                message_id=payload.message_id,
                removed_at=datetime.now(timezone.utc),
            ),
        )

    @comando_di_gruppo(
        "utility",
        nome="reactionsnipe",
        descrizione="Mostra l'ultima reazione rimossa in questo canale.",
    )
    async def reactionsnipe(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or interaction.channel is None:
            return

        rimossa = self._last_removed_reaction.get(interaction.channel.id)
        if rimossa is None:
            await interaction.response.send_message(
                "Nessuna reazione rimossa recentemente in questo canale.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🎯 Reactionsnipe",
            description=(
                f"{rimossa.emoji} rimossa da <@{rimossa.user_id}> dal "
                f"[messaggio](https://discord.com/channels/{interaction.guild.id}/"
                f"{interaction.channel.id}/{rimossa.message_id})."
            ),
            color=discord.Color.orange(),
            timestamp=rimossa.removed_at,
        )
        await interaction.response.send_message(embed=embed)

    # ================================================================
    # SPEC.md §14.12 — Ghost ping detection
    # ================================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None:
            return
        if not await db.is_module_active_for_guild(message.guild.id, MODULE_GHOST_PING):
            return

        mentioned_ids = [m.id for m in message.mentions]
        if not is_ghost_ping_candidate(mentioned_ids, message.mention_everyone, message.author.bot):
            return

        self._tracked_mentions.set(
            message.id,
            _TrackedMention(
                author_id=message.author.id,
                mentioned_user_ids=tuple(mentioned_ids),
                mentions_everyone=message.mention_everyone,
                channel_id=message.channel.id,
                created_at=datetime.now(timezone.utc),
            ),
        )

    async def _cancellato_da_moderatore(
        self, guild: discord.Guild, author_id: int, channel_id: int, evento_ts: float
    ) -> bool:
        """M 5.9: il registro dice che un moderatore ha cancellato proprio questo messaggio."""
        await asyncio.sleep(AUDIT_ATTESA_SECONDI)
        voci = []
        try:
            async for voce in guild.audit_logs(action=discord.AuditLogAction.message_delete, limit=10):
                voci.append(
                    VoceRegistro(
                        entry_id=voce.id,
                        user_id=voce.user_id,
                        target_id=getattr(voce.target, "id", None),
                        channel_id=getattr(getattr(voce.extra, "channel", None), "id", None),
                        count=getattr(voce.extra, "count", 1) or 1,
                        created_ts=voce.created_at.timestamp(),
                    )
                )
        except discord.HTTPException:
            return False  # senza il registro non si può dire: vale la regola di prima
        risultato = cancellato_da_altri(voci, author_id, channel_id, self._voci_viste, evento_ts)
        if len(self._voci_viste) > _CACHE_MAX_SIZE:
            self._voci_viste.clear()
        return risultato

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        if payload.guild_id is None:
            return
        evento_ts = discord.utils.utcnow().timestamp()
        tracciato = self._tracked_mentions.get(payload.message_id)
        if tracciato is not None:
            self._tracked_mentions.delete(payload.message_id)
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        ricorda = await self._vuole_snipe(payload, guild)
        destinazione = None
        if tracciato is not None and await db.is_module_active_for_guild(payload.guild_id, MODULE_GHOST_PING):
            predefinito = await db.get_guild_setting(payload.guild_id, SETTING_LOG_CHANNEL)
            destinazione = await router.destinazione(guild, TIPO_MESSAGGI, predefinito)
        if not ricorda and destinazione is None:
            return

        # Una sola lettura del registro per evento: la seconda vedrebbe la voce già «vista».
        messaggio = payload.cached_message
        autore = messaggio.author.id if messaggio is not None else tracciato.author_id
        da_moderatore = await self._cancellato_da_moderatore(guild, autore, payload.channel_id, evento_ts)
        if da_moderatore:
            return  # né snipe né ghost ping: l'ha tolto un moderatore o l'automod

        if ricorda:
            self._ultimo_cancellato.set(
                payload.channel_id,
                _MessaggioCancellato(
                    author_id=messaggio.author.id,
                    author_nome=messaggio.author.display_name,
                    content=messaggio.content,
                    allegati=tuple(a.filename for a in messaggio.attachments),
                    quando=datetime.now(timezone.utc),
                    guild_id=payload.guild_id,
                ),
            )
        if destinazione is not None:
            await self._avvisa_ghost_ping(guild, destinazione, tracciato)

    async def _avvisa_ghost_ping(self, guild: discord.Guild, destinazione, tracciato: _TrackedMention) -> None:
        if tracciato.mentions_everyone:
            menzioni = "@everyone/@here"
        else:
            menzioni = ", ".join(f"<@{uid}>" for uid in tracciato.mentioned_user_ids)

        embed = discord.Embed(
            title="👻 Ghost ping rilevato",
            description=(
                f"<@{tracciato.author_id}> ha menzionato {menzioni} in "
                f"<#{tracciato.channel_id}> e ha cancellato il messaggio."
            ),
            color=discord.Color.dark_grey(),
        )
        await router.invia_a(destinazione, guild, TIPO_MESSAGGI, embed=embed)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_SNIPE,
            display_name="Snipe ed Editsnipe",
            category="utility",
            description="Mostra l'ultimo messaggio cancellato o modificato in un canale (5 minuti, solo in memoria).",
            premium_capable=False,
        )
    )
    registry.register(
        PremiumModule(
            name=MODULE_REACTIONSNIPE,
            display_name="Reactionsnipe",
            category="utility",
            description="Mostra l'ultima reazione rimossa in un canale.",
            premium_capable=False,
        )
    )
    registry.register(
        PremiumModule(
            name=MODULE_GHOST_PING,
            display_name="Ghost Ping Detection",
            category="utility",
            description="Segnala nel canale log chi menziona e poi cancella il messaggio.",
            premium_capable=False,
        )
    )
    await bot.add_cog(SnipeCog(bot))
