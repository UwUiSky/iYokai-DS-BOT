"""
cogs/moderation/softban_mute.py
===================================
Softban e mute via ruolo (SPEC.md §5.1 — due foglie mancanti,
coincidenti con la proposta indipendente di Gemini in BACKLOG.md §5).
File separato da actions.py solo per non far crescere ulteriormente
un file già di ~530 righe — stesso modulo MODULE_ACTIONS, stesso
tier gratuito, stesso pattern a quattro passi.

Softban: ban + unban immediato, per cancellare i messaggi recenti
dell'utente senza allontanarlo permanentemente (a differenza del
kick, che non cancella nulla).

Mute via ruolo: alternativa al timeout nativo di Discord — utile per
mute più lunghi dei 28 giorni massimi del timeout, o semplicemente
come preferenza di alcuni admin. Il ruolo "Muted" viene creato
automaticamente al primo utilizzo, con i permessi negati (scrivere,
anche nei thread, aprire thread, reagire, entrare e parlare in vocale)
su ogni canale di ogni tipo. I canali creati dopo ricevono lo stesso
blocco da on_guild_channel_create.
Funzioni coperte: SPEC §5.1, §5.10
"""

# DA FARE (issue #57, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §1 (Moderazione).

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.repositories.moderation_repo import moderation_repo
from cogs.moderation._shared import (
    MODULE_ACTIONS,
    ensure_module_enabled,
    check_can_moderate,
    try_dm,
    validate_reason,
    Reason,
    audit_reason,
    post_to_mod_log,
    SETTING_MOD_LOG_CHANNEL,
)

logger = logging.getLogger("iyokai.moderation.softban_mute")

MUTE_ROLE_ACTION_TYPE = "mute_role"

# Chiave in guild_config.settings per il ruolo mute — stesso
# meccanismo generico già usato da report.py e dal canale mod-log.
SETTING_MUTE_ROLE_ID = "mute_role_id"

# Cosa non può fare chi ha il ruolo Muted (LIM-30). Lo stesso blocco
# vale per ogni tipo di canale: testo, forum, vocale (che ha anche una
# chat), palco e categoria. I thread seguono il canale che li contiene.
MUTE_OVERWRITE = {
    "send_messages": False,
    "send_messages_in_threads": False,
    "create_public_threads": False,
    "create_private_threads": False,
    "add_reactions": False,
    "speak": False,
    "connect": False,
}


async def _apply_mute_overwrite(channel: discord.abc.GuildChannel, role: discord.Role) -> None:
    """
    Mette il blocco del ruolo Muted su un canale. Completa solo i
    permessi non ancora impostati: quelli che un admin ha scelto a mano
    per il ruolo in quel canale restano (es. un canale "appelli" dove i
    silenziati possono scrivere). Un canale che fallisce (permessi
    mancanti, canale appena cancellato) non deve fermare gli altri: lo
    scriviamo nel log e basta.
    """
    overwrite = channel.overwrites_for(role)
    overwrite.update(
        **{name: False for name in MUTE_OVERWRITE if getattr(overwrite, name) is None}
    )
    try:
        await channel.set_permissions(role, overwrite=overwrite, reason="Setup ruolo mute")
    except discord.HTTPException:
        logger.warning(
            "Impossibile impostare il blocco mute sul canale %s (server %s).",
            channel.id,
            channel.guild.id,
        )


def _case_embed(
    title: str,
    color: discord.Color,
    target: discord.abc.User,
    moderator: discord.abc.User,
    reason: str,
    case_number: int,
) -> discord.Embed:
    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="Utente", value=f"{target.mention} ({target.id})", inline=False)
    embed.add_field(name="Moderatore", value=moderator.mention, inline=True)
    embed.add_field(name="Caso", value=f"#{case_number}", inline=True)
    embed.add_field(name="Motivo", value=reason, inline=False)
    return embed


def _has_mute_overwrite(channel: discord.abc.GuildChannel, role: discord.Role) -> bool:
    """True se nel canale ogni permesso del blocco è già stato deciso (negato o no)."""
    current = channel.overwrites_for(role)
    return all(getattr(current, name) is not None for name in MUTE_OVERWRITE)


