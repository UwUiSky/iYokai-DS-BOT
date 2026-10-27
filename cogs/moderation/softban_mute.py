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
blocco da on_guild_channel_create. Il mute può avere una fine (lo toglie lo
scheduler, anche dopo un riavvio), può essere un hardmute (toglie anche gli
altri ruoli e li ridà alla fine) e resta se l'utente esce e rientra.
Funzioni coperte: SPEC §5.1, §5.10 (MOD-014, 015, 021)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo

from core.database import db
from core.moderation_mute_logic import (
    MAX_MUTE_SECONDI,
    mute_finito,
    ruoli_dopo_nuovo_mute,
    ruoli_hardmute,
)
from core.scheduler import in_seconds, scheduler
from core.repositories.moderation_repo import moderation_repo
from cogs.moderation._shared import (
    MODULE_ACTIONS,
    ensure_module_enabled,
    check_can_moderate,
    try_dm,
    try_dm_message,
    delete_dm,
    validate_reason,
    Reason,
    audit_reason,
    format_duration,
    parse_duration,
    post_to_mod_log,
)
from cogs.moderation._tempban_modes import info_ruoli, ruoli_da_riprendere

logger = logging.getLogger("iyokai.moderation.softban_mute")

MUTE_ROLE_ACTION_TYPE = "mute_role"
# Fine di un mute a tempo. Nella riga dello scheduler `user_id` è l'utente
# silenziato; il payload porta il numero del caso, per ignorare le attese vecchie.
SCHEDULED_MUTE_EXPIRE = "moderation_mute_expire"

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
    case_number: int | None,
) -> discord.Embed:
    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="Utente", value=f"{target.mention} ({target.id})", inline=False)
    embed.add_field(name="Moderatore", value=moderator.mention, inline=True)
    if case_number is not None:
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


