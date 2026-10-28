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

Se il server lo sceglie, anche un warn dato a mano conta
un'infrazione (M 1.10, `scala_per_warn_manuale`). In quel caso la scala fa
solo ciò che il moderatore potrebbe fare da sé (permessi e gerarchia), e
dai warn in massa non partono mai kick e ban (D29). Un gradino di timeout
non accorcia mai un timeout più lungo già in corso.

Un messaggio conta una sola infrazione anche se la regola ha più
azioni (Discord manda un evento per azione). Il conteggio è una sola
istruzione nel database (core/repositories/escalation_repo.py).

Doppio gate per l'attivazione: il modulo AutoMod di base deve essere
attivo (MODULE_AUTOMOD — l'escalation non ha senso senza le regole
che genera i trigger) E l'escalation deve essere esplicitamente
abilitata (EscalationConfig.enabled) — un admin potrebbe volere solo
il filtro nativo senza la scala di severità crescente.

Anche una parola vietata trovata dal filtro del bot conta un'infrazione
(AMD-014, evento `automod_parole_vietate` mandato da cogs/automod/automod.py).
Funzioni coperte: SPEC §6 (escalation ladder, M 1.10, AMD-014)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo

from core import bot_roles
from core.bounded_cache import BoundedCache
from core.database import db
from core.escalation_ladder_logic import get_ladder_action
from core.repositories.escalation_repo import escalation_repo
from core.repositories.moderation_repo import moderation_repo
from cogs.automod.automod import MODULE_AUTOMOD, _is_safe_from_automated_action
from cogs.moderation._shared import actor_from_member
from core.permissions import can_moderate

logger = logging.getLogger("iyokai.automod.escalation")

ESCALATION_ACTION_TYPE = "automod_escalation"

# Discord manda un evento per OGNI azione della regola (blocca, avvisa,
# timeout): gli eventi uguali arrivati entro questi secondi sono lo
# stesso messaggio e contano come una sola infrazione.
FINESTRA_STESSO_MESSAGGIO = 5

# Lunghezza massima di un motivo nel registro di controllo di Discord.
MAX_MOTIVO = 512


def _adesso() -> datetime:
    return datetime.now(timezone.utc)


# D29: il permesso di Discord che serve al moderatore per ogni gradino.
_PERMESSO_GRADINO = {"timeout": "moderate_members", "kick": "kick_members", "ban": "ban_members"}


def _timeout_piu_lungo_in_corso(member: discord.Member, step) -> bool:
    """True se il gradino è un timeout e quello già in corso finisce dopo."""
    if step.action_type != "timeout":
        return False
    fine = getattr(member, "timed_out_until", None)
    if not isinstance(fine, datetime):
        return False
    return fine >= _adesso() + timedelta(seconds=step.duration_seconds or 600)


def _motivo_non_permesso(moderatore: discord.Member, member: discord.Member, step) -> str | None:
    """D29: il gradino parte solo se il moderatore del warn potrebbe farlo da sé."""
    if moderatore.id != member.guild.owner_id:
        if not getattr(moderatore.guild_permissions, _PERMESSO_GRADINO[step.action_type]):
            return "non hai il permesso di Discord per farlo"
    consentito, motivo = can_moderate(
        actor_from_member(moderatore), actor_from_member(member),
        bot_top_role_position=member.guild.me.top_role.position,
    )
    return None if consentito else motivo.rstrip(".").lower()


async def _applica_passo(
    bot: commands.Bot, guild_id: int, member: discord.Member, step, reason: str
) -> int | None:
    """
    Esegue un gradino della scala e apre il caso. Restituisce il numero del
    caso, oppure None se l'azione su Discord non è riuscita.
    """
    # Prima l'azione su Discord, poi il caso: se l'azione fallisce
    # non resta un caso per una punizione mai data.
    try:
        if step.action_type == "timeout":
            await bot_roles.isola(member, timedelta(seconds=step.duration_seconds or 600), reason=reason)
        elif step.action_type == "kick":
            await bot_roles.espelli(member, reason=reason)
        elif step.action_type == "ban":
            await bot_roles.banna(
                member.guild, member, reason=reason, delete_message_seconds=86400,
                principale=lambda: member.ban(reason=reason),
            )
    except discord.HTTPException as errore:
        logger.warning(
            "Azione di escalation '%s' non riuscita sull'utente %s nel server %s: %s",
            step.action_type, member.id, guild_id, errore,
        )
        return None

    case_number = await moderation_repo.create_case(
        guild_id=guild_id,
        user_id=member.id,
        moderator_id=bot.user.id,
        action_type=ESCALATION_ACTION_TYPE,
        reason=reason,
        duration_seconds=step.duration_seconds if step.action_type == "timeout" else None,
    )
    if step.action_type == "warn":
        try:
            await member.send(f"⚠️ {reason} (caso #{case_number})")
        except discord.HTTPException:
            pass
    return case_number


