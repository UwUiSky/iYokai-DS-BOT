"""
cogs/automod/escalation.py
=============================
Smart AutoMod Escalation Ladder (BACKLOG.md §11, estensione di
SPEC.md §6 AutoMod). Ascolta on_automod_action (l'evento che Discord
manda quando una regola AutoMod NATIVA scatta — badword, anti-invite,
ecc., già configurate da cogs/automod/automod.py) e applica un'azione
via via più severa in base a quante volte l'utente ha già triggerato
una regola, invece della stessa identica azione ogni volta (quello
che l'AutoMod nativo farebbe da solo).

Doppio gate per l'attivazione: il modulo AutoMod di base deve essere
attivo (MODULE_AUTOMOD — l'escalation non ha senso senza le regole
che genera i trigger) E l'escalation deve essere esplicitamente
abilitata (EscalationConfig.enabled) — un admin potrebbe volere solo
il filtro nativo senza la scala di severità crescente.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.escalation_ladder_logic import (
    get_ladder_action,
    next_violation_count,
    should_reset_violation_count,
)
from core.repositories.escalation_repo import escalation_repo
from core.repositories.moderation_repo import moderation_repo
from cogs.automod.automod import MODULE_AUTOMOD

logger = logging.getLogger("iyokai.automod.escalation")

ESCALATION_ACTION_TYPE = "automod_escalation"


class EscalationCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_automod_action(self, execution: discord.AutoModAction) -> None:
        if execution.guild_id is None:
            return

        if not await db.is_module_active_for_guild(execution.guild_id, MODULE_AUTOMOD):
            return

        config = await escalation_repo.get_config(execution.guild_id)
        if not config.enabled:
            return

        member = execution.member
        if member is None or member.bot:
            return

        current_count, last_violation_at = await escalation_repo.get_violation_state(
            execution.guild_id, member.id
        )
        now = datetime.now(timezone.utc)
        deve_resettare = should_reset_violation_count(
            last_violation_at, config.reset_after_days, now
        )
        nuovo_conteggio = next_violation_count(current_count, deve_resettare)

        step = get_ladder_action(nuovo_conteggio, config.ladder)
        await escalation_repo.record_violation(
            execution.guild_id, member.id, nuovo_conteggio, now
        )

        if step is None:
            return  # scala non configurata: solo il conteggio viene tenuto

        reason = (
            f"AutoMod Escalation — infrazione #{nuovo_conteggio} "
            f"(regola: {execution.matched_keyword or 'trigger AutoMod'})"
        )

        try:
            if step.action_type == "warn":
                case_number = await moderation_repo.create_case(
                    guild_id=execution.guild_id,
                    user_id=member.id,
                    moderator_id=self.bot.user.id,
                    action_type=ESCALATION_ACTION_TYPE,
                    reason=reason,
                )
                try:
                    await member.send(f"⚠️ {reason} (caso #{case_number})")
                except discord.HTTPException:
                    pass

            elif step.action_type == "timeout":
                await member.timeout(
                    timedelta(seconds=step.duration_seconds or 600), reason=reason
                )
                await moderation_repo.create_case(
                    guild_id=execution.guild_id,
                    user_id=member.id,
                    moderator_id=self.bot.user.id,
                    action_type=ESCALATION_ACTION_TYPE,
                    reason=reason,
                    duration_seconds=step.duration_seconds,
                )

            elif step.action_type == "kick":
                await moderation_repo.create_case(
                    guild_id=execution.guild_id,
                    user_id=member.id,
                    moderator_id=self.bot.user.id,
                    action_type=ESCALATION_ACTION_TYPE,
                    reason=reason,
                )
                await member.kick(reason=reason)

            elif step.action_type == "ban":
                await moderation_repo.create_case(
                    guild_id=execution.guild_id,
                    user_id=member.id,
                    moderator_id=self.bot.user.id,
                    action_type=ESCALATION_ACTION_TYPE,
                    reason=reason,
                )
                await member.ban(reason=reason)
        except discord.Forbidden:
            logger.warning(
                "Permessi insufficienti per applicare l'azione di escalation "
                "'%s' sull'utente %s nel server %s.",
                step.action_type,
                member.id,
                execution.guild_id,
            )

    # ================================================================
    # Comandi
    # ================================================================
    escalation_group = app_commands.Group(
        name="escalation", description="Configura la scala di escalation AutoMod."
    )

    @escalation_group.command(name="enable", description="[Admin] Attiva l'escalation ladder.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def enable(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        await escalation_repo.set_enabled(interaction.guild.id, True)
        await interaction.response.send_message("Escalation ladder attivata.", ephemeral=True)

    @escalation_group.command(name="disable", description="[Admin] Disattiva l'escalation ladder.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def disable(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        await escalation_repo.set_enabled(interaction.guild.id, False)
        await interaction.response.send_message("Escalation ladder disattivata.", ephemeral=True)

    @escalation_group.command(
        name="set-reset-days", description="[Admin] Giorni di buona condotta per azzerare il conteggio."
    )
    @app_commands.describe(days="Numero di giorni (default 30)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_reset_days(
        self, interaction: discord.Interaction, days: app_commands.Range[int, 1, 365]
    ) -> None:
        if interaction.guild is None:
            return
        await escalation_repo.set_reset_after_days(interaction.guild.id, days)
        await interaction.response.send_message(
            f"Il conteggio si azzererà dopo {days} giorni senza infrazioni.", ephemeral=True
        )

    @escalation_group.command(
        name="set-step", description="[Admin] Configura l'azione per un livello della scala."
    )
    @app_commands.describe(
        level="Numero dell'infrazione (1 = prima volta, 2 = seconda...)",
        action="Azione da applicare",
        duration_minutes="Durata in minuti (solo per timeout)",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Warn", value="warn"),
            app_commands.Choice(name="Timeout", value="timeout"),
            app_commands.Choice(name="Kick", value="kick"),
            app_commands.Choice(name="Ban", value="ban"),
        ]
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_step(
        self,
        interaction: discord.Interaction,
        level: app_commands.Range[int, 1, 20],
        action: app_commands.Choice[str],
        duration_minutes: app_commands.Range[int, 1, 40320] | None = None,
    ) -> None:
        if interaction.guild is None:
            return

        if action.value == "timeout" and duration_minutes is None:
            await interaction.response.send_message(
                "Specifica una durata in minuti per l'azione timeout.", ephemeral=True
            )
            return

        durata_secondi = duration_minutes * 60 if duration_minutes else None
        await escalation_repo.set_step(interaction.guild.id, level, action.value, durata_secondi)
        await interaction.response.send_message(
            f"Livello {level} impostato su **{action.name}**"
            + (f" ({duration_minutes} minuti)" if durata_secondi else "")
            + ".",
            ephemeral=True,
        )

    @escalation_group.command(
        name="remove-step", description="[Admin] Rimuove un livello dalla scala personalizzata."
    )
    @app_commands.describe(level="Il livello da rimuovere")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def remove_step(self, interaction: discord.Interaction, level: int) -> None:
        if interaction.guild is None:
            return
        rimosso = await escalation_repo.remove_step(interaction.guild.id, level)
        if rimosso:
            await interaction.response.send_message(f"Livello {level} rimosso.", ephemeral=True)
        else:
            await interaction.response.send_message(
                "Nessun gradino personalizzato trovato a questo livello.", ephemeral=True
            )

    @escalation_group.command(
        name="reset", description="[Admin] Azzera il conteggio infrazioni di un membro."
    )
    @app_commands.describe(member="Il membro da azzerare")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def reset(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if interaction.guild is None:
            return
        await escalation_repo.reset_violations(interaction.guild.id, member.id)
        await interaction.response.send_message(
            f"Conteggio infrazioni di {member.mention} azzerato.", ephemeral=True
        )

    @escalation_group.command(
        name="status", description="Mostra la scala di escalation configurata."
    )
    async def status(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        config = await escalation_repo.get_config(interaction.guild.id)

        righe = []
        for step in config.ladder:
            testo_azione = step.action_type
            if step.duration_seconds:
                testo_azione += f" ({step.duration_seconds // 60} min)"
            righe.append(f"**{step.level}**: {testo_azione}")

        embed = discord.Embed(
            title="🪜 Escalation Ladder",
            description=(
                f"Stato: {'attiva' if config.enabled else 'disattivata'}\n"
                f"Reset dopo: {config.reset_after_days} giorni di buona condotta\n\n"
                + "\n".join(righe)
            ),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EscalationCog(bot))
