"""
cogs/security/verify.py
==========================
Verify Base (SPEC.md §4.1, §4.4, §4.5, §4.6). Modulo SEMPRE GRATUITO,
come da schema.

Due modalità mutuamente esclusive, scelte a `/verify setup`:
- button: bottone persistente (stesso pattern di TicketPanelView) —
  supporta il captcha, perché un click su bottone È un'Interaction e
  può aprire un Modal.
- reaction: l'utente reagisce a un messaggio con un'emoji — NON
  supporta il captcha: una reazione non è un'Interaction, non può
  aprire un Modal. La combinazione reaction+captcha viene rifiutata
  esplicitamente a `/verify setup`, non implementata a metà con un
  flusso DM fragile.

Fuori scope, dichiarato: §4.2 (Verify Avanzato, fingerprint IP/ISP)
e §4.3 (Anti-Alt) dipendono dal Web Panel (SPEC.md §C), non
costruito — non tentati qui.
"""

from __future__ import annotations

import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.premium import PremiumModule, registry
from core.repositories.verify_repo import verify_repo
from core.verify_logic import decide_verify_outcome, meets_account_age, meets_mutual_servers

logger = logging.getLogger("iyokai.verify")

MODULE_VERIFY = "verify"

VERIFY_BUTTON_CUSTOM_ID = "iyokai_verify_button"
VERIFY_REACTION_EMOJI = "✅"


class CaptchaModal(discord.ui.Modal, title="Verification"):
    """
    Captcha testuale (nessuna immagine — evita di introdurre Pillow
    come dipendenza solo per questo). Una semplice domanda di somma,
    generata al momento del click, diversa ogni volta: filtra i bot
    di join automatico più semplici, che non elaborano Modal.
    """

    def __init__(self, cog: "VerifyCog", guild_id: int, user_id: int) -> None:
        super().__init__()
        a, b = random.randint(1, 9), random.randint(1, 9)
        self._expected_answer = str(a + b)
        # discord.ui.Label che avvolge il TextInput è il pattern
        # corretto e non deprecato (TextInput.label= produce un
        # DeprecationWarning reale con discord.py 2.7.1, verificato
        # prima di scrivere questo file — stessa correzione applicata
        # a StaffReplyModal in cogs/security/spam_trap.py). Il
        # riferimento a self.answer_input resta valido per leggere
        # .value in on_submit, perché è lo stesso oggetto passato
        # come component= al Label.
        self.answer_input = discord.ui.TextInput(max_length=5)
        self.add_item(
            discord.ui.Label(text=f"What is {a} + {b}?", component=self.answer_input)
        )
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        captcha_ok = self.answer_input.value.strip() == self._expected_answer
        guild = interaction.client.get_guild(self.guild_id)
        if guild is None:
            await interaction.response.send_message(
                "Something went wrong, please try again.", ephemeral=True
            )
            return
        member = guild.get_member(self.user_id)
        if member is None:
            await interaction.response.send_message(
                "Something went wrong, please try again.", ephemeral=True
            )
            return

        outcome = await self.cog.run_checks_and_finalize(guild, member, captcha_ok)
        await interaction.response.send_message(outcome.reason, ephemeral=True)


