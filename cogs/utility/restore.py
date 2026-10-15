"""
cogs/utility/restore.py
===========================
Restore massivo utenti via OAuth2 (SPEC.md §11.11/§11.12) — comandi
/backup restore-modo e /backup restore-utenti, più i listener che tengono
aggiornata la retention dei token salvati (uscita spontanea/kick/
ban, come concordato esplicitamente con l'utente).

Tre modalità per server (impostate con /backup restore-modo),
esattamente come discusso: server NUOVI raccolgono il consenso al
momento della verifica (verify_oauth, non gestito qui — vedi
cogs/security/verify.py per il pannello che offre il link);
server ESISTENTI grandi usano la modalità on-demand (default:
raccoglie il consenso solo se/quando serve un restore, riusando i
token già raccolti da restore precedenti); in alternativa, invito
classico senza alcun token.

A fine verifica (cogs/security/verify.py) il membro di un server con backup
riceve la proposta di consenso: un bottone per accettare i DM di ripristino
(M 12.12) e, in modalità «OAuth alla verifica», anche il link OAuth (M 12.14).
Il restore manda DM solo a chi ha accettato o ha dato il consenso OAuth.
Funzioni coperte: SPEC §11.11, §11.12, M 12.10–12.14
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.config import config
from core.database import db
from core.oauth_crypto import OAuthEncryptionNotConfigured
from core.repositories.backup_repo import backup_repo
from core.repositories.backup_user_snapshot_repo import backup_user_snapshot_repo
from core.repositories.restore_oauth_repo import STATUS_BANNED_BLACKLISTED, restore_oauth_repo
from core.repositories.verify_repo import verify_repo
from core.restore_batch_logic import (
    ACTION_AUTO_JOIN,
    ACTION_CLASSIC_INVITE,
    ACTION_REQUEST_CONSENT,
    ACTION_SKIP_BLACKLISTED,
    DEFAULT_RESTORE_MODE,
    MODE_CLASSIC_INVITE,
    MODE_ON_DEMAND_OAUTH,
    MODE_VERIFY_OAUTH,
    plan_restore_action,
)
from core.restore_oauth_logic import (
    STATE_TTL_SECONDS,
    RestoreStateSigningError,
    build_authorize_url,
)
from core.restore_orchestrator import LimiteDiFrequenza, restore_orchestrator
from core.restore_retention_logic import was_recently_kicked
from core.restore_web_server import CONSENT_ONLY_TARGET
from core.role_safety import motivo_ruolo_automatico_non_assegnabile
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.restore")

# M 12.11: pausa dopo ogni DM tentato (i DM a utenti diversi hanno un limite loro)
# e margine entro cui un token si rinnova prima di scadere (M 12.10).
PAUSA_TRA_DM_SECONDI = 1.5
MARGINE_RINNOVO_TOKEN = timedelta(minutes=5)
_pausa = asyncio.sleep

SETTING_RESTORE_MODE = "backup_restore_mode"
SETTING_AUTO_INVITE_ON_JOIN = "backup_auto_invite_on_join"

# Da cogs/moderation/_shared.py — stesso canale già usato per il log
# di moderazione, riusato per l'avviso "un utente kickato è rientrato"
# invece di inventare un secondo canale da configurare a parte.
SETTING_MOD_LOG_CHANNEL = "mod_log_channel_id"


class ConsensoRestoreView(BaseView):
    """M 12.12: il membro sceglie se ricevere un DM quando il server va ripristinato."""

    def __init__(self, guild_id: int, user_id: int) -> None:
        super().__init__(timeout=900)
        self.guild_id = guild_id
        self.user_id = user_id

    @discord.ui.button(label="Sì, avvisami", style=discord.ButtonStyle.success)
    async def accetta(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await restore_oauth_repo.salva_consenso(self.guild_id, self.user_id)
        await interaction.response.edit_message(
            content="✅ Se il server dovrà essere ripristinato riceverai un DM con il link per rientrare.",
            view=None,
        )

    @discord.ui.button(label="No, grazie", style=discord.ButtonStyle.secondary)
    async def rifiuta(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await restore_oauth_repo.ritira_consenso(self.guild_id, self.user_id)
        await interaction.response.edit_message(
            content="Va bene: in caso di ripristino non riceverai DM da questo server.", view=None
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id and await super().interaction_check(interaction)


async def proposta_consenso_restore(
    guild_id: int, user_id: int
) -> tuple[str, ConsensoRestoreView] | None:
    """
    M 12.12/12.14: testo e bottoni da mostrare a fine verifica. None se il server
    non usa il backup, è in modalità «solo invito classico» senza coppia, o se
    l'utente ha già dato il consenso.
    """
    modalita = await db.get_guild_setting(guild_id, SETTING_RESTORE_MODE, DEFAULT_RESTORE_MODE)
    if modalita != MODE_VERIFY_OAUTH and await backup_repo.get_pair(guild_id) is None:
        return None
    if await restore_oauth_repo.ha_consenso(guild_id, user_id):
        return None
    testo = (
        "📦 Questo server ha un backup. Se un giorno dovrà essere ripristinato, "
        "vuoi ricevere un DM con il link per rientrare?"
    )
    if modalita == MODE_VERIFY_OAUTH:
        try:
            url = build_authorize_url(
                client_id=config.OAUTH2_CLIENT_ID,
                redirect_uri=config.OAUTH2_REDIRECT_URI,
                source_guild_id=guild_id,
                target_guild_id=CONSENT_ONLY_TARGET,
                user_id=user_id,
                signing_key_b64=config.OAUTH_ENCRYPTION_KEY,
            )
            testo += (
                f"\nOppure [autorizza il rientro automatico]({url}): in caso di ripristino "
                "sarai aggiunto da solo, senza DM."
            )
        except RestoreStateSigningError:
            logger.warning("Link OAuth di fine verifica non creato: OAUTH_ENCRYPTION_KEY non configurata.")
    return testo, ConsensoRestoreView(guild_id, user_id)


class RestoreCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------
    # Configurazione
    # ------------------------------------------------------------
    @comando_di_gruppo(
        "backup",
        nome="restore-modo",
        descrizione="Scegli come questo server gestisce il restore utenti via OAuth2.",
    )
    @app_commands.describe(
        modalita="Come raccogliere il consenso per il restore automatico",
        auto_invito_nuovi_membri="Solo con invito classico: DM automatico ai nuovi membri con il link di backup",
    )
    @app_commands.choices(
        modalita=[
            app_commands.Choice(name="OAuth al momento della verifica (server nuovi)", value=MODE_VERIFY_OAUTH),
            app_commands.Choice(name="OAuth solo al bisogno (default, server esistenti)", value=MODE_ON_DEMAND_OAUTH),
            app_commands.Choice(name="Solo invito classico (nessun token salvato)", value=MODE_CLASSIC_INVITE),
        ]
    )
    async def configura_restore(
        self,
        interaction: discord.Interaction,
        modalita: app_commands.Choice[str],
        auto_invito_nuovi_membri: bool = False,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        await db.set_guild_setting(interaction.guild.id, SETTING_RESTORE_MODE, modalita.value)
        await db.set_guild_setting(
            interaction.guild.id, SETTING_AUTO_INVITE_ON_JOIN, auto_invito_nuovi_membri
        )

        await interaction.response.send_message(
            f"✅ Modalità restore impostata: **{modalita.name}**"
            + (" (auto-invito nuovi membri attivo)" if auto_invito_nuovi_membri else ""),
            ephemeral=True,
        )

    # ------------------------------------------------------------
    # /backup restore-utenti
    # ------------------------------------------------------------
    @comando_di_gruppo(
        "backup",
        nome="restore-utenti",
        descrizione="Ripristina in QUESTO server gli utenti dell'ultimo snapshot di un altro server.",
    )
    @app_commands.describe(
        server_di_origine="ID del server (main originale) da cui ripristinare gli utenti"
    )
    async def restore_users(
        self, interaction: discord.Interaction, server_di_origine: app_commands.Range[str, 1, 20]
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        try:
            source_guild_id = int(server_di_origine)
        except ValueError:
            await interaction.response.send_message(
                "L'ID del server di origine deve essere un numero.", ephemeral=True
            )
            return

        # SEC-2: il restore è permesso SOLO dal server di origine
        # verso il suo backup designato — senza questo controllo un
        # admin potrebbe scrivere l'ID di un server qualunque e
        # farsi ripristinare (o invitare a forza) gli utenti di
        # qualcun altro nel proprio server.
        # M 12.13 (BUG-34): vale anche la coppia storica dopo una promozione.
        if not await backup_repo.is_backup_of(source_guild_id, interaction.guild.id):
            await interaction.response.send_message(
                "⚠️ Questo server non è registrato come backup di quello indicato. "
                "Il restore è permesso solo dal server di origine verso il suo "
                "backup designato (vedi /backup main e /backup crea).",
                ephemeral=True,
            )
            return

        snapshot = await backup_user_snapshot_repo.get_snapshot(source_guild_id)
        if not snapshot:
            await interaction.response.send_message(
                "⚠️ Nessuno snapshot trovato per quel server — nessun utente da ripristinare.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Un solo ripristino alla volta per server: due insieme rinnoverebbero lo
        # stesso token (Discord ruota il refresh token) e manderebbero DM doppi.
        async with restore_oauth_repo.blocco_restore(interaction.guild.id) as preso:
            if not preso:
                await interaction.followup.send(
                    "⏳ C'è già un ripristino in corso per questo server: attendi che finisca.",
                    ephemeral=True,
                )
                return
            await self._esegui_restore(interaction, source_guild_id, snapshot)

    async def _esegui_restore(self, interaction, source_guild_id: int, snapshot) -> None:
        modalita = await db.get_guild_setting(
            interaction.guild.id, SETTING_RESTORE_MODE, DEFAULT_RESTORE_MODE
        )
        config_verifica = await verify_repo.get_config(interaction.guild.id)
        ruolo_verificato_id = config_verifica.verified_role_id if config_verifica else None

        contatori = {
            ACTION_AUTO_JOIN: 0,
            ACTION_REQUEST_CONSENT: 0,
            ACTION_CLASSIC_INVITE: 0,
            ACTION_SKIP_BLACKLISTED: 0,
            "dm_falliti": 0,
            "join_falliti": 0,
            "illeggibili": 0,
            "rimandati": 0,
            "gia_contattati": 0,
            "senza_consenso": 0,
            "ruolo_non_assegnato": 0,
        }

        invito_classico_url: str | None = None

        for entry in snapshot:
            stato_riga = await restore_oauth_repo.get_stato(source_guild_id, entry.user_id)
            token = await restore_oauth_repo.get_token(source_guild_id, entry.user_id)
            if stato_riga is not None and token is None:
                # Riga che non si legge (chiave cambiata, dato rovinato): errore già nel log.
                # Mai un permesso a rientrare: un bannato resta saltato, gli altri si trattano
                # come senza token (nuovo consenso).
                contatori["illeggibili"] += 1
            try:
                token = await self._rinnova_se_serve(source_guild_id, entry.user_id, token)
            except LimiteDiFrequenza:
                contatori["rimandati"] += 1  # il token non è scaduto: niente DM, si riprova dopo
                continue
            token_status = token.status if token is not None else None
            if stato_riga == STATUS_BANNED_BLACKLISTED:
                token_status = STATUS_BANNED_BLACKLISTED
            token_scaduto = (
                token is not None and token.expires_at < datetime.now(timezone.utc)
            )
            azione = plan_restore_action(modalita, token_status, token_scaduto)

            if azione == ACTION_SKIP_BLACKLISTED:
                contatori[azione] += 1
                continue

            if azione == ACTION_AUTO_JOIN:
                aggiunto = await restore_orchestrator.join_user_via_oauth(
                    bot_token=config.YOKAI_BOT_TOKEN,
                    guild_id=interaction.guild.id,
                    user_id=entry.user_id,
                    access_token=token.access_token,
                )
                if not aggiunto:
                    contatori["join_falliti"] += 1
                    continue
                contatori[azione] += 1  # M 12.11: si conta dopo l'esito
                if ruolo_verificato_id is not None:
                    assegnato = await self._assegna_ruolo_verificato(
                        interaction.guild, entry.user_id, ruolo_verificato_id
                    )
                    if not assegnato:
                        contatori["ruolo_non_assegnato"] += 1
                continue

            if azione in (ACTION_REQUEST_CONSENT, ACTION_CLASSIC_INVITE) and not (
                await restore_oauth_repo.ha_consenso(source_guild_id, entry.user_id)
            ):
                contatori["senza_consenso"] += 1  # M 12.12: niente contatti senza permesso
                continue

            if azione in (ACTION_REQUEST_CONSENT, ACTION_CLASSIC_INVITE) and (
                await restore_oauth_repo.gia_contattato(
                    interaction.guild.id, source_guild_id, entry.user_id
                )
            ):
                contatori["gia_contattati"] += 1  # niente DM ripetuti ai rilanci
                continue

            if azione == ACTION_REQUEST_CONSENT:
                try:
                    url = build_authorize_url(
                        client_id=config.OAUTH2_CLIENT_ID,
                        redirect_uri=config.OAUTH2_REDIRECT_URI,
                        source_guild_id=source_guild_id,
                        target_guild_id=interaction.guild.id,
                        user_id=entry.user_id,
                        signing_key_b64=config.OAUTH_ENCRYPTION_KEY,
                    )
                    utente = await self.bot.fetch_user(entry.user_id)
                    await utente.send(
                        f"👋 Il server **{interaction.guild.name}** ha bisogno di ripristinarti "
                        f"dopo un backup. Clicca per rientrare automaticamente (il link è "
                        f"personale e vale {STATE_TTL_SECONDS // 86400} giorni): {url}"
                    )
                    contatori[azione] += 1
                    await restore_oauth_repo.segna_contattato(
                        interaction.guild.id, source_guild_id, entry.user_id, azione
                    )
                except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                    contatori["dm_falliti"] += 1
                except RestoreStateSigningError:
                    logger.warning(
                        "Impossibile firmare lo state OAuth2 per il restore (OAUTH_ENCRYPTION_KEY "
                        "non configurata): DM di autorizzazione non inviato a %s.",
                        entry.user_id,
                    )
                    contatori["dm_falliti"] += 1
                await _pausa(PAUSA_TRA_DM_SECONDI)
                continue

            if azione == ACTION_CLASSIC_INVITE:
                if invito_classico_url is None:
                    invito_classico_url = await self._crea_invito_classico(interaction)
                try:
                    utente = await self.bot.fetch_user(entry.user_id)
                    await utente.send(
                        f"👋 Il server **{interaction.guild.name}** ha bisogno di ripristinarti "
                        f"dopo un backup. Ecco l'invito: {invito_classico_url}"
                    )
                    contatori[azione] += 1
                    await restore_oauth_repo.segna_contattato(
                        interaction.guild.id, source_guild_id, entry.user_id, azione
                    )
                except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                    contatori["dm_falliti"] += 1
                await _pausa(PAUSA_TRA_DM_SECONDI)
                continue

        riepilogo = (
            "**Restore completato.**\n"
            f"✅ Aggiunti automaticamente (token già autorizzato): {contatori[ACTION_AUTO_JOIN]}\n"
            f"✉️ DM di autorizzazione inviati: {contatori[ACTION_REQUEST_CONSENT]}\n"
            f"📨 Inviti classici inviati: {contatori[ACTION_CLASSIC_INVITE]}\n"
            f"🚫 Saltati (in blacklist da un ban): {contatori[ACTION_SKIP_BLACKLISTED]}\n"
            f"⚠️ DM non consegnati (privacy/bloccati): {contatori['dm_falliti']}\n"
            f"⚠️ Aggiunta non riuscita: {contatori['join_falliti']}\n"
            f"🔒 Token illeggibili (da rifare): {contatori['illeggibili']}\n"
            f"⏱️ Rimandati (limite di frequenza): {contatori['rimandati']}\n"
            f"🔁 Già contattati di recente: {contatori['gia_contattati']}\n"
            f"🤐 Non contattati (nessun consenso ai DM): {contatori['senza_consenso']}"
            + (
                f"\n⚠️ Ruolo verificato non assegnato (controlla il ruolo scelto in "
                f"/security verify setup): {contatori['ruolo_non_assegnato']}"
                if contatori["ruolo_non_assegnato"]
                else ""
            )
        )
        await self._manda_riepilogo(interaction, riepilogo)

    async def _manda_riepilogo(self, interaction: discord.Interaction, testo: str) -> None:
        """Un solo messaggio finale. Il ciclo può durare più dei 15 minuti di vita
        della risposta dell'interazione: in quel caso il riepilogo va nel canale."""
        try:
            await interaction.followup.send(testo, ephemeral=True)
        except discord.HTTPException:
            canale = interaction.channel
            if canale is not None:
                await canale.send(testo)

    async def _rinnova_se_serve(self, source_guild_id: int, user_id: int, token):
        """
        M 12.10 (LIM-37): un token scaduto o vicino alla scadenza si rinnova con il
        refresh token e si salva. Se Discord rifiuta il rinnovo (token revocato) si
        restituisce il token com'è: sarà trattato come scaduto e si chiede il consenso.
        """
        if token is None or token.status == STATUS_BANNED_BLACKLISTED:
            return token
        if token.expires_at - MARGINE_RINNOVO_TOKEN > datetime.now(timezone.utc):
            return token
        nuovo = await restore_orchestrator.refresh_access_token(
            config.OAUTH2_CLIENT_ID, config.OAUTH2_CLIENT_SECRET, token.refresh_token
        )
        if nuovo is None:
            return token
        await restore_oauth_repo.aggiorna_token(
            source_guild_id, user_id, nuovo.access_token, nuovo.refresh_token, nuovo.expires_at
        )
        return await restore_oauth_repo.get_token(source_guild_id, user_id)

    async def _assegna_ruolo_verificato(
        self, guild: discord.Guild, user_id: int, role_id: int
    ) -> bool:
        """
        SEC-4/SEC-17: il ruolo verificato può aver preso permessi
        pericolosi dopo il /security verify setup, quindi si ricontrolla al
        momento dell'assegnazione. Se non va bene l'utente resta nel
        server senza il ruolo (False) e resta un avviso nei log.
        """
        motivo_rifiuto = motivo_ruolo_automatico_non_assegnabile(guild, role_id)
        if motivo_rifiuto is not None:
            logger.warning(
                "Ruolo verificato %s non assegnato a %s nel server %s durante il restore: %s",
                role_id,
                user_id,
                guild.id,
                motivo_rifiuto,
            )
            return False
        return await restore_orchestrator.assign_role(
            bot_token=config.YOKAI_BOT_TOKEN,
            guild_id=guild.id,
            user_id=user_id,
            role_id=role_id,
        )

    async def _crea_invito_classico(self, interaction: discord.Interaction) -> str:
        canale = interaction.channel
        invito = await canale.create_invite(
            max_age=7 * 24 * 60 * 60, reason="Restore utenti (SPEC.md §11.11, invito classico)"
        )
        return invito.url

    # ------------------------------------------------------------
    # Listener: retention (SPEC.md §11.11)
    # ------------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.abc.User) -> None:
        try:
            await restore_oauth_repo.mark_banned(guild.id, user.id)
        except OAuthEncryptionNotConfigured:
            pass  # nessun token salvato per nessuno: nulla da marcare

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        try:
            voci_kick = [
                voce
                async for voce in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.kick)
            ]
        except discord.Forbidden:
            voci_kick = []  # bot senza permesso "Visualizza registro audit" - non blocchiamo nulla

        try:
            if was_recently_kicked(voci_kick, member.id, datetime.now(timezone.utc)):
                await restore_oauth_repo.mark_kicked(member.guild.id, member.id)
            else:
                await restore_oauth_repo.mark_left_voluntarily(member.guild.id, member.id)
        except OAuthEncryptionNotConfigured:
            pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        try:
            token = await restore_oauth_repo.get_token(member.guild.id, member.id)
        except OAuthEncryptionNotConfigured:
            return

        from core.repositories.restore_oauth_repo import STATUS_KICKED_FLAGGED

        if token is None or token.status != STATUS_KICKED_FLAGGED:
            return

        canale_id = await db.get_guild_setting(member.guild.id, SETTING_MOD_LOG_CHANNEL)
        if canale_id is None:
            return
        canale = member.guild.get_channel(canale_id)
        if canale is not None:
            await canale.send(
                f"⚠️ {member.mention} era stato **kickato** e ha un token di restore salvato — "
                f"è rientrato nel server, verificate se è opportuno."
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RestoreCog(bot))
