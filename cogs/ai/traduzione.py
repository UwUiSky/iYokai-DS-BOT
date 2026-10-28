"""
cogs/ai/traduzione.py
=====================
Traduzione con l'AI: `/utility ai traduci`, traduzione automatica dei canali
scelti con `/ai traduzione`, traduzione quando qualcuno reagisce con la
bandiera di un paese (`/ai funzioni bandiere`). Le traduzioni passano dalla
cache: lo stesso testo non si ritraduce.
Funzioni coperte: SPEC §25.74–§25.81 (i messaggi di fila della stessa persona si traducono insieme, §25.77) (AI-R-081..088; catalogo AI-020, AI-021)

La reazione con la bandiera non porta un'interazione: la traduzione si manda
come risposta al messaggio e si cancella da sola dopo 2 minuti (Discord non
permette un messaggio privato "effimero" fuori da un'interazione).
"""

from __future__ import annotations

import asyncio
import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

from cogs.ai._comune import (
    MODULO_AI, NESSUNA_MENZIONE, SOTTO_AI, chiedi, completa_lingue, registra_modulo_ai, richiesta_da, taglia,
)
from core.ai_servizio import RichiestaAI, servizio_ai
from core.ai_testi_logic import BANDIERE, ISTRUZIONI, LINGUE, nome_lingua, riconosci_lingua
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.premium import requires_module
from core.repositories.ai_repo import ai_repo
from core.traduzione_gruppo_logic import ATTESA_SECONDI, RaccoltaMessaggi

logger = logging.getLogger("iyokai.ai_traduzione")

DURATA_RISPOSTA_BANDIERA = 120
_GIA_TRADOTTI_SECONDI = 600


def istruzioni_traduzione(lingua: str) -> str:
    return f"{ISTRUZIONI['traduci']} Lingua di arrivo: {nome_lingua(lingua)} ({lingua})."


def serve_tradurre(testo: str, lingua: str) -> bool:
    """Niente traduzione per testi vuoti, solo link o emoji, o già nella lingua di arrivo."""
    pulito = testo.strip()
    if len(pulito) < 3 or pulito.startswith(("http://", "https://")):
        return False
    if not any(c.isalpha() for c in pulito):
        return False
    return riconosci_lingua(pulito, predefinita="?") != lingua


class AiTraduzioneCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.canali: dict[int, str] | None = None  # letti dal database al primo messaggio
        self._fatti: dict[tuple[int, str], float] = {}
        self.raccolta = RaccoltaMessaggi()

    async def ricarica_canali(self) -> None:
        try:
            self.canali = await ai_repo.traduzione_canali()
        except Exception:
            self.canali = None
            logger.warning("Canali con traduzione automatica non letti.", exc_info=True)

    def _gia_fatto(self, message_id: int, lingua: str) -> bool:
        ora = time.monotonic()
        self._fatti = {k: v for k, v in self._fatti.items() if v > ora - _GIA_TRADOTTI_SECONDI}
        if (message_id, lingua) in self._fatti:
            return True
        self._fatti[(message_id, lingua)] = ora
        return False

    async def _traduci(
        self, user_id: int, guild_id: int, channel_id: int, testo: str, lingua: str, funzione: str,
        *, conta_utente: bool = True,
    ):
        return await chiedi(RichiestaAI(
            user_id=user_id, funzione=funzione, tipo="traduzione", testo=testo[:3000], guild_id=guild_id,
            channel_id=channel_id, istruzioni=istruzioni_traduzione(lingua), messaggi_utenti=True,
            conta_utente=conta_utente,
        ))

    # ------------------------------------------------------------ comando
    async def _completa(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return completa_lingue(current)

    @comando_di_gruppo("utility", nome="traduci", descrizione="Traduce un testo nella lingua che scegli.", sottogruppo=SOTTO_AI)
    @app_commands.describe(testo="Il testo da tradurre", lingua="Lingua di arrivo")
    @app_commands.autocomplete(lingua=_completa)
    @requires_module(MODULO_AI)
    async def traduci(self, interaction: discord.Interaction, testo: app_commands.Range[str, 1, 1500], lingua: app_commands.Range[str, 2, 5]) -> None:
        if lingua not in LINGUE:
            await interaction.response.send_message("Lingua non riconosciuta: scegli dall'elenco.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        risposta, locale = await chiedi(richiesta_da(
            interaction, "traduci", "traduzione", testo, istruzioni=istruzioni_traduzione(lingua),
        ))
        await interaction.followup.send(
            taglia(risposta.testo, 2000) if risposta else locale, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE
        )

    # ------------------------------------------------------------ automatico
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        if self.canali is None:
            await self.ricarica_canali()
        lingua = (self.canali or {}).get(message.channel.id)
        if lingua is None or message.guild is None or message.author.bot or not message.content:
            return
        if not servizio_ai().configurato:
            return
        # I messaggi di fila della stessa persona si traducono insieme (AI-R-084).
        if self.raccolta.aggiungi(message.channel.id, message.author.id, message.id, message.content):
            await asyncio.sleep(ATTESA_SECONDI)
            await self._traduci_raccolta(message, lingua)

    async def _traduci_raccolta(self, ultimo: discord.Message, lingua: str) -> None:
        chiusa = self.raccolta.chiudi(ultimo.channel.id, ultimo.author.id)
        if chiusa is None:
            return
        ids, testo = chiusa
        if not serve_tradurre(testo, lingua) or all(self._gia_fatto(i, lingua) for i in ids):
            return
        risposta, _ = await self._traduci(
            ultimo.author.id, ultimo.guild.id, ultimo.channel.id, testo, lingua, "traduzione_auto",
            conta_utente=False,  # la chiede il server, non chi scrive
        )
        if risposta is None or not risposta.testo:
            return
        try:
            await ultimo.channel.send(
                taglia(f"🌐 {risposta.testo}", 2000), reference=discord.MessageReference(
                    message_id=ids[0], channel_id=ultimo.channel.id, fail_if_not_exists=False),
                allowed_mentions=NESSUNA_MENZIONE, mention_author=False,
            )
        except discord.HTTPException:
            logger.info("Traduzione automatica non inviata nel canale %s.", ultimo.channel.id)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        lingua = BANDIERE.get(str(payload.emoji))
        if lingua is None or payload.guild_id is None or (payload.member and payload.member.bot):
            return
        if not servizio_ai().configurato:
            return
        cfg = await ai_repo.get_config(payload.guild_id)
        if not (cfg.attivo and cfg.bandiere) or self._gia_fatto(payload.message_id, lingua):
            return
        canale = self.bot.get_channel(payload.channel_id)
        if canale is None:
            return
        try:
            messaggio = await canale.fetch_message(payload.message_id)
        except discord.HTTPException:
            return
        if not messaggio.content:
            return
        risposta, _ = await self._traduci(
            payload.user_id, payload.guild_id, payload.channel_id, messaggio.content, lingua, "traduzione_bandiera"
        )
        if risposta is None or not risposta.testo:
            return
        try:
            await messaggio.reply(
                taglia(f"{payload.emoji} {risposta.testo}", 2000), allowed_mentions=NESSUNA_MENZIONE,
                mention_author=False, delete_after=DURATA_RISPOSTA_BANDIERA,
            )
        except discord.HTTPException:
            logger.info("Traduzione con bandiera non inviata nel canale %s.", payload.channel_id)


async def setup(bot: commands.Bot) -> None:
    registra_modulo_ai()
    await bot.add_cog(AiTraduzioneCog(bot))
