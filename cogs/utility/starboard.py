"""
cogs/utility/starboard.py
=========================
Starboard (NF-08, SPEC §22.4): un messaggio che riceve abbastanza stelle
viene copiato nel canale "bacheca". Comandi in `/admin-moduli starboard`.
Funzioni coperte: SPEC §22 (NF-08)
"""

from __future__ import annotations

import asyncio
import logging
import time
import weakref

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.i18n import testo_per
from core.premium import PremiumModule, registry
from core.repositories.starboard_repo import starboard_repo
from core.role_menu_logic import valida_emoji
from core.starboard_logic import (
    EMOJI_PREDEFINITA,
    SOGLIA_MAX,
    SOGLIA_MIN,
    SOGLIA_PREDEFINITA,
    conta_stelle,
    POSTI_PER_PAGINA,
    contenuto_bacheca,
    costruisci_embed,
    link_bacheca,
    messaggio_valido_per_auto,
    riga_classifica,
)

logger = logging.getLogger("iyokai.starboard")

MODULE_STARBOARD = "starboard"

_SG_STARBOARD = ("starboard", "Bacheca dei messaggi più votati")
_SG_STELLE = ("stelle", "Bacheca: chi ha più stelle e un messaggio a caso")
_DURATA_CACHE = 60.0  # secondi: la sorgente automatica si controlla a ogni messaggio, la config no
_NESSUNA_MENZIONE = discord.AllowedMentions.none()


class StarboardCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Un blocco per messaggio: due reazioni insieme non pubblicano due volte.
        self._blocchi: "weakref.WeakValueDictionary[int, asyncio.Lock]" = weakref.WeakValueDictionary()
        # server -> (scadenza, canale sorgente o None): si riempie solo dopo una lettura riuscita
        self._cache_auto: dict[int, tuple[float, int | None]] = {}

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
        if not self._canale_ammesso(guild, canale, config):
            return

        async with self._blocco(message_id):
            try:
                messaggio = await canale.fetch_message(message_id)
            except discord.HTTPException:
                return
            if messaggio.author.bot and messaggio.author.id == guild.me.id:
                return  # non si mette in bacheca il bot stesso
            stelle = await self._conta(messaggio, config)
            esistente = await starboard_repo.get_post(guild_id, message_id)

            if esistente is not None:
                if esistente.board_message_id is None:
                    return  # lo sta pubblicando un altro processo
                await self._aggiorna_post(guild_id, bacheca, esistente.board_message_id, config, stelle, canale.id, message_id)
                return
            if stelle < config.threshold:
                return
            await self._pubblica(guild_id, bacheca, config, messaggio, stelle, channel_id)

    async def _pubblica(self, guild_id, bacheca, config, messaggio, stelle, channel_id, *, con_stelle: bool = True) -> None:
        """Prenota il posto e manda il messaggio in bacheca. L'invio fallito libera il posto."""
        message_id = messaggio.id
        if not await starboard_repo.claim_post(guild_id, channel_id, message_id, messaggio.author.id):
            return
        testo = contenuto_bacheca(config.emoji, stelle, channel_id) if con_stelle else f"<#{channel_id}>"
        try:
            inviato = await bacheca.send(testo, embed=self._embed(messaggio), allowed_mentions=_NESSUNA_MENZIONE)
        except discord.HTTPException as errore:
            logger.warning("Bacheca %s: invio fallito: %s", config.channel_id, errore)
            await starboard_repo.release_post(guild_id, message_id)
            return
        except BaseException:
            await starboard_repo.release_post(guild_id, message_id)  # errore imprevisto: il posto non resta bloccato
            raise
        await starboard_repo.set_board_message(guild_id, message_id, inviato.id, stelle)

    @staticmethod
    def _canale_ammesso(guild, canale, config) -> bool:
        if isinstance(canale, discord.Thread) and (canale.is_private() or canale.parent is None):
            return False  # i thread privati ereditano i permessi del padre: non si sa chi li vede
        if canale.is_nsfw() and not config.allow_nsfw:
            return False
        pubblico = canale.permissions_for(guild.default_role)
        return bool(pubblico.view_channel and pubblico.read_message_history)  # la bacheca è pubblica

    async def _canale_auto(self, guild_id: int) -> int | None:
        scadenza, valore = self._cache_auto.get(guild_id, (0.0, None))
        adesso = time.monotonic()
        if scadenza > adesso:
            return valore
        config = await starboard_repo.get_config(guild_id)  # se fallisce, la cache non si riempie
        valore = config.canale_auto if config is not None and config.enabled else None
        self._cache_auto[guild_id] = (adesso + _DURATA_CACHE, valore)
        return valore

    @commands.Cog.listener()
    async def on_message(self, messaggio: discord.Message) -> None:
        """Canale sorgente: ogni messaggio vero finisce in bacheca, senza contare le stelle."""
        if messaggio.guild is None or not messaggio_valido_per_auto(
            bot=messaggio.author.bot, tipo_sistema=messaggio.type not in (discord.MessageType.default, discord.MessageType.reply)
        ):
            return
        if await self._canale_auto(messaggio.guild.id) != messaggio.channel.id:
            return
        if not await db.is_module_active_for_guild(messaggio.guild.id, MODULE_STARBOARD):
            return
        config = await starboard_repo.get_config(messaggio.guild.id)
        bacheca = messaggio.guild.get_channel(config.channel_id) if config else None
        if config is None or not config.enabled or not isinstance(bacheca, discord.TextChannel):
            return
        if not self._canale_ammesso(messaggio.guild, messaggio.channel, config):
            return
        async with self._blocco(messaggio.id):
            await self._pubblica(messaggio.guild.id, bacheca, config, messaggio, 0, messaggio.channel.id, con_stelle=False)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, canale: discord.abc.GuildChannel) -> None:
        self._cache_auto.pop(canale.guild.id, None)
        try:
            await starboard_repo.togli_canale(canale.guild.id, canale.id)
        except Exception:
            logger.exception("Bacheca: pulizia del canale %s fallita", canale.id)

    async def _conta(self, messaggio: discord.Message, config) -> int:
        for reazione in messaggio.reactions:
            if str(reazione.emoji) == config.emoji:
                utenti = [u async for u in reazione.users(limit=100)]
                return conta_stelle(utenti, messaggio.author.id, config.self_star)
        return 0

    async def _aggiorna_post(self, guild_id, bacheca, board_id, config, stelle, channel_id, message_id) -> None:
        try:
            post = await bacheca.fetch_message(board_id)
            await post.edit(content=contenuto_bacheca(config.emoji, stelle, channel_id), allowed_mentions=_NESSUNA_MENZIONE)
        except discord.NotFound:
            return  # cancellato a mano dallo staff: non si ripubblica
        except discord.HTTPException as errore:
            logger.warning("Bacheca %s: aggiornamento fallito: %s", bacheca.id, errore)
            return
        await starboard_repo.set_board_message(guild_id, message_id, board_id, stelle)

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
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_STARBOARD):
            await interaction.response.send_message(
                await testo_per(interaction, "ping_questo_modulo_non_attivo_su"),
                ephemeral=True,
            )
            return False
        return True

    @comando_di_gruppo(
        "admin-moduli",
        nome="imposta",
        descrizione="Scegli il canale della bacheca e la soglia di stelle.",
        sottogruppo=_SG_STARBOARD,
    )
    @app_commands.describe(
        canale="Il canale dove finiscono i messaggi più votati",
        soglia="Quante stelle servono (predefinito 3)",
        emoji="L'emoji da contare (predefinita ⭐)",
        nsfw="Includere anche i canali vietati ai minori? (non cambia se vuoto)",
        voto_autore="Conta anche la stella dell'autore? (non cambia se vuoto)",
        blocca="Solo il bot scrive nella bacheca? (non cambia se vuoto)",
        canale_auto="Ogni messaggio di questo canale va in bacheca, senza stelle",
        senza_auto="Spegni il canale che manda tutto in bacheca",
    )
    async def imposta(
        self,
        interaction: discord.Interaction,
        canale: discord.TextChannel,
        soglia: app_commands.Range[int, SOGLIA_MIN, SOGLIA_MAX] = SOGLIA_PREDEFINITA,
        emoji: app_commands.Range[str, 1, 64] = EMOJI_PREDEFINITA,
        nsfw: bool | None = None,
        voto_autore: bool | None = None,
        blocca: bool | None = None,
        canale_auto: discord.TextChannel | None = None,
        senza_auto: bool = False,
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return
        if not valida_emoji(emoji):
            await interaction.response.send_message(
                await testo_per(interaction, "starboard_emoji_non_valida_serve_una"), ephemeral=True
            )
            return
        permessi = canale.permissions_for(interaction.guild.me)
        if not (permessi.send_messages and permessi.embed_links):
            await interaction.response.send_message(
                await testo_per(interaction, "starboard_nel_canale_al_bot_servono", mention=canale.mention),
                ephemeral=True,
                allowed_mentions=_NESSUNA_MENZIONE,
            )
            return
        if canale_auto is not None and canale_auto.id == canale.id:
            await interaction.response.send_message(
                await testo_per(interaction, "starboard_auto_uguale_bacheca"), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        await starboard_repo.set_config(
            interaction.guild.id, canale.id, soglia, emoji, allow_nsfw=nsfw, self_star=voto_autore
        )
        await starboard_repo.set_opzioni(
            interaction.guild.id, blocca=blocca,
            canale_auto=canale_auto.id if canale_auto else None, togli_auto=senza_auto and canale_auto is None,
        )
        self._cache_auto.pop(interaction.guild.id, None)
        salvata = await starboard_repo.get_config(interaction.guild.id)
        righe = [
            f"Bacheca attiva in {canale.mention}: servono {soglia} {emoji}. "
            + ("I canali vietati ai minori sono inclusi." if salvata.allow_nsfw else "I canali vietati ai minori sono esclusi.")
        ]
        if blocca is not None:
            righe.append(await self._applica_blocco(interaction, canale, blocca))
        if salvata.canale_auto:
            righe.append(await testo_per(interaction, "starboard_auto_attivo", canale=f"<#{salvata.canale_auto}>"))
        await interaction.followup.send("\n".join(righe), ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE)

    async def _applica_blocco(self, interaction: discord.Interaction, canale: discord.TextChannel, blocca: bool) -> str:
        """Nega (o ridà) `send_messages` a @everyone nella bacheca; il bot si tiene il suo permesso."""
        guild = interaction.guild
        if not canale.permissions_for(guild.me).manage_roles:
            return await testo_per(interaction, "starboard_blocca_manca_permesso", mention=canale.mention)
        try:
            if blocca:
                await canale.set_permissions(guild.me, send_messages=True, embed_links=True, reason="Bacheca bloccata")
                await canale.set_permissions(
                    guild.default_role, send_messages=False, send_messages_in_threads=False,
                    create_public_threads=False, reason="Bacheca bloccata",
                )
            else:
                await canale.set_permissions(
                    guild.default_role, send_messages=None, send_messages_in_threads=None,
                    create_public_threads=None, reason="Bacheca sbloccata",
                )
        except discord.HTTPException:
            return await testo_per(interaction, "starboard_blocca_fallito", mention=canale.mention)
        return await testo_per(interaction, "starboard_bloccata" if blocca else "starboard_sbloccata")

    @comando_di_gruppo(
        "admin-moduli",
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
            testo = "La bacheca non è ancora impostata: usa prima `/admin-moduli starboard imposta`."
        await interaction.response.send_message(testo, ephemeral=True)

    @comando_di_gruppo(
        "admin-moduli",
        nome="disattiva",
        descrizione="Spegni la bacheca.",
        sottogruppo=_SG_STARBOARD,
    )
    async def disattiva(self, interaction: discord.Interaction) -> None:
        if not await self._modulo_attivo(interaction):
            return
        spenta = await starboard_repo.disable(interaction.guild.id)
        await interaction.response.send_message(
            await testo_per(interaction, "starboard_bacheca_spenta") if spenta else await testo_per(interaction, "starboard_la_bacheca_non_era_impostata"), ephemeral=True
        )

    # ================================================================
    # /level stelle
    # ================================================================
    @comando_di_gruppo(
        "level",
        nome="classifica",
        descrizione="Chi ha ricevuto più stelle in bacheca.",
        sottogruppo=_SG_STELLE,
    )
    @app_commands.describe(pagina="Pagina della classifica (10 membri per pagina)")
    async def stelle_classifica(
        self, interaction: discord.Interaction, pagina: app_commands.Range[int, 1, 100] = 1
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return
        await interaction.response.defer()
        guild_id = interaction.guild.id
        totale = await starboard_repo.conta_autori(guild_id)
        if totale == 0:
            await interaction.followup.send(await testo_per(interaction, "starboard_bacheca_vuota", pubblica=True))
            return
        pagine = (totale + POSTI_PER_PAGINA - 1) // POSTI_PER_PAGINA
        pagina = min(pagina, pagine)
        scarto = (pagina - 1) * POSTI_PER_PAGINA
        config = await starboard_repo.get_config(guild_id)
        emoji = config.emoji if config else EMOJI_PREDEFINITA
        autori = await starboard_repo.classifica_autori(guild_id, POSTI_PER_PAGINA, scarto)
        righe = [riga_classifica(scarto + i, a.author_id, a.stelle, a.messaggi, emoji) for i, a in enumerate(autori, 1)]
        embed = discord.Embed(
            title=await testo_per(interaction, "starboard_classifica_titolo", pubblica=True),
            description="\n".join(righe), color=0xFFAC33,
        )
        embed.set_footer(text=await testo_per(interaction, "starboard_classifica_piede", pubblica=True, pagina=pagina, pagine=pagine))
        await interaction.followup.send(embed=embed, allowed_mentions=_NESSUNA_MENZIONE)

    @comando_di_gruppo(
        "level",
        nome="caso",
        descrizione="Un messaggio a caso dalla bacheca.",
        sottogruppo=_SG_STELLE,
    )
    async def stelle_caso(self, interaction: discord.Interaction) -> None:
        if not await self._modulo_attivo(interaction):
            return
        config = await starboard_repo.get_config(interaction.guild.id)
        post = await starboard_repo.post_a_caso(interaction.guild.id) if config else None
        if post is None:
            await interaction.response.send_message(await testo_per(interaction, "starboard_bacheca_vuota", pubblica=True))
            return
        await interaction.response.send_message(
            link_bacheca(interaction.guild.id, config.channel_id, post.board_message_id),
            allowed_mentions=_NESSUNA_MENZIONE,
        )


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_STARBOARD,
            display_name="Starboard",
            category="community",
            description="Bacheca dei messaggi che ricevono abbastanza stelle.",
            premium_capable=False,
        )
    )
    await bot.add_cog(StarboardCog(bot))
