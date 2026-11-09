"""
cogs/utility/conteggio.py
=========================
Gioco del conteggio (NF-40, D69 B14): fino a 10 canali dove si conta a turno 1, 2, 3... anche in binario, in numeri
romani o in lettere; chi sbaglia può restare bloccato per un po'; chi ha contato per ultimo può avere un ruolo.
Comandi: `/admin-giochi conteggio canale|regole` (staff), `/giochi conteggio classifica` (tutti).
Funzioni coperte: SPEC §23.16 (NF-40), catalogo UTL-186, 187, 188, 189, 190, 192
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.channel_access import PERMESSI_DI_REAZIONE, motivo_se_il_bot_non_puo
from core.command_access import Livello, richiedi
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.conteggio_logic import MAX_PUNIZIONE_MINUTI, MODI, leggi_numero, scrivi_numero
from core.database import db
from core.giveaway_logic import motivo_ruolo_non_assegnabile
from core.i18n import lingua_risposta, t, testo_per
from core.repositories.counting_game_repo import NON_CAMBIA, TroppiCanali, counting_game_repo

logger = logging.getLogger("iyokai.conteggio")

MODULE_FUN = "fun"  # il conteggio sta nel modulo «Divertimento»
_SG_ADMIN = ("conteggio", "Gioco del conteggio: canali, regole, traguardi")
_SG_GIOCHI = ("conteggio", "Gioco del conteggio: classifica e avvisi")
_NESSUNA_MENZIONE = discord.AllowedMentions.none()
RIGHE_CLASSIFICA = 10
_SCELTE_AZIONE = [
    app_commands.Choice(name="aggiungi o cambia", value="aggiungi"),
    app_commands.Choice(name="togli", value="togli"),
    app_commands.Choice(name="elenco", value="elenco"),
]


class ConteggioCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _pronto(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_FUN):
            await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
            return False
        return True

    # ================================================================
    # Il gioco
    # ================================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None or message.type not in (discord.MessageType.default, discord.MessageType.reply):
            return
        try:
            cfg = (await counting_game_repo.canali(message.guild.id)).get(message.channel.id)
            if cfg is None:
                return
            modo, filtro = cfg
            numero = leggi_numero(message.content or "", modo, filtro)
            if numero is None:
                return
            if not await db.is_module_active_for_guild(message.guild.id, MODULE_FUN):
                return
            if await counting_game_repo.blocco_attivo(message.guild.id, message.channel.id, message.author.id):
                await self._reagisci(message, "⛔")
                return
            esito = await counting_game_repo.register(message.guild.id, message.channel.id, message.author.id, numero)
        except Exception:
            logger.warning("Conteggio non registrato nel server %s.", message.guild.id, exc_info=True)
            return
        if esito is None:
            return
        await self._dopo_il_numero(message, modo, esito)

    @staticmethod
    async def _reagisci(message: discord.Message, emoji: str) -> None:
        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            pass

    async def _dopo_il_numero(self, message: discord.Message, modo: str, esito) -> None:
        lingua = await lingua_risposta(message.guild.id, pubblica=True)
        stato = await counting_game_repo.get(message.guild.id, message.channel.id)
        if esito.corretto:
            await self._reagisci(message, "✅")
            await self._ruolo_ultimo(message, stato, esito)
            return
        await self._reagisci(message, "❌")
        testo = t("conteggio_sbagliato", lingua, utente=message.author.mention, numero=scrivi_numero(esito.numero, modo),
                  inizio=scrivi_numero(1, modo), record=scrivi_numero(esito.record, modo))
        if esito.bloccato_fino is not None:
            testo += " " + t("conteggio_bloccato", lingua, quando=int(esito.bloccato_fino.timestamp()))
        try:
            await message.channel.send(testo, allowed_mentions=discord.AllowedMentions(users=[message.author]))
        except discord.HTTPException:
            pass
        if stato is not None and esito.precedente:
            await self._togli_ruolo(message.guild, stato.ruolo_ultimo, esito.precedente)

    async def _ruolo_ultimo(self, message: discord.Message, stato, esito) -> None:
        """Il ruolo passa a chi ha contato per ultimo (se il canale lo prevede)."""
        if stato is None or not stato.ruolo_ultimo or esito.precedente == message.author.id:
            return
        guild = message.guild
        ruolo = guild.get_role(stato.ruolo_ultimo)
        if ruolo is None or not isinstance(message.author, discord.Member):
            return
        try:
            await message.author.add_roles(ruolo, reason="Ultimo del conteggio")
        except discord.HTTPException:
            logger.info("Conteggio: ruolo %s non dato a %s", ruolo.id, message.author.id)
            return
        if esito.precedente:
            await self._togli_ruolo(guild, stato.ruolo_ultimo, esito.precedente)

    @staticmethod
    async def _togli_ruolo(guild: discord.Guild, ruolo_id: int | None, user_id: int) -> None:
        ruolo = guild.get_role(ruolo_id) if ruolo_id else None
        membro = guild.get_member(user_id)
        if ruolo is None or membro is None or ruolo not in membro.roles:
            return
        try:
            await membro.remove_roles(ruolo, reason="Non è più l'ultimo del conteggio")
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, canale: discord.abc.GuildChannel) -> None:
        try:
            await counting_game_repo.togli_canale(canale.guild.id, canale.id)
        except Exception:
            logger.exception("Conteggio: pulizia del canale %s fallita", canale.id)

    # ================================================================
    # /admin-giochi conteggio
    # ================================================================
    @comando_di_gruppo("admin-giochi", nome="canale", descrizione="Scegli i canali dove si conta (fino a 10) e come.", sottogruppo=_SG_ADMIN)
    @app_commands.describe(
        azione="Cosa fare", canale="Il canale", modo="Come si scrivono i numeri",
        filtro="Il messaggio è solo il numero, oppure il numero e poi un commento",
    )
    @app_commands.choices(
        azione=_SCELTE_AZIONE,
        modo=[app_commands.Choice(name=m, value=m) for m in MODI],
        filtro=[app_commands.Choice(name="solo il numero", value="solo_numero"), app_commands.Choice(name="numero e commento", value="con_testo")],
    )
    @richiedi(Livello.ADMIN)
    async def conteggio_canale(
        self, interaction: discord.Interaction, azione: app_commands.Choice[str], canale: discord.TextChannel | None = None,
        modo: app_commands.Choice[str] | None = None, filtro: app_commands.Choice[str] | None = None,
    ) -> None:
        if not await self._pronto(interaction):
            return
        guild_id = interaction.guild.id
        if azione.value == "elenco":
            stati = await counting_game_repo.elenco(guild_id)
            if not stati:
                await interaction.response.send_message(await testo_per(interaction, "coingames_il_gioco_non_attivo"), ephemeral=True)
                return
            righe = [
                await testo_per(interaction, "conteggio_riga_canale", canale=f"<#{s.channel_id}>", modo=s.modo, filtro=s.filtro,
                                numero=scrivi_numero(s.current, s.modo), record=scrivi_numero(s.best, s.modo),
                                punizione=s.punizione_minuti, ruolo=f"<@&{s.ruolo_ultimo}>" if s.ruolo_ultimo else "-")
                for s in stati
            ]
            await interaction.response.send_message("\n".join(righe)[:1900], ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE)
            return
        if canale is None:
            await interaction.response.send_message(await testo_per(interaction, "coingames_indica_il_canale"), ephemeral=True)
            return
        if azione.value == "togli":
            tolto = await counting_game_repo.togli_canale(guild_id, canale.id)
            await interaction.response.send_message(
                await testo_per(interaction, "conteggio_canale_tolto" if tolto else "conteggio_canale_non_attivo"), ephemeral=True
            )
            return
        motivo = motivo_se_il_bot_non_puo(canale, interaction.guild.me, PERMESSI_DI_REAZIONE)
        if motivo is not None:
            await interaction.response.send_message(
                await testo_per(interaction, "conteggio_bot_non_puo", canale=canale.mention, motivo=motivo), ephemeral=True,
                allowed_mentions=_NESSUNA_MENZIONE,
            )
            return
        try:
            await counting_game_repo.aggiungi_canale(
                guild_id, canale.id, modo.value if modo else "decimale", filtro.value if filtro else "solo_numero"
            )
        except TroppiCanali:
            await interaction.response.send_message(await testo_per(interaction, "conteggio_troppi_canali"), ephemeral=True)
            return
        await interaction.response.send_message(
            await testo_per(interaction, "coingames_si_conta_in_scrivete_poi", mention=canale.mention),
            ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
        )

    @comando_di_gruppo("admin-giochi", nome="regole", descrizione="Punizione dopo uno sbaglio e ruolo di chi ha contato per ultimo.", sottogruppo=_SG_ADMIN)
    @app_commands.describe(
        canale="Il canale del conteggio", punizione_minuti=f"Minuti senza poter contare dopo uno sbaglio (0 = nessuna, al massimo {MAX_PUNIZIONE_MINUTI})",
        ruolo_ultimo="Ruolo di chi ha contato per ultimo", senza_ruolo="Togli il ruolo dell'ultimo",
    )
    @richiedi(Livello.ADMIN)
    async def conteggio_regole(
        self, interaction: discord.Interaction, canale: discord.TextChannel,
        punizione_minuti: app_commands.Range[int, 0, MAX_PUNIZIONE_MINUTI] | None = None,
        ruolo_ultimo: discord.Role | None = None, senza_ruolo: bool = False,
    ) -> None:
        if not await self._pronto(interaction):
            return
        guild = interaction.guild
        if ruolo_ultimo is not None:
            chiave = motivo_ruolo_non_assegnabile(
                posizione_ruolo=ruolo_ultimo.position, gestito=ruolo_ultimo.managed, di_base=ruolo_ultimo.is_default(),
                posizione_bot=guild.me.top_role.position, bot_puo_gestire_ruoli=guild.me.guild_permissions.manage_roles,
            )
            if chiave is not None:
                await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)
                return
        ruolo = ruolo_ultimo.id if ruolo_ultimo else (None if senza_ruolo else NON_CAMBIA)
        fatto = await counting_game_repo.imposta_regole(
            guild.id, canale.id, punizione_minuti=NON_CAMBIA if punizione_minuti is None else punizione_minuti, ruolo_ultimo=ruolo
        )
        if not fatto:
            await interaction.response.send_message(await testo_per(interaction, "conteggio_canale_non_attivo"), ephemeral=True)
            return
        s = await counting_game_repo.get(guild.id, canale.id)
        await interaction.response.send_message(
            await testo_per(interaction, "conteggio_regole_salvate", canale=canale.mention, punizione=s.punizione_minuti,
                            ruolo=f"<@&{s.ruolo_ultimo}>" if s.ruolo_ultimo else "-"),
            ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
        )

    # ================================================================
    # /giochi conteggio
    # ================================================================
    @comando_di_gruppo("giochi", nome="classifica", descrizione="Chi ha contato più numeri giusti.", sottogruppo=_SG_GIOCHI)
    @app_commands.describe(canale="Un canale del conteggio (se vuoto, tutto il server)", pagina="Pagina (10 per pagina)")
    async def conteggio_classifica(
        self, interaction: discord.Interaction, canale: discord.TextChannel | None = None,
        pagina: app_commands.Range[int, 1, 100] = 1,
    ) -> None:
        if not await self._pronto(interaction):
            return
        await interaction.response.defer()
        guild_id = interaction.guild.id
        canale_id = canale.id if canale else None
        totale = await counting_game_repo.conta_giocatori(guild_id, canale_id)
        if totale == 0:
            await interaction.followup.send(await testo_per(interaction, "conteggio_classifica_vuota", pubblica=True))
            return
        pagine = (totale + RIGHE_CLASSIFICA - 1) // RIGHE_CLASSIFICA
        pagina = min(pagina, pagine)
        scarto = (pagina - 1) * RIGHE_CLASSIFICA
        righe = [
            f"**{scarto + i}.** <@{p.user_id}> · ✅ {p.giusti} · ❌ {p.sbagliati}"
            for i, p in enumerate(await counting_game_repo.classifica(guild_id, canale_id, RIGHE_CLASSIFICA, scarto), 1)
        ]
        embed = discord.Embed(
            title=await testo_per(interaction, "conteggio_classifica_titolo", pubblica=True), description="\n".join(righe), color=0x5865F2
        )
        embed.set_footer(text=await testo_per(interaction, "conteggio_classifica_piede", pubblica=True, pagina=pagina, pagine=pagine))
        await interaction.followup.send(embed=embed, allowed_mentions=_NESSUNA_MENZIONE)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ConteggioCog(bot))
