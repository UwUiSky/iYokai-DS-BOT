"""
cogs/voice_temp/voice_temp.py
================================
Vocali temporanei: modalità automatica (entra nel canale generatore
-> il bot crea un canale e ti sposta dentro) e modalità manuale
(pannello con bottone, nessuno spostamento forzato). ENTRAMBE SEMPRE
VISIBILI a tutti gli utenti — decisione già presa in fase di
progettazione: i problemi di disconnessione su spostamento forzato
in vocale riguardano sia PlayStation sia mobile, quindi non ha senso
nascondere una modalità in base alla piattaforma dichiarata
dall'utente (che comunque non sappiamo con certezza).

Il bottone della modalità manuale è un altro pannello "a vita
lunga": stessa esigenza di persistenza già affrontata in
cogs/tickets/tickets.py — vedi TicketPanelView per il precedente,
qui si applica lo stesso pattern (timeout=None, custom_id esplicito,
bot.add_view() in setup()).
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.repositories.voice_temp_repo import voice_temp_repo
from core.voice_temp_logic import (
    can_manage_voice_channel,
    is_generator_join,
    should_delete_after_leave,
)
from core.premium import PremiumModule, registry

logger = logging.getLogger("iyokai.voice_temp")

MODULE_VOICE_TEMP = "voice_temp"

CREATE_VOICE_CUSTOM_ID = "iyokai_voice_temp_create"


async def _create_temp_channel(
    guild: discord.Guild, owner: discord.Member, category: discord.CategoryChannel
) -> discord.VoiceChannel | None:
    """
    Crea il canale vocale temporaneo, lo registra nel repository, e
    lo restituisce. None se la creazione fallisce (permessi mancanti
    o categoria al limite di 50 canali) — il chiamante decide come
    comunicarlo, dato che i due punti di ingresso (evento vocale
    automatico, bottone manuale) rispondono in modo diverso.
    """
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(),  # eredita, nessuna restrizione
        owner: discord.PermissionOverwrite(
            manage_channels=True, move_members=True, mute_members=True
        ),
    }
    try:
        channel = await category.create_voice_channel(
            name=f"Canale di {owner.display_name}",
            overwrites=overwrites,
            reason=f"Vocale temporaneo per {owner}",
        )
    except (discord.Forbidden, discord.HTTPException):
        logger.warning(
            "Impossibile creare il vocale temporaneo per %s nel server %s",
            owner.id,
            guild.id,
        )
        return None

    await voice_temp_repo.register_channel(channel.id, guild.id, owner.id)
    return channel


class CreateVoiceView(discord.ui.View):
    """Persistente — stesso motivo di TicketPanelView (vedi cogs/tickets/tickets.py)."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Crea canale vocale",
        style=discord.ButtonStyle.primary,
        emoji="🔊",
        custom_id=CREATE_VOICE_CUSTOM_ID,
    )
    async def create_voice(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            return

        if not await db.is_module_active_for_guild(guild.id, MODULE_VOICE_TEMP):
            await interaction.response.send_message(
                "I vocali temporanei non sono attivi su questo server.",
                ephemeral=True,
            )
            return

        config = await voice_temp_repo.get_config(guild.id)
        if config.category_id is None:
            await interaction.response.send_message(
                "Il sistema non è ancora configurato. Un amministratore "
                "deve usare /voicetemp-setup.",
                ephemeral=True,
            )
            return

        category = guild.get_channel(config.category_id)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                "La categoria configurata non esiste più. Un "
                "amministratore deve riconfigurarla.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        channel = await _create_temp_channel(guild, interaction.user, category)
        if channel is None:
            await interaction.followup.send(
                "Non sono riuscito a creare il canale (permessi mancanti "
                "o categoria piena).",
                ephemeral=True,
            )
            return

        # Modalità MANUALE: nessuno spostamento forzato, a differenza
        # della modalità automatica — è esattamente la differenza tra
        # le due modalità richiesta in fase di progettazione.
        await interaction.followup.send(
            f"Canale creato: {channel.mention}. Entra quando vuoi.",
            ephemeral=True,
        )


class VoiceTempCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ================================================================
    # Configurazione
    # ================================================================
    @app_commands.command(
        name="voicetemp-setup",
        description="[Admin] Configura il canale generatore e la categoria dei vocali temporanei.",
    )
    @app_commands.describe(
        generator="Il canale vocale che, se raggiunto, crea un vocale temporaneo",
        category="La categoria dove verranno creati i vocali temporanei",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def voicetemp_setup(
        self,
        interaction: discord.Interaction,
        generator: discord.VoiceChannel,
        category: discord.CategoryChannel,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.",
                ephemeral=True,
            )
            return

        await voice_temp_repo.set_config(interaction.guild.id, generator.id, category.id)
        await interaction.response.send_message(
            f"Configurato: entrando in {generator.mention} verrà creato "
            f"un vocale temporaneo dentro **{category.name}**.",
            ephemeral=True,
        )

    @app_commands.command(
        name="voicetemp-panel",
        description="[Admin] Pubblica il pannello per la creazione manuale di un vocale.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def voicetemp_panel(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="🔊 Vocali temporanei",
            description=(
                "Premi il bottone per crearti un canale vocale personale "
                "senza essere spostato automaticamente."
            ),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, view=CreateVoiceView())

    # ================================================================
    # Gestione del proprio canale
    # ================================================================
    voice_group = app_commands.Group(
        name="voice", description="Gestisci il tuo canale vocale temporaneo."
    )

    async def _get_managed_channel_or_reply(
        self, interaction: discord.Interaction
    ) -> discord.VoiceChannel | None:
        if not isinstance(interaction.user, discord.Member) or interaction.user.voice is None:
            await interaction.response.send_message(
                "Devi essere connesso al tuo canale vocale temporaneo "
                "per usare questo comando.",
                ephemeral=True,
            )
            return None

        channel = interaction.user.voice.channel
        owner_id = await voice_temp_repo.get_owner(channel.id)
        if owner_id is None:
            await interaction.response.send_message(
                "Questo non è un canale vocale temporaneo gestito da iYokai.",
                ephemeral=True,
            )
            return None

        actor_has_manage_channels = interaction.user.guild_permissions.manage_channels
        if not can_manage_voice_channel(interaction.user.id, owner_id, actor_has_manage_channels):
            await interaction.response.send_message(
                "Solo il proprietario del canale (o lo staff) può gestirlo.",
                ephemeral=True,
            )
            return None

        return channel

    @voice_group.command(name="rename", description="Rinomina il tuo canale vocale.")
    @app_commands.describe(name="Il nuovo nome del canale")
    async def rename(self, interaction: discord.Interaction, name: str) -> None:
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return
        await channel.edit(name=name)
        await interaction.response.send_message(f"Canale rinominato in **{name}**.")

    @voice_group.command(name="limit", description="Imposta il limite di utenti del canale.")
    @app_commands.describe(limit="Numero massimo di utenti (0 per nessun limite)")
    async def limit(
        self, interaction: discord.Interaction, limit: app_commands.Range[int, 0, 99]
    ) -> None:
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return
        await channel.edit(user_limit=limit)
        testo = "nessun limite" if limit == 0 else f"{limit} utenti"
        await interaction.response.send_message(f"Limite impostato: {testo}.")

    @voice_group.command(name="lock", description="Blocca il canale (nessun nuovo ingresso).")
    async def lock(self, interaction: discord.Interaction) -> None:
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return
        await channel.set_permissions(
            interaction.guild.default_role, connect=False
        )
        await interaction.response.send_message("Canale bloccato.")

    @voice_group.command(name="unlock", description="Sblocca il canale.")
    async def unlock(self, interaction: discord.Interaction) -> None:
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return
        await channel.set_permissions(interaction.guild.default_role, overwrite=None)
        await interaction.response.send_message("Canale sbloccato.")

    @voice_group.command(name="kick", description="Espelli un utente dal tuo canale.")
    @app_commands.describe(member="L'utente da espellere dal canale")
    async def kick(self, interaction: discord.Interaction, member: discord.Member) -> None:
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return
        if member.voice is not None and member.voice.channel and member.voice.channel.id == channel.id:
            await member.move_to(None, reason="Espulso dal proprietario del canale")
        await interaction.response.send_message(f"{member.mention} espulso dal canale.")

    @voice_group.command(name="transfer", description="Trasferisci la proprietà del canale.")
    @app_commands.describe(member="Il nuovo proprietario del canale")
    async def transfer(self, interaction: discord.Interaction, member: discord.Member) -> None:
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return
        await voice_temp_repo.set_owner(channel.id, member.id)
        await interaction.response.send_message(
            f"Proprietà del canale trasferita a {member.mention}."
        )

    # ================================================================
    # Eventi vocali: creazione automatica + eliminazione a canale vuoto
    # ================================================================
    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        before_channel_id = before.channel.id if before.channel else None
        after_channel_id = after.channel.id if after.channel else None

        if before_channel_id == after_channel_id:
            return  # non è un cambio di canale (es. solo mute/deafen)

        guild = member.guild

        # --- Modalità automatica: ingresso nel canale generatore ---
        if not await db.is_module_active_for_guild(guild.id, MODULE_VOICE_TEMP):
            pass  # non blocchiamo qui: il cleanup sotto deve comunque
            # girare anche se il modulo viene disattivato con canali
            # temporanei ancora aperti, altrimenti resterebbero orfani
        else:
            config = await voice_temp_repo.get_config(guild.id)
            if is_generator_join(after_channel_id, config.generator_channel_id):
                category = guild.get_channel(config.category_id) if config.category_id else None
                if isinstance(category, discord.CategoryChannel):
                    channel = await _create_temp_channel(guild, member, category)
                    if channel is not None:
                        try:
                            await member.move_to(channel, reason="Vocale temporaneo automatico")
                        except (discord.Forbidden, discord.HTTPException):
                            logger.warning(
                                "Canale temporaneo creato ma impossibile spostare %s",
                                member.id,
                            )

        # --- Cleanup: il canale lasciato è un temporaneo tracciato ed è vuoto? ---
        if before_channel_id is not None:
            owner_id = await voice_temp_repo.get_owner(before_channel_id)
            remaining = len(before.channel.members) if before.channel else 0
            if should_delete_after_leave(before_channel_id, owner_id is not None, remaining):
                try:
                    await before.channel.delete(reason="Vocale temporaneo rimasto vuoto")
                except (discord.Forbidden, discord.HTTPException):
                    pass
                await voice_temp_repo.unregister_channel(before_channel_id)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_VOICE_TEMP,
            display_name="Vocali temporanei",
            description="Creazione automatica e manuale di canali vocali personali.",
            premium_capable=False,
        )
    )
    await bot.add_cog(VoiceTempCog(bot))
    bot.add_view(CreateVoiceView())
