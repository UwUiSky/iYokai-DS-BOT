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

SPEC.md §12.4 + §12.5: alla creazione del canale (automatica o
manuale) viene inviato un messaggio nella chat testuale del canale
vocale stesso (un VoiceChannel è Messageable) con la notifica "il tuo
canale è pronto" e, SE il server ha configurato almeno un ruolo
piattaforma, dei bottoni PC/Console/Mobile — vedi PlatformRoleView.
Restano SOLO informativi (nessun filtro di visibilità), per la stessa
ragione già registrata sopra sulle due modalità sempre visibili.

SPEC.md §12.8: il cap per categoria (/voicetemp-cap) è sempre
troncato al limite hard di Discord di 50 canali per categoria — vedi
core/voice_temp_logic.py:effective_category_cap/is_category_full.
"""

# DA FARE (issue #63, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §7 (Vocali temporanei).

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.channel_rename import (
    RenameRateLimited,
    rename_channel,
    rename_limit_message,
    rename_tracker,
)
from core.database import db
from core.repositories.blacklist_repo import blacklist_repo
from core.repositories.voice_temp_repo import voice_temp_repo
from core.role_safety import check_role_assignable
from core.voice_temp_logic import (
    can_manage_voice_channel,
    is_category_full,
    is_generator_join,
    should_delete_after_leave,
)
from core.premium import PremiumModule, registry
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.voice_temp")

MODULE_VOICE_TEMP = "voice_temp"

CREATE_VOICE_CUSTOM_ID = "iyokai_voice_temp_create"

# Il nome di un canale Discord va da 1 a 100 caratteri (LIM-3).
MAX_CHANNEL_NAME_LENGTH = 100

# I permessi che il proprietario ha sul suo canale. /voice transfer li
# sposta al nuovo proprietario.
OWNER_PERMISSIONS = {"manage_channels": True, "move_members": True, "mute_members": True}

MESSAGGIO_ERRORE_DISCORD = (
    "Non sono riuscito a farlo: controlla i miei permessi sul canale e riprova."
)

# SPEC.md §12.5: selezione piattaforma, SOLO informativa (nessun
# filtro di visibilità — decisione già presa in fase di progettazione,
# vedi il docstring del modulo). custom_id fissi perché la view va
# comunque ricreata ad ogni canale (non è persistente: il canale
# stesso è temporaneo, non ha senso sopravviva a un riavvio del bot).
PLATFORM_CHOICES = (
    ("pc", "PC", "🖥️"),
    ("console", "Console", "🎮"),
    ("mobile", "Mobile", "📱"),
)


class PlatformRoleView(BaseView):
    """
    Bottoni PC/Console/Mobile mostrati insieme alla notifica di
    creazione del canale (SPEC.md §12.4 + §12.5 insieme: la notifica
    esiste comunque, i bottoni compaiono solo se il server ha
    configurato almeno un ruolo piattaforma). Selezionare una
    piattaforma assegna QUEL ruolo e rimuove gli altri due — è un
    indicatore mutuamente esclusivo ("sto giocando da..."), non un
    filtro su cosa il membro può vedere o fare.
    """

    def __init__(self, config) -> None:
        super().__init__(timeout=300)
        self._roles_by_key = {
            "pc": config.role_pc_id,
            "console": config.role_console_id,
            "mobile": config.role_mobile_id,
        }
        for key, label, emoji in PLATFORM_CHOICES:
            if self._roles_by_key.get(key) is None:
                continue
            self.add_item(self._make_button(key, label, emoji))

    def _make_button(self, key: str, label: str, emoji: str) -> discord.ui.Button:
        button = discord.ui.Button(
            label=label, emoji=emoji, style=discord.ButtonStyle.secondary,
            custom_id=f"iyokai_voice_temp_platform_{key}",
        )

        async def callback(interaction: discord.Interaction) -> None:
            if not isinstance(interaction.user, discord.Member):
                return
            guild = interaction.guild
            if guild is None:
                return

            ruolo_scelto = guild.get_role(self._roles_by_key[key])
            if ruolo_scelto is None:
                await interaction.response.send_message(
                    "Il ruolo configurato per questa piattaforma non esiste più.",
                    ephemeral=True,
                )
                return

            # SEC-4/SEC-17: assegnazione self-service, ricontrolla il
            # ruolo scelto — può aver preso permessi pericolosi dopo
            # /voicetemp-platform-setup.
            motivo_rifiuto = check_role_assignable(guild, ruolo_scelto, guild.me, self_service=True)
            if motivo_rifiuto is not None:
                await interaction.response.send_message(motivo_rifiuto, ephemeral=True)
                return

            altri_ruoli_id = {
                rid for rid in self._roles_by_key.values() if rid is not None and rid != ruolo_scelto.id
            }
            da_rimuovere = [
                r for r in interaction.user.roles if r.id in altri_ruoli_id
            ]
            try:
                if da_rimuovere:
                    await interaction.user.remove_roles(*da_rimuovere, reason="Cambio piattaforma vocale temporaneo")
                if ruolo_scelto not in interaction.user.roles:
                    await interaction.user.add_roles(ruolo_scelto, reason="Selezione piattaforma vocale temporaneo")
            except (discord.Forbidden, discord.HTTPException):
                await interaction.response.send_message(
                    "Non ho i permessi per assegnare il ruolo piattaforma.",
                    ephemeral=True,
                )
                return

            await interaction.response.send_message(
                f"Piattaforma impostata: {ruolo_scelto.mention}.", ephemeral=True
            )

        button.callback = callback
        return button


async def _create_temp_channel(
    guild: discord.Guild,
    owner: discord.Member,
    category: discord.CategoryChannel,
    config,
) -> discord.VoiceChannel | None:
    """
    Crea il canale vocale temporaneo, lo registra nel repository, e
    lo restituisce. None se la creazione fallisce (permessi mancanti,
    categoria al cap configurato, o limite hard Discord di 50 canali)
    — il chiamante decide come comunicarlo, dato che i due punti di
    ingresso (evento vocale automatico, bottone manuale) rispondono
    in modo diverso.
    """
    if is_category_full(len(category.channels), config.category_cap):
        logger.info(
            "Categoria %s piena (cap effettivo raggiunto), vocale temporaneo per %s non creato",
            category.id,
            owner.id,
        )
        return None

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(),  # eredita, nessuna restrizione
        owner: discord.PermissionOverwrite(**OWNER_PERMISSIONS),
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

    # SPEC.md §12.4: notifica personale alla creazione del canale —
    # richiesta esplicitamente perché la modalità automatica sposta
    # l'utente in totale silenzio. Un canale vocale è Messageable
    # (ha una sua chat testuale), quindi il messaggio va dritto lì.
    embed = discord.Embed(
        title="🔊 Canale vocale creato",
        description=f"{owner.mention}, il tuo canale **{channel.name}** è pronto.",
        color=discord.Color.blurple(),
    )
    view = PlatformRoleView(config)
    try:
        if view.children:
            await channel.send(embed=embed, view=view)
        else:
            await channel.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        logger.warning("Impossibile inviare la notifica di creazione nel canale %s", channel.id)

    return channel


class CreateVoiceView(BaseView):
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
        channel = await _create_temp_channel(guild, interaction.user, category, config)
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

    @app_commands.command(
        name="voicetemp-cap",
        description="[Admin] Imposta il numero massimo di vocali temporanei per categoria.",
    )
    @app_commands.describe(
        cap="Numero massimo di canali nella categoria (max 50, limite Discord). Vuoto per rimuovere il limite."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def voicetemp_cap(
        self,
        interaction: discord.Interaction,
        cap: app_commands.Range[int, 1, 50] | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        config = await voice_temp_repo.get_config(interaction.guild.id)
        if config.category_id is None:
            await interaction.response.send_message(
                "Configura prima generatore e categoria con /voicetemp-setup.",
                ephemeral=True,
            )
            return

        await voice_temp_repo.set_category_cap(interaction.guild.id, cap)
        testo = f"massimo **{cap}** canali" if cap is not None else "nessun limite (oltre a quello di Discord, 50)"
        await interaction.response.send_message(
            f"Cap per categoria impostato: {testo}.", ephemeral=True
        )

    @app_commands.command(
        name="voicetemp-platform-setup",
        description="[Admin] Configura i ruoli informativi PC/Console/Mobile per i vocali temporanei.",
    )
    @app_commands.describe(
        pc="Ruolo per chi gioca da PC (facoltativo)",
        console="Ruolo per chi gioca da Console (facoltativo)",
        mobile="Ruolo per chi gioca da Mobile (facoltativo)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def voicetemp_platform_setup(
        self,
        interaction: discord.Interaction,
        pc: discord.Role | None = None,
        console: discord.Role | None = None,
        mobile: discord.Role | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        config = await voice_temp_repo.get_config(interaction.guild.id)
        if config.category_id is None:
            await interaction.response.send_message(
                "Configura prima generatore e categoria con /voicetemp-setup.",
                ephemeral=True,
            )
            return

        if not isinstance(interaction.user, discord.Member):
            return

        for ruolo in (pc, console, mobile):
            if ruolo is None:
                continue
            motivo_rifiuto = check_role_assignable(
                interaction.guild, ruolo, interaction.user, self_service=True
            )
            if motivo_rifiuto is not None:
                await interaction.response.send_message(motivo_rifiuto, ephemeral=True)
                return

        await voice_temp_repo.set_platform_roles(
            interaction.guild.id,
            role_pc_id=pc.id if pc else None,
            role_console_id=console.id if console else None,
            role_mobile_id=mobile.id if mobile else None,
        )
        await interaction.response.send_message(
            "Ruoli piattaforma aggiornati. Sono puramente informativi: non "
            "filtrano la visibilità del canale.",
            ephemeral=True,
        )

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
    async def rename(
        self,
        interaction: discord.Interaction,
        name: app_commands.Range[str, 1, MAX_CHANNEL_NAME_LENGTH],
    ) -> None:
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return

        # Discord permette 2 rinomine ogni 10 minuti per canale (LIM-3):
        # alla terza si risponde subito, senza restare in attesa.
        attesa = rename_tracker.seconds_until_allowed(channel.id)
        if attesa > 0:
            await interaction.response.send_message(
                rename_limit_message(attesa), ephemeral=True
            )
            return

        await interaction.response.defer()
        try:
            await rename_channel(
                channel, name, reason=f"Vocale rinominato da {interaction.user}"
            )
        except RenameRateLimited as limite:
            await interaction.followup.send(
                rename_limit_message(limite.retry_after), ephemeral=True
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                "Non sono riuscito a rinominare il canale: controlla i miei "
                "permessi e che il nome sia ammesso da Discord.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"Canale rinominato in **{name}**.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @voice_group.command(name="limit", description="Imposta il limite di utenti del canale.")
    @app_commands.describe(limit="Numero massimo di utenti (0 per nessun limite)")
    async def limit(
        self, interaction: discord.Interaction, limit: app_commands.Range[int, 0, 99]
    ) -> None:
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return
        try:
            await channel.edit(user_limit=limit)
        except discord.HTTPException:
            await interaction.response.send_message(MESSAGGIO_ERRORE_DISCORD, ephemeral=True)
            return
        testo = "nessun limite" if limit == 0 else f"{limit} utenti"
        await interaction.response.send_message(f"Limite impostato: {testo}.")

    @voice_group.command(name="lock", description="Blocca il canale (nessun nuovo ingresso).")
    async def lock(self, interaction: discord.Interaction) -> None:
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return
        try:
            await channel.set_permissions(
                interaction.guild.default_role, connect=False
            )
        except discord.HTTPException:
            await interaction.response.send_message(MESSAGGIO_ERRORE_DISCORD, ephemeral=True)
            return
        await interaction.response.send_message("Canale bloccato.")

    @voice_group.command(name="unlock", description="Sblocca il canale.")
    async def unlock(self, interaction: discord.Interaction) -> None:
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return
        try:
            await channel.set_permissions(interaction.guild.default_role, overwrite=None)
        except discord.HTTPException:
            await interaction.response.send_message(MESSAGGIO_ERRORE_DISCORD, ephemeral=True)
            return
        await interaction.response.send_message("Canale sbloccato.")

    @voice_group.command(name="kick", description="Espelli un utente dal tuo canale.")
    @app_commands.describe(member="L'utente da espellere dal canale")
    async def kick(self, interaction: discord.Interaction, member: discord.Member) -> None:
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return
        if member.voice is not None and member.voice.channel and member.voice.channel.id == channel.id:
            try:
                await member.move_to(None, reason="Espulso dal proprietario del canale")
            except discord.HTTPException:
                await interaction.response.send_message(
                    MESSAGGIO_ERRORE_DISCORD, ephemeral=True
                )
                return
        await interaction.response.send_message(f"{member.mention} espulso dal canale.")

    @voice_group.command(name="transfer", description="Trasferisci la proprietà del canale.")
    @app_commands.describe(member="Il nuovo proprietario del canale")
    async def transfer(self, interaction: discord.Interaction, member: discord.Member) -> None:
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return
        if member.bot:
            await interaction.response.send_message(
                "Non puoi trasferire il canale a un bot.", ephemeral=True
            )
            return
        if member.voice is None or member.voice.channel is None or member.voice.channel.id != channel.id:
            await interaction.response.send_message(
                f"{member.mention} non è nel canale: puoi trasferirlo solo "
                f"a chi è connesso qui.",
                ephemeral=True,
            )
            return
        vecchio_id = await voice_temp_repo.get_owner(channel.id)
        if member.id == vecchio_id:
            await interaction.response.send_message(
                f"{member.mention} è già il proprietario del canale.", ephemeral=True
            )
            return

        # Prima i permessi su Discord, poi il database: se Discord
        # rifiuta, la proprietà non cambia.
        try:
            await channel.set_permissions(
                member, reason="Nuovo proprietario del vocale temporaneo", **OWNER_PERMISSIONS
            )
        except discord.HTTPException:
            await interaction.response.send_message(MESSAGGIO_ERRORE_DISCORD, ephemeral=True)
            return
        await voice_temp_repo.set_owner(channel.id, member.id)

        # Al vecchio proprietario i permessi vanno tolti. Se è uscito
        # dal server non c'è più niente da togliere.
        vecchio = interaction.guild.get_member(vecchio_id)
        if vecchio is not None:
            try:
                await channel.set_permissions(
                    vecchio, overwrite=None, reason="Non è più il proprietario del vocale"
                )
            except discord.HTTPException:
                logger.warning(
                    "Permessi del vecchio proprietario %s non tolti dal canale %s",
                    vecchio_id,
                    channel.id,
                )

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
            # SEC-21: chi è in blacklist non ottiene un vocale
            # temporaneo (il cleanup più sotto gira comunque).
            if is_generator_join(
                after_channel_id, config.generator_channel_id
            ) and not await blacklist_repo.is_user_blacklisted(member.id):
                category = guild.get_channel(config.category_id) if config.category_id else None
                if isinstance(category, discord.CategoryChannel):
                    channel = await _create_temp_channel(guild, member, category, config)
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
            category="voice",
            description="Creazione automatica e manuale di canali vocali personali.",
            premium_capable=False,
        )
    )
    await bot.add_cog(VoiceTempCog(bot))
    bot.add_view(CreateVoiceView())
