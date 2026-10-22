"""
cogs/moderation/channel_control.py
=====================================
Comandi di controllo sul canale: /mod lock, /mod unlock, /mod slowmode. Modulo
SEMPRE GRATUITO (MODULE_CHANNEL_CONTROL, premium_capable=False), come
da schema ("Lock/Unlock" e "Slowmode" sono [Free]). Ogni comando scrive
una riga nel log di moderazione (M 1.8); il motivo del lock è al massimo
512 caratteri (registro di Discord). Lock a tempo (MOD-090): lo sblocco è
un'azione dello scheduler, che sopravvive al riavvio e rimette il permesso
di prima; un unlock a mano o un nuovo lock la annullano.
Funzioni coperte: SPEC §5.5, §5.10
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo

from core.premium import PremiumModule, registry
from core.scheduler import in_seconds, scheduler
from cogs.moderation._shared import (
    MODULE_CHANNEL_CONTROL,
    Reason,
    ensure_module_enabled,
    format_duration,
    parse_duration,
    post_to_mod_log,
)

# Sblocco pianificato di un lock a tempo. Nella riga dello scheduler
# `user_id` porta l'ID del CANALE (una sola attesa per canale).
SCHEDULED_CHANNEL_UNLOCK = "channel_unlock"
# Un lock a tempo dura al massimo 30 giorni: oltre, si usa il lock normale.
MAX_LOCK_SECONDS = 30 * 86400

# Limite reale di Discord per lo slowmode: 6 ore (21600 secondi). Lo
# controlliamo prima di chiamare l'API per dare un errore chiaro
# invece di un 400 generico.
MAX_SLOWMODE_SECONDS = 21600


async def _log(interaction: discord.Interaction, embed: discord.Embed) -> None:
    """Riga nel log di moderazione, con chi ha dato il comando (M 1.8)."""
    copia = embed.copy()
    copia.add_field(name="Moderatore", value=interaction.user.mention, inline=True)
    await post_to_mod_log(interaction.guild, copia)


def _permesso_sbloccato(prima: bool | None) -> bool | None:
    """Il permesso di scrivere dopo uno sblocco: «sì» se c'era, altrimenti ereditato."""
    return True if prima is True else None


async def _sblocco_in_attesa(guild_id: int, channel_id: int) -> dict | None:
    """Lo sblocco pianificato di questo canale, se c'è."""
    for azione in await scheduler.list_pending_for_guild(guild_id, SCHEDULED_CHANNEL_UNLOCK, 100):
        if azione["user_id"] == channel_id:
            return azione
    return None


class ModerationChannelControlCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def handle_unlock(self, guild_id: int, channel_id: int, payload: dict) -> None:
        """
        Fine di un lock a tempo. Rimette il permesso di prima solo se il
        canale è ancora bloccato: se qualcuno l'ha già cambiato a mano,
        non si tocca. Canale o server spariti: niente da fare.
        """
        guild = self.bot.get_guild(guild_id)
        canale = guild.get_channel(channel_id) if guild is not None else None
        if not isinstance(canale, discord.TextChannel):
            return
        everyone = guild.default_role
        overwrite = canale.overwrites_for(everyone)
        if overwrite.send_messages is not False:
            return
        # Come unlock: un «no» di prima (lock senza durata, poi lock a tempo)
        # non si rimette, se no il canale resterebbe bloccato.
        overwrite.send_messages = _permesso_sbloccato(payload.get("prima"))
        await canale.set_permissions(everyone, overwrite=overwrite, reason="Fine del lock a tempo")
        embed = discord.Embed(
            title="🔓 Canale sbloccato",
            description=f"{canale.mention}: è finito il lock a tempo.",
            color=discord.Color.green(),
        )
        await post_to_mod_log(guild, embed)

    @comando_di_gruppo(
        "mod",
        nome="lock",
        descrizione="Blocca la possibilità di scrivere in un canale.",
    )
    @app_commands.describe(
        channel="Il canale da bloccare (default: quello attuale)",
        reason="Motivo del blocco",
        durata="Si sblocca da solo dopo, es. 30m, 2h, 1d (max 30 giorni). Vuoto: finché non lo sblocchi",
    )
    async def lock(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        reason: Reason | None = None,
        durata: app_commands.Range[str, 1, 20] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CHANNEL_CONTROL):
            return

        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message(
                "Questo comando funziona solo su canali testuali.", ephemeral=True
            )
            return

        secondi = None
        if durata is not None:
            try:
                secondi = parse_duration(durata)
            except ValueError as exc:
                await interaction.response.send_message(str(exc), ephemeral=True)
                return
            if secondi > MAX_LOCK_SECONDS:
                await interaction.response.send_message(
                    "Un lock a tempo dura al massimo 30 giorni.", ephemeral=True
                )
                return

        everyone = interaction.guild.default_role
        overwrite = target.overwrites_for(everyone)
        prima = overwrite.send_messages
        overwrite.send_messages = False

        try:
            await target.set_permissions(
                everyone, overwrite=overwrite, reason=reason or "Canale bloccato"
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                "Non ho i permessi per modificare questo canale.", ephemeral=True
            )
            return

        # Un lock nuovo sostituisce lo sblocco pianificato di prima.
        attesa = await _sblocco_in_attesa(interaction.guild.id, target.id)
        await scheduler.cancel_for_user(interaction.guild.id, target.id, SCHEDULED_CHANNEL_UNLOCK)
        if attesa is not None:
            prima = attesa["payload"].get("prima")  # il permesso vero è quello di prima del primo lock
        descrizione = f"{target.mention} è stato bloccato."
        if secondi is not None:
            fine = in_seconds(secondi)
            await scheduler.schedule(
                guild_id=interaction.guild.id,
                user_id=target.id,
                action_type=SCHEDULED_CHANNEL_UNLOCK,
                execute_at=fine,
                payload={"prima": prima},
            )
            descrizione += (
                f" Si sblocca da solo {discord.utils.format_dt(fine, 'R')} ({format_duration(secondi)})."
            )

        embed = discord.Embed(
            title="🔒 Canale bloccato",
            description=descrizione,
            color=discord.Color.red(),
        )
        if reason:
            embed.add_field(name="Motivo", value=reason)
        await interaction.response.send_message(embed=embed)
        await _log(interaction, embed)

    @comando_di_gruppo(
        "mod",
        nome="unlock",
        descrizione="Sblocca la possibilità di scrivere in un canale.",
    )
    @app_commands.describe(channel="Il canale da sbloccare (default: quello attuale)")
    async def unlock(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CHANNEL_CONTROL):
            return

        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message(
                "Questo comando funziona solo su canali testuali.", ephemeral=True
            )
            return

        everyone = interaction.guild.default_role
        overwrite = target.overwrites_for(everyone)
        # None invece di True: ripristina il comportamento ereditato
        # dalla categoria/dai permessi di ruolo, invece di imporre
        # esplicitamente "può scrivere" (che potrebbe sovrascrivere
        # una restrizione voluta a un livello superiore). Se c'era un
        # lock a tempo, si rimette il permesso di prima.
        # Un «no» esplicito di prima non si rimette: unlock deve sbloccare.
        attesa = await _sblocco_in_attesa(interaction.guild.id, target.id)
        prima = attesa["payload"].get("prima") if attesa else None
        overwrite.send_messages = _permesso_sbloccato(prima)

        try:
            await target.set_permissions(
                everyone, overwrite=overwrite, reason="Canale sbloccato"
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                "Non ho i permessi per modificare questo canale.", ephemeral=True
            )
            return

        await scheduler.cancel_for_user(interaction.guild.id, target.id, SCHEDULED_CHANNEL_UNLOCK)

        embed = discord.Embed(
            title="🔓 Canale sbloccato",
            description=f"{target.mention} è stato sbloccato.",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)
        await _log(interaction, embed)

    @comando_di_gruppo(
        "mod",
        nome="slowmode",
        descrizione="Imposta lo slowmode su un canale.",
    )
    @app_commands.describe(
        seconds="Secondi di attesa tra un messaggio e l'altro (0 per disattivare, max 21600)",
        channel="Il canale su cui applicare lo slowmode (default: quello attuale)",
    )
    async def slowmode(
        self,
        interaction: discord.Interaction,
        seconds: app_commands.Range[int, 0, MAX_SLOWMODE_SECONDS],
        channel: discord.TextChannel | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CHANNEL_CONTROL):
            return

        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message(
                "Questo comando funziona solo su canali testuali.", ephemeral=True
            )
            return

        try:
            await target.edit(slowmode_delay=seconds)
        except discord.HTTPException:
            await interaction.response.send_message(
                "Non ho i permessi per modificare questo canale.", ephemeral=True
            )
            return

        if seconds == 0:
            messaggio = f"Slowmode disattivato in {target.mention}."
        else:
            messaggio = f"Slowmode impostato a {seconds}s in {target.mention}."
        await interaction.response.send_message(messaggio)
        embed = discord.Embed(title="🐌 Slowmode", description=messaggio, color=discord.Color.blurple())
        await _log(interaction, embed)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_CHANNEL_CONTROL,
            display_name="Moderazione — Controllo canale",
            category="moderation",
            description="Lock, unlock, slowmode.",
            premium_capable=False,
        )
    )
    cog = ModerationChannelControlCog(bot)
    await bot.add_cog(cog)
    scheduler.register_handler(SCHEDULED_CHANNEL_UNLOCK, cog.handle_unlock)
