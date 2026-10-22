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

Gli elenchi restano dentro i limiti di un embed: ogni riga è tagliata
e l'elenco si ferma a 4000 caratteri con "…e altri N".
In più: storico filtrato per tipo, cambio del motivo di un caso,
eliminazione di un caso, classifica dello staff (/mod caso), note da
togliere, cambiare o svuotare (/mod nota), warn da togliere o azzerare
e classifica dei warn (/mod avvisi). Le azioni che cancellano dati
(elimina caso, svuota note, azzera warn) chiedono "Gestire il server".
Sanzioni a tempo ancora attive (MOD-013): tempban, timeout e lock a tempo.
Funzioni coperte: SPEC §5.2, §5.3 (MOD-013, 027..031, 037, 039, 041, 042, 044, 054..056)
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo

from core.repositories.moderation_repo import moderation_repo, ModerationCase
from core.premium import PremiumModule, registry, requires_module
from core.scheduler import scheduler
from cogs.moderation.actions import SCHEDULED_TEMPBAN_EXPIRE
from cogs.moderation.channel_control import SCHEDULED_CHANNEL_UNLOCK
from cogs.moderation._shared import (
    MAX_FIELD_LENGTH,
    MAX_LINE_TEXT_LENGTH,
    MODULE_CASE_SYSTEM,
    Reason,
    ensure_module_enabled,
    join_within_limit,
    post_to_mod_log,
    truncate_text,
    validate_reason,
)

# Una nota finisce nella descrizione di un embed insieme alle altre:
# 1000 caratteri bastano e tengono leggibile l'elenco.
MAX_NOTE_LENGTH = 1000

# Numeri di caso e di nota sono INTEGER nel database: oltre questo limite
# Postgres darebbe DataError.
INT4_MAX = 2**31 - 1

# Colori per tipo di azione, usati per rendere lo storico leggibile
# a colpo d'occhio invece di un elenco di testo uniforme.
TIPI_CASO = [
    ("Warn", "warn"),
    ("Kick", "kick"),
    ("Ban", "ban"),
    ("Tempban", "tempban"),
    ("Softban", "softban"),
    ("Timeout", "timeout"),
    ("Mute (ruolo)", "mute_role"),
    ("Isolamento", "isolamento"),
]
SCELTE_TIPO = [app_commands.Choice(name=n, value=v) for n, v in TIPI_CASO]

# Elenchi: quanti casi leggere dal database (poi l'embed si ferma a 4000 caratteri).
CASI_PER_ELENCO = 25


def _puo_gestire(interaction: discord.Interaction) -> bool:
    """Chi può cancellare dati di moderazione: chi gestisce il server."""
    permessi = interaction.user.guild_permissions
    return permessi.administrator or permessi.manage_guild


async def _rifiuta_senza_gestione(interaction: discord.Interaction) -> bool:
    """True (e risponde) se chi comanda non può cancellare dati."""
    if _puo_gestire(interaction):
        return False
    await interaction.response.send_message(
        "Serve il permesso «Gestire il server» per questa azione.", ephemeral=True
    )
    return True


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
    "softban": "🧹",
    "mute_role": "🔇",
    "isolamento": "🔒",
}


def _format_case_line(case: ModerationCase) -> str:
    icon = _ACTION_ICONS.get(case.action_type, "•")
    stato = "" if case.active else " *(revocato)*"
    data = case.created_at.strftime("%d/%m/%Y %H:%M")
    motivo = truncate_text(case.reason or "Nessun motivo fornito", MAX_LINE_TEXT_LENGTH)
    return f"{icon} **#{case.case_number}** — {case.action_type} — {data}{stato}\n> {motivo}"


# Quante sanzioni a tempo si leggono per tipo (poi l'embed si ferma a 4000 caratteri).
MAX_ATTIVE_PER_TIPO = 100


async def righe_sanzioni_attive(guild: discord.Guild) -> list[str]:
    """MOD-013: tempban, timeout e lock a tempo ancora in corso, dal primo che scade."""
    righe: list[str] = []
    for azione in await scheduler.list_pending_for_guild(guild.id, SCHEDULED_TEMPBAN_EXPIRE, MAX_ATTIVE_PER_TIPO):
        caso = azione["payload"].get("case_number")
        righe.append(
            f"⏳ **Tempban** <@{azione['user_id']}> (`{azione['user_id']}`) — fine "
            f"{discord.utils.format_dt(azione['execute_at'], 'R')}" + (f" — caso #{caso}" if caso else "")
        )
    adesso = discord.utils.utcnow()
    in_timeout = sorted(
        (m for m in guild.members if m.timed_out_until is not None and m.timed_out_until > adesso),
        key=lambda m: m.timed_out_until,
    )[:MAX_ATTIVE_PER_TIPO]
    for membro in in_timeout:
        righe.append(
            f"🔇 **Timeout** {membro.mention} (`{membro.id}`) — fine "
            f"{discord.utils.format_dt(membro.timed_out_until, 'R')}"
        )
    for azione in await scheduler.list_pending_for_guild(guild.id, SCHEDULED_CHANNEL_UNLOCK, MAX_ATTIVE_PER_TIPO):
        righe.append(
            f"🔒 **Lock** <#{azione['user_id']}> — si sblocca "
            f"{discord.utils.format_dt(azione['execute_at'], 'R')}"
        )
    return righe


class ModerationCaseSystemCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "mod",
        nome="attive",
        descrizione="Sanzioni a tempo ancora in corso: tempban, timeout, lock a tempo.",
        sottogruppo=("caso", "Storico e dettagli dei casi di moderazione."),
    )
    @requires_module(MODULE_CASE_SYSTEM)
    async def active(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        await interaction.response.defer(ephemeral=True)
        righe = await righe_sanzioni_attive(interaction.guild)
        embed = discord.Embed(
            title="Sanzioni a tempo in corso",
            color=discord.Color.blurple(),
            description=join_within_limit(righe, "…e altre {n}.") if righe else "Nessuna.",
        )
        await interaction.followup.send(
            embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )

    @comando_di_gruppo(
        "mod",
        nome="storico",
        descrizione="Mostra lo storico casi di un membro.",
        sottogruppo=("caso", "Storico e dettagli dei casi di moderazione."),
    )
    @app_commands.describe(
        member="Il membro di cui vedere lo storico",
        tipo="Mostra solo un tipo di caso (warn, ban, kick...)",
    )
    @app_commands.choices(tipo=SCELTE_TIPO)
    @requires_module(MODULE_CASE_SYSTEM)
    async def history(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        tipo: app_commands.Choice[str] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return

        casi = await moderation_repo.list_cases_for_user(
            interaction.guild.id, member.id,
            limit=CASI_PER_ELENCO, action_type=tipo.value if tipo else None,
        )
        if not casi:
            await interaction.response.send_message(
                f"Nessun caso registrato per {member.mention}.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"Storico moderazione — {member.display_name}",
            color=discord.Color.blurple(),
            description=join_within_limit(
                [_format_case_line(c) for c in casi], "…e altri {n} casi."
            ),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Ultimi {len(casi)} casi")
        await interaction.response.send_message(embed=embed)

    @comando_di_gruppo(
        "mod",
        nome="vedi",
        descrizione="Mostra i dettagli di un singolo caso.",
        sottogruppo=("caso", "Storico e dettagli dei casi di moderazione."),
    )
    @app_commands.describe(case_number="Il numero del caso da visualizzare")
    @requires_module(MODULE_CASE_SYSTEM)
    async def view(
        self, interaction: discord.Interaction, case_number: app_commands.Range[int, 1, INT4_MAX]
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
        embed.add_field(
            name="Motivo",
            value=truncate_text(case.reason or "Nessun motivo fornito", MAX_FIELD_LENGTH),
            inline=False,
        )

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

    @comando_di_gruppo(
        "mod",
        nome="aggiungi",
        descrizione="Aggiunge una nota su un utente.",
        sottogruppo=("nota", "Note dello staff su un utente."),
    )
    @app_commands.describe(member="Il membro a cui aggiungere la nota", note="Testo della nota")
    @requires_module(MODULE_CASE_SYSTEM)
    async def note_add(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        note: app_commands.Range[str, 1, MAX_NOTE_LENGTH],
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return

        await moderation_repo.add_note(
            interaction.guild.id, member.id, interaction.user.id, note
        )
        await interaction.response.send_message(
            f"Nota aggiunta per {member.mention}.", ephemeral=True
        )

    @comando_di_gruppo(
        "mod",
        nome="elenca",
        descrizione="Elenca le note su un utente.",
        sottogruppo=("nota", "Note dello staff su un utente."),
    )
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

        righe = [
            f"**#{n.id}** · {n.created_at.strftime('%d/%m/%Y %H:%M')} — <@{n.moderator_id}>\n"
            f"> {truncate_text(n.note, MAX_LINE_TEXT_LENGTH)}"
            for n in note
        ]
        descrizione = join_within_limit(righe, "…e altre {n} note.")
        embed = discord.Embed(
            title=f"Note — {member.display_name}",
            description=descrizione,
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ================================================================
    # /mod caso: modifica motivo, elimina, classifica staff
    # ================================================================
    @comando_di_gruppo(
        "mod",
        nome="motivo",
        descrizione="Cambia il motivo di un caso già registrato.",
        sottogruppo=("caso", "Storico e dettagli dei casi di moderazione."),
    )
    @app_commands.describe(case_number="Il numero del caso", reason="Il nuovo motivo")
    @requires_module(MODULE_CASE_SYSTEM)
    async def case_reason(
        self, interaction: discord.Interaction, case_number: app_commands.Range[int, 1, INT4_MAX], reason: Reason
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        if not await validate_reason(interaction, reason):
            return
        if not await moderation_repo.update_case_reason(interaction.guild.id, case_number, reason):
            await interaction.response.send_message(
                f"Nessun caso #{case_number} trovato su questo server.", ephemeral=True
            )
            return
        await interaction.response.send_message(f"Motivo del caso #{case_number} aggiornato.", ephemeral=True)
        embed = discord.Embed(title=f"✏️ Motivo cambiato — caso #{case_number}", color=discord.Color.blurple())
        embed.add_field(name="Moderatore", value=interaction.user.mention, inline=True)
        embed.add_field(name="Nuovo motivo", value=truncate_text(reason, MAX_FIELD_LENGTH), inline=False)
        await post_to_mod_log(interaction.guild, embed)

    @comando_di_gruppo(
        "mod",
        nome="elimina",
        descrizione="Elimina un caso (serve «Gestire il server»).",
        sottogruppo=("caso", "Storico e dettagli dei casi di moderazione."),
    )
    @app_commands.describe(case_number="Il numero del caso da eliminare")
    @requires_module(MODULE_CASE_SYSTEM)
    async def case_delete(self, interaction: discord.Interaction, case_number: app_commands.Range[int, 1, INT4_MAX]) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        if await _rifiuta_senza_gestione(interaction):
            return
        if not await moderation_repo.delete_case(interaction.guild.id, case_number):
            await interaction.response.send_message(
                f"Nessun caso #{case_number} trovato su questo server.", ephemeral=True
            )
            return
        await interaction.response.send_message(f"Caso #{case_number} eliminato.", ephemeral=True)
        embed = discord.Embed(title=f"🗑️ Caso #{case_number} eliminato", color=discord.Color.dark_grey())
        embed.add_field(name="Moderatore", value=interaction.user.mention, inline=True)
        await post_to_mod_log(interaction.guild, embed)

    @comando_di_gruppo(
        "mod",
        nome="classifica-staff",
        descrizione="Classifica dei moderatori per numero di azioni, o casi di uno solo.",
        sottogruppo=("caso", "Storico e dettagli dei casi di moderazione."),
    )
    @app_commands.describe(
        moderatore="Se indicato, mostra i suoi ultimi casi invece della classifica",
        tipo="Con un moderatore: solo questo tipo di caso",
    )
    @app_commands.choices(tipo=SCELTE_TIPO)
    @requires_module(MODULE_CASE_SYSTEM)
    async def staff_ranking(
        self,
        interaction: discord.Interaction,
        moderatore: discord.Member | None = None,
        tipo: app_commands.Choice[str] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        if moderatore is not None:
            casi = await moderation_repo.list_cases_by_moderator(
                interaction.guild.id, moderatore.id, CASI_PER_ELENCO, tipo.value if tipo else None
            )
            if not casi:
                await interaction.response.send_message(
                    f"Nessun caso fatto da {moderatore.mention}.", ephemeral=True
                )
                return
            testo = join_within_limit([_format_case_line(c) for c in casi], "…e altri {n} casi.")
            titolo = f"Casi di {moderatore.display_name}"
        else:
            classifica = await moderation_repo.moderator_ranking(interaction.guild.id)
            if not classifica:
                await interaction.response.send_message("Ancora nessun caso registrato.", ephemeral=True)
                return
            testo = "\n".join(f"{i}. <@{m}> — {n} azioni" for i, (m, n) in enumerate(classifica, 1))
            titolo = "Moderatori più attivi"
        embed = discord.Embed(title=titolo, description=testo, color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ================================================================
    # /mod nota: toglie, cambia, svuota
    # ================================================================
    @comando_di_gruppo(
        "mod",
        nome="rimuovi",
        descrizione="Toglie una nota (il numero è nell'elenco delle note).",
        sottogruppo=("nota", "Note dello staff su un utente."),
    )
    @app_commands.describe(nota_id="Il numero della nota")
    @requires_module(MODULE_CASE_SYSTEM)
    async def note_remove(self, interaction: discord.Interaction, nota_id: app_commands.Range[int, 1, INT4_MAX]) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        if not await moderation_repo.delete_note(interaction.guild.id, nota_id):
            await interaction.response.send_message(f"Nessuna nota #{nota_id} su questo server.", ephemeral=True)
            return
        await interaction.response.send_message(f"Nota #{nota_id} tolta.", ephemeral=True)

    @comando_di_gruppo(
        "mod",
        nome="modifica",
        descrizione="Cambia il testo di una nota.",
        sottogruppo=("nota", "Note dello staff su un utente."),
    )
    @app_commands.describe(nota_id="Il numero della nota", note="Il nuovo testo")
    @requires_module(MODULE_CASE_SYSTEM)
    async def note_edit(
        self,
        interaction: discord.Interaction,
        nota_id: app_commands.Range[int, 1, INT4_MAX],
        note: app_commands.Range[str, 1, MAX_NOTE_LENGTH],
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        if not await moderation_repo.update_note(interaction.guild.id, nota_id, note):
            await interaction.response.send_message(f"Nessuna nota #{nota_id} su questo server.", ephemeral=True)
            return
        await interaction.response.send_message(f"Nota #{nota_id} aggiornata.", ephemeral=True)

    @comando_di_gruppo(
        "mod",
        nome="svuota",
        descrizione="Cancella tutte le note di un membro (serve «Gestire il server»).",
        sottogruppo=("nota", "Note dello staff su un utente."),
    )
    @app_commands.describe(member="Il membro di cui cancellare le note")
    @requires_module(MODULE_CASE_SYSTEM)
    async def note_clear(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        if await _rifiuta_senza_gestione(interaction):
            return
        n = await moderation_repo.delete_notes_for_user(interaction.guild.id, member.id)
        await interaction.response.send_message(f"Cancellate {n} note di {member.mention}.", ephemeral=True)

    # ================================================================
    # /mod avvisi: togliere i warn e la classifica
    # ================================================================
    @comando_di_gruppo(
        "mod",
        nome="togli",
        descrizione="Toglie un singolo warn (per numero di caso).",
        sottogruppo=("avvisi", "Warn: toglierli, azzerarli, classifica."),
    )
    @app_commands.describe(case_number="Il numero del caso di tipo warn")
    @requires_module(MODULE_CASE_SYSTEM)
    async def warn_remove(self, interaction: discord.Interaction, case_number: app_commands.Range[int, 1, INT4_MAX]) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        caso = await moderation_repo.get_case(interaction.guild.id, case_number)
        if caso is None or caso.action_type != "warn":
            await interaction.response.send_message(
                f"Il caso #{case_number} non esiste o non è un warn.", ephemeral=True
            )
            return
        if not await moderation_repo.revoke_case(interaction.guild.id, case_number, interaction.user.id):
            await interaction.response.send_message("Questo warn è già stato tolto.", ephemeral=True)
            return
        await interaction.response.send_message(f"Warn #{case_number} tolto a <@{caso.user_id}>.")

    @comando_di_gruppo(
        "mod",
        nome="azzera",
        descrizione="Toglie tutti i warn attivi di un membro (serve «Gestire il server»).",
        sottogruppo=("avvisi", "Warn: toglierli, azzerarli, classifica."),
    )
    @app_commands.describe(member="Il membro a cui azzerare i warn")
    @requires_module(MODULE_CASE_SYSTEM)
    async def warn_reset(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        if await _rifiuta_senza_gestione(interaction):
            return
        n = await moderation_repo.revoke_active_cases_for_user(
            interaction.guild.id, member.id, "warn", interaction.user.id
        )
        await interaction.response.send_message(f"Tolti {n} warn a {member.mention}.")

    @comando_di_gruppo(
        "mod",
        nome="classifica",
        descrizione="I membri con più warn attivi.",
        sottogruppo=("avvisi", "Warn: toglierli, azzerarli, classifica."),
    )
    @requires_module(MODULE_CASE_SYSTEM)
    async def warn_ranking(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        classifica = await moderation_repo.warn_ranking(interaction.guild.id)
        if not classifica:
            await interaction.response.send_message("Nessun warn attivo sul server.", ephemeral=True)
            return
        testo = "\n".join(f"{i}. <@{u}> — {n} warn" for i, (u, n) in enumerate(classifica, 1))
        embed = discord.Embed(title="Più warn attivi", description=testo, color=discord.Color.yellow())
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_CASE_SYSTEM,
            display_name="Moderazione — Case System avanzato",
            category="moderation",
            description="Storico casi, dettaglio caso, note dello staff.",
            premium_capable=True,
        )
    )
    await bot.add_cog(ModerationCaseSystemCog(bot))
