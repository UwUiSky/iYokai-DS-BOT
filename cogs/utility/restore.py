"""
cogs/utility/restore.py
===========================
Restore massivo utenti via OAuth2 (SPEC.md §11.11/§11.12) — comandi
/configura-restore e /restore-users, più i listener che tengono
aggiornata la retention dei token salvati (uscita spontanea/kick/
ban, come concordato esplicitamente con l'utente).

Tre modalità per server (impostate con /configura-restore),
esattamente come discusso: server NUOVI raccolgono il consenso al
momento della verifica (verify_oauth, non gestito qui — vedi
cogs/security/verify.py per il pannello che offre il link);
server ESISTENTI grandi usano la modalità on-demand (default:
raccoglie il consenso solo se/quando serve un restore, riusando i
token già raccolti da restore precedenti); in alternativa, invito
classico senza alcun token.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.config import config
from core.database import db
from core.oauth_crypto import OAuthEncryptionNotConfigured
from core.repositories.backup_user_snapshot_repo import backup_user_snapshot_repo
from core.repositories.restore_oauth_repo import restore_oauth_repo
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
from core.restore_oauth_logic import build_authorize_url
from core.restore_orchestrator import restore_orchestrator
from core.restore_retention_logic import was_recently_kicked

logger = logging.getLogger("iyokai.restore")

SETTING_RESTORE_MODE = "backup_restore_mode"
SETTING_AUTO_INVITE_ON_JOIN = "backup_auto_invite_on_join"

# Da cogs/moderation/_shared.py — stesso canale già usato per il log
# di moderazione, riusato per l'avviso "un utente kickato è rientrato"
# invece di inventare un secondo canale da configurare a parte.
SETTING_MOD_LOG_CHANNEL = "mod_log_channel_id"


class RestoreCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------
    # Configurazione
    # ------------------------------------------------------------
    @app_commands.command(
        name="configura-restore",
        description="[Admin] Scegli come questo server gestisce il restore utenti via OAuth2.",
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
    @app_commands.checks.has_permissions(manage_guild=True)
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
    # /restore-users
    # ------------------------------------------------------------
    @app_commands.command(
        name="restore-users",
        description="[Admin] Ripristina in QUESTO server gli utenti dell'ultimo snapshot di un altro server.",
    )
    @app_commands.describe(
        server_di_origine="ID del server (main originale) da cui ripristinare gli utenti"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def restore_users(self, interaction: discord.Interaction, server_di_origine: str) -> None:
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

        snapshot = await backup_user_snapshot_repo.get_snapshot(source_guild_id)
        if not snapshot:
            await interaction.response.send_message(
                "⚠️ Nessuno snapshot trovato per quel server — nessun utente da ripristinare.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

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
        }

        invito_classico_url: str | None = None

        for entry in snapshot:
            token = await restore_oauth_repo.get_token(source_guild_id, entry.user_id)
            token_status = token.status if token is not None else None
            token_scaduto = (
                token is not None and token.expires_at < datetime.now(timezone.utc)
            )
            azione = plan_restore_action(modalita, token_status, token_scaduto)
            contatori[azione] += 1

            if azione == ACTION_SKIP_BLACKLISTED:
                continue

            if azione == ACTION_AUTO_JOIN:
                aggiunto = await restore_orchestrator.join_user_via_oauth(
                    bot_token=config.YOKAI_BOT_TOKEN,
                    guild_id=interaction.guild.id,
                    user_id=entry.user_id,
                    access_token=token.access_token,
                )
                if aggiunto and ruolo_verificato_id is not None:
                    await restore_orchestrator.assign_role(
                        bot_token=config.YOKAI_BOT_TOKEN,
                        guild_id=interaction.guild.id,
                        user_id=entry.user_id,
                        role_id=ruolo_verificato_id,
                    )
                continue

            if azione == ACTION_REQUEST_CONSENT:
                try:
                    url = build_authorize_url(
                        client_id=config.OAUTH2_CLIENT_ID,
                        redirect_uri=config.OAUTH2_REDIRECT_URI,
                        source_guild_id=source_guild_id,
                        target_guild_id=interaction.guild.id,
                        user_id=entry.user_id,
                    )
                    utente = await self.bot.fetch_user(entry.user_id)
                    await utente.send(
                        f"👋 Il server **{interaction.guild.name}** ha bisogno di ripristinarti "
                        f"dopo un backup. Clicca per rientrare automaticamente: {url}"
                    )
                except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                    contatori["dm_falliti"] += 1
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
                except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                    contatori["dm_falliti"] += 1
                continue

        await interaction.followup.send(
            "**Restore completato.**\n"
            f"✅ Aggiunti automaticamente (token già autorizzato): {contatori[ACTION_AUTO_JOIN]}\n"
            f"✉️ DM di autorizzazione inviati: {contatori[ACTION_REQUEST_CONSENT]}\n"
            f"📨 Inviti classici inviati: {contatori[ACTION_CLASSIC_INVITE]}\n"
            f"🚫 Saltati (in blacklist da un ban): {contatori[ACTION_SKIP_BLACKLISTED]}\n"
            f"⚠️ DM non consegnati (privacy/bloccati): {contatori['dm_falliti']}",
            ephemeral=True,
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