class VerifyPanelView(discord.ui.View):
    """Persistente — stesso motivo/pattern di TicketPanelView e CreateVoiceView."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Verify",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id=VERIFY_BUTTON_CUSTOM_ID,
    )
    async def verify_click(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            return

        if not await db.is_module_active_for_guild(guild.id, MODULE_VERIFY):
            await interaction.response.send_message(
                "Verify non è attivo su questo server.", ephemeral=True
            )
            return

        cog = interaction.client.get_cog("VerifyCog")
        if cog is None:
            return

        config = await verify_repo.get_config(guild.id)
        if config.captcha_enabled:
            await interaction.response.send_modal(
                CaptchaModal(cog, guild.id, interaction.user.id)
            )
        else:
            outcome = await cog.run_checks_and_finalize(guild, interaction.user, captcha_ok=True)
            await interaction.response.send_message(outcome.reason, ephemeral=True)


class VerifyCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _count_mutual_guilds(self, user_id: int, excluding_guild_id: int) -> int:
        """
        Quanti server, TRA QUELLI IN CUI SI TROVA QUESTO BOT, hanno
        anche loro questo utente come membro — non tutti i server
        dell'utente in assoluto (Discord non lo espone a un bot).
        Segnale debole, non prova — vedi core/verify_logic.py.
        """
        count = 0
        for guild in self.bot.guilds:
            if guild.id == excluding_guild_id:
                continue
            if guild.get_member(user_id) is not None:
                count += 1
        return count

    async def run_checks_and_finalize(
        self, guild: discord.Guild, member: discord.Member, captcha_ok: bool
    ):
        config = await verify_repo.get_config(guild.id)

        is_whitelisted = await verify_repo.is_whitelisted(guild.id, member.id)
        is_blacklisted = await verify_repo.is_blacklisted(guild.id, member.id)
        age_ok = meets_account_age(member.created_at, config.min_account_age_days)
        mutual_count = self._count_mutual_guilds(member.id, guild.id)
        mutual_ok = meets_mutual_servers(mutual_count, config.min_mutual_servers)

        outcome = decide_verify_outcome(
            is_whitelisted, is_blacklisted, age_ok, mutual_ok, captcha_ok
        )

        await verify_repo.log_attempt(guild.id, member.id, outcome.success, outcome.reason)

        if outcome.success and config.verified_role_id is not None:
            role = guild.get_role(config.verified_role_id)
            if role is not None:
                try:
                    await member.add_roles(role, reason="iYokai Verify")
                except discord.Forbidden:
                    logger.warning(
                        "Permessi insufficienti per assegnare il ruolo verify "
                        "nel server %s.",
                        guild.id,
                    )

        if config.log_channel_id is not None:
            log_channel = guild.get_channel(config.log_channel_id)
            if isinstance(log_channel, discord.TextChannel):
                embed = discord.Embed(
                    title="Verify succeeded" if outcome.success else "Verify failed",
                    color=discord.Color.green() if outcome.success else discord.Color.red(),
                )
                embed.add_field(
                    name="User", value=f"{member.mention} ({member.id})", inline=False
                )
                embed.add_field(name="Reason", value=outcome.reason, inline=False)
                try:
                    await log_channel.send(embed=embed)
                except discord.HTTPException:
                    pass

        return outcome

    # ================================================================
    # Comandi
    # ================================================================
    verify_group = app_commands.Group(
        name="verify", description="Configura e gestisci il sistema di verifica."
    )

    @verify_group.command(name="setup", description="[Admin] Configura il Verify.")
    @app_commands.describe(
        method="Modalità: bottone (supporta captcha) o reazione",
        verified_role="Ruolo da assegnare dopo la verifica",
        min_account_age_days="Età minima dell'account in giorni (0 = disattivato)",
        min_mutual_servers="Server in comune minimi richiesti (0 = disattivato)",
        captcha_enabled="Richiedi un captcha testuale (solo modalità bottone)",
        log_channel="Canale dove loggare ogni tentativo",
    )
    @app_commands.choices(
        method=[
            app_commands.Choice(name="Button", value="button"),
            app_commands.Choice(name="Reaction", value="reaction"),
        ]
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_cmd(
        self,
        interaction: discord.Interaction,
        method: app_commands.Choice[str],
        verified_role: discord.Role,
        min_account_age_days: app_commands.Range[int, 0, 3650] = 0,
        min_mutual_servers: app_commands.Range[int, 0, 100] = 0,
        captcha_enabled: bool = False,
        log_channel: discord.TextChannel | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.",
                ephemeral=True,
            )
            return

        if method.value == "reaction" and captcha_enabled:
            await interaction.response.send_message(
                "Il captcha non è supportato in modalità reaction: una "
                "reazione non può aprire una finestra di verifica. Usa la "
                "modalità Button se vuoi il captcha.",
                ephemeral=True,
            )
            return

        await verify_repo.set_config(
            guild_id=interaction.guild.id,
            method=method.value,
            verified_role_id=verified_role.id,
            min_account_age_days=min_account_age_days,
            min_mutual_servers=min_mutual_servers,
            captcha_enabled=captcha_enabled,
            log_channel_id=log_channel.id if log_channel else None,
        )

        await interaction.response.send_message(
            f"Verify configurato: modalità **{method.name}**, ruolo "
            f"{verified_role.mention}. Usa /verify panel per pubblicare "
            f"il pannello.",
            ephemeral=True,
        )

    @verify_group.command(name="panel", description="[Admin] Pubblica il pannello di verifica.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def panel_cmd(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.",
                ephemeral=True,
            )
            return

        config = await verify_repo.get_config(interaction.guild.id)
        if config.verified_role_id is None:
            await interaction.response.send_message(
                "Configura prima il Verify con /verify setup.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="✅ Server Verification",
            description="Click the button below to verify and gain access to the server."
            if config.method == "button"
            else f"React with {VERIFY_REACTION_EMOJI} to verify and gain access to the server.",
            color=discord.Color.blurple(),
        )

        if config.method == "button":
            await interaction.response.send_message(embed=embed, view=VerifyPanelView())
            sent = await interaction.original_response()
        else:
            await interaction.response.send_message(embed=embed)
            sent = await interaction.original_response()
            await sent.add_reaction(VERIFY_REACTION_EMOJI)

        await verify_repo.set_panel_message(interaction.guild.id, sent.channel.id, sent.id)

    @verify_group.command(name="whitelist-add", description="[Admin] Aggiungi un utente alla whitelist.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def whitelist_add(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if interaction.guild is None:
            return
        await verify_repo.add_whitelist(interaction.guild.id, member.id)
        await interaction.response.send_message(f"{member.mention} aggiunto alla whitelist.", ephemeral=True)

    @verify_group.command(name="whitelist-remove", description="[Admin] Rimuovi un utente dalla whitelist.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def whitelist_remove(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if interaction.guild is None:
            return
        await verify_repo.remove_whitelist(interaction.guild.id, member.id)
        await interaction.response.send_message(f"{member.mention} rimosso dalla whitelist.", ephemeral=True)

    @verify_group.command(name="blacklist-add", description="[Admin] Aggiungi un utente alla blacklist.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def blacklist_add(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if interaction.guild is None:
            return
        await verify_repo.add_blacklist(interaction.guild.id, member.id)
        await interaction.response.send_message(f"{member.mention} aggiunto alla blacklist.", ephemeral=True)

    @verify_group.command(name="blacklist-remove", description="[Admin] Rimuovi un utente dalla blacklist.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def blacklist_remove(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if interaction.guild is None:
            return
        await verify_repo.remove_blacklist(interaction.guild.id, member.id)
        await interaction.response.send_message(f"{member.mention} rimosso dalla blacklist.", ephemeral=True)

    # ================================================================
    # Modalità reaction
    # ================================================================
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None or payload.member is None or payload.member.bot:
            return
        if str(payload.emoji) != VERIFY_REACTION_EMOJI:
            return

        if not await db.is_module_active_for_guild(payload.guild_id, MODULE_VERIFY):
            return

        config = await verify_repo.get_config(payload.guild_id)
        if config.method != "reaction" or config.panel_message_id != payload.message_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        outcome = await self.run_checks_and_finalize(guild, payload.member, captcha_ok=True)

        try:
            await payload.member.send(outcome.reason)
        except discord.HTTPException:
            pass  # DM chiusi: l'esito resta comunque nel log


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_VERIFY,
            display_name="Verify",
            description="Verifica dei nuovi membri: bottone/reazione, captcha, età account, mutual servers.",
            premium_capable=False,
        )
    )
    cog = VerifyCog(bot)
    await bot.add_cog(cog)
    bot.add_view(VerifyPanelView())