async def scala_per_warn_manuale(
    bot: commands.Bot,
    member: discord.Member,
    caso_warn: int,
    *,
    moderatore: discord.Member,
    in_massa: bool = False,
) -> str | None:
    """
    M 1.10: un warn dato a mano conta un'infrazione, se il server l'ha
    scelto (`/security escalation enable warn_manuali:`). Restituisce cosa
    ha fatto la scala, da dire al moderatore, o None. Il gradino «warn»
    non aggiunge un secondo warn: l'utente l'ha appena ricevuto.
    D29: il gradino parte solo se `moderatore` potrebbe farlo da sé; con
    `in_massa` kick e ban non partono mai. L'infrazione resta contata.
    """
    if member.bot:
        return None
    config = await escalation_repo.get_config(member.guild.id)
    if not (config.enabled and config.conta_warn_manuali):
        return None
    conteggio = await escalation_repo.record_violation(
        member.guild.id, member.id, _adesso(), config.reset_after_days
    )
    step = get_ladder_action(conteggio, config.ladder)
    if step is None or step.action_type == "warn":
        return None
    azione = step.action_type + (f" {step.duration_seconds // 60} min" if step.action_type == "timeout" else "")
    richiesta = f"La scala chiedeva **{azione}** (infrazione #{conteggio}), ma"
    if in_massa and step.action_type in ("kick", "ban"):
        return f"{richiesta} dai warn in massa kick e ban non partono: decidi tu."
    non_permesso = _motivo_non_permesso(moderatore, member, step)
    if non_permesso:
        return f"{richiesta} non l'ho applicato: {non_permesso}."
    if _timeout_piu_lungo_in_corso(member, step):
        return f"{richiesta} c'è già un timeout più lungo: resta quello."
    reason = f"Scala dei warn — infrazione #{conteggio} (warn manuale, caso #{caso_warn})"[:MAX_MOTIVO]
    caso = await _applica_passo(bot, member.guild.id, member, step, reason)
    if caso is None:
        return f"{richiesta} non ci sono riuscito: controlla i miei permessi."
    return f"La scala ha applicato **{azione}** (infrazione #{conteggio}, caso #{caso})."


class EscalationCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._gia_contati: BoundedCache[tuple, datetime] = BoundedCache(max_size=5000)

    def _gia_contato(self, execution: discord.AutoModAction, now: datetime) -> bool:
        """
        True se questo evento riguarda un messaggio già contato da
        poco (un'altra azione della stessa regola). Altrimenti lo
        segna come contato. Nessun `await` qui dentro: due eventi
        arrivati insieme non possono passare entrambi.
        """
        chiave = (
            execution.guild_id,
            execution.user_id,
            execution.rule_id,
            execution.message_id,
            hash(execution.content),
        )
        visto = self._gia_contati.get(chiave)
        if visto is not None and (now - visto).total_seconds() <= FINESTRA_STESSO_MESSAGGIO:
            return True
        self._gia_contati.set(chiave, now)
        return False

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

        now = _adesso()
        if self._gia_contato(execution, now):
            return

        nuovo_conteggio = await escalation_repo.record_violation(
            execution.guild_id, member.id, now, config.reset_after_days
        )
        step = get_ladder_action(nuovo_conteggio, config.ladder)
        if step is None:
            return  # scala non configurata: solo il conteggio viene tenuto

        reason = (
            f"AutoMod Escalation — infrazione #{nuovo_conteggio} "
            f"(regola: {execution.matched_keyword or 'trigger AutoMod'})"
        )[:MAX_MOTIVO]
        if _timeout_piu_lungo_in_corso(member, step):
            return  # non si accorcia un timeout più lungo già in corso
        await _applica_passo(self.bot, execution.guild_id, member, step, reason)

    @commands.Cog.listener()
    async def on_automod_parole_vietate(self, message: discord.Message) -> None:
        """
        AMD-014: una parola vietata trovata dal filtro del bot conta
        un'infrazione, come una regola nativa. Chi ha «Gestisci server» o
        «Amministratore», e il proprietario, non entrano nella scala: il
        messaggio viene comunque cancellato dall'AutoMod.
        """
        member = message.author
        if message.guild is None or not isinstance(member, discord.Member) or member.bot:
            return
        if _is_safe_from_automated_action(member):
            return
        config = await escalation_repo.get_config(message.guild.id)
        if not config.enabled:
            return
        now = _adesso()
        chiave = ("parole", message.guild.id, member.id, message.id)
        if self._gia_contati.get(chiave) is not None:
            return
        self._gia_contati.set(chiave, now)
        conteggio = await escalation_repo.record_violation(
            message.guild.id, member.id, now, config.reset_after_days
        )
        step = get_ladder_action(conteggio, config.ladder)
        if step is None:
            return
        if _timeout_piu_lungo_in_corso(member, step):
            return
        reason = f"AutoMod Escalation — infrazione #{conteggio} (parola vietata)"[:MAX_MOTIVO]
        await _applica_passo(self.bot, message.guild.id, member, step, reason)

    # ================================================================
    # Comandi
    # ================================================================
    @comando_di_gruppo(
        "security",
        nome="enable",
        descrizione="Attiva l'escalation ladder.",
        sottogruppo=("escalation", "Scala di escalation delle sanzioni."),
    )
    @app_commands.describe(warn_manuali="Conta anche i warn dati a mano con /mod warn. Vuoto: resta com'è")
    async def enable(self, interaction: discord.Interaction, warn_manuali: bool | None = None) -> None:
        if interaction.guild is None:
            return
        await escalation_repo.set_enabled(interaction.guild.id, True)
        if warn_manuali is not None:
            await escalation_repo.set_conta_warn_manuali(interaction.guild.id, warn_manuali)
        config = await escalation_repo.get_config(interaction.guild.id)
        await interaction.response.send_message(
            "Escalation ladder attivata. Warn dati a mano: "
            + ("contano." if config.conta_warn_manuali else "non contano."),
            ephemeral=True,
        )

    @comando_di_gruppo(
        "security",
        nome="disable",
        descrizione="Disattiva l'escalation ladder.",
        sottogruppo=("escalation", "Scala di escalation delle sanzioni."),
    )
    async def disable(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        await escalation_repo.set_enabled(interaction.guild.id, False)
        await interaction.response.send_message("Escalation ladder disattivata.", ephemeral=True)

    @comando_di_gruppo(
        "security",
        nome="set-reset-days",
        descrizione="Giorni di buona condotta per azzerare il conteggio.",
        sottogruppo=("escalation", "Scala di escalation delle sanzioni."),
    )
    @app_commands.describe(days="Numero di giorni (default 30)")
    async def set_reset_days(
        self, interaction: discord.Interaction, days: app_commands.Range[int, 1, 365]
    ) -> None:
        if interaction.guild is None:
            return
        await escalation_repo.set_reset_after_days(interaction.guild.id, days)
        await interaction.response.send_message(
            f"Il conteggio si azzererà dopo {days} giorni senza infrazioni.", ephemeral=True
        )

    @comando_di_gruppo(
        "security",
        nome="set-step",
        descrizione="Configura l'azione per un livello della scala.",
        sottogruppo=("escalation", "Scala di escalation delle sanzioni."),
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

    @comando_di_gruppo(
        "security",
        nome="remove-step",
        descrizione="Rimuove un livello dalla scala personalizzata.",
        sottogruppo=("escalation", "Scala di escalation delle sanzioni."),
    )
    @app_commands.describe(level="Il livello da rimuovere")
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

    @comando_di_gruppo(
        "security",
        nome="reset",
        descrizione="Azzera il conteggio infrazioni di un membro.",
        sottogruppo=("escalation", "Scala di escalation delle sanzioni."),
    )
    @app_commands.describe(member="Il membro da azzerare")
    async def reset(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if interaction.guild is None:
            return
        await escalation_repo.reset_violations(interaction.guild.id, member.id)
        await interaction.response.send_message(
            f"Conteggio infrazioni di {member.mention} azzerato.", ephemeral=True
        )

    @comando_di_gruppo(
        "security",
        nome="status",
        descrizione="Mostra la scala di escalation configurata.",
        sottogruppo=("escalation", "Scala di escalation delle sanzioni."),
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
                f"Reset dopo: {config.reset_after_days} giorni di buona condotta\n"
                f"Warn dati a mano: {'contano' if config.conta_warn_manuali else 'non contano'}\n\n"
                + "\n".join(righe)
            ),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EscalationCog(bot))
