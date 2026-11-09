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
eliminazione di un caso, classifica dello staff (/mod-casi caso), note da
togliere, cambiare o svuotare (/mod-casi nota), warn da togliere o azzerare
e classifica dei warn (/mod-casi avvisi). Le azioni che cancellano dati
(elimina caso, svuota note, azzera warn) chiedono "Gestire il server".
Casi anche per ban, kick e timeout fatti fuori da iYokai (MOD-047, se acceso).
Avviso allo staff quando rientra chi ha dei casi (MOD-064, se acceso).
Sanzioni ancora attive (MOD-013): tempban, timeout, mute con ruolo e lock a tempo.
Casi: durata nuova (MOD-012), esportazione (MOD-043), nascosti (MOD-045), elenco e azzeramento dei
warn del server (MOD-027, 030), scadenza dei casi AutoMod (MOD-048).
Funzioni coperte: SPEC §5.2, §5.3 (MOD-012, 013, 027..031, 037, 039, 041..049, 054..056, 064)
"""

from __future__ import annotations

import io
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core import bot_roles, moderation_opzioni
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.moderation_casi_logic import errore_durata_caso, testo_esportazione
from core.i18n import testo_per
from core.moderation_casi_esterni_logic import ACTION_TYPE_POSSIBILI, caso_da_voce

from core.repositories.moderation_repo import moderation_repo, ModerationCase
from core.premium import PremiumModule, registry, requires_module
from core import moderation_motivi
from core.scheduler import in_seconds, scheduler
from cogs.leveling._pagine import invia_lista
from cogs.moderation.softban_mute import SCHEDULED_MUTE_EXPIRE
from cogs.moderation.actions import SCHEDULED_TEMPBAN_EXPIRE
from cogs.moderation.channel_control import SCHEDULED_CHANNEL_UNLOCK
from cogs.moderation._shared import (
    MAX_FIELD_LENGTH,
    MAX_LINE_TEXT_LENGTH,
    MODULE_CASE_SYSTEM,
    Reason,
    audit_reason,
    format_duration,
    parse_duration,
    check_can_moderate,
    ensure_module_enabled,
    join_within_limit,
    post_to_mod_log,
    completa_motivo,
    risolvi_motivo,
    truncate_text,
    validate_reason,
)

logger = logging.getLogger(__name__)

# File di esportazione: sotto i 10 MiB che Discord accetta.
MAX_FILE_ESPORTAZIONE = 9 * 1024 * 1024
# MOD-012: permesso che serve per cambiare la durata di ogni tipo di caso.
PERMESSO_DURATA = {"tempban": "ban_members", "timeout": "moderate_members", "mute_role": "manage_roles"}
SOTTOGRUPPO_MOTIVI = ("motivi", "Motivi pronti per le sanzioni.")
SCELTE_SEVERITA = [app_commands.Choice(name=n, value=v) for n, v in (("Lieve", "lieve"), ("Media", "media"), ("Grave", "grave"), ("Gravissima", "gravissima"))]
SCELTE_AZIONE = [app_commands.Choice(name=n, value=v) for n, v in (("Avviso (warn)", "warn"), ("Timeout", "timeout"), ("Espulsione (kick)", "kick"), ("Ban", "ban"))]


async def _durata_del_motivo(interaction: discord.Interaction, durata: str | None) -> int | None:
    """I secondi della durata scritta; None se non c'è; -1 dopo aver risposto che non va."""
    if durata is None:
        return None
    try:
        return parse_duration(durata)
    except ValueError as errore:
        await interaction.response.send_message(str(errore), ephemeral=True)
        return -1


async def _motivo_non_valido(interaction: discord.Interaction, codice: str) -> None:
    chiavi = {
        "tetto": "casesystem_motivi_tetto",
        "doppio": "casesystem_motivi_doppio",
        "durata": "casesystem_motivi_durata_non_valida",
    }
    await interaction.response.send_message(
        await testo_per(interaction, chiavi.get(codice, "casesystem_motivi_non_valido"), v1=moderation_motivi.MAX_MOTIVI), ephemeral=True
    )
