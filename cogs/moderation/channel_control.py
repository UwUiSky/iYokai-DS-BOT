"""
cogs/moderation/channel_control.py
=====================================
Comandi di controllo sul canale: /mod-canali lock, /mod-canali unlock, /mod-canali slowmode. Modulo
SEMPRE GRATUITO (MODULE_CHANNEL_CONTROL, premium_capable=False), come
da schema ("Lock/Unlock" e "Slowmode" sono [Free]). Ogni comando scrive
una riga nel log di moderazione (M 1.8); il motivo del lock è al massimo
512 caratteri (registro di Discord). Lock a tempo (MOD-090): lo sblocco è
un'azione dello scheduler, che sopravvive al riavvio e rimette il permesso
di prima; un unlock a mano o un nuovo lock la annullano.
Funzioni coperte: SPEC §5.5, §5.10 (MOD-098, 099, 100)
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo

from cogs.leveling._pagine import invia_lista
from core import moderazione_canali_logic as logica
from core.i18n import testo_guild, testo_per
from core.repositories.moderation_repo import moderation_repo
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
PAUSA_CANALI = 0.3  # secondi fra due canali di una categoria
MAX_AVVISI_IN_MEMORIA = 5000
logger = logging.getLogger(__name__)


async def _log(interaction: discord.Interaction, embed: discord.Embed) -> None:
    """Riga nel log di moderazione, con chi ha dato il comando (M 1.8)."""
    copia = embed.copy()
    copia.add_field(name=await testo_per(interaction, "channelcontr_moderatore", pubblica=True), value=interaction.user.mention, inline=True)
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
        # canale -> secondi dello slowmode lungo (riempita alla prima necessità); avvisi già mandati (server, utente) -> istante
        self._lungo: dict[int, int] = {}
        self._lungo_caricato = False
        self._blocco_lunghi = asyncio.Lock()
        self._avvisi: dict[tuple[int, int], float] = {}

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
        "mod-canali",
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
                await testo_per(interaction, "channelcontr_questo_comando_funziona_solo_su"), ephemeral=True
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
                    await testo_per(interaction, "channelcontr_un_lock_tempo_dura_al"), ephemeral=True
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
                await testo_per(interaction, "channelcontr_non_ho_permessi_per_modificare"), ephemeral=True
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
            title=await testo_per(interaction, "channelcontr_canale_bloccato", pubblica=True),
            description=descrizione,
            color=discord.Color.red(),
        )
        if reason:
            embed.add_field(name=await testo_per(interaction, "channelcontr_motivo", pubblica=True), value=reason)
        await interaction.response.send_message(embed=embed)
        await _log(interaction, embed)

    @comando_di_gruppo(
        "mod-canali",
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
                await testo_per(interaction, "channelcontr_questo_comando_funziona_solo_su"), ephemeral=True
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
                await testo_per(interaction, "channelcontr_non_ho_permessi_per_modificare"), ephemeral=True
            )
            return

        await scheduler.cancel_for_user(interaction.guild.id, target.id, SCHEDULED_CHANNEL_UNLOCK)

        embed = discord.Embed(
            title=await testo_per(interaction, "channelcontr_canale_sbloccato", pubblica=True),
            description=await testo_per(interaction, "channelcontr_stato_sbloccato", mention=target.mention, pubblica=True),
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)
        await _log(interaction, embed)

    @comando_di_gruppo(
        "mod-canali",
        nome="slowmode",
        descrizione="Slowmode di un canale o di una categoria. Senza valori: mostra i canali con slowmode.",
    )
    @app_commands.describe(
        seconds="Secondi di attesa tra un messaggio e l'altro (0 per disattivare, max 21600)",
        channel="Il canale su cui applicare lo slowmode (default: quello attuale)",
        categoria="Applica lo slowmode a tutti i canali di testo di questa categoria (al massimo 50)",
        lunga="Slowmode oltre le 6 ore, gestito dal bot (da 7h a 7d, es. 2d)",
    )
    async def slowmode(
        self,
        interaction: discord.Interaction,
        seconds: app_commands.Range[int, 0, MAX_SLOWMODE_SECONDS] | None = None,
        channel: discord.TextChannel | None = None,
        categoria: discord.CategoryChannel | None = None,
        lunga: app_commands.Range[str, 1, 20] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CHANNEL_CONTROL):
            return
        if seconds is None and lunga is None:
            await self._elenco_slowmode(interaction)
            return
        if seconds is not None and lunga is not None:
            await interaction.response.send_message(await testo_per(interaction, "channelcontr_slowmode_due_valori"), ephemeral=True)
            return
        if channel is not None and categoria is not None:
            await interaction.response.send_message(await testo_per(interaction, "channelcontr_slowmode_canale_o_categoria"), ephemeral=True)
            return
        secondi_lungo = None
        if lunga is not None:
            try:
                secondi_lungo = logica.secondi_slowmode_lungo(lunga)
            except ValueError:
                await interaction.response.send_message(await testo_per(interaction, "channelcontr_slowmode_lungo_fuori"), ephemeral=True)
                return

        if categoria is not None:
            canali = logica.canali_della_categoria(categoria)
        else:
            target = channel or interaction.channel
            if not isinstance(target, discord.TextChannel):
                await interaction.response.send_message(
                    await testo_per(interaction, "channelcontr_questo_comando_funziona_solo_su"), ephemeral=True
                )
                return
            canali = [target]
        if not canali:
            await interaction.response.send_message(await testo_per(interaction, "channelcontr_slowmode_categoria_vuota"), ephemeral=True)
            return
        guild = interaction.guild
        if secondi_lungo is not None:
            gia = {c for c, _ in await moderation_repo.list_slowmode_lungo(guild.id)}
            nuovi = [c for c in canali if c.id not in gia]
            if len(gia) + len(nuovi) > logica.MAX_CANALI_LUNGHI:
                await interaction.response.send_message(
                    await testo_per(interaction, "channelcontr_slowmode_troppi_lunghi", v1=logica.MAX_CANALI_LUNGHI), ephemeral=True
                )
                return

        await interaction.response.defer()
        nativo = MAX_SLOWMODE_SECONDS if secondi_lungo is not None else seconds
        fatti = 0
        for canale in canali:
            try:
                await canale.edit(slowmode_delay=nativo)
            except discord.HTTPException:
                continue
            fatti += 1
            if secondi_lungo is not None:
                await moderation_repo.set_slowmode_lungo(guild.id, canale.id, secondi_lungo)
                self._lungo[canale.id] = secondi_lungo
            else:
                await moderation_repo.delete_slowmode_lungo(guild.id, canale.id)
                self._lungo.pop(canale.id, None)
            if len(canali) > 1:
                await asyncio.sleep(PAUSA_CANALI)
        if fatti == 0:
            await interaction.followup.send(await testo_per(interaction, "channelcontr_non_ho_permessi_per_modificare"), ephemeral=True)
            return

        luogo = canali[0].mention if len(canali) == 1 else await testo_per(interaction, "channelcontr_slowmode_n_canali", v1=fatti, pubblica=True)
        if secondi_lungo is not None:
            messaggio = await testo_per(interaction, "channelcontr_slowmode_lungo_ok", durata=format_duration(secondi_lungo), luogo=luogo, pubblica=True)
        elif seconds == 0:
            messaggio = f"Slowmode disattivato in {luogo}."
        else:
            messaggio = f"Slowmode impostato a {seconds}s in {luogo}."
        await interaction.followup.send(messaggio)
        embed = discord.Embed(title=await testo_per(interaction, "channelcontr_slowmode", pubblica=True), description=messaggio, color=discord.Color.blurple())
        await _log(interaction, embed)

    async def _elenco_slowmode(self, interaction: discord.Interaction) -> None:
        """MOD-100: i canali con slowmode, nativo e lungo, a pagine."""
        guild = interaction.guild
        lunghi = dict(await moderation_repo.list_slowmode_lungo(guild.id))
        righe = [f"<#{cid}>: {format_duration(sec)} ({await testo_per(interaction, 'channelcontr_slowmode_gestito_bot')})" for cid, sec in lunghi.items()]
        righe += [
            f"{c.mention}: {format_duration(c.slowmode_delay)}"
            for c in guild.text_channels
            if c.slowmode_delay and c.id not in lunghi
        ]
        if not righe:
            await interaction.response.send_message(await testo_per(interaction, "channelcontr_slowmode_nessuno"), ephemeral=True)
            return
        await invia_lista(
            interaction, await testo_per(interaction, "channelcontr_slowmode_elenco_titolo"), righe,
            discord.Color.blurple(), ephemeral=True,
        )

    async def _carica_lunghi(self) -> None:
        """Riempie la cache una volta; se il database non risponde si riprova al messaggio dopo."""
        if self._lungo_caricato:
            return
        async with self._blocco_lunghi:
            if self._lungo_caricato:
                return
            try:
                self._lungo.update(await moderation_repo.all_slowmode_lungo())
            except Exception:  # noqa: BLE001 - senza tabella o senza database non si ferma la chat
                logger.warning("Slowmode lunghi non letti: riprovo al prossimo messaggio.", exc_info=False)
                return
            self._lungo_caricato = True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """MOD-099: nei canali con slowmode lungo il messaggio arrivato troppo presto si cancella (staff e bot esenti)."""
        if message.guild is None or message.author.bot:
            return
        await self._carica_lunghi()
        secondi = self._lungo.get(message.channel.id)
        if secondi is None:
            return
        permessi = message.author.guild_permissions
        if permessi.administrator or permessi.manage_messages or permessi.manage_channels:
            return
        guild_id, utente = message.guild.id, message.author.id
        adesso = datetime.now(timezone.utc)
        ultimo = await moderation_repo.get_slowmode_ultimo(guild_id, message.channel.id, utente)
        if logica.deve_cancellare(ultimo, adesso, secondi):
            try:
                await message.delete()
            except discord.HTTPException:
                return
            quando = time.monotonic()
            if logica.puo_avvisare(self._avvisi.get((guild_id, utente)), quando):
                self._avvisi[(guild_id, utente)] = quando
                if len(self._avvisi) > MAX_AVVISI_IN_MEMORIA:
                    self._avvisi.clear()
                try:
                    await message.author.send(
                        await testo_guild(message.guild, "channelcontr_slowmode_avviso", canale=message.channel.mention, durata=format_duration(secondi))
                    )
                except discord.HTTPException:
                    pass
            return
        await moderation_repo.set_slowmode_ultimo(guild_id, message.channel.id, utente, adesso)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        """MOD-099: un canale cancellato esce dallo slowmode lungo (altrimenti occupa il tetto e resta nell'elenco)."""
        if channel.id not in self._lungo and self._lungo_caricato:
            return
        await moderation_repo.delete_slowmode_lungo(channel.guild.id, channel.id)
        self._lungo.pop(channel.id, None)


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
