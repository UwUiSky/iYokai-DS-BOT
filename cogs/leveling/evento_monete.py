"""
cogs/leveling/evento_monete.py
==============================
Evento di monete: lo staff lo avvia in un canale (/admin-giochi evento avvia) e lo chiude
(/admin-giochi evento chiudi); chi scrive nel canale riceve monete, con una pausa per persona e un
tetto di monete distribuite che chiude l'evento da solo.
Funzioni coperte: ECO-057
Dipende da: core/repositories/economia_repo.py
"""

from __future__ import annotations

import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

from cogs.leveling.leveling import _comando_rifiutato
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.i18n import testo_per
from core.repositories.economia_repo import economia_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo

logger = logging.getLogger("iyokai.leveling.evento")
PAUSA_PER_PERSONA = 30  # secondi: chi scrive di più non guadagna di più
_SG = ("evento", "Evento di monete in un canale")


class EventoMoneteCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._ultimo: dict[tuple[int, int], float] = {}
        self._canali: dict[int, int | None] = {}  # server -> canale dell'evento attivo (None = nessuno); copia veloce

    def cog_unload(self) -> None:
        togli_comandi_del_cog(self)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot or message.type not in (
            discord.MessageType.default, discord.MessageType.reply
        ):
            return
        guild_id = message.guild.id
        if guild_id not in self._canali:
            try:
                evento = await economia_repo.evento_attivo(guild_id)
            except Exception:
                return
            self._canali[guild_id] = evento["channel_id"] if evento else None
        if self._canali[guild_id] != message.channel.id:
            return
        chiave = (guild_id, message.author.id)
        adesso = time.monotonic()
        if adesso - self._ultimo.get(chiave, -1e9) < PAUSA_PER_PERSONA:
            return
        self._ultimo[chiave] = adesso
        try:
            dato = await economia_repo.premia_messaggio(guild_id, message.channel.id, message.author.id)
        except Exception:
            logger.warning("Evento: monete non date (server %s)", guild_id, exc_info=True)
            return
        if dato == 0:  # tetto raggiunto o evento chiuso
            self._canali[guild_id] = None
            self._ultimo.clear()

    @comando_di_gruppo("admin-giochi", nome="avvia", descrizione="Avvia l'evento: chi scrive nel canale riceve monete.", sottogruppo=_SG)
    @app_commands.describe(
        canale="Dove si scrive", monete="Monete per ogni messaggio (1-1000)", tetto="Monete totali da distribuire (massimo 1000000)"
    )
    async def avvia(
        self,
        interaction: discord.Interaction,
        canale: discord.TextChannel,
        monete: app_commands.Range[int, 1, 1000],
        tetto: app_commands.Range[int, 1, 1_000_000],
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        if tetto < monete:
            await interaction.response.send_message(await testo_per(interaction, "evt_tetto_basso"), ephemeral=True)
            return
        eid = await economia_repo.avvia_evento(interaction.guild.id, canale.id, monete, tetto, interaction.user.id)
        if eid is None:
            await interaction.response.send_message(await testo_per(interaction, "evt_gia_attivo"), ephemeral=True)
            return
        self._canali[interaction.guild.id] = canale.id
        moneta = (await leveling_settings_repo.get_config(interaction.guild.id)).impostazioni.currency_name
        logger.info("Evento di monete: server %s, staff %s, canale %s, %s per messaggio, tetto %s.", interaction.guild.id, interaction.user.id, canale.id, monete, tetto)
        await interaction.response.send_message(
            await testo_per(interaction, "evt_avviato", canale=canale.mention, monete=monete, moneta=moneta, tetto=tetto, pubblica=True),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @comando_di_gruppo("admin-giochi", nome="chiudi", descrizione="Chiudi l'evento di monete in corso.", sottogruppo=_SG)
    async def chiudi(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        esito = await economia_repo.chiudi_evento(interaction.guild.id)
        self._canali[interaction.guild.id] = None
        if esito is None:
            await interaction.response.send_message(await testo_per(interaction, "evt_nessuno"), ephemeral=True)
            return
        await interaction.response.send_message(
            await testo_per(interaction, "evt_chiuso", dato=esito[0], tetto=esito[1], pubblica=True)
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EventoMoneteCog(bot))
