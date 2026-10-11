"""
cogs/utility/greetings.py
============================
Welcome / Goodbye / Boost messages (SPEC.md §14.4-14.6). Modulo
gratuito — stessa assunzione dichiarata di role_menus.py: lo schema
non specifica esplicitamente Free/Premium per questa voce di §14.
"""

# DA FARE (issue #82, fase F9): NF-11, Immagine di benvenuto. Vedi
#   revisione/02-piano/NUOVE_FUNZIONI.md.

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.admin_mentions_logic import menzioni_ammesse, puo_pingare_ruoli, taglia_messaggio
from core.greetings_logic import MAX_MESSAGE_LENGTH, lunghezza_dopo_segnaposto, render_template
from core.premium import PremiumModule, registry
from core.repositories.greetings_repo import greetings_repo
from core.security_raid_state import raid_in_corso

logger = logging.getLogger("iyokai.greetings")

MODULE_GREETINGS = "greetings"


def _render_for_member(template: str, member: discord.Member) -> str:
    return render_template(
        template,
        user_mention=member.mention,
        username=member.name,
        server_name=member.guild.name,
        member_count=member.guild.member_count or 0,
    )


# L'opzione accetta il testo grezzo: il limite vero (2000) si controlla
# dopo i segnaposto, a configurazione, con `_errore_lunghezza`.
TestoMessaggio = app_commands.Range[str, 1, MAX_MESSAGE_LENGTH]


def _errore_lunghezza(guild: discord.Guild, template: str) -> str | None:
    """M 10.2 (LIM-10): None se il testo, a segnaposto espansi, sta in 2000 caratteri."""
    lunghezza = lunghezza_dopo_segnaposto(template, guild.name, guild.member_count or 0)
    if lunghezza <= MAX_MESSAGE_LENGTH:
        return None
    return (
        f"Con i segnaposto sostituiti il messaggio arriva a {lunghezza} caratteri: "
        f"Discord ne accetta {MAX_MESSAGE_LENGTH}. Accorcialo."
    )


def _ping_ruoli_di(interaction: discord.Interaction) -> bool:
    """D12: i ruoli del messaggio vengono avvisati solo se chi configura può menzionarli."""
    utente = interaction.user
    return isinstance(utente, discord.Member) and puo_pingare_ruoli(utente.guild_permissions)


_SG_BENVENUTO = ("benvenuto", "Messaggi di benvenuto, addio e boost")


class GreetingsCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ================================================================
    # Eventi
    # ================================================================
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        # Niente benvenuto ai bot: non possono ricevere messaggi privati
        # da un altro bot e li ha aggiunti un amministratore.
        if member.bot:
            return
        if not await db.is_module_active_for_guild(member.guild.id, MODULE_GREETINGS):
            return

        config = await greetings_repo.get_config(member.guild.id)
        if not config.welcome_enabled:
            return

        testo = taglia_messaggio(_render_for_member(config.welcome_message, member))
        menzioni = menzioni_ammesse(config.welcome_ping_ruoli, [member])

        if config.welcome_channel_id is not None:
            channel = member.guild.get_channel(config.welcome_channel_id)
            if isinstance(channel, discord.TextChannel):
                try:
                    await channel.send(testo, allowed_mentions=menzioni)
                except discord.HTTPException:
                    logger.warning(
                        "Impossibile inviare il welcome message nel server %s.",
                        member.guild.id,
                    )

        # M 10.16: durante un raid niente DM di benvenuto (non si scrive agli
        # account entrati nel raid).
        if config.welcome_dm and not raid_in_corso(member.guild.id):
            try:
                await member.send(testo, allowed_mentions=menzioni_ammesse(False))
            except discord.HTTPException:
                pass  # DM chiusi: non è un errore da segnalare, è normale

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if member.bot:
            return
        if not await db.is_module_active_for_guild(member.guild.id, MODULE_GREETINGS):
            return

        config = await greetings_repo.get_config(member.guild.id)
        if not config.goodbye_enabled or config.goodbye_channel_id is None:
            return

        channel = member.guild.get_channel(config.goodbye_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        testo = taglia_messaggio(_render_for_member(config.goodbye_message, member))
        try:
            await channel.send(
                testo, allowed_mentions=menzioni_ammesse(config.goodbye_ping_ruoli, [member])
            )
        except discord.HTTPException:
            logger.warning(
                "Impossibile inviare il goodbye message nel server %s.", member.guild.id
            )

    @commands.Cog.listener()
    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        # Rilevamento inizio boost: premium_since passa da None a un
        # timestamp. Non ci interessa il caso opposto (fine boost) né
        # i cambi di ruolo/nickname — quelli sono gestiti da
        # cogs/logging/basic_logs.py, un evento diverso con uno scopo
        # diverso (log, non annuncio).
        if before.premium_since is not None or after.premium_since is None:
            return

        if not await db.is_module_active_for_guild(after.guild.id, MODULE_GREETINGS):
            return

        config = await greetings_repo.get_config(after.guild.id)
        if not config.boost_enabled or config.boost_channel_id is None:
            return

        channel = after.guild.get_channel(config.boost_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        testo = taglia_messaggio(_render_for_member(config.boost_message, after))
        try:
            await channel.send(
                testo, allowed_mentions=menzioni_ammesse(config.boost_ping_ruoli, [after])
            )
        except discord.HTTPException:
            logger.warning(
                "Impossibile inviare il boost message nel server %s.", after.guild.id
            )

    # ================================================================
    # Comandi
    # ================================================================

    @comando_di_gruppo(
        "gestione",
        nome="benvenuto",
        descrizione="Configura il messaggio di benvenuto.",
        sottogruppo=_SG_BENVENUTO,
    )
    @app_commands.describe(
        enabled="Attiva o disattiva il welcome message",
        channel="Canale dove pubblicarlo",
        message="Testo del messaggio ({user}, {username}, {server}, {membercount})",
        dm="Manda anche un DM all'utente (se non lo indichi resta com'è)",
    )
    async def welcome_setup(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        channel: discord.TextChannel | None = None,
        message: TestoMessaggio | None = None,
        dm: bool | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        config_attuale = await greetings_repo.get_config(guild.id)
        canale_finale = channel or (
            guild.get_channel(config_attuale.welcome_channel_id)
            if config_attuale.welcome_channel_id
            else None
        )
        if enabled and canale_finale is None:
            await interaction.response.send_message(
                "Specifica un canale per attivare il welcome message.", ephemeral=True
            )
            return

        testo_finale = message or config_attuale.welcome_message
        errore = _errore_lunghezza(guild, testo_finale)
        if errore is not None:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        await greetings_repo.set_welcome(
            guild.id,
            enabled=enabled,
            channel_id=canale_finale.id if canale_finale else 0,
            message=testo_finale,
            dm=config_attuale.welcome_dm if dm is None else dm,
            ping_ruoli=_ping_ruoli_di(interaction),
        )
        await interaction.response.send_message(
            f"Welcome message {'attivato' if enabled else 'disattivato'}.", ephemeral=True
        )

    @comando_di_gruppo(
        "gestione",
        nome="addio",
        descrizione="Configura il messaggio di addio.",
        sottogruppo=_SG_BENVENUTO,
    )
    @app_commands.describe(
        enabled="Attiva o disattiva il goodbye message",
        channel="Canale dove pubblicarlo",
        message="Testo del messaggio ({username}, {server}, {membercount})",
    )
    async def goodbye_setup(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        channel: discord.TextChannel | None = None,
        message: TestoMessaggio | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        config_attuale = await greetings_repo.get_config(guild.id)
        canale_finale = channel or (
            guild.get_channel(config_attuale.goodbye_channel_id)
            if config_attuale.goodbye_channel_id
            else None
        )
        if enabled and canale_finale is None:
            await interaction.response.send_message(
                "Specifica un canale per attivare il goodbye message.", ephemeral=True
            )
            return

        testo_finale = message or config_attuale.goodbye_message
        errore = _errore_lunghezza(guild, testo_finale)
        if errore is not None:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        await greetings_repo.set_goodbye(
            guild.id,
            enabled=enabled,
            channel_id=canale_finale.id if canale_finale else 0,
            message=testo_finale,
            ping_ruoli=_ping_ruoli_di(interaction),
        )
        await interaction.response.send_message(
            f"Goodbye message {'attivato' if enabled else 'disattivato'}.", ephemeral=True
        )

    @comando_di_gruppo(
        "gestione",
        nome="boost",
        descrizione="Configura il messaggio di boost.",
        sottogruppo=_SG_BENVENUTO,
    )
    @app_commands.describe(
        enabled="Attiva o disattiva il boost message",
        channel="Canale dove pubblicarlo",
        message="Testo del messaggio ({user}, {server})",
    )
    async def boost_setup(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        channel: discord.TextChannel | None = None,
        message: TestoMessaggio | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        config_attuale = await greetings_repo.get_config(guild.id)
        canale_finale = channel or (
            guild.get_channel(config_attuale.boost_channel_id)
            if config_attuale.boost_channel_id
            else None
        )
        if enabled and canale_finale is None:
            await interaction.response.send_message(
                "Specifica un canale per attivare il boost message.", ephemeral=True
            )
            return

        testo_finale = message or config_attuale.boost_message
        errore = _errore_lunghezza(guild, testo_finale)
        if errore is not None:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        await greetings_repo.set_boost(
            guild.id,
            enabled=enabled,
            channel_id=canale_finale.id if canale_finale else 0,
            message=testo_finale,
            ping_ruoli=_ping_ruoli_di(interaction),
        )
        await interaction.response.send_message(
            f"Boost message {'attivato' if enabled else 'disattivato'}.", ephemeral=True
        )

    @comando_di_gruppo(
        "gestione",
        nome="anteprima",
        descrizione="Mostra un'anteprima di come apparirebbe un messaggio.",
        sottogruppo=_SG_BENVENUTO,
    )
    @app_commands.describe(kind="Quale messaggio vedere in anteprima")
    @app_commands.choices(
        kind=[
            app_commands.Choice(name="Welcome", value="welcome"),
            app_commands.Choice(name="Goodbye", value="goodbye"),
            app_commands.Choice(name="Boost", value="boost"),
        ]
    )
    async def preview(self, interaction: discord.Interaction, kind: app_commands.Choice[str]) -> None:
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        config = await greetings_repo.get_config(guild.id)
        template = {
            "welcome": config.welcome_message,
            "goodbye": config.goodbye_message,
            "boost": config.boost_message,
        }[kind.value]

        # M 10.2: un testo salvato prima del controllo (o allungato da un
        # cambio di nome del server) non deve far fallire l'anteprima.
        try:
            testo = _render_for_member(template, interaction.user)
        except Exception:
            logger.exception("Anteprima del messaggio non riuscita nel server %s.", guild.id)
            await interaction.response.send_message(
                "Non riesco a mostrare l'anteprima di questo messaggio.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            taglia_messaggio(f"Anteprima:\n\n{testo}"),
            ephemeral=True,
            allowed_mentions=menzioni_ammesse(False),
        )


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_GREETINGS,
            display_name="Greetings",
            category="utility",
            description="Messaggi di benvenuto, addio e boost con segnaposto personalizzabili.",
            premium_capable=False,
        )
    )
    await bot.add_cog(GreetingsCog(bot))
