"""
cogs/ai/moderazione.py
======================
Aiuto alla moderazione: nei canali scelti con `/ai moderazione` l'AI legge i
messaggi nuovi e segnala allo staff quelli sospetti (motivo e gravità), nel
canale delle segnalazioni AI (router, tipo "ai"; senza scelta: il canale dei
log). L'AI non punisce: lo staff decide.
Funzioni coperte: SPEC §25.17, §25.37 (AI-R-015, AI-R-039; catalogo AI-018)
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

import discord
from discord.ext import commands

import core.channel_router as router
from cogs.ai._comune import NESSUNA_MENZIONE, registra_modulo_ai, taglia
from core.ai_servizio import AINonDisponibile, RichiestaAI, servizio_ai
from core.ai_testi_logic import ISTRUZIONI, leggi_giudizio
from core.database import db
from core.repositories.ai_repo import ConfigAI, ai_repo

logger = logging.getLogger("iyokai.ai_moderazione")

CONTROLLI_AL_MINUTO = 20
DURATA_CONFIG = 60
GRAVITA_MINIMA = 2


class AiModerazioneCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._config: dict[int, tuple[float, ConfigAI]] = {}
        self._controlli: dict[int, deque[float]] = defaultdict(deque)

    async def _cfg(self, guild_id: int) -> ConfigAI:
        ora = time.monotonic()
        salvata = self._config.get(guild_id)
        if salvata is None or salvata[0] < ora:
            salvata = (ora + DURATA_CONFIG, await ai_repo.get_config(guild_id))
            self._config[guild_id] = salvata
        return salvata[1]

    def _sotto_il_tetto(self, guild_id: int) -> bool:
        ora = time.monotonic()
        coda = self._controlli[guild_id]
        while coda and coda[0] < ora - 60:
            coda.popleft()
        if len(coda) >= CONTROLLI_AL_MINUTO:
            return False
        coda.append(ora)
        return True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot or len(message.content or "") < 5:
            return
        if not servizio_ai().configurato:
            return
        cfg = await self._cfg(message.guild.id)
        if not cfg.attivo or message.channel.id not in cfg.moderazione_canali:
            return
        if not self._sotto_il_tetto(message.guild.id):
            return
        try:
            risposta = await servizio_ai().richiedi(RichiestaAI(
                user_id=message.author.id, funzione="moderazione", tipo="giudizio", testo=message.content[:2000],
                guild_id=message.guild.id, channel_id=message.channel.id, fascia="media",
                istruzioni=ISTRUZIONI["moderazione"], messaggi_utenti=True,
            ))
        except AINonDisponibile:
            return
        giudizio = leggi_giudizio(risposta.testo)
        if giudizio is None or not giudizio.violazione or giudizio.gravita < GRAVITA_MINIMA:
            return
        await self._segnala(message, giudizio)

    async def _segnala(self, message: discord.Message, giudizio) -> None:
        predefinito = await db.get_guild_setting(message.guild.id, router.SETTING_LOG_CHANNEL)
        dest = await router.destinazione(message.guild, router.TIPO_AI, predefinito)
        if dest is None:
            return
        embed = discord.Embed(
            title=f"Messaggio segnalato dall'AI (gravità {giudizio.gravita}/5)",
            description=taglia(message.content, 1000), color=discord.Color.orange(),
        )
        embed.add_field(name="Autore", value=f"{message.author.mention} ({message.author.id})")
        embed.add_field(name="Canale", value=message.channel.mention)
        embed.add_field(name="Motivo", value=taglia(giudizio.motivo or "-", 300), inline=False)
        embed.add_field(name="Messaggio", value=f"[Vai al messaggio]({message.jump_url})", inline=False)
        embed.set_footer(text="L'AI propone, lo staff decide: nessuna azione è stata presa.")
        await router.invia_a(dest, message.guild, router.TIPO_AI, embed=embed, allowed_mentions=NESSUNA_MENZIONE)


async def setup(bot: commands.Bot) -> None:
    registra_modulo_ai()
    await bot.add_cog(AiModerazioneCog(bot))