class ModerationSoftbanMuteCog(CogConGruppi, commands.Cog):
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
    # /softban
    # ================================================================
    @comando_di_gruppo(
        "modban",
        nome="softban",
        descrizione="Banna e sbanna subito un membro, per cancellarne i messaggi recenti.",
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

        # Il DM parte prima (dopo il ban non arriverebbe); il caso e il
        # log partono solo se l'azione è riuscita (LIM-8).
        dm = await try_dm_message(
            member,
            _case_embed(
                "🧹 Softban", discord.Color.dark_orange(), member, interaction.user, reason, None
            ),
            azione="softban", guild_id=interaction.guild.id,
        )
        try:
            await member.ban(
                reason=audit_reason(f"Softban: {reason}"),
                delete_message_seconds=delete_message_days * 86400,
            )
        except discord.HTTPException:
            await delete_dm(dm)
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
            avvisi.append("Lo sblocco automatico è fallito: usa /modban unban.")
        if dm is None:
            avvisi.append("Non è stato possibile notificare l'utente in DM.")
        if avvisi:
            embed.set_footer(text=" ".join(avvisi))
        await interaction.followup.send(embed=embed)

    # ================================================================
    # Fine del mute, rientro, ripristino ruoli
    # ================================================================
    async def _rilascia_mute(
        self,
        guild: discord.Guild,
        member: discord.Member | None,
        stato: dict | None,
        motivo: str,
        revocato_da: int,
    ) -> bool:
        """
        Toglie il ruolo mute, ridà i ruoli di un hardmute, chiude il caso e cancella
        lo stato. Se il membro non è nel server lo stato resta (lo chiude il rientro).
        False se Discord ha rifiutato una modifica dei ruoli.
        """
        user_id = member.id if member is not None else (stato or {}).get("user_id")
        if member is not None:
            role_id = await db.get_guild_setting(guild.id, SETTING_MUTE_ROLE_ID)
            ruolo = guild.get_role(role_id) if role_id else None
            try:
                if ruolo is not None and ruolo in member.roles:
                    await member.remove_roles(ruolo, reason=audit_reason(motivo))
                if stato and stato["hard"]:
                    ridare = [r for r in ruoli_da_riprendere(guild, list(stato["ruoli"])) if r not in member.roles]
                    if ridare:
                        await member.add_roles(*ridare, reason=audit_reason(motivo))
            except discord.HTTPException:
                logger.warning("Fine mute: ruoli non sistemati per %s (server %s).", member.id, guild.id)
                return False
        if user_id is not None:
            await scheduler.cancel_for_user(guild.id, user_id, SCHEDULED_MUTE_EXPIRE)
            await moderation_repo.revoke_active_cases_for_user(
                guild.id, user_id, MUTE_ROLE_ACTION_TYPE, revocato_da
            )
            if member is not None:
                await moderation_repo.delete_mute_state(guild.id, user_id)
        return True

    async def handle_mute_expire(self, guild_id: int, user_id: int, payload: dict) -> None:
        """Lo scheduler: il mute a tempo è finito."""
        stato = await moderation_repo.get_mute_state(guild_id, user_id)
        if stato is None or stato["case_number"] != payload.get("caso"):
            return  # tolto prima, oppure sostituito da un mute più nuovo
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        member = guild.get_member(user_id)
        if member is None:
            # Fuori dal server: il rientro vedrà che è finito e chiuderà tutto.
            await moderation_repo.revoke_active_cases_for_user(
                guild_id, user_id, MUTE_ROLE_ACTION_TYPE, self.bot.user.id
            )
            return
        if not await self._rilascia_mute(guild, member, stato, "Mute scaduto", self.bot.user.id):
            raise RuntimeError("ruoli del mute non sistemati")  # lo scheduler riprova
        embed = discord.Embed(title="🔊 Mute (ruolo) scaduto", color=discord.Color.green())
        embed.add_field(name="Utente", value=f"{member.mention} ({member.id})", inline=False)
        await post_to_mod_log(guild, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """MOD-021: chi è silenziato e rientra resta silenziato, finché il mute non finisce."""
        stato = await moderation_repo.get_mute_state(member.guild.id, member.id)
        if stato is None:
            return
        if mute_finito(stato["finisce_il"], datetime.now(timezone.utc)):
            await self._rilascia_mute(member.guild, member, stato, "Mute scaduto", self.bot.user.id)
            return
        role_id = await db.get_guild_setting(member.guild.id, SETTING_MUTE_ROLE_ID)
        ruolo = member.guild.get_role(role_id) if role_id else None
        if ruolo is None:
            return
        try:
            await member.add_roles(ruolo, reason="Mute ancora in corso")
        except discord.HTTPException:
            logger.warning("Rientro: ruolo mute non rimesso a %s (server %s).", member.id, member.guild.id)

    # ================================================================
    # /mute-role e /unmute-role
    # ================================================================
    @comando_di_gruppo(
        "mod",
        nome="mute",
        descrizione="Silenzia un membro con un ruolo dedicato (alternativa al timeout).",
    )
    @app_commands.describe(
        member="Il membro da silenziare",
        reason="Motivo del mute",
        durata="Per quanto tempo (es. 2h, 3d). Vuoto: finché non lo togli (max 1 anno)",
        hardmute="Toglie anche tutti gli altri ruoli e li ridà alla fine del mute",
    )
    async def mute_role(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Reason,
        durata: app_commands.Range[str, 1, 20] | None = None,
        hardmute: bool = False,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        if not await validate_reason(interaction, reason):
            return
        if not await check_can_moderate(interaction, member):
            return

        secondi = None
        if durata is not None:
            try:
                secondi = parse_duration(durata)
            except ValueError as exc:
                await interaction.response.send_message(str(exc), ephemeral=True)
                return
            if secondi > MAX_MUTE_SECONDI:
                await interaction.response.send_message(
                    "Un mute a tempo dura al massimo un anno. Per un mute senza fine lascia la durata vuota.",
                    ephemeral=True,
                )
                return

        await interaction.response.defer()
        guild = interaction.guild

        role = await _get_or_create_mute_role(guild)
        if role is None:
            await interaction.followup.send(
                "Non sono riuscito a creare il ruolo mute: controlla i miei "
                "permessi e che il server non abbia già 250 ruoli.",
                ephemeral=True,
            )
            return

        # Lo stato si scrive PRIMA di togliere i ruoli: se il bot si ferma a metà,
        # i ruoli tolti si ricordano comunque.
        precedente = await moderation_repo.get_mute_state(guild.id, member.id)
        ruoli_ora = ruoli_hardmute(info_ruoli(member.roles), guild.me.top_role.position, role.id) if hardmute else []
        ruoli = ruoli_dopo_nuovo_mute(
            bool(precedente and precedente["hard"]), list(precedente["ruoli"]) if precedente else [],
            ruoli_ora, hardmute,
        )
        fine = in_seconds(secondi) if secondi is not None else None
        hard = hardmute or bool(precedente and precedente["hard"])
        if hard:
            await moderation_repo.save_mute_state(guild.id, member.id, True, ruoli, None, fine)

        try:
            if ruoli_ora:
                da_togliere = [r for r in member.roles if r.id in set(ruoli_ora)]
                await member.remove_roles(*da_togliere, reason=audit_reason(f"Hardmute: {reason}"))
            await member.add_roles(role, reason=audit_reason(reason))
        except discord.HTTPException:
            if ruoli_ora:  # a metà: si rimette quello che si è già tolto
                try:
                    await member.add_roles(*ruoli_da_riprendere(guild, ruoli_ora), reason="Hardmute fallito")
                except discord.HTTPException:
                    logger.warning("Hardmute fallito a metà per %s (server %s).", member.id, guild.id)
            if precedente is None:
                await moderation_repo.delete_mute_state(guild.id, member.id)
            else:
                await moderation_repo.save_mute_state(
                    guild.id, member.id, precedente["hard"], list(precedente["ruoli"]),
                    precedente["case_number"], precedente["finisce_il"],
                )
            await interaction.followup.send(
                "Non sono riuscito ad assegnare il ruolo mute: controlla i "
                "miei permessi e la posizione del mio ruolo.",
                ephemeral=True,
            )
            return

        # Un mute nuovo sostituisce quello di prima (e la sua scadenza).
        await scheduler.cancel_for_user(guild.id, member.id, SCHEDULED_MUTE_EXPIRE)
        await moderation_repo.revoke_active_cases_for_user(
            guild.id, member.id, MUTE_ROLE_ACTION_TYPE, interaction.user.id
        )
        case_number = await moderation_repo.create_case(
            guild_id=guild.id,
            user_id=member.id,
            moderator_id=interaction.user.id,
            action_type=MUTE_ROLE_ACTION_TYPE,
            reason=reason,
            duration_seconds=secondi,
        )
        # Lo stato serve sempre: fa restare il mute al rientro e porta la fine.
        await moderation_repo.save_mute_state(guild.id, member.id, hard, ruoli, case_number, fine)
        if fine is not None:
            await scheduler.schedule(
                guild_id=guild.id,
                user_id=member.id,
                action_type=SCHEDULED_MUTE_EXPIRE,
                execute_at=fine,
                payload={"caso": case_number},
            )

        titolo = "🔇 Hardmute (ruolo)" if hardmute else "🔇 Mute (ruolo)"
        embed = _case_embed(titolo, discord.Color.dark_grey(), member, interaction.user, reason, case_number)
        if fine is not None:
            embed.add_field(
                name="Fine",
                value=f"{discord.utils.format_dt(fine, 'R')} ({format_duration(secondi)})",
                inline=True,
            )
        if hardmute:
            embed.add_field(name="Ruoli tolti", value=str(len(ruoli_ora)), inline=True)
        await post_to_mod_log(guild, embed)
        await try_dm(member, embed, azione="mute", guild_id=guild.id)
        await interaction.followup.send(embed=embed)

    @comando_di_gruppo(
        "mod",
        nome="unmute",
        descrizione="Rimuove il ruolo mute da un membro.",
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
        stato = await moderation_repo.get_mute_state(interaction.guild.id, member.id)
        if (role is None or role not in member.roles) and stato is None:
            await interaction.response.send_message(
                f"{member.mention} non ha il ruolo mute.", ephemeral=True
            )
            return

        await interaction.response.defer()
        if not await self._rilascia_mute(interaction.guild, member, stato, reason, interaction.user.id):
            await interaction.followup.send(
                "Non sono riuscito a sistemare i ruoli: controlla i "
                "miei permessi e la posizione del mio ruolo.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(f"Ruolo mute rimosso da {member.mention}.")
        log_embed = discord.Embed(title="🔊 Mute (ruolo) tolto", color=discord.Color.green())
        log_embed.add_field(name="Utente", value=f"{member.mention} ({member.id})", inline=False)
        log_embed.add_field(name="Moderatore", value=interaction.user.mention, inline=True)
        log_embed.add_field(name="Motivo", value=reason, inline=False)
        await post_to_mod_log(interaction.guild, log_embed)


async def setup(bot: commands.Bot) -> None:
    cog = ModerationSoftbanMuteCog(bot)
    await bot.add_cog(cog)
    scheduler.register_handler(SCHEDULED_MUTE_EXPIRE, cog.handle_mute_expire)