async def _cover_all_channels(guild: discord.Guild, role: discord.Role) -> None:
    """
    Mette il blocco sui canali che non l'hanno ancora: tutti per un
    ruolo appena creato, solo quelli scoperti (canali nati mentre il
    bot era spento, ruolo creato da una versione vecchia) negli altri
    casi. Legge dalla cache: se è tutto a posto non chiama Discord.
    """
    for channel in guild.channels:
        if not _has_mute_overwrite(channel, role):
            await _apply_mute_overwrite(channel, role)


async def _get_or_create_mute_role(guild: discord.Guild) -> discord.Role | None:
    """
    Restituisce il ruolo mute configurato per questo server,
    creandolo se non esiste ancora. In entrambi i casi controlla che
    ogni canale abbia il blocco. None se Discord rifiuta la creazione
    (permessi mancanti, oppure il server ha già 250 ruoli).
    """
    role_id = await db.get_guild_setting(guild.id, SETTING_MUTE_ROLE_ID)
    if role_id is not None:
        role = guild.get_role(role_id)
        if role is not None:
            await _cover_all_channels(guild, role)
            return role
        # L'ID salvato non corrisponde più a nessun ruolo esistente
        # (es. eliminato manualmente da un admin) — ne creiamo uno
        # nuovo sotto, invece di fallire silenziosamente.

    try:
        role = await guild.create_role(
            name="Muted", reason="Ruolo mute creato automaticamente da iYokai"
        )
    except discord.HTTPException:
        return None

    await _cover_all_channels(guild, role)
    await db.set_guild_setting(guild.id, SETTING_MUTE_ROLE_ID, role.id)
    return role


class ModerationSoftbanMuteCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        """
        Un canale nuovo non ha il blocco del ruolo Muted: lo mettiamo
        subito, altrimenti chi è silenziato potrebbe scriverci. Se lo
        ha già preso dalla sua categoria non serve nessuna chiamata.
        """
        role_id = await db.get_guild_setting(channel.guild.id, SETTING_MUTE_ROLE_ID)
        if role_id is None:
            return
        role = channel.guild.get_role(role_id)
        if role is None:
            return
        if not _has_mute_overwrite(channel, role):
            await _apply_mute_overwrite(channel, role)

    # ================================================================
    # /mod-log-setup (SPEC.md §5.10 — canale dedicato per il log di
    # ogni sanzione, non legato a softban/mute in particolare, ma
    # vive qui per non aprire un quarto file solo per un comando)
    # ================================================================
    @app_commands.command(
        name="mod-log-setup",
        description="[Admin] Imposta il canale dove arriva il log di ogni sanzione.",
    )
    @app_commands.describe(channel="Il canale mod-log dedicato")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def mod_log_setup(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return

        await db.set_guild_setting(interaction.guild.id, SETTING_MOD_LOG_CHANNEL, channel.id)
        await interaction.response.send_message(
            f"Le sanzioni verranno registrate anche in {channel.mention}.",
            ephemeral=True,
        )

    # ================================================================
    # /softban
    # ================================================================
    @app_commands.command(
        name="softban",
        description="Banna e sbanna subito un membro, per cancellarne i messaggi recenti.",
    )
    @app_commands.describe(
        member="Il membro da softban",
        reason="Motivo del softban",
        delete_message_days="Giorni di messaggi da cancellare (1-7, default 1)",
    )
    async def softban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Reason,
        delete_message_days: app_commands.Range[int, 1, 7] = 1,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        if not await validate_reason(interaction, reason):
            return
        if not await check_can_moderate(interaction, member):
            return

        await interaction.response.defer()

        # Prima l'azione: il caso, il log e il DM partono solo se è
        # riuscita (LIM-8).
        try:
            await member.ban(
                reason=audit_reason(f"Softban: {reason}"),
                delete_message_seconds=delete_message_days * 86400,
            )
        except discord.HTTPException:
            await interaction.followup.send(
                "Non sono riuscito a fare il softban di questo utente: "
                "controlla i miei permessi e la posizione del mio ruolo.",
                ephemeral=True,
            )
            return

        sbloccato = True
        try:
            await interaction.guild.unban(
                discord.Object(id=member.id), reason="Softban: sblocco automatico"
            )
        except discord.HTTPException:
            sbloccato = False
            logger.warning(
                "Softban: ban riuscito ma sblocco automatico fallito per "
                "l'utente %s nel server %s — richiede intervento manuale.",
                member.id,
                interaction.guild.id,
            )

        case_number = await moderation_repo.create_case(
            guild_id=interaction.guild.id,
            user_id=member.id,
            moderator_id=interaction.user.id,
            action_type="softban",
            reason=reason,
        )
        embed = _case_embed(
            "🧹 Softban", discord.Color.dark_orange(), member, interaction.user, reason, case_number
        )
        await post_to_mod_log(interaction.guild, embed)

        avvisi = []
        if not sbloccato:
            avvisi.append("Lo sblocco automatico è fallito: usa /unban.")
        if not await try_dm(member, embed):
            avvisi.append("Non è stato possibile notificare l'utente in DM.")
        if avvisi:
            embed.set_footer(text=" ".join(avvisi))
        await interaction.followup.send(embed=embed)

    # ================================================================
    # /mute-role e /unmute-role
    # ================================================================
    @app_commands.command(
        name="mute-role",
        description="Silenzia un membro con un ruolo dedicato (alternativa al timeout).",
    )
    @app_commands.describe(member="Il membro da silenziare", reason="Motivo del mute")
    async def mute_role(
        self, interaction: discord.Interaction, member: discord.Member, reason: Reason
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        if not await validate_reason(interaction, reason):
            return
        if not await check_can_moderate(interaction, member):
            return

        await interaction.response.defer()

        role = await _get_or_create_mute_role(interaction.guild)
        if role is None:
            await interaction.followup.send(
                "Non sono riuscito a creare il ruolo mute: controlla i miei "
                "permessi e che il server non abbia già 250 ruoli.",
                ephemeral=True,
            )
            return

        try:
            await member.add_roles(role, reason=reason)
        except discord.HTTPException:
            await interaction.followup.send(
                "Non sono riuscito ad assegnare il ruolo mute: controlla i "
                "miei permessi e la posizione del mio ruolo.",
                ephemeral=True,
            )
            return

        case_number = await moderation_repo.create_case(
            guild_id=interaction.guild.id,
            user_id=member.id,
            moderator_id=interaction.user.id,
            action_type=MUTE_ROLE_ACTION_TYPE,
            reason=reason,
        )
        embed = _case_embed(
            "🔇 Mute (ruolo)", discord.Color.dark_grey(), member, interaction.user, reason, case_number
        )
        await post_to_mod_log(interaction.guild, embed)
        await try_dm(member, embed)
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="unmute-role", description="Rimuove il ruolo mute da un membro."
    )
    @app_commands.describe(member="Il membro da cui rimuovere il mute", reason="Motivo")
    async def unmute_role(
        self, interaction: discord.Interaction, member: discord.Member, reason: Reason
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        if not await validate_reason(interaction, reason):
            return

        role_id = await db.get_guild_setting(interaction.guild.id, SETTING_MUTE_ROLE_ID)
        if role_id is None:
            await interaction.response.send_message(
                "Nessun ruolo mute configurato su questo server.", ephemeral=True
            )
            return

        role = interaction.guild.get_role(role_id)
        if role is None or role not in member.roles:
            await interaction.response.send_message(
                f"{member.mention} non ha il ruolo mute.", ephemeral=True
            )
            return

        try:
            await member.remove_roles(role, reason=reason)
        except discord.HTTPException:
            await interaction.response.send_message(
                "Non sono riuscito a rimuovere il ruolo mute: controlla i "
                "miei permessi e la posizione del mio ruolo.",
                ephemeral=True,
            )
            return

        case = await moderation_repo.get_latest_active_case(
            interaction.guild.id, member.id, MUTE_ROLE_ACTION_TYPE
        )
        if case is not None:
            await moderation_repo.revoke_case(
                interaction.guild.id, case.case_number, interaction.user.id
            )

        await interaction.response.send_message(f"Ruolo mute rimosso da {member.mention}.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModerationSoftbanMuteCog(bot))
