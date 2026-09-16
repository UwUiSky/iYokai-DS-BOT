"""
cogs/moderation/case_system.py
=================================
Consultazione del case system: storico casi di un utente, dettaglio
di un singolo caso, note dello staff. Modulo CANDIDATO PREMIUM
(MODULE_CASE_SYSTEM, premium_capable=True) — coerente con lo schema:
le azioni di moderazione restano gratis, ma lo storico/note avanzati
sono un modulo separabile.

Le azioni stesse (warn/kick/ban...) restano in actions.py, sempre
gratuite: qui c'è SOLO la consultazione, non l'esecuzione. Un server
senza questo modulo attivo può comunque bannare/warnare — semplicemente
non vede lo storico formattato, i casi restano comunque salvati nel
database (create_case avviene sempre in actions.py, indipendente da
questo modulo).
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.repositories.moderation_repo import moderation_repo, ModerationCase
from core.premium import PremiumModule, registry, requires_module
from cogs.moderation._shared import MODULE_CASE_SYSTEM, ensure_module_enabled

# Colori per tipo di azione, usati per rendere lo storico leggibile
# a colpo d'occhio invece di un elenco di testo uniforme.
_ACTION_COLORS: dict[str, discord.Color] = {
    "warn": discord.Color.yellow(),
    "kick": discord.Color.orange(),
    "ban": discord.Color.red(),
    "tempban": discord.Color.dark_red(),
    "timeout": discord.Color.dark_orange(),
}

_ACTION_ICONS: dict[str, str] = {
    "warn": "⚠️",
    "kick": "👢",
    "ban": "🔨",
    "tempban": "⏳",
    "timeout": "🔇",
}


def _format_case_line(case: ModerationCase) -> str:
    icon = _ACTION_ICONS.get(case.action_type, "•")
    stato = "" if case.active else " *(revocato)*"
    data = case.created_at.strftime("%d/%m/%Y %H:%M")
    motivo = case.reason or "Nessun motivo fornito"
    return f"{icon} **#{case.case_number}** — {case.action_type} — {data}{stato}\n> {motivo}"


class ModerationCaseSystemCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    modcase_group = app_commands.Group(
        name="modcase", description="Consulta lo storico dei casi di moderazione."
    )

    @modcase_group.command(name="history", description="Mostra lo storico casi di un membro.")
    @app_commands.describe(member="Il membro di cui vedere lo storico")
    @requires_module(MODULE_CASE_SYSTEM)
    async def history(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return

        casi = await moderation_repo.list_cases_for_user(interaction.guild.id, member.id)
        if not casi:
            await interaction.response.send_message(
                f"Nessun caso registrato per {member.mention}.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"Storico moderazione — {member.display_name}",
            color=discord.Color.blurple(),
            description="\n\n".join(_format_case_line(c) for c in casi),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Ultimi {len(casi)} casi")
        await interaction.response.send_message(embed=embed)

    @modcase_group.command(name="view", description="Mostra i dettagli di un singolo caso.")
    @app_commands.describe(case_number="Il numero del caso da visualizzare")
    @requires_module(MODULE_CASE_SYSTEM)
    async def view(
        self, interaction: discord.Interaction, case_number: int
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return

        case = await moderation_repo.get_case(interaction.guild.id, case_number)
        if case is None:
            await interaction.response.send_message(
                f"Nessun caso #{case_number} trovato su questo server.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"Caso #{case.case_number} — {case.action_type}",
            color=_ACTION_COLORS.get(case.action_type, discord.Color.greyple()),
        )
        embed.add_field(name="Utente", value=f"<@{case.user_id}> ({case.user_id})", inline=False)
        embed.add_field(name="Moderatore", value=f"<@{case.moderator_id}>", inline=True)
        embed.add_field(
            name="Data", value=case.created_at.strftime("%d/%m/%Y %H:%M"), inline=True
        )
        embed.add_field(name="Motivo", value=case.reason or "Nessun motivo fornito", inline=False)

        if case.active:
            embed.add_field(name="Stato", value="Attivo", inline=True)
        else:
            revocato_da = f"<@{case.revoked_by}>" if case.revoked_by else "sconosciuto"
            embed.add_field(
                name="Stato",
                value=f"Revocato da {revocato_da} il "
                f"{case.revoked_at.strftime('%d/%m/%Y %H:%M') if case.revoked_at else '?'}",
                inline=True,
            )

        await interaction.response.send_message(embed=embed)

    modnote_group = app_commands.Group(
        name="modnote", description="Gestisce le note dello staff su un utente."
    )

    @modnote_group.command(name="add", description="Aggiunge una nota su un utente.")
    @app_commands.describe(member="Il membro a cui aggiungere la nota", note="Testo della nota")
    @requires_module(MODULE_CASE_SYSTEM)
    async def note_add(
        self, interaction: discord.Interaction, member: discord.Member, note: str
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return

        await moderation_repo.add_note(
            interaction.guild.id, member.id, interaction.user.id, note
        )
        await interaction.response.send_message(
            f"Nota aggiunta per {member.mention}.", ephemeral=True
        )

    @modnote_group.command(name="list", description="Elenca le note su un utente.")
    @app_commands.describe(member="Il membro di cui vedere le note")
    @requires_module(MODULE_CASE_SYSTEM)
    async def note_list(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return

        note = await moderation_repo.list_notes_for_user(interaction.guild.id, member.id)
        if not note:
            await interaction.response.send_message(
                f"Nessuna nota per {member.mention}.", ephemeral=True
            )
            return

        descrizione = "\n\n".join(
            f"**{n.created_at.strftime('%d/%m/%Y %H:%M')}** — <@{n.moderator_id}>\n> {n.note}"
            for n in note
        )
        embed = discord.Embed(
            title=f"Note — {member.display_name}",
            description=descrizione,
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_CASE_SYSTEM,
            display_name="Moderazione — Case System avanzato",
            description="Storico casi, dettaglio caso, note dello staff.",
            premium_capable=True,
        )
    )
    await bot.add_cog(ModerationCaseSystemCog(bot))
