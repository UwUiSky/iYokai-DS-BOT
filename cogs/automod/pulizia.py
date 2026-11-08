"""
cogs/automod/pulizia.py
=======================
Pulizia di un canale a intervalli (AMD-073) per tipo di messaggio (AMD-074): comando `/admin-automod pulizia`,
ciclo ogni 5 minuti che fa i giri dovuti (al massimo 10 canali per ciclo) e uscita della riga quando il canale
viene cancellato. Dopo tre rifiuti 403 la pulizia si spegne e lo staff è avvisato una volta.
Funzioni coperte: SPEC §6 (AMD-073, 074), D63
Dipende da: core/automod_pulizia.py, core/automod_pulizia_service.py
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.automod.automod import MODULE_AUTOMOD
from cogs.moderation._shared import ensure_module_enabled
from core import automod_pulizia_logic as lg
from core import automod_pulizia_service as servizio
from core import channel_router as router
from core.automod_pulizia import pulisci
from core.bot_ready import attendi_bot_pronto
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.i18n import testo_guild, testo_per
from core.repositories.automod_pulizie_repo import Pulizia, automod_pulizie_repo

logger = logging.getLogger("iyokai.automod.pulizia")

TIPI = [app_commands.Choice(name=n, value=n) for n in lg.TIPI]


class PuliziaAutomodCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        await super().cog_load()  # registra i comandi del gruppo
        self._ciclo.start()

    async def cog_unload(self) -> None:
        self._ciclo.cancel()
        await super().cog_unload()

    @tasks.loop(minutes=5)
    async def _ciclo(self) -> None:
        try:
            await self.giro()
        except Exception:  # noqa: BLE001
            logger.warning("Giro di pulizia dei canali non riuscito.", exc_info=True)

    @_ciclo.before_loop
    async def _prima(self) -> None:
        await attendi_bot_pronto(self.bot)

    async def giro(self) -> int:
        """Le pulizie dovute, al massimo MAX_CANALI_PER_CICLO. Restituisce quanti canali ha pulito."""
        fatti = 0
        for p in await automod_pulizie_repo.riserva_dovute(lg.MAX_CANALI_PER_CICLO):
            canale = self.bot.get_channel(p.canale_id)
            if not isinstance(canale, discord.TextChannel) or canale.guild.id != p.guild_id:
                continue  # non in cache: se il canale è stato cancellato lo toglie on_guild_channel_delete
            if not await db.is_module_active_for_guild(p.guild_id, MODULE_AUTOMOD):
                continue
            try:
                esito = await pulisci(canale, p)
            except Exception:  # noqa: BLE001 — il giro degli altri canali è già segnato: non va perso
                logger.warning("Pulizia %s/%s non riuscita.", p.guild_id, p.canale_id, exc_info=True)
                continue
            fatti += 1
            if esito.fermo:
                await automod_pulizie_repo.spegni(p.guild_id, p.canale_id)
                logger.warning("Pulizia %s/%s spenta: tre rifiuti 403.", p.guild_id, p.canale_id)
                await self._avvisa(canale, "ampulizia_fermata")
            elif esito.senza_permessi:
                logger.info("Pulizia %s/%s: mancano i permessi nel canale.", p.guild_id, p.canale_id)
        return fatti

    async def _avvisa(self, canale: discord.TextChannel, chiave: str) -> None:
        try:
            destinazione = await router.destinazione(canale.guild, router.TIPO_AUTOMOD, None)
            if destinazione is not None:
                await destinazione.send(await testo_guild(canale.guild, chiave, canale=canale.mention),
                                        allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            logger.info("Staff non avvisato della pulizia ferma in %s.", canale.id)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        await servizio.canale_cancellato(channel.guild.id, channel.id)

    @comando_di_gruppo(
        "admin-automod", nome="pulizia", descrizione="Pulisce un canale ogni tanto, per tipo di messaggio."
    )
    @app_commands.describe(
        canale="Il canale da pulire", ogni="Ogni quanto, da 1h a 30d (per esempio 6h, 2d, 1h30m)",
        tipo="Quali messaggi cancellare", fissati="Cancella anche i messaggi fissati (di base restano)",
        attiva="Accesa o spenta", rimuovi="Toglie la pulizia di questo canale",
    )
    @app_commands.choices(tipo=TIPI)
    async def pulizia(
        self, interaction: discord.Interaction, canale: discord.TextChannel, ogni: app_commands.Range[str, 2, 10] | None = None,
        tipo: app_commands.Choice[str] | None = None, fissati: bool | None = None, attiva: bool | None = None,
        rimuovi: bool = False,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return
        guild = interaction.guild
        if rimuovi:
            chiave = "ampulizia_tolta" if await servizio.rimuovi(guild.id, canale.id) else "ampulizia_nessuna_riga"
            await interaction.response.send_message(await testo_per(interaction, chiave, canale=canale.mention), ephemeral=True)
            return
        try:
            if ogni is None and tipo is None and fissati is None and attiva is None:
                p = await automod_pulizie_repo.leggi(guild.id, canale.id)
                if p is None:
                    raise lg.PuliziaNonValida("intervallo")
            else:
                p = await servizio.imposta(guild.id, canale.id, ogni=ogni, tipo=tipo.value if tipo else None, fissati=fissati,
                                           attiva=attiva, autore_id=interaction.user.id)
        except lg.PuliziaNonValida:
            await interaction.response.send_message(await testo_per(interaction, "ampulizia_non_valida"), ephemeral=True)
            return
        except servizio.TroppePulizie:
            await interaction.response.send_message(
                await testo_per(interaction, "ampulizia_troppe", massimo=lg.MAX_RIGHE_PER_SERVER), ephemeral=True)
            return
        await interaction.response.send_message(await self._stato(interaction, canale, p), ephemeral=True)

    async def _stato(self, interaction: discord.Interaction, canale: discord.TextChannel, p: Pulizia) -> str:
        si, no = await testo_per(interaction, "amcalore_si"), await testo_per(interaction, "amcalore_no")
        testo = await testo_per(
            interaction, "ampulizia_stato", canale=canale.mention, ogni=lg.scrivi_ogni(p.ogni_secondi), tipo=p.tipo,
            fissati=si if p.fissati else no, stato=await testo_per(interaction, "ampulizia_accesa" if p.attiva else "ampulizia_spenta"))
        perms = canale.permissions_for(interaction.guild.me)
        if not (perms.view_channel and perms.read_message_history and perms.manage_messages):
            testo += "\n" + await testo_per(interaction, "ampulizia_senza_permessi")
        return testo


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PuliziaAutomodCog(bot))