# Warn del server: se ne leggono al massimo 200 (20 pagine da 10).
MAX_WARN_ELENCO = 200

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
        await testo_per(interaction, "casesystem_serve_il_permesso_gestire_il"), ephemeral=True
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
    """MOD-013: tempban, timeout, mute e lock a tempo ancora in corso, dal primo che scade."""
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
    for stato in await moderation_repo.list_mute_states(guild.id, MAX_ATTIVE_PER_TIPO):
        tipo = "Hardmute" if stato["hard"] else "Mute"
        fine = (
            f"fine {discord.utils.format_dt(stato['finisce_il'], 'R')}"
            if stato["finisce_il"] is not None else "senza fine"
        )
        righe.append(f"🔇 **{tipo}** <@{stato['user_id']}> (`{stato['user_id']}`) — {fine}")
    for azione in await scheduler.list_pending_for_guild(guild.id, SCHEDULED_CHANNEL_UNLOCK, MAX_ATTIVE_PER_TIPO):
        righe.append(
            f"🔒 **Lock** <#{azione['user_id']}> — si sblocca "
            f"{discord.utils.format_dt(azione['execute_at'], 'R')}"
        )
    return righe


class ModerationCaseSystemCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        await super().cog_load()
        self.scadenza_casi.start()

    async def cog_unload(self) -> None:
        self.scadenza_casi.cancel()
        await super().cog_unload()

    @tasks.loop(hours=1)
    async def scadenza_casi(self) -> None:
        """MOD-048: i casi AutoMod con la scadenza passata non contano più."""
        try:
            await moderation_repo.expire_due_cases()
        except Exception:  # noqa: BLE001 - un errore del database non ferma il giro dopo
            logger.exception("Scadenza dei casi AutoMod non riuscita.")

    @scadenza_casi.before_loop
    async def _prima_della_scadenza(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """MOD-064: se il server lo vuole, lo staff sa quando rientra chi ha già dei casi."""
        if member.bot or not (await moderation_opzioni.leggi(member.guild.id)).avviso_rientro:
            return
        if not await db.is_module_active_for_guild(member.guild.id, MODULE_CASE_SYSTEM):
            return
        casi = await moderation_repo.list_cases_for_user(member.guild.id, member.id, 5)
        if not casi:
            return
        embed = discord.Embed(
            title="👀 Rientra un utente con dei casi",
            description=f"{member.mention} ({member.id}). Ultimi casi:\n"
            + join_within_limit([_format_case_line(c) for c in casi], "…e altri {n}."),
            color=discord.Color.orange(),
        )
        await post_to_mod_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry) -> None:
        """MOD-047: ban, kick e timeout fatti dal menu di Discord o da altri bot diventano casi."""
        azione = entry.action
        if azione not in (
            discord.AuditLogAction.ban,
            discord.AuditLogAction.kick,
            discord.AuditLogAction.unban,
            discord.AuditLogAction.member_update,
        ):
            return
        if entry.user_id is None or entry.target is None:
            return
        # Le azioni di iYokai hanno già il loro caso; chi si sanziona da solo non conta.
        if bot_roles.e_un_nostro_bot(entry.user_id, self.bot) or entry.user_id == entry.target.id:
            return
        guild = entry.guild
        if not (await moderation_opzioni.leggi(guild.id)).casi_esterni:
            return
        if not await db.is_module_active_for_guild(guild.id, MODULE_CASE_SYSTEM):
            return
        voce = caso_da_voce(
            azione.name,
            entry.reason,
            timeout_fino=getattr(entry.after, "timed_out_until", None),
            ora=discord.utils.utcnow(),
        )
        if voce is None:
            return
        if voce.tipo == "unban":
            for tipo in ("ban", "tempban"):
                await moderation_repo.revoke_active_cases_for_user(guild.id, entry.target.id, tipo, entry.user_id)
            return
        if voce.tipo not in ACTION_TYPE_POSSIBILI:
            return
        numero = await moderation_repo.create_case(
            guild_id=guild.id,
            user_id=entry.target.id,
            moderator_id=entry.user_id,
            action_type=voce.tipo,
            reason=voce.motivo,
            duration_seconds=voce.durata_secondi,
            origine="esterno",
        )
        embed = discord.Embed(
            title=f"{_ACTION_ICONS.get(voce.tipo, '•')} Caso #{numero} (fatto fuori da iYokai)",
            color=_ACTION_COLORS.get(voce.tipo, discord.Color.blurple()),
        )
        embed.add_field(name="Utente", value=f"<@{entry.target.id}> ({entry.target.id})", inline=False)
        embed.add_field(name="Moderatore", value=f"<@{entry.user_id}>", inline=True)
        embed.add_field(name="Motivo", value=truncate_text(voce.motivo, MAX_FIELD_LENGTH), inline=False)
        await post_to_mod_log(guild, embed)

    @comando_di_gruppo(
        "mod-casi",
        nome="attive",
        descrizione="Sanzioni ancora in corso: tempban, timeout, mute, lock a tempo.",
        sottogruppo=("caso", "Storico e dettagli dei casi di moderazione."),
    )
    @requires_module(MODULE_CASE_SYSTEM)
    async def active(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        await interaction.response.defer(ephemeral=True)
        righe = await righe_sanzioni_attive(interaction.guild)
        embed = discord.Embed(
            title=await testo_per(interaction, "casesystem_sanzioni_tempo_in_corso"),
            color=discord.Color.blurple(),
            description=join_within_limit(righe, "…e altre {n}.") if righe else await testo_per(interaction, "casesystem_nessuna"),
        )
        await interaction.followup.send(
            embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )

    @comando_di_gruppo(
        "mod-casi",
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
                await testo_per(interaction, "casesystem_nessun_caso_registrato_per", mention=member.mention), ephemeral=True
            )
            return

        embed = discord.Embed(
            title=await testo_per(interaction, "casesystem_storico_moderazione", display_name=member.display_name, pubblica=True),
            color=discord.Color.blurple(),
            description=join_within_limit(
                [_format_case_line(c) for c in casi], "…e altri {n} casi."
            ),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=await testo_per(interaction, "casesystem_ultimi_casi", v1=len(casi), pubblica=True))
        await interaction.response.send_message(embed=embed)

    @comando_di_gruppo(
        "mod-casi",
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
                await testo_per(interaction, "casesystem_nessun_caso_trovato_su_questo", case_number=case_number),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=await testo_per(interaction, "casesystem_caso", case_number=case.case_number, action_type=case.action_type, pubblica=True),
            color=_ACTION_COLORS.get(case.action_type, discord.Color.greyple()),
        )
        embed.add_field(name=await testo_per(interaction, "banappeal_utente", pubblica=True), value=f"<@{case.user_id}> ({case.user_id})", inline=False)
        embed.add_field(name=await testo_per(interaction, "channelcontr_moderatore", pubblica=True), value=f"<@{case.moderator_id}>", inline=True)
        embed.add_field(
            name=await testo_per(interaction, "casesystem_data", pubblica=True), value=case.created_at.strftime("%d/%m/%Y %H:%M"), inline=True
        )
        embed.add_field(
            name=await testo_per(interaction, "channelcontr_motivo", pubblica=True),
            value=truncate_text(case.reason or "Nessun motivo fornito", MAX_FIELD_LENGTH),
            inline=False,
        )

        if case.active:
            embed.add_field(name=await testo_per(interaction, "ricerca_stato", pubblica=True), value=await testo_per(interaction, "casesystem_attivo", pubblica=True), inline=True)
        else:
            revocato_da = f"<@{case.revoked_by}>" if case.revoked_by else "sconosciuto"
            embed.add_field(
                name=await testo_per(interaction, "ricerca_stato", pubblica=True),
                value=f"Revocato da {revocato_da} il "
                f"{case.revoked_at.strftime('%d/%m/%Y %H:%M') if case.revoked_at else '?'}",
                inline=True,
            )

        await interaction.response.send_message(embed=embed)

    @comando_di_gruppo(
        "mod-casi",
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
            await testo_per(interaction, "casesystem_nota_aggiunta_per", mention=member.mention), ephemeral=True
        )

    @comando_di_gruppo(
        "mod-casi",
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
                await testo_per(interaction, "casesystem_nessuna_nota_per", mention=member.mention), ephemeral=True
            )
            return

        righe = [
            f"**#{n.id}** · {n.created_at.strftime('%d/%m/%Y %H:%M')} — <@{n.moderator_id}>\n"
            f"> {truncate_text(n.note, MAX_LINE_TEXT_LENGTH)}"
            for n in note
        ]
        descrizione = join_within_limit(righe, "…e altre {n} note.")
        embed = discord.Embed(
            title=await testo_per(interaction, "casesystem_note", display_name=member.display_name),
            description=descrizione,
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ================================================================
    # /mod-casi caso: modifica motivo, elimina, classifica staff
    # ================================================================
    @comando_di_gruppo(
        "mod-casi",
        nome="motivo",
        descrizione="Cambia il motivo di un caso già registrato.",
        sottogruppo=("caso", "Storico e dettagli dei casi di moderazione."),
    )
    @app_commands.describe(case_number="Il numero del caso", reason="Il nuovo motivo (anche un motivo pronto)")
    @app_commands.autocomplete(reason=completa_motivo)
    @requires_module(MODULE_CASE_SYSTEM)
    async def case_reason(
        self, interaction: discord.Interaction, case_number: app_commands.Range[int, 1, INT4_MAX], reason: Reason
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        reason = await risolvi_motivo(interaction, reason, obbligatorio=True)
        if reason is None:
            return
        if not await moderation_repo.update_case_reason(interaction.guild.id, case_number, reason):
            await interaction.response.send_message(
                await testo_per(interaction, "casesystem_nessun_caso_trovato_su_questo", case_number=case_number), ephemeral=True
            )
            return
        await interaction.response.send_message(await testo_per(interaction, "casesystem_motivo_del_caso_aggiornato", case_number=case_number), ephemeral=True)
        embed = discord.Embed(title=await testo_per(interaction, "casesystem_motivo_cambiato_caso", case_number=case_number, pubblica=True), color=discord.Color.blurple())
        embed.add_field(name=await testo_per(interaction, "channelcontr_moderatore", pubblica=True), value=interaction.user.mention, inline=True)
        embed.add_field(name=await testo_per(interaction, "casesystem_nuovo_motivo", pubblica=True), value=truncate_text(reason, MAX_FIELD_LENGTH), inline=False)
        await post_to_mod_log(interaction.guild, embed)

    # ================================================================
    # /mod-casi motivi: motivi pronti (MOD-113)
    # ================================================================
    @comando_di_gruppo(
        "mod-casi",
        nome="aggiungi",
        descrizione="Aggiunge un motivo pronto, da richiamare nel campo «motivo» (serve «Gestire il server»).",
        sottogruppo=SOTTOGRUPPO_MOTIVI,
    )
    @app_commands.describe(
        nome="Nome breve del motivo (fino a 32 caratteri)",
        testo="Il testo del motivo (da 3 a 512 caratteri)",
        severita="Quanto è grave (D68)",
        azione="La sanzione che il bot propone",
        durata="Durata del timeout proposto, es. 1h, 24h, 7d (max 28 giorni)",
    )
    @app_commands.choices(severita=SCELTE_SEVERITA, azione=SCELTE_AZIONE)
    async def motivo_aggiungi(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, moderation_motivi.MAX_NOME],
        testo: app_commands.Range[str, moderation_motivi.MIN_TESTO, moderation_motivi.MAX_TESTO],
        severita: app_commands.Choice[str] | None = None,
        azione: app_commands.Choice[str] | None = None,
        durata: app_commands.Range[str, 1, 20] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        if await _rifiuta_senza_gestione(interaction):
            return
        secondi = await _durata_del_motivo(interaction, durata)
        if secondi == -1:
            return
        try:
            await moderation_motivi.aggiungi(
                interaction.guild.id, nome, testo, interaction.user.id,
                severita.value if severita else None, azione.value if azione else None, secondi,
            )
        except ValueError as errore:
            await _motivo_non_valido(interaction, str(errore))
            return
        await interaction.response.send_message(await testo_per(interaction, "casesystem_motivi_aggiunto", nome=nome), ephemeral=True)

    @comando_di_gruppo(
        "mod-casi",
        nome="modifica",
        descrizione="Cambia testo, severità o sanzione di un motivo pronto (serve «Gestire il server»).",
        sottogruppo=SOTTOGRUPPO_MOTIVI,
    )
    @app_commands.describe(
        nome="Il motivo da cambiare",
        testo="Il nuovo testo (da 3 a 512 caratteri)",
        severita="La nuova severità",
        azione="La nuova sanzione proposta",
        durata="Nuova durata del timeout, es. 1h, 24h, 7d (max 28 giorni)",
    )
    @app_commands.choices(severita=SCELTE_SEVERITA, azione=SCELTE_AZIONE)
    async def motivo_modifica(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, moderation_motivi.MAX_NOME],
        testo: app_commands.Range[str, moderation_motivi.MIN_TESTO, moderation_motivi.MAX_TESTO] | None = None,
        severita: app_commands.Choice[str] | None = None,
        azione: app_commands.Choice[str] | None = None,
        durata: app_commands.Range[str, 1, 20] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        if await _rifiuta_senza_gestione(interaction):
            return
        secondi = await _durata_del_motivo(interaction, durata)
        if secondi == -1:
            return
        try:
            trovato = await moderation_motivi.modifica(
                interaction.guild.id, nome, testo, severita.value if severita else None, azione.value if azione else None, secondi
            )
        except ValueError as errore:
            await _motivo_non_valido(interaction, str(errore))
            return
        chiave = "casesystem_motivi_modificato" if trovato else "casesystem_motivi_non_trovato"
        await interaction.response.send_message(await testo_per(interaction, chiave, nome=nome), ephemeral=True)

    @comando_di_gruppo(
        "mod-casi",
        nome="elenco",
        descrizione="Mostra i motivi pronti del server.",
        sottogruppo=SOTTOGRUPPO_MOTIVI,
    )
    async def motivo_elenco(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        elenco = await moderation_motivi.elenco(interaction.guild.id)
        if not elenco:
            await interaction.response.send_message(await testo_per(interaction, "casesystem_motivi_nessuno"), ephemeral=True)
            return
        righe = [
            f"**{m['nome']}**" + (f" [{moderation_motivi.sanzione_breve(m)}]" if moderation_motivi.sanzione_breve(m) else "")
            + f": {truncate_text(m['testo'], 90)}"
            for m in elenco
        ]
        embed = discord.Embed(
            title=await testo_per(interaction, "casesystem_motivi_titolo"),
            description="\n".join(righe)[:4000],
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @comando_di_gruppo(
        "mod-casi",
        nome="togli",
        descrizione="Toglie un motivo pronto (serve «Gestire il server»).",
        sottogruppo=SOTTOGRUPPO_MOTIVI,
    )
    @app_commands.describe(nome="Il nome del motivo da togliere")
    async def motivo_togli(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, moderation_motivi.MAX_NOME]) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        if await _rifiuta_senza_gestione(interaction):
            return
        chiave = "casesystem_motivi_tolto" if await moderation_motivi.togli(interaction.guild.id, nome) else "casesystem_motivi_non_trovato"
        await interaction.response.send_message(await testo_per(interaction, chiave, nome=nome), ephemeral=True)

    @comando_di_gruppo(
        "mod-casi",
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
                await testo_per(interaction, "casesystem_nessun_caso_trovato_su_questo", case_number=case_number), ephemeral=True
            )
            return
        await interaction.response.send_message(await testo_per(interaction, "casesystem_caso_eliminato", case_number=case_number), ephemeral=True)
        embed = discord.Embed(title=await testo_per(interaction, "casesystem_caso_eliminato_2", case_number=case_number, pubblica=True), color=discord.Color.dark_grey())
        embed.add_field(name=await testo_per(interaction, "channelcontr_moderatore", pubblica=True), value=interaction.user.mention, inline=True)
        await post_to_mod_log(interaction.guild, embed)

    @comando_di_gruppo(
        "mod-casi",
        nome="registra",
        descrizione="Registra un caso senza eseguire l'azione (sanzione data fuori dal bot).",
        sottogruppo=("caso", "Storico e dettagli dei casi di moderazione."),
    )
    @app_commands.describe(
        utente="L'utente sanzionato (anche fuori dal server)",
        tipo="Che sanzione è stata data",
        reason="Motivo della sanzione",
        a_nome_di="Il moderatore che l'ha data, se non sei tu (serve «Gestire il server»)",
    )
    @app_commands.choices(tipo=SCELTE_TIPO)
    @requires_module(MODULE_CASE_SYSTEM)
    async def case_register(
        self,
        interaction: discord.Interaction,
        utente: discord.User,
        tipo: app_commands.Choice[str],
        reason: Reason,
        a_nome_di: discord.Member | None = None,
    ) -> None:
        """MOD-046, MOD-049: il caso entra nello storico, ma sul server non cambia nulla."""
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        if not await validate_reason(interaction, reason):
            return
        if a_nome_di is not None and a_nome_di.id != interaction.user.id:
            if await _rifiuta_senza_gestione(interaction):
                return
        # Gerarchia e ruoli immuni come per le azioni vere (MOD-068); chi non è nel server non ha ruoli.
        membro = interaction.guild.get_member(utente.id)
        if membro is not None and not await check_can_moderate(interaction, membro, azione_su_discord=False):
            return
        moderatore = a_nome_di or interaction.user
        numero = await moderation_repo.create_case(
            guild_id=interaction.guild.id,
            user_id=utente.id,
            moderator_id=moderatore.id,
            action_type=tipo.value,
            reason=reason,
        )
        embed = discord.Embed(
            title=f"{_ACTION_ICONS.get(tipo.value, '•')} Caso #{numero} registrato a mano",
            color=_ACTION_COLORS.get(tipo.value, discord.Color.blurple()),
        )
        embed.add_field(name=await testo_per(interaction, "banappeal_utente", pubblica=True), value=f"<@{utente.id}> ({utente.id})", inline=False)
        embed.add_field(name=await testo_per(interaction, "casesystem_tipo", pubblica=True), value=tipo.name, inline=True)
        embed.add_field(name=await testo_per(interaction, "channelcontr_moderatore", pubblica=True), value=moderatore.mention, inline=True)
        embed.add_field(name=await testo_per(interaction, "channelcontr_motivo", pubblica=True), value=truncate_text(reason, MAX_FIELD_LENGTH), inline=False)
        embed.set_footer(text=await testo_per(interaction, "casesystem_registrato_da_nessuna_azione_eseguita", display_name=interaction.user.display_name, pubblica=True))
        await interaction.response.send_message(
            embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )
        await post_to_mod_log(interaction.guild, embed)

    @comando_di_gruppo(
        "mod-casi",
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
                    await testo_per(interaction, "casesystem_nessun_caso_fatto_da", mention=moderatore.mention), ephemeral=True
                )
                return
            testo = join_within_limit([_format_case_line(c) for c in casi], "…e altri {n} casi.")
            titolo = f"Casi di {moderatore.display_name}"
        else:
            classifica = await moderation_repo.moderator_ranking(interaction.guild.id)
            if not classifica:
                await interaction.response.send_message(await testo_per(interaction, "casesystem_ancora_nessun_caso_registrato"), ephemeral=True)
                return
            testo = "\n".join(f"{i}. <@{m}> — {n} azioni" for i, (m, n) in enumerate(classifica, 1))
            titolo = "Moderatori più attivi"
        embed = discord.Embed(title=titolo, description=testo, color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ================================================================
    # /mod-casi nota: toglie, cambia, svuota
    # ================================================================
    @comando_di_gruppo(
        "mod-casi",
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
            await interaction.response.send_message(await testo_per(interaction, "casesystem_nessuna_nota_su_questo_server", nota_id=nota_id), ephemeral=True)
            return
        await interaction.response.send_message(await testo_per(interaction, "casesystem_nota_tolta", nota_id=nota_id), ephemeral=True)

    @comando_di_gruppo(
        "mod-casi",
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
            await interaction.response.send_message(await testo_per(interaction, "casesystem_nessuna_nota_su_questo_server", nota_id=nota_id), ephemeral=True)
            return
        await interaction.response.send_message(await testo_per(interaction, "casesystem_nota_aggiornata", nota_id=nota_id), ephemeral=True)

    @comando_di_gruppo(
        "mod-casi",
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
        await interaction.response.send_message(await testo_per(interaction, "casesystem_cancellate_note_di", n=n, mention=member.mention), ephemeral=True)

    # ================================================================
    # /mod-casi caso: durata, nascondi, esporta (M3)
    # ================================================================
    @comando_di_gruppo(
        "mod-casi",
        nome="durata",
        descrizione="Cambia la durata di un tempban, di un timeout o di un mute ancora in corso.",
        sottogruppo=("caso", "Storico e dettagli dei casi di moderazione."),
    )
    @app_commands.describe(
        case_number="Il numero del caso", durata="La nuova durata, contata da adesso (es. 2h, 7d)"
    )
    @requires_module(MODULE_CASE_SYSTEM)
    async def case_duration(
        self,
        interaction: discord.Interaction,
        case_number: app_commands.Range[int, 1, INT4_MAX],
        durata: app_commands.Range[str, 2, 20],
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        guild = interaction.guild
        try:
            secondi = parse_duration(durata)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        caso = await moderation_repo.get_case(guild.id, case_number)
        if caso is None:
            await interaction.response.send_message(
                await testo_per(interaction, "casesystem_nessun_caso_trovato_su_questo", case_number=case_number), ephemeral=True
            )
            return
        errore = errore_durata_caso(caso.action_type, caso.active, secondi)
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return
        # Il bot agisce per chi comanda: serve il permesso della sanzione e la gerarchia.
        permessi = interaction.user.guild_permissions
        if not (permessi.administrator or getattr(permessi, PERMESSO_DURATA[caso.action_type])):
            await interaction.response.send_message(
                await testo_per(interaction, "casesystem_durata_serve_permesso"), ephemeral=True
            )
            return
        bersaglio = guild.get_member(caso.user_id)
        if bersaglio is not None and not await check_can_moderate(interaction, bersaglio):
            return
        await interaction.response.defer(ephemeral=True)
        fine = in_seconds(secondi)
        if caso.action_type == "timeout":
            membro = bersaglio
            if membro is None:
                await interaction.followup.send(await testo_per(interaction, "casesystem_durata_membro_assente"), ephemeral=True)
                return
            try:
                await membro.edit(timed_out_until=fine, reason=audit_reason(f"Durata del caso #{case_number} cambiata"))
            except discord.HTTPException:
                await interaction.followup.send(await testo_per(interaction, "casesystem_durata_non_riuscita"), ephemeral=True)
                return
        elif caso.action_type == "tempban":
            stato = await moderation_repo.get_tempban_state(guild.id, caso.user_id)
            await moderation_repo.cancel_tempban_jobs(guild.id, caso.user_id)
            if stato:
                await moderation_repo.save_tempban_state(
                    guild.id, caso.user_id, stato["modo"], list(stato["ruoli"]), fine,
                    stato["invito_codice"], case_number, stato["oauth_rientro"],
                )
            await scheduler.schedule(
                guild_id=guild.id, user_id=caso.user_id, action_type=SCHEDULED_TEMPBAN_EXPIRE,
                execute_at=fine, payload={"case_number": case_number, "modo": stato["modo"] if stato else "ban"},
            )
        else:  # mute con ruolo
            stato = await moderation_repo.get_mute_state(guild.id, caso.user_id)
            await scheduler.cancel_for_user(guild.id, caso.user_id, SCHEDULED_MUTE_EXPIRE)
            await moderation_repo.save_mute_state(
                guild.id, caso.user_id, bool(stato and stato["hard"]), list(stato["ruoli"]) if stato else [],
                case_number, fine,
            )
            await scheduler.schedule(
                guild_id=guild.id, user_id=caso.user_id, action_type=SCHEDULED_MUTE_EXPIRE,
                execute_at=fine, payload={"caso": case_number},
            )
        await moderation_repo.update_case_duration(guild.id, case_number, secondi)
        await interaction.followup.send(
            await testo_per(interaction, "casesystem_durata_cambiata", case_number=case_number, durata=format_duration(secondi)),
            ephemeral=True,
        )
        embed = discord.Embed(
            title=await testo_per(interaction, "casesystem_durata_log", case_number=case_number, pubblica=True),
            color=discord.Color.blurple(),
        )
        embed.add_field(name=await testo_per(interaction, "channelcontr_moderatore", pubblica=True), value=interaction.user.mention, inline=True)
        embed.add_field(name=await testo_per(interaction, "casesystem_durata_nuova", pubblica=True), value=format_duration(secondi), inline=True)
        await post_to_mod_log(guild, embed)

    @comando_di_gruppo(
        "mod-casi",
        nome="nascondi",
        descrizione="Nasconde un caso (non conta in classifiche e avvisi) o lo riattiva.",
        sottogruppo=("caso", "Storico e dettagli dei casi di moderazione."),
    )
    @app_commands.describe(case_number="Il numero del caso", nascosto="Sì per nascondere, no per riattivare")
    @requires_module(MODULE_CASE_SYSTEM)
    async def case_hide(
        self,
        interaction: discord.Interaction,
        case_number: app_commands.Range[int, 1, INT4_MAX],
        nascosto: bool = True,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        if not await moderation_repo.set_case_hidden(interaction.guild.id, case_number, nascosto):
            await interaction.response.send_message(
                await testo_per(interaction, "casesystem_nessun_caso_trovato_su_questo", case_number=case_number), ephemeral=True
            )
            return
        chiave = "casesystem_caso_nascosto" if nascosto else "casesystem_caso_riattivato"
        await interaction.response.send_message(await testo_per(interaction, chiave, case_number=case_number), ephemeral=True)
        embed = discord.Embed(
            title=await testo_per(interaction, chiave, case_number=case_number, pubblica=True), color=discord.Color.dark_grey()
        )
        embed.add_field(name=await testo_per(interaction, "channelcontr_moderatore", pubblica=True), value=interaction.user.mention, inline=True)
        await post_to_mod_log(interaction.guild, embed)

    @comando_di_gruppo(
        "mod-casi",
        nome="esporta",
        descrizione="Manda in un file di testo i casi e le note di un membro.",
        sottogruppo=("caso", "Storico e dettagli dei casi di moderazione."),
    )
    @app_commands.describe(utente="Il membro (anche se ha lasciato il server)")
    @requires_module(MODULE_CASE_SYSTEM)
    async def case_export(self, interaction: discord.Interaction, utente: discord.User) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        await interaction.response.defer(ephemeral=True)
        casi = await moderation_repo.list_all_cases_for_user(interaction.guild.id, utente.id)
        note = await moderation_repo.list_notes_for_user(interaction.guild.id, utente.id, 1000)
        if not casi and not note:
            await interaction.followup.send(await testo_per(interaction, "casesystem_esporta_vuoto"), ephemeral=True)
            return
        testo = testo_esportazione(utente.id, casi, note)
        dati = testo.encode("utf-8")
        if len(dati) > MAX_FILE_ESPORTAZIONE:  # sotto i 10 MiB dei file di Discord
            dati = dati[:MAX_FILE_ESPORTAZIONE].decode("utf-8", errors="ignore").encode("utf-8")
        await interaction.followup.send(
            await testo_per(interaction, "casesystem_esporta_pronto", v1=len(casi), v2=len(note)),
            file=discord.File(io.BytesIO(dati), filename=f"casi_{utente.id}.txt"),
            ephemeral=True,
        )

    # ================================================================
    # /mod-casi avvisi: togliere i warn e la classifica
    # ================================================================
    @comando_di_gruppo(
        "mod-casi",
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
                await testo_per(interaction, "casesystem_il_caso_non_esiste_non", case_number=case_number), ephemeral=True
            )
            return
        if not await moderation_repo.revoke_case(interaction.guild.id, case_number, interaction.user.id):
            await interaction.response.send_message(await testo_per(interaction, "casesystem_questo_warn_gia_stato_tolto"), ephemeral=True)
            return
        await interaction.response.send_message(await testo_per(interaction, "casesystem_warn_tolto", pubblica=True, case_number=case_number, user_id=caso.user_id))

    @comando_di_gruppo(
        "mod-casi",
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
        await interaction.response.send_message(await testo_per(interaction, "casesystem_tolti_warn", pubblica=True, n=n, mention=member.mention))

    @comando_di_gruppo(
        "mod-casi",
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
            await interaction.response.send_message(await testo_per(interaction, "casesystem_nessun_warn_attivo_sul_server"), ephemeral=True)
            return
        testo = "\n".join(f"{i}. <@{u}> — {n} warn" for i, (u, n) in enumerate(classifica, 1))
        embed = discord.Embed(title=await testo_per(interaction, "casesystem_piu_warn_attivi"), description=testo, color=discord.Color.yellow())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @comando_di_gruppo(
        "mod-casi",
        nome="elenco",
        descrizione="Tutti i warn attivi del server, a pagine.",
        sottogruppo=("avvisi", "Warn: toglierli, azzerarli, classifica."),
    )
    @requires_module(MODULE_CASE_SYSTEM)
    async def warn_list(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        warn = await moderation_repo.list_active_warns(interaction.guild.id, MAX_WARN_ELENCO)
        if not warn:
            await interaction.response.send_message(await testo_per(interaction, "casesystem_nessun_warn_attivo_sul_server"), ephemeral=True)
            return
        righe = [
            f"**#{c.case_number}** <@{c.user_id}> — {truncate_text(c.reason or '-', MAX_LINE_TEXT_LENGTH)}" for c in warn
        ]
        await invia_lista(
            interaction, await testo_per(interaction, "casesystem_warn_attivi_titolo"), righe,
            discord.Color.yellow(), ephemeral=True,
        )

    @comando_di_gruppo(
        "mod-casi",
        nome="azzera-tutti",
        descrizione="Toglie i warn attivi di tutto il server (serve «Gestire il server»).",
        sottogruppo=("avvisi", "Warn: toglierli, azzerarli, classifica."),
    )
    @app_commands.describe(conferma="Scrivi quanti warn attivi ha il server adesso (lo vedi con /mod-casi avvisi elenco)")
    @requires_module(MODULE_CASE_SYSTEM)
    async def warn_reset_all(
        self, interaction: discord.Interaction, conferma: app_commands.Range[int, 0, INT4_MAX]
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        if await _rifiuta_senza_gestione(interaction):
            return
        quanti = await moderation_repo.count_active_warns(interaction.guild.id)
        if conferma != quanti:
            await interaction.response.send_message(
                await testo_per(interaction, "casesystem_azzera_tutti_numero_sbagliato", v1=quanti), ephemeral=True
            )
            return
        n = await moderation_repo.revoke_all_warns(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(await testo_per(interaction, "casesystem_azzera_tutti_fatto", v1=n), ephemeral=True)
        embed = discord.Embed(
            title=await testo_per(interaction, "casesystem_azzera_tutti_log", pubblica=True), color=discord.Color.dark_grey()
        )
        embed.add_field(name=await testo_per(interaction, "channelcontr_moderatore", pubblica=True), value=interaction.user.mention, inline=True)
        embed.add_field(name=await testo_per(interaction, "clear_cancellati", pubblica=True), value=str(n), inline=True)
        await post_to_mod_log(interaction.guild, embed)


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
