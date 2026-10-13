"""
cogs/utility/starboard.py
=========================
Starboard (NF-08, SPEC §22.4): un messaggio che riceve abbastanza stelle
viene copiato nel canale "bacheca". Comandi in `/moduli starboard`.
Funzioni coperte: SPEC §22 (NF-08)
"""

from __future__ import annotations

import asyncio
import logging
import weakref

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.premium import PremiumModule, registry
from core.repositories.starboard_repo import starboard_repo
from core.role_menu_logic import valida_emoji
from core.starboard_logic import (
    EMOJI_PREDEFINITA,
    SOGLIA_MAX,
    SOGLIA_MIN,
    SOGLIA_PREDEFINITA,
    conta_stelle,
    contenuto_bacheca,
    costruisci_embed,
)

logger = logging.getLogger("iyokai.starboard")

MODULE_STARBOARD = "starboard"

_SG_STARBOARD = ("starboard", "Bacheca dei messaggi più votati")
_NESSUNA_MENZIONE = discord.AllowedMentions.none()


class StarboardCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Un blocco per messaggio: due reazioni insieme non pubblicano due volte.
        self._blocchi: "weakref.WeakValueDictionary[int, asyncio.Lock]" = weakref.WeakValueDictionary()

    def _blocco(self, message_id: int) -> asyncio.Lock:
        blocco = self._blocchi.get(message_id)
        if blocco is None:
            blocco = asyncio.Lock()
            self._blocchi[message_id] = blocco
        return blocco

    # ================================================================
    # Ascolto
    # ================================================================
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        await self._da_evento(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        await self._da_evento(payload)

    async def _da_evento(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None:
            return
        if not await db.is_module_active_for_guild(payload.guild_id, MODULE_STARBOARD):
            return
        config = await starboard_repo.get_config(payload.guild_id)
        if config is None or not config.enabled or str(payload.emoji) != config.emoji:
            return
        await self.aggiorna(payload.guild_id, payload.channel_id, payload.message_id)

    async def aggiorna(self, guild_id: int, channel_id: int, message_id: int) -> None:
        """Conta le stelle del messaggio e pubblica o aggiorna il post in bacheca."""
        config = await starboard_repo.get_config(guild_id)
        if config is None or not config.enabled or channel_id == config.channel_id:
            return
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        canale = guild.get_channel(channel_id) or guild.get_thread(channel_id)
        bacheca = guild.get_channel(config.channel_id)
        if canale is None or not isinstance(bacheca, discord.TextChannel):
            return
        if canale.is_nsfw() and not config.allow_nsfw:
            return
        pubblico = canale.permissions_for(guild.default_role)
        if not (pubblico.view_channel and pubblico.read_message_history):
            return  # la bacheca è pubblica: i canali che @everyone non vede non ci finiscono

        async with self._blocco(message_id):
            try:
                messaggio = await canale.fetch_message(message_id)
            except discord.HTTPException:
                return
            if messaggio.author.bot and messaggio.author.id == guild.me.id:
                return  # non si mette in bacheca il bot stesso
            stelle = await self._conta(messaggio, config)
            esistente = await starboard_repo.get_post(message_id)

            if esistente is not None:
                if esistente.board_message_id is None:
                    return  # lo sta pubblicando un altro processo
                await self._aggiorna_post(bacheca, esistente.board_message_id, config, stelle, canale.id, message_id)
                return
            if stelle < config.threshold:
                return
            if not await starboard_repo.claim_post(guild_id, channel_id, message_id, messaggio.author.id):
                return
            try:
                inviato = await bacheca.send(
                    contenuto_bacheca(config.emoji, stelle, channel_id),
                    embed=self._embed(messaggio),
                    allowed_mentions=_NESSUNA_MENZIONE,
                )
            except discord.HTTPException as errore:
                logger.warning("Bacheca %s: invio fallito: %s", config.channel_id, errore)
                await starboard_repo.release_post(message_id)
                return
            except BaseException:
                await starboard_repo.release_post(message_id)  # errore imprevisto: il posto non resta bloccato
                raise
            await starboard_repo.set_board_message(message_id, inviato.id, stelle)

    async def _conta(self, messaggio: discord.Message, config) -> int:
        for reazione in messaggio.reactions:
            if str(reazione.emoji) == config.emoji:
                utenti = [u async for u in reazione.users(limit=100)]
                return conta_stelle(utenti, messaggio.author.id, config.self_star)
        return 0

    async def _aggiorna_post(self, bacheca, board_id, config, stelle, channel_id, message_id) -> None:
        try:
            post = await bacheca.fetch_message(board_id)
            await post.edit(content=contenuto_bacheca(config.emoji, stelle, channel_id), allowed_mentions=_NESSUNA_MENZIONE)
        except discord.NotFound:
            return  # cancellato a mano dallo staff: non si ripubblica
        except discord.HTTPException as errore:
            logger.warning("Bacheca %s: aggiornamento fallito: %s", bacheca.id, errore)
            return
        await starboard_repo.set_board_message(message_id, board_id, stelle)

    @staticmethod
    def _embed(messaggio: discord.Message) -> discord.Embed:
        immagine = None
        altri: list[str] = []
        for allegato in messaggio.attachments:
            tipo = getattr(allegato, "content_type", None) or ""
            if immagine is None and tipo.startswith("image/"):
                immagine = allegato.url
            else:
                altri.append(allegato.url)
        return costruisci_embed(
            testo=messaggio.content or "",
            nome_autore=messaggio.author.display_name,
            avatar_url=messaggio.author.display_avatar.url,
            link=messaggio.jump_url,
            immagine_url=immagine,
            allegati=altri,
        )

    # ================================================================
    # Comandi
    # ================================================================
    async def _modulo_attivo(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_STARBOARD):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /admin setup attiva.",
                ephemeral=True,
            )
            return False
        return True

    @comando_di_gruppo(
        "moduli",
        nome="imposta",
        descrizione="Scegli il canale della bacheca e la soglia di stelle.",
        sottogruppo=_SG_STARBOARD,
    )
    @app_commands.describe(
        canale="Il canale dove finiscono i messaggi più votati",
        soglia="Quante stelle servono (predefinito 3)",
        emoji="L'emoji da contare (predefinita ⭐)",
    )
    async def imposta(
        self,
        interaction: discord.Interaction,
        canale: discord.TextChannel,
        soglia: app_commands.Range[int, SOGLIA_MIN, SOGLIA_MAX] = SOGLIA_PREDEFINITA,
        emoji: app_commands.Range[str, 1, 64] = EMOJI_PREDEFINITA,
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return
        if not valida_emoji(emoji):
            await interaction.response.send_message(
                "L'emoji non è valida: serve una sola emoji.", ephemeral=True
            )
            return
        permessi = canale.permissions_for(interaction.guild.me)
        if not (permessi.send_messages and permessi.embed_links):
            await interaction.response.send_message(
                f"Nel canale {canale.mention} al bot servono i permessi per scrivere e incorporare link.",
                ephemeral=True,
                allowed_mentions=_NESSUNA_MENZIONE,
            )
            return
        await starboard_repo.set_config(interaction.guild.id, canale.id, soglia, emoji)
        await interaction.response.send_message(
            f"Bacheca attiva in {canale.mention}: servono {soglia} {emoji}. "
            "I canali vietati ai minori sono esclusi.",
            ephemeral=True,
            allowed_mentions=_NESSUNA_MENZIONE,
        )

    @comando_di_gruppo(
        "moduli",
        nome="soglia",
        descrizione="Cambia quante stelle servono per finire in bacheca.",
        sottogruppo=_SG_STARBOARD,
    )
    @app_commands.describe(numero="Stelle necessarie")
    async def soglia(
        self, interaction: discord.Interaction, numero: app_commands.Range[int, SOGLIA_MIN, SOGLIA_MAX]
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return
        if await starboard_repo.set_threshold(interaction.guild.id, numero):
            testo = f"Ora servono {numero} stelle."
        else:
            testo = "La bacheca non è ancora impostata: usa prima `/moduli starboard imposta`."
        await interaction.response.send_message(testo, ephemeral=True)

    @comando_di_gruppo(
        "moduli",
        nome="disattiva",
        descrizione="Spegni la bacheca.",
        sottogruppo=_SG_STARBOARD,
    )
    async def disattiva(self, interaction: discord.Interaction) -> None:
        if not await self._modulo_attivo(interaction):
            return
        spenta = await starboard_repo.disable(interaction.guild.id)
        await interaction.response.send_message(
            "Bacheca spenta." if spenta else "La bacheca non era impostata.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_STARBOARD,
            display_name="Starboard",
            category="utility",
            description="Bacheca dei messaggi che ricevono abbastanza stelle.",
            premium_capable=False,
        )
    )
    await bot.add_cog(StarboardCog(bot))
