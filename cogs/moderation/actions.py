"""
cogs/moderation/actions.py
=============================
Azioni di moderazione base: warn, kick, ban, unban, tempban, timeout,
untimeout. Modulo SEMPRE GRATUITO (MODULE_ACTIONS, premium_capable=
False), coerente con lo schema di progetto ("Azioni base" è [Free]).

Ogni comando segue lo stesso schema:
  1. ensure_module_enabled — il server ha attivato la moderazione?
  2. check_can_moderate — chi comanda può agire su questo bersaglio?
     (gerarchia ruoli, owner, bot stesso — vedi core/permissions.py)
  3. `defer()` prima di parlare con Discord (kick, ban, tempban)
  4. azione vera su Discord (kick/ban/timeout...)
  5. solo se l'azione è riuscita: caso, log, DM all'utente, risposta
Funzioni coperte: SPEC §5.1, §5.8, §5.9, §5.10

Il tempban è l'unico caso "speciale": non esiste un ban a tempo
nativo su Discord, quindi banniamo normalmente e PIANIFICHIAMO lo
sblocco tramite core/scheduler.py, che sopravvive a un riavvio del
bot (vedi quel file per il perché serve, non un semplice
asyncio.sleep). Tre modi (#138): fuori, fuori con rientro (invito mandato
prima del ban, ruoli ridati al ritorno), isolamento (resta nel server,
vede un solo canale). Lo stato (ruoli veri) si salva prima dell'azione; ogni nuovo
caso cancella la scadenza del precedente. Funzioni coperte anche: SPEC §5.11, §5.12, parte E (D15: scadenze via iYokai Mod).

Un warn dato a mano sale la scala di escalation, se il server l'ha
scelto (M 1.10), solo con azioni che il moderatore potrebbe fare da sé;
dai warn in massa non partono mai kick e ban (D29).

Azioni su più utenti insieme (MOD-002…006): ban (anche di chi non è nel
server, con il ban in blocco di Discord), unban, kick, timeout e warn; un
caso per utente, un solo riepilogo nel log. Chi non si può moderare viene
saltato con il motivo.

Con la soglia scelta dal server (MOD-036) chi riceve un warn avendone già troppi
fa scattare un avviso allo staff nel log di moderazione, senza punire.
"""

from __future__ import annotations

import datetime
import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

from core import bot_roles
from core.command_groups import CogConGruppi, comando_di_gruppo

from core import moderation_opzioni
from core.database import db
from core.repositories.moderation_repo import moderation_repo
from core.scheduler import scheduler, in_seconds
from core.tempban_logic import (
    MODO_FUORI,
    MODO_ISOLAMENTO,
    MODO_RIENTRO,
    ruoli_da_salvare,
    ruoli_da_tenere_in_isolamento,
    testo_fine,
)
from cogs.moderation import _tempban_modes as tempban_modes
from cogs.moderation.ban_appeal import vista_appello
from cogs.automod.escalation import scala_per_warn_manuale
from core.spam_trap_logic import BAN_ACTION_TYPE as SPAM_TRAP_BAN_ACTION_TYPE
from cogs.moderation._shared import (
    MODULE_ACTIONS,
    ensure_module_enabled,
    check_can_moderate,
    try_dm,
    try_dm_message,
    delete_dm,
    audit_reason,
    parse_duration,
    format_duration,
    validate_reason,
    Reason,
    actor_from_member,
    motivo_immune,
    post_to_mod_log,
)
from core.premium import PremiumModule, registry
from core.moderation_bulk_logic import (
    MAX_TESTO_UTENTI, MAX_USI_ORA, MAX_UTENTI_MASSA, leggi_utenti, prenota_uso, riepilogo,
)
from core.permissions import can_moderate
from cogs.security.global_ban import revoca_ban_propagati

logger = logging.getLogger("iyokai.moderation.actions")

# action_type registrato nello scheduler per il tempban automatico.
# Costante qui perché serve sia a create_case (usa lo stesso testo
# come action_type del CASO, per coerenza nello storico) sia
# all'handler registrato in setup().
TEMPBAN_ACTION_TYPE = "tempban"
SCHEDULED_TEMPBAN_EXPIRE = "moderation_tempban_expire"

# Timeout nativo di Discord: massimo 28 giorni, oltre l'API rifiuta
# la richiesta. Lo controlliamo PRIMA di chiamare Discord per dare
# un messaggio chiaro invece di un errore HTTP criptico.
MAX_TIMEOUT_SECONDS = 28 * 86400

_BAN_FALLITO = (
    "Non sono riuscito a bannare questo utente: controlla i miei permessi "
    "e la posizione del mio ruolo."
)


async def _avvisa_staff_se_troppi_warn(guild: discord.Guild, member: discord.abc.User) -> None:
    """MOD-036: avviso nel log di moderazione se i warn attivi superano la soglia del server."""
    soglia = (await moderation_opzioni.leggi(guild.id)).avviso_warn
    if not soglia:
        return
    totali = await moderation_repo.count_active_cases(guild.id, member.id, "warn")
    if not moderation_opzioni.avviso_warn_scatta(totali, soglia):
        return
    embed = discord.Embed(
        title="⚠️ Troppi warn",
        description=f"{member.mention} ({member.id}) ha ora **{totali}** warn attivi (soglia: {soglia}).",
        color=discord.Color.orange(),
    )
    await post_to_mod_log(guild, embed)


def _case_embed(
    title: str,
    color: discord.Color,
    target: discord.abc.User,
    moderator: discord.abc.User,
    reason: str | None,
    case_number: int | None,
    extra_field: tuple[str, str] | None = None,
) -> discord.Embed:
    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="Utente", value=f"{target.mention} ({target.id})", inline=False)
    embed.add_field(name="Moderatore", value=moderator.mention, inline=True)
    if case_number is not None:
        embed.add_field(name="Caso", value=f"#{case_number}", inline=True)
    if extra_field:
        embed.add_field(name=extra_field[0], value=extra_field[1], inline=True)
    embed.add_field(name="Motivo", value=reason or "Nessun motivo fornito", inline=False)
    return embed


async def _log_e_risposta(
    interaction: discord.Interaction, embed: discord.Embed, dm_inviato: bool
) -> None:
    """
    Ultimi passi di una sanzione già riuscita e già registrata: log e
    risposta al moderatore. Il DM è partito prima dell'azione (dopo un
    kick o un ban non c'è più un server in comune): se non è arrivato
    lo diciamo al moderatore.
    """
    await post_to_mod_log(interaction.guild, embed)
    if not dm_inviato:
        embed.set_footer(text="Non è stato possibile notificare l'utente in DM.")
    await interaction.followup.send(embed=embed)


class ModerationActionsCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _chiudi_sanzioni_a_tempo(
        self, guild: discord.Guild, user_id: int, moderatore_id: int
    ) -> None:
        """
        Un ban o un kick diretto sostituisce un isolamento o un tempban in corso:
        via scadenza, stato, invito di rientro e caso (altrimenti un `/modban unban`
        successivo prenderebbe la strada dell'isolamento e non sbannerebbe).
        """
        stato = await moderation_repo.get_tempban_state(guild.id, user_id)
        await moderation_repo.cancel_tempban_jobs(guild.id, user_id)
        if stato is None:
            return
        await moderation_repo.delete_tempban_state(guild.id, user_id)
        await tempban_modes.cancella_invito_per_codice(self.bot, stato["invito_codice"])
        if stato["case_number"] is not None:
            await moderation_repo.revoke_case(guild.id, stato["case_number"], moderatore_id)

    async def _dopo_unban(self, client, guild_id: int, uid: int, moderatore_id: int, stato) -> None:
        """Pulizia dopo uno sban riuscito: casi, scadenze, stato del tempban, appelli."""
        # Revoca l'ultimo caso attivo di tipo ban O tempban per
        # questo utente, qualunque dei due sia: get_latest_active_case
        # richiede un action_type preciso, quindi controlliamo
        # entrambi in ordine.
        for action_type in ("ban", TEMPBAN_ACTION_TYPE):
            case = await moderation_repo.get_latest_active_case(guild_id, uid, action_type)
            if case is not None:
                await moderation_repo.revoke_case(guild_id, case.case_number, moderatore_id)
                break

        # La scadenza automatica non serve più (e non deve toccare un caso nuovo).
        await moderation_repo.cancel_tempban_jobs(guild_id, uid)

        # Tempban con rientro sbannato a mano: al ritorno riprende i ruoli.
        if stato is not None:
            await moderation_repo.mark_tempban_state_expired(guild_id, uid)
            await tempban_modes.cancella_invito_per_codice(client, stato["invito_codice"])
        await moderation_repo.close_open_appeals(guild_id, uid, moderatore_id)

        # BUG-24: anche i ban scattati dallo spam-trap. Tutti quelli
        # attivi, non solo l'ultimo: se restassero, l'utente
        # risulterebbe ancora bannato per l'appello in DM.
        await moderation_repo.revoke_active_cases_for_user(
            guild_id, uid, SPAM_TRAP_BAN_ACTION_TYPE, moderatore_id
        )

    # ================================================================
    # /warn
    # ================================================================
    @comando_di_gruppo(
        "mod",
        nome="warn",
        descrizione="Assegna un warn a un membro.",
    )
    @app_commands.describe(member="Il membro da avvisare", reason="Motivo del warn")
    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Reason,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        if not await validate_reason(interaction, reason):
            return
        if not await check_can_moderate(interaction, member):
            return

        case_number = await moderation_repo.create_case(
            guild_id=interaction.guild.id,
            user_id=member.id,
            moderator_id=interaction.user.id,
            action_type="warn",
            reason=reason,
        )

        embed = _case_embed(
            "⚠️ Warn", discord.Color.yellow(), member, interaction.user, reason, case_number
        )
        await interaction.response.send_message(embed=embed)
        await try_dm(member, embed, azione="warn", guild_id=interaction.guild.id)
        await post_to_mod_log(interaction.guild, embed)
        # M 1.10: se il server l'ha scelto, il warn sale la scala di escalation.
        await _avvisa_staff_se_troppi_warn(interaction.guild, member)
        esito_scala = await scala_per_warn_manuale(self.bot, member, case_number, moderatore=interaction.user)
        if esito_scala:
            await interaction.followup.send(esito_scala, ephemeral=True)

    # ================================================================
    # /kick
    # ================================================================
    @comando_di_gruppo(
        "modban",
        nome="kick",
        descrizione="Espelle un membro dal server.",
    )
    @app_commands.describe(member="Il membro da espellere", reason="Motivo dell'espulsione")
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Reason,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        if not await validate_reason(interaction, reason):
            return
        if not await check_can_moderate(interaction, member):
            return

        await interaction.response.defer()

        # Il DM parte prima (dopo il kick non arriverebbe); il caso e il
        # log partono solo se l'azione è riuscita (LIM-8).
        dm = await try_dm_message(
            member,
            _case_embed("👢 Kick", discord.Color.orange(), member, interaction.user, reason, None),
            azione="kick", guild_id=interaction.guild.id,
        )
        try:
            await member.kick(reason=reason)
        except discord.HTTPException:
            await delete_dm(dm)
            await interaction.followup.send(
                "Non sono riuscito a espellere questo utente: controlla i "
                "miei permessi e la posizione del mio ruolo.",
                ephemeral=True,
            )
            return

        case_number = await moderation_repo.create_case(
            guild_id=interaction.guild.id,
            user_id=member.id,
            moderator_id=interaction.user.id,
            action_type="kick",
            reason=reason,
        )
        await self._chiudi_sanzioni_a_tempo(interaction.guild, member.id, interaction.user.id)
        embed = _case_embed(
            "👢 Kick", discord.Color.orange(), member, interaction.user, reason, case_number
        )
        await _log_e_risposta(interaction, embed, dm is not None)

    # ================================================================
    # /ban
    # ================================================================
    @comando_di_gruppo(
        "modban",
        nome="ban",
        descrizione="Banna permanentemente un membro.",
    )
    @app_commands.describe(
        member="Il membro da bannare",
        reason="Motivo del ban",
        delete_message_days="Giorni di messaggi da cancellare (0-7). Vuoto: quelli di /mod opzioni",
    )
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Reason,
        delete_message_days: app_commands.Range[int, 0, 7] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        if not await validate_reason(interaction, reason):
            return
        if not await check_can_moderate(interaction, member):
            return

        await interaction.response.defer()
        if delete_message_days is None:  # MOD-010: valore del server
            delete_message_days = (await moderation_opzioni.leggi(interaction.guild.id)).giorni_ban

        dm = await try_dm_message(
            member,
            _case_embed("🔨 Ban", discord.Color.red(), member, interaction.user, reason, None),
            view=await vista_appello(interaction.guild.id),
            azione="ban", guild_id=interaction.guild.id,
        )
        try:
            await member.ban(
                reason=reason,
                delete_message_seconds=delete_message_days * 86400,
            )
        except discord.HTTPException:
            await delete_dm(dm)
            await interaction.followup.send(_BAN_FALLITO, ephemeral=True)
            return

        case_number = await moderation_repo.create_case(
            guild_id=interaction.guild.id,
            user_id=member.id,
            moderator_id=interaction.user.id,
            action_type="ban",
            reason=reason,
        )
        await self._chiudi_sanzioni_a_tempo(interaction.guild, member.id, interaction.user.id)
        embed = _case_embed(
            "🔨 Ban", discord.Color.red(), member, interaction.user, reason, case_number
        )
        await _log_e_risposta(interaction, embed, dm is not None)

    # ================================================================
    # /tempban (con rientro o in isolamento, #138)
    # ================================================================
    @comando_di_gruppo(
        "modban",
        nome="tempban",
        descrizione="Banna un membro per una durata definita.",
    )
    @app_commands.describe(
        member="Il membro da bannare temporaneamente",
        duration="Durata, es. 7d, 12h, 30m",
        reason="Motivo del ban",
        modo="Fuori dal server, fuori con invito e ruoli al rientro, oppure isolamento",
    )
    @app_commands.choices(
        modo=[
            app_commands.Choice(name="Fuori dal server", value=MODO_FUORI),
            app_commands.Choice(name="Fuori, con invito e ruoli al rientro", value=MODO_RIENTRO),
            app_commands.Choice(name="Isolamento: resta, vede un solo canale", value=MODO_ISOLAMENTO),
        ]
    )
    async def tempban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: str,
        reason: Reason,
        modo: str = MODO_FUORI,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        if not await validate_reason(interaction, reason):
            return
        if not await check_can_moderate(interaction, member):
            return

        try:
            duration_seconds = parse_duration(duration)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        await interaction.response.defer()
        guild = interaction.guild
        fine = in_seconds(duration_seconds)
        fine_ts = int(fine.timestamp())
        isolamento = modo == MODO_ISOLAMENTO

        # Isolamento: ruolo e canale pronti prima di toccare l'utente.
        ruolo_iso = canale_iso = None
        canali_non_nascosti = 0
        if isolamento:
            preparati = await tempban_modes.prepara_isolamento(guild)
            if preparati is None:
                await interaction.followup.send(
                    "Non sono riuscito a preparare ruolo e canale di isolamento: "
                    "controlla i miei permessi.",
                    ephemeral=True,
                )
                return
            ruolo_iso, canale_iso, canali_non_nascosti = preparati

        # Rientro: l'invito si crea e si manda PRIMA del ban (dopo, il DM
        # non parte più). Vale oltre la scadenza: non scade, un solo uso.
        invito = None
        oauth_rientro = False
        if modo == MODO_RIENTRO:
            invito = await tempban_modes.crea_invito(guild)
            oauth_rientro = await tempban_modes.rientro_oauth_possibile(guild.id, member.id, fine)
            if invito is None and not oauth_rientro:
                # Senza invito e senza autorizzazione l'utente non potrebbe più
                # rientrare: si ferma prima di bannare.
                await interaction.followup.send(
                    "Non posso creare un invito di rientro (nessun canale me lo permette) e "
                    "l'utente non ha autorizzato il rientro automatico: non banno. "
                    "Dammi «Creare invito» su un canale, oppure usa un'altra modalità.",
                    ephemeral=True,
                )
                return

        titolo = "🔒 Isolamento" if isolamento else "⏳ Tempban"
        durata = ("Durata", format_duration(duration_seconds))

        def _embed(caso: int | None, per_dm: bool) -> discord.Embed:
            e = _case_embed(
                titolo, discord.Color.dark_red(), member, interaction.user,
                reason, caso, extra_field=durata,
            )
            e.add_field(name="Fine", value=testo_fine(fine_ts), inline=False)
            if per_dm and invito is not None:
                e.add_field(name="Invito per rientrare", value=invito.url, inline=False)
            return e

        dm = await try_dm_message(
            member, _embed(None, True),
            view=None if modo != MODO_FUORI else await vista_appello(guild.id),
            azione="tempban", guild_id=guild.id,
        )

        # Ruoli veri da salvare: mai il ruolo di isolamento. Se l'utente è già
        # isolato, i suoi ruoli veri stanno nello stato precedente: si tengono
        # (un secondo isolamento o tempban non deve perderli).
        precedente = await moderation_repo.get_tempban_state(guild.id, member.id)
        ruolo_iso_id = ruolo_iso.id if ruolo_iso else await db.get_guild_setting(
            guild.id, tempban_modes.SETTING_ISOLAMENTO_RUOLO
        )
        ruoli_salvati = [
            i for i in ruoli_da_salvare(tempban_modes.info_ruoli(member.roles)) if i != ruolo_iso_id
        ]
        if precedente is not None and precedente["modo"] == MODO_ISOLAMENTO and not precedente["scaduto"]:
            ruoli_salvati = list(dict.fromkeys([*precedente["ruoli"], *ruoli_salvati]))
        nuovi = []
        if isolamento:
            tenuti = ruoli_da_tenere_in_isolamento(
                tempban_modes.info_ruoli(member.roles), guild.me.top_role.position
            )
            nuovi = [r for r in member.roles if r.id in tenuti] + [ruolo_iso]
            ruoli_salvati = [i for i in ruoli_salvati if i not in tenuti]

        # Lo stato si salva PRIMA dell'azione che non si può disfare (togliere i
        # ruoli o bannare): se qualcosa si ferma dopo, i ruoli non sono persi.
        if modo != MODO_FUORI:
            await moderation_repo.save_tempban_state(
                guild.id, member.id, modo, ruoli_salvati, fine,
                invito_codice=invito.code if invito else None,
                case_number=None,
                oauth_rientro=oauth_rientro,
            )
        try:
            if isolamento:
                await member.edit(roles=nuovi, reason=audit_reason(f"Isolamento: {reason}"))
            else:
                await member.ban(reason=reason)
        except discord.HTTPException:
            await delete_dm(dm)
            await tempban_modes.cancella_invito(invito)
            if modo != MODO_FUORI:
                await tempban_modes.ripristina_stato(guild.id, member.id, precedente)
            await interaction.followup.send(_BAN_FALLITO, ephemeral=True)
            return

        case_number = await moderation_repo.create_case(
            guild_id=guild.id,
            user_id=member.id,
            moderator_id=interaction.user.id,
            action_type="isolamento" if isolamento else TEMPBAN_ACTION_TYPE,
            reason=reason,
            duration_seconds=duration_seconds,
        )

        if modo != MODO_FUORI:
            await moderation_repo.set_tempban_state_case(guild.id, member.id, case_number)
        elif precedente is not None:
            # Bannato fuori: l'isolamento di prima non ha più senso.
            await moderation_repo.delete_tempban_state(guild.id, member.id)
        if precedente is not None and precedente["invito_codice"] not in (
            None, invito.code if invito else None
        ):
            await tempban_modes.cancella_invito_per_codice(self.bot, precedente["invito_codice"])

        # La sanzione di prima è sostituita da questa: la sua scadenza non deve
        # più scattare (libererebbe il caso nuovo) e il suo caso si chiude.
        await moderation_repo.cancel_tempban_jobs(guild.id, member.id)
        if precedente is not None and precedente["case_number"] is not None:
            await moderation_repo.revoke_case(
                guild.id, precedente["case_number"], revoked_by=interaction.user.id
            )

        # Pianifica lo sblocco automatico. Il payload porta il
        # case_number, così l'handler può revocare il caso corretto
        # quando scade (vedi handle_tempban_expire più sotto).
        await scheduler.schedule(
            guild_id=guild.id,
            user_id=member.id,
            action_type=SCHEDULED_TEMPBAN_EXPIRE,
            execute_at=fine,
            payload={"case_number": case_number, "modo": modo},
        )

        if isolamento and canale_iso is not None:
            try:
                await canale_iso.send(
                    f"{member.mention} è in isolamento fino a {testo_fine(fine_ts)}.\n"
                    f"Motivo: {reason}"
                )
            except discord.HTTPException:
                logger.warning("Isolamento: messaggio nel canale non inviato (server %s).", guild.id)

        await _log_e_risposta(interaction, _embed(case_number, False), dm is not None)
        if canali_non_nascosti:
            await interaction.followup.send(
                f"Attenzione: {canali_non_nascosti} canali non sono stati nascosti "
                "(Discord ha rifiutato): l'utente li vede ancora. Controlla i miei permessi "
                "su quei canali.",
                ephemeral=True,
            )
        if dm is None and invito is not None:
            # DM chiuso: l'invito (non scade, un solo uso) non deve restare
            # orfano. Lo vede solo il moderatore, che lo gira all'utente.
            await interaction.followup.send(
                f"Messaggio privato non consegnato. Invito di rientro da girare a {member.mention}: "
                f"{invito.url}",
                ephemeral=True,
            )

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        """Un canale nuovo non deve essere visibile a chi è in isolamento."""
        await tempban_modes.nega_canale_nuovo(channel)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """
        Rientro dopo un tempban con rientro: si ridanno i ruoli salvati.
        Se l'utente è uscito durante l'isolamento e torna prima della fine,
        riprende l'isolamento (altrimenti basterebbe uscire e rientrare).
        """
        guild = member.guild
        stato = await moderation_repo.get_tempban_state(guild.id, member.id)
        if stato is None:
            return
        try:
            if stato["modo"] == MODO_ISOLAMENTO and not stato["scaduto"]:
                ruolo_id = await db.get_guild_setting(
                    guild.id, tempban_modes.SETTING_ISOLAMENTO_RUOLO
                )
                ruolo = guild.get_role(ruolo_id) if ruolo_id else None
                if ruolo is not None:
                    await member.add_roles(ruolo, reason="Isolamento ancora in corso")
                return
            if not stato["scaduto"]:
                return
            ruoli = tempban_modes.ruoli_da_riprendere(guild, list(stato["ruoli"]))
            if ruoli:
                await member.add_roles(*ruoli, reason="Rientro dopo il ban temporaneo")
        except discord.HTTPException:
            logger.warning("Rientro: ruoli non ridati a %s (server %s).", member.id, guild.id)
            return
        await moderation_repo.delete_tempban_state(guild.id, member.id)

    async def _rilascia_isolamento(
        self, guild: discord.Guild, member: discord.Member, stato: dict, motivo: str
    ) -> None:
        """Toglie il ruolo di isolamento e ridà i ruoli salvati."""
        ruolo_id = await db.get_guild_setting(guild.id, tempban_modes.SETTING_ISOLAMENTO_RUOLO)
        ruolo = guild.get_role(ruolo_id) if ruolo_id else None
        # D15: la fine dell'isolamento la fa iYokai Mod, se c'è e può.
        if ruolo is not None and ruolo in member.roles:
            await bot_roles.togli_ruolo(member, ruolo, reason=motivo)
        for vecchio in tempban_modes.ruoli_da_riprendere(guild, list(stato["ruoli"])):
            await bot_roles.aggiungi_ruolo(member, vecchio, reason=motivo)
        await moderation_repo.delete_tempban_state(guild.id, member.id)

    async def handle_tempban_expire(
        self, guild_id: int, user_id: int, payload: dict
    ) -> None:
        """
        Handler chiamato dallo scheduler quando un tempban scade.
        Registrato in setup() (vedi in fondo al file). Se il server
        non esiste più (bot rimosso) o l'utente non è più bannato
        (sbannato a mano nel frattempo), l'eccezione viene gestita
        dallo scheduler stesso: non marca l'azione come eseguita e
        la ritenta — MA qui gestiamo esplicitamente il caso "non è
        più bannato" come esito normale, non come errore, altrimenti
        verrebbe ritentato all'infinito inutilmente.
        """
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            logger.warning(
                "Tempban scaduto per guild_id=%s ma il bot non è più in "
                "quel server: impossibile sbannare.",
                guild_id,
            )
            return

        modo = payload.get("modo", MODO_FUORI)
        rientrato_da_solo = False
        stato = await moderation_repo.get_tempban_state(guild_id, user_id)

        # Un vecchio job (sostituito da un nuovo caso) non deve liberare
        # il caso nuovo.
        caso_job = payload.get("case_number")
        if (
            stato is not None
            and caso_job is not None
            and stato["case_number"] != caso_job
        ):
            logger.info(
                "Scadenza ignorata per user_id=%s: lo stato appartiene a un altro caso.", user_id
            )
            return

        if modo == MODO_ISOLAMENTO:
            member = await tempban_modes.trova_membro(guild, user_id)
            if member is not None and stato is not None:
                try:
                    await self._rilascia_isolamento(
                        guild, member, stato, "Isolamento scaduto automaticamente"
                    )
                except discord.HTTPException:
                    logger.error(
                        "Fine isolamento non riuscita per user_id=%s in guild_id=%s.",
                        user_id, guild_id,
                    )
                    return
            elif stato is not None:
                # Uscito durante l'isolamento: al rientro riprende i ruoli.
                await moderation_repo.mark_tempban_state_expired(guild_id, user_id)
        else:
            try:
                await bot_roles.sbanna(
                    guild, discord.Object(id=user_id), reason="Tempban scaduto automaticamente"
                )
            except discord.NotFound:
                # L'utente non risultava più bannato (già sbannato a
                # mano): non è un errore, è l'esito che ci aspettavamo.
                pass
            except discord.Forbidden:
                logger.error(
                    "Permessi insufficienti per sbannare user_id=%s in "
                    "guild_id=%s alla scadenza del tempban.",
                    user_id,
                    guild_id,
                )
                return
            if stato is not None:
                await moderation_repo.mark_tempban_state_expired(guild_id, user_id)
                if stato["oauth_rientro"] and await tempban_modes.rientra_via_oauth(
                    guild_id, user_id
                ):
                    # Il rientro è automatico: l'invito non serve più. I ruoli li
                    # ridà on_member_join (lo stato è scaduto).
                    rientrato_da_solo = True
                    await tempban_modes.cancella_invito_per_codice(
                        self.bot, stato["invito_codice"]
                    )

        case_number = payload.get("case_number")
        if case_number is not None:
            await moderation_repo.revoke_case(
                guild_id, case_number, revoked_by=self.bot.user.id
            )

        # M 1.8: anche la scadenza lascia una riga nel log di moderazione.
        embed = discord.Embed(
            title="⏱️ Isolamento finito" if modo == MODO_ISOLAMENTO else "⏱️ Tempban scaduto",
            color=discord.Color.green(),
        )
        embed.add_field(name="Utente", value=f"<@{user_id}> ({user_id})", inline=False)
        if case_number is not None:
            embed.add_field(name="Caso", value=f"#{case_number}", inline=True)
        if rientrato_da_solo:
            embed.add_field(name="Rientro", value="Automatico (autorizzazione OAuth)", inline=True)
        await post_to_mod_log(guild, embed)

    async def _fine_isolamento(self, interaction: discord.Interaction, uid: int) -> None:
        """Isolamento chiuso a mano: via scadenza, caso e appelli aperti."""
        await moderation_repo.cancel_tempban_jobs(interaction.guild.id, uid)
        caso = await moderation_repo.get_latest_active_case(interaction.guild.id, uid, "isolamento")
        if caso is not None:
            await moderation_repo.revoke_case(
                interaction.guild.id, caso.case_number, interaction.user.id
            )
        await moderation_repo.close_open_appeals(interaction.guild.id, uid, interaction.user.id)

    # ================================================================
    # /unban
    # ================================================================
    @comando_di_gruppo(
        "modban",
        nome="unban",
        descrizione="Rimuove il ban da un utente.",
    )
    @app_commands.describe(user_id="ID Discord dell'utente da sbannare", reason="Motivo dello sblocco")
    async def unban(
        self, interaction: discord.Interaction, user_id: str, reason: Reason
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        if not await validate_reason(interaction, reason):
            return

        try:
            uid = int(user_id)
        except ValueError:
            await interaction.response.send_message("ID utente non valido.", ephemeral=True)
            return

        # Ban in isolamento (#138): l'utente è ancora nel server, si libera qui.
        stato = await moderation_repo.get_tempban_state(interaction.guild.id, uid)
        isolato = stato is not None and stato["modo"] == MODO_ISOLAMENTO
        if isolato:
            try:
                member = await tempban_modes.trova_membro(interaction.guild, uid)
            except discord.HTTPException:
                member = None
            if member is not None:
                await interaction.response.defer()
                try:
                    await self._rilascia_isolamento(interaction.guild, member, stato, reason)
                except discord.HTTPException:
                    await interaction.followup.send(
                        "Non sono riuscito a liberare l'utente: controlla i miei permessi.",
                        ephemeral=True,
                    )
                    return
                await self._fine_isolamento(interaction, uid)
                await interaction.followup.send(f"Utente `{uid}` liberato dall'isolamento.")
                return

        try:
            await interaction.guild.unban(discord.Object(id=uid), reason=reason)
        except discord.NotFound:
            if isolato:
                # Uscito durante l'isolamento e non bannato: al rientro riprende i ruoli.
                await moderation_repo.mark_tempban_state_expired(interaction.guild.id, uid)
                await self._fine_isolamento(interaction, uid)
                await interaction.response.send_message(f"Utente `{uid}` liberato dall'isolamento.")
                return
            await interaction.response.send_message(
                "Questo utente non risulta bannato.", ephemeral=True
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                "Non sono riuscito a sbannare questo utente: controlla i miei permessi.",
                ephemeral=True,
            )
            return

        await self._dopo_unban(interaction.client, interaction.guild.id, uid, interaction.user.id, stato)

        await interaction.response.send_message(f"Utente `{uid}` sbannato.")
        log_embed = discord.Embed(title="🔓 Unban", color=discord.Color.green())
        log_embed.add_field(name="Utente", value=f"`{uid}`", inline=False)
        log_embed.add_field(name="Moderatore", value=interaction.user.mention, inline=True)
        log_embed.add_field(name="Motivo", value=reason, inline=False)
        await post_to_mod_log(interaction.guild, log_embed)

        # Se il ban era partito da qui verso la rete di ban globali, lo si
        # toglie anche dagli altri server. Dopo la risposta: con una rete
        # grande ci vuole piu' dei 3 secondi che Discord concede.
        try:
            tolti = await revoca_ban_propagati(interaction.client, interaction.guild.id, uid)
        except Exception:
            logger.exception("Revoca dei ban propagati fallita (server %s).", interaction.guild.id)
            return
        if tolti:
            await interaction.followup.send(
                f"Il ban era arrivato anche ad altri server della rete: tolto da {tolti}.", ephemeral=True
            )

    # ================================================================
    # /timeout e /untimeout
    # ================================================================
    @comando_di_gruppo(
        "mod",
        nome="timeout",
        descrizione="Mette in timeout un membro (max 28 giorni).",
    )
    @app_commands.describe(
        member="Il membro da mettere in timeout",
        duration="Durata, es. 10m, 1h, 7d (max 28 giorni). Vuoto: quella di /mod opzioni",
        reason="Motivo del timeout",
    )
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Reason,
        duration: app_commands.Range[str, 1, 20] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        if not await validate_reason(interaction, reason):
            return
        if not await check_can_moderate(interaction, member):
            return

        if duration is None:
            # MOD-017: durata predefinita del server.
            predefinita = (await moderation_opzioni.leggi(interaction.guild.id)).durata_timeout
            if predefinita is None:
                await interaction.response.send_message(
                    "Scrivi una durata, oppure impostane una predefinita con `/mod opzioni imposta durata_timeout:`.",
                    ephemeral=True,
                )
                return
            duration_seconds = predefinita
        else:
            try:
                duration_seconds = parse_duration(duration)
            except ValueError as exc:
                await interaction.response.send_message(str(exc), ephemeral=True)
                return

        if duration_seconds > MAX_TIMEOUT_SECONDS:
            await interaction.response.send_message(
                "Il timeout nativo di Discord non può superare i 28 giorni. "
                "Per durate più lunghe usa /modban tempban se l'intento è "
                "allontanare l'utente dal server.",
                ephemeral=True,
            )
            return

        try:
            await member.timeout(
                datetime.timedelta(seconds=duration_seconds),
                reason=reason,
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                "Non sono riuscito a mettere in timeout questo utente: "
                "controlla i miei permessi e la posizione del mio ruolo.",
                ephemeral=True,
            )
            return

        case_number = await moderation_repo.create_case(
            guild_id=interaction.guild.id,
            user_id=member.id,
            moderator_id=interaction.user.id,
            action_type="timeout",
            reason=reason,
            duration_seconds=duration_seconds,
        )
        embed = _case_embed(
            "🔇 Timeout",
            discord.Color.dark_orange(),
            member,
            interaction.user,
            reason,
            case_number,
            extra_field=("Durata", format_duration(duration_seconds)),
        )
        await interaction.response.send_message(embed=embed)
        await try_dm(member, embed, azione="timeout", guild_id=interaction.guild.id)
        await post_to_mod_log(interaction.guild, embed)

    @comando_di_gruppo(
        "mod",
        nome="untimeout",
        descrizione="Rimuove il timeout da un membro.",
    )
    @app_commands.describe(member="Il membro da cui rimuovere il timeout")
    async def untimeout(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return

        try:
            await member.timeout(None, reason="Timeout rimosso manualmente")
        except discord.HTTPException:
            await interaction.response.send_message(
                "Non sono riuscito a rimuovere il timeout da questo utente: "
                "controlla i miei permessi.",
                ephemeral=True,
            )
            return

        case = await moderation_repo.get_latest_active_case(
            interaction.guild.id, member.id, "timeout"
        )
        if case is not None:
            await moderation_repo.revoke_case(
                interaction.guild.id, case.case_number, interaction.user.id
            )

        await interaction.response.send_message(f"Timeout rimosso da {member.mention}.")
        log_embed = discord.Embed(title="🔊 Timeout rimosso", color=discord.Color.green())
        log_embed.add_field(name="Utente", value=f"{member.mention} ({member.id})", inline=False)
        log_embed.add_field(name="Moderatore", value=interaction.user.mention, inline=True)
        await post_to_mod_log(interaction.guild, log_embed)

    # ================================================================
    # Azioni su più utenti insieme (MOD-002…006)
    # ================================================================
    async def _prepara_massa(
        self, interaction: discord.Interaction, utenti: str, reason: str, limite: str | None = None
    ) -> list[int] | None:
        """Controlli comuni: modulo, motivo, elenco. Dopo, l'interazione è in attesa (defer)."""
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return None
        if not await validate_reason(interaction, reason):
            return None
        ids, tagliato = leggi_utenti(utenti)
        if not ids:
            await interaction.response.send_message(
                "Non ho trovato utenti: scrivi ID o menzioni separati da spazi.", ephemeral=True
            )
            return None
        if (
            limite is not None
            and interaction.user.id != interaction.guild.owner_id
            and not prenota_uso(interaction.guild.id, interaction.user.id, limite, time.monotonic())
        ):
            # MOD-002: tetto di usi all'ora, perché un account rubato non svuoti il server.
            await interaction.response.send_message(
                f"Hai già usato questo comando {MAX_USI_ORA} volte nell'ultima ora: riprova più tardi.",
                ephemeral=True,
            )
            return None
        await interaction.response.defer()
        if tagliato:
            await interaction.followup.send(
                f"Elenco troppo lungo: agisco sui primi {MAX_UTENTI_MASSA}.", ephemeral=True
            )
        return ids

    async def _cerca_membro(self, guild: discord.Guild, uid: int) -> tuple[discord.Member | None, str | None]:
        """
        (membro, errore). Fuori dalla cache si chiede a Discord: senza il
        membro non si può controllare la gerarchia dei ruoli.
        """
        membro = guild.get_member(uid)
        if membro is not None:
            return membro, None
        try:
            return await guild.fetch_member(uid), None
        except discord.NotFound:
            return None, None
        except discord.HTTPException:
            return None, "non riesco a leggere il membro da Discord"

    async def _non_moderabile(self, interaction: discord.Interaction, uid: int, membro) -> str | None:
        """Il motivo per cui `uid` va saltato, o None. Stesse regole di check_can_moderate."""
        guild = interaction.guild
        if uid == interaction.user.id:
            return "sei tu"
        if guild.me is not None and uid == guild.me.id:
            return "sono io"
        if uid == guild.owner_id:
            return "proprietario del server"
        if membro is None:
            return None
        moderatore = guild.get_member(interaction.user.id)
        if moderatore is None:
            return "non riesco a verificare i tuoi permessi"
        consentito, motivo = can_moderate(
            actor_from_member(moderatore), actor_from_member(membro),
            bot_top_role_position=guild.me.top_role.position,
        )
        if not consentito:
            return motivo
        immune = await motivo_immune(guild, moderatore, membro)
        return immune.rstrip(".").lower() if immune else None

    async def _ban_uno_alla_volta(
        self, guild: discord.Guild, ids: list[int], reason: str, giorni: int
    ) -> set[int]:
        """Ban singoli al posto del ban in blocco. Gli ID bannati davvero."""
        bannati: set[int] = set()
        for uid in ids:
            try:
                await guild.ban(
                    discord.Object(id=uid), reason=audit_reason(f"Ban in massa: {reason}"),
                    delete_message_seconds=giorni * 86400,
                )
            except discord.HTTPException:
                continue
            bannati.add(uid)
        return bannati

    async def _chiudi_massa(
        self, interaction: discord.Interaction, titolo: str, colore: discord.Color,
        reason: str, fatti: list[str], saltati: list[str],
    ) -> None:
        embed = discord.Embed(title=titolo, color=colore, description=riepilogo(fatti, saltati))
        embed.add_field(name="Moderatore", value=interaction.user.mention, inline=True)
        embed.add_field(name="Motivo", value=reason, inline=False)
        await post_to_mod_log(interaction.guild, embed)
        await interaction.followup.send(embed=embed)

    @comando_di_gruppo(
        "modban",
        nome="ban",
        descrizione="Banna più utenti insieme, anche fuori dal server (ID o menzioni).",
        sottogruppo=("massa", "Azioni su più utenti insieme."),
    )
    @app_commands.describe(
        utenti=f"ID o menzioni separati da spazi (al massimo {MAX_UTENTI_MASSA})",
        reason="Motivo del ban",
        delete_message_days="Giorni di messaggi da cancellare (0-7). Vuoto: quelli di /mod opzioni",
    )
    async def ban_massa(
        self,
        interaction: discord.Interaction,
        utenti: app_commands.Range[str, 1, MAX_TESTO_UTENTI],
        reason: Reason,
        delete_message_days: app_commands.Range[int, 0, 7] | None = None,
    ) -> None:
        ids = await self._prepara_massa(interaction, utenti, reason, limite="ban")
        if ids is None:
            return
        guild = interaction.guild
        if delete_message_days is None:  # MOD-010: valore del server
            delete_message_days = (await moderation_opzioni.leggi(guild.id)).giorni_ban
        saltati: list[str] = []
        bersagli: list[tuple[int, discord.Message | None]] = []
        for uid in ids:
            membro, errore = await self._cerca_membro(guild, uid)
            motivo = errore or await self._non_moderabile(interaction, uid, membro)
            if motivo:
                saltati.append(f"`{uid}`: {motivo}")
                continue
            dm = None
            if membro is not None:
                # Il DM parte prima del ban: dopo non c'è più un server in comune.
                dm = await try_dm_message(
                    membro,
                    _case_embed("🔨 Ban", discord.Color.red(), membro, interaction.user, reason, None),
                    view=await vista_appello(guild.id),
                    azione="ban", guild_id=guild.id,
                )
            bersagli.append((uid, dm))
        bannati: set[int] = set()
        if bersagli:
            try:
                esito = await guild.bulk_ban(
                    [discord.Object(id=uid) for uid, _ in bersagli],
                    reason=audit_reason(f"Ban in massa: {reason}"),
                    delete_message_seconds=delete_message_days * 86400,
                )
                bannati = {u.id for u in esito.banned}
            except discord.Forbidden:
                # Il ban in blocco vuole anche «Gestisci server»: senza, uno alla volta.
                bannati = await self._ban_uno_alla_volta(guild, [uid for uid, _ in bersagli], reason, delete_message_days)
            except discord.HTTPException:
                bannati = set()
        fatti: list[str] = []
        for uid, dm in bersagli:
            if uid not in bannati:
                await delete_dm(dm)
                saltati.append(f"`{uid}`: Discord ha rifiutato")
                continue
            numero = await moderation_repo.create_case(
                guild_id=guild.id, user_id=uid, moderator_id=interaction.user.id, action_type="ban", reason=reason
            )
            await self._chiudi_sanzioni_a_tempo(guild, uid, interaction.user.id)
            fatti.append(f"<@{uid}> (`{uid}`) caso #{numero}")
        await self._chiudi_massa(interaction, "🔨 Ban in massa", discord.Color.red(), reason, fatti, saltati)

    @comando_di_gruppo(
        "modban",
        nome="unban",
        descrizione="Toglie il ban a più utenti insieme (ID).",
        sottogruppo=("massa", "Azioni su più utenti insieme."),
    )
    @app_commands.describe(
        utenti=f"ID separati da spazi (al massimo {MAX_UTENTI_MASSA})", reason="Motivo dello sblocco"
    )
    async def unban_massa(
        self, interaction: discord.Interaction, utenti: app_commands.Range[str, 1, MAX_TESTO_UTENTI], reason: Reason
    ) -> None:
        ids = await self._prepara_massa(interaction, utenti, reason)
        if ids is None:
            return
        guild = interaction.guild
        fatti: list[str] = []
        saltati: list[str] = []
        for uid in ids:
            stato = await moderation_repo.get_tempban_state(guild.id, uid)
            if stato is not None and stato["modo"] == MODO_ISOLAMENTO:
                saltati.append(f"`{uid}`: in isolamento, usa /modban unban")
                continue
            try:
                await guild.unban(discord.Object(id=uid), reason=audit_reason(reason))
            except discord.NotFound:
                saltati.append(f"`{uid}`: non è bannato")
                continue
            except discord.HTTPException:
                saltati.append(f"`{uid}`: Discord ha rifiutato")
                continue
            await self._dopo_unban(interaction.client, guild.id, uid, interaction.user.id, stato)
            fatti.append(f"<@{uid}> (`{uid}`)")
            try:
                await revoca_ban_propagati(interaction.client, guild.id, uid)
            except Exception:
                logger.exception("Revoca dei ban propagati fallita (server %s).", guild.id)
        await self._chiudi_massa(interaction, "🔓 Unban in massa", discord.Color.green(), reason, fatti, saltati)

    @comando_di_gruppo(
        "modban",
        nome="kick",
        descrizione="Espelle più membri insieme (ID o menzioni).",
        sottogruppo=("massa", "Azioni su più utenti insieme."),
    )
    @app_commands.describe(
        utenti=f"ID o menzioni separati da spazi (al massimo {MAX_UTENTI_MASSA})", reason="Motivo dell'espulsione"
    )
    async def kick_massa(
        self, interaction: discord.Interaction, utenti: app_commands.Range[str, 1, MAX_TESTO_UTENTI], reason: Reason
    ) -> None:
        ids = await self._prepara_massa(interaction, utenti, reason, limite="kick")
        if ids is None:
            return
        guild = interaction.guild
        fatti: list[str] = []
        saltati: list[str] = []
        for uid in ids:
            membro, errore = await self._cerca_membro(guild, uid)
            if membro is None:
                saltati.append(f"`{uid}`: {errore or 'non è nel server'}")
                continue
            motivo = await self._non_moderabile(interaction, uid, membro)
            if motivo:
                saltati.append(f"`{uid}`: {motivo}")
                continue
            dm = await try_dm_message(
                membro, _case_embed("👢 Kick", discord.Color.orange(), membro, interaction.user, reason, None),
                azione="kick", guild_id=guild.id,
            )
            try:
                await membro.kick(reason=audit_reason(reason))
            except discord.HTTPException:
                await delete_dm(dm)
                saltati.append(f"`{uid}`: Discord ha rifiutato")
                continue
            numero = await moderation_repo.create_case(
                guild_id=guild.id, user_id=uid, moderator_id=interaction.user.id, action_type="kick", reason=reason
            )
            await self._chiudi_sanzioni_a_tempo(guild, uid, interaction.user.id)
            fatti.append(f"{membro.mention} (`{uid}`) caso #{numero}")
        await self._chiudi_massa(interaction, "👢 Kick in massa", discord.Color.orange(), reason, fatti, saltati)

    @comando_di_gruppo(
        "mod",
        nome="timeout",
        descrizione="Mette in timeout più membri insieme (max 28 giorni).",
        sottogruppo=("massa", "Azioni su più membri insieme."),
    )
    @app_commands.describe(
        utenti=f"ID o menzioni separati da spazi (al massimo {MAX_UTENTI_MASSA})",
        duration="Durata, es. 10m, 2h, 1d (max 28d)",
        reason="Motivo del timeout",
    )
    async def timeout_massa(
        self,
        interaction: discord.Interaction,
        utenti: app_commands.Range[str, 1, MAX_TESTO_UTENTI],
        duration: app_commands.Range[str, 1, 20],
        reason: Reason,
    ) -> None:
        try:
            secondi = parse_duration(duration)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        if secondi > MAX_TIMEOUT_SECONDS:
            await interaction.response.send_message(
                "Il timeout nativo di Discord non può superare i 28 giorni.", ephemeral=True
            )
            return
        ids = await self._prepara_massa(interaction, utenti, reason)
        if ids is None:
            return
        guild = interaction.guild
        fatti: list[str] = []
        saltati: list[str] = []
        for uid in ids:
            membro, errore = await self._cerca_membro(guild, uid)
            if membro is None:
                saltati.append(f"`{uid}`: {errore or 'non è nel server'}")
                continue
            motivo = await self._non_moderabile(interaction, uid, membro)
            if motivo:
                saltati.append(f"`{uid}`: {motivo}")
                continue
            try:
                await membro.timeout(datetime.timedelta(seconds=secondi), reason=audit_reason(reason))
            except discord.HTTPException:
                saltati.append(f"`{uid}`: Discord ha rifiutato")
                continue
            numero = await moderation_repo.create_case(
                guild_id=guild.id, user_id=uid, moderator_id=interaction.user.id,
                action_type="timeout", reason=reason, duration_seconds=secondi,
            )
            embed = _case_embed(
                "🔇 Timeout", discord.Color.dark_orange(), membro, interaction.user, reason, numero,
                extra_field=("Durata", format_duration(secondi)),
            )
            await try_dm(membro, embed, azione="timeout", guild_id=guild.id)
            fatti.append(f"{membro.mention} (`{uid}`) caso #{numero}")
        await self._chiudi_massa(
            interaction, f"🔇 Timeout in massa ({format_duration(secondi)})", discord.Color.dark_orange(),
            reason, fatti, saltati,
        )

    @comando_di_gruppo(
        "mod",
        nome="warn",
        descrizione="Assegna un warn a più membri insieme.",
        sottogruppo=("massa", "Azioni su più membri insieme."),
    )
    @app_commands.describe(
        utenti=f"ID o menzioni separati da spazi (al massimo {MAX_UTENTI_MASSA})", reason="Motivo del warn"
    )
    async def warn_massa(
        self, interaction: discord.Interaction, utenti: app_commands.Range[str, 1, MAX_TESTO_UTENTI], reason: Reason
    ) -> None:
        ids = await self._prepara_massa(interaction, utenti, reason)
        if ids is None:
            return
        guild = interaction.guild
        fatti: list[str] = []
        saltati: list[str] = []
        for uid in ids:
            membro, errore = await self._cerca_membro(guild, uid)
            if membro is None:
                saltati.append(f"`{uid}`: {errore or 'non è nel server'}")
                continue
            motivo = await self._non_moderabile(interaction, uid, membro)
            if motivo:
                saltati.append(f"`{uid}`: {motivo}")
                continue
            numero = await moderation_repo.create_case(
                guild_id=guild.id, user_id=uid, moderator_id=interaction.user.id, action_type="warn", reason=reason
            )
            await try_dm(
                membro, _case_embed("⚠️ Warn", discord.Color.yellow(), membro, interaction.user, reason, numero),
                azione="warn", guild_id=guild.id,
            )
            await _avvisa_staff_se_troppi_warn(guild, membro)
            esito_scala = await scala_per_warn_manuale(
                self.bot, membro, numero, moderatore=guild.get_member(interaction.user.id), in_massa=True
            )
            fatti.append(f"{membro.mention} (`{uid}`) caso #{numero}" + (f" — {esito_scala}" if esito_scala else ""))
        await self._chiudi_massa(interaction, "⚠️ Warn in massa", discord.Color.yellow(), reason, fatti, saltati)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_ACTIONS,
            display_name="Moderazione — Azioni base",
            category="moderation",
            description="Warn, kick, ban, tempban, timeout.",
            premium_capable=False,  # resta SEMPRE gratis, come da schema
        )
    )

    cog = ModerationActionsCog(bot)
    await bot.add_cog(cog)

    # Collega l'handler del tempban allo scheduler. Fatto qui e non
    # dentro il costruttore del cog: lo scheduler è uno stato globale
    # condiviso, registrarlo nel punto di caricamento del cog (setup)
    # è coerente con come core/scheduler.py descrive il pattern d'uso.
    scheduler.register_handler(
        SCHEDULED_TEMPBAN_EXPIRE, cog.handle_tempban_expire
    )
