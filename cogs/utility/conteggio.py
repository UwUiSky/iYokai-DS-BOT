"""
cogs/utility/conteggio.py
=========================
Gioco del conteggio (NF-40, D69 B14-B15): fino a 10 canali dove si conta a turno 1, 2, 3... anche in binario, in numeri
romani o in lettere; chi sbaglia può restare bloccato per un po'; chi ha contato per ultimo può avere un ruolo.
Traguardi (ruolo o messaggio) e avvisi a un numero.
Comandi: `/admin-giochi conteggio canale|regole|traguardo|importa` (staff), `/giochi conteggio classifica|avvisami` (tutti).
Funzioni coperte: SPEC §23.16 (NF-40), catalogo UTL-186, 187, 188, 189, 190, 191, 192, 193, 194
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.channel_access import PERMESSI_DI_REAZIONE, motivo_se_il_bot_non_puo
from core.command_access import Livello, puo_usare, richiedi
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.conteggio_logic import (
    MAX_BYTE_IMPORT, MAX_MESSAGGIO_TRAGUARDO, MAX_PUNIZIONE_MINUTI, MODI, ImportErrato, leggi_importazione, leggi_numero,
    scrivi_numero, traguardi_raggiunti,
)
from core.database import db
from core.giveaway_logic import motivo_ruolo_non_assegnabile
from core.i18n import lingua_risposta, t, testo_per
from core.ui_base import BaseView
from core.repositories.counting_game_repo import NON_CAMBIA, TroppiAvvisi, TroppiCanali, TroppiTraguardi, counting_game_repo

logger = logging.getLogger("iyokai.conteggio")

MODULE_FUN = "fun"  # il conteggio sta nel modulo «Divertimento»
_SG_ADMIN = ("conteggio", "Gioco del conteggio: canali, regole, traguardi")
_SG_GIOCHI = ("conteggio", "Gioco del conteggio: classifica e avvisi")
_NESSUNA_MENZIONE = discord.AllowedMentions.none()
RIGHE_CLASSIFICA = 10
SECONDI_CONFERMA = 60
_SCELTE_AZIONE = [
    app_commands.Choice(name="aggiungi o cambia", value="aggiungi"),
    app_commands.Choice(name="togli", value="togli"),
    app_commands.Choice(name="elenco", value="elenco"),
]


class ConfermaTogliCanale(BaseView):
    """Togliere un canale cancella anche punteggi, traguardi, avvisi e blocchi: serve una conferma di chi ha dato il comando."""

    def __init__(self, proprietario: int, guild_id: int, channel_id: int, etichette: tuple[str, str]) -> None:
        super().__init__(timeout=SECONDI_CONFERMA)
        self.proprietario = proprietario
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.conferma.label, self.annulla.label = etichette[0][:80], etichette[1][:80]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.proprietario:
            await interaction.response.send_message(await testo_per(interaction, "conteggio_non_e_tuo"), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Conferma", style=discord.ButtonStyle.danger)
    async def conferma(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        if not await puo_usare(interaction, Livello.ADMIN):  # il livello si ricontrolla: il tasto non è il comando
            await interaction.response.edit_message(content=await testo_per(interaction, "conteggio_non_e_tuo"), view=None)
            return
        tolto = await counting_game_repo.togli_canale(self.guild_id, self.channel_id)
        await interaction.response.edit_message(
            content=await testo_per(interaction, "conteggio_canale_tolto" if tolto else "conteggio_canale_non_attivo"), view=None
        )

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def annulla(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content=await testo_per(interaction, "conteggio_togli_annullato"), view=None)


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
            await self._traguardi_e_avvisi(message, modo, esito.numero, lingua)
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

    async def _traguardi_e_avvisi(self, message: discord.Message, modo: str, numero: int, lingua: str) -> None:
        """Ruolo e messaggio dei traguardi toccati, poi gli avvisi chiesti per questo numero."""
        guild_id, canale_id = message.guild.id, message.channel.id
        try:
            toccati = traguardi_raggiunti(numero, await counting_game_repo.traguardi(guild_id, canale_id))
            da_avvisare = await counting_game_repo.consuma_avvisi(guild_id, canale_id, numero)
        except Exception:
            logger.warning("Conteggio: traguardi non letti nel server %s.", guild_id, exc_info=True)
            return
        for traguardo in toccati:
            if traguardo.ruolo_id and isinstance(message.author, discord.Member):
                ruolo = message.guild.get_role(traguardo.ruolo_id)
                if ruolo is not None:
                    try:
                        await message.author.add_roles(ruolo, reason="Traguardo del conteggio")
                    except discord.HTTPException:
                        logger.info("Conteggio: ruolo %s non dato a %s", ruolo.id, message.author.id)
            if traguardo.messaggio:
                testo = traguardo.messaggio.replace("{utente}", message.author.mention).replace("{numero}", scrivi_numero(numero, modo))
                await self._scrivi(message.channel, testo[:MAX_MESSAGGIO_TRAGUARDO + 100], [message.author])
        if da_avvisare:
            testo = t("conteggio_avviso_scattato", lingua, numero=scrivi_numero(numero, modo), utenti=" ".join(f"<@{u}>" for u in da_avvisare))
            await self._scrivi(message.channel, testo, [discord.Object(id=u) for u in da_avvisare])

    @staticmethod
    async def _scrivi(canale, testo: str, utenti: list) -> None:
        """Mai @everyone, @here o ruoli: solo le persone dette."""
        try:
            await canale.send(testo[:2000], allowed_mentions=discord.AllowedMentions(users=utenti, roles=False, everyone=False))
        except discord.HTTPException:
            pass

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
            if await counting_game_repo.get(guild_id, canale.id) is None:
                await interaction.response.send_message(await testo_per(interaction, "conteggio_canale_non_attivo"), ephemeral=True)
                return
            etichette = (await testo_per(interaction, "conteggio_togli_bottone"), await testo_per(interaction, "conteggio_togli_annulla"))
            await interaction.response.send_message(
                await testo_per(interaction, "conteggio_togli_chiedi", canale=canale.mention), ephemeral=True,
                allowed_mentions=_NESSUNA_MENZIONE, view=ConfermaTogliCanale(interaction.user.id, guild_id, canale.id, etichette),
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

    @comando_di_gruppo("admin-giochi", nome="traguardo", descrizione="Ruolo o messaggio quando il conteggio tocca un numero.", sottogruppo=_SG_ADMIN)
    @app_commands.describe(
        azione="Cosa fare", canale="Il canale del conteggio", numero="Un numero preciso", ogni="Oppure ogni tanti numeri",
        ruolo="Ruolo dato a chi lo raggiunge", messaggio=f"Messaggio nel canale ({{utente}} e {{numero}}, al massimo {MAX_MESSAGGIO_TRAGUARDO} caratteri)",
        traguardo="Il numero d'ordine, per toglierlo (lo vedi nell'elenco)",
    )
    @app_commands.choices(azione=[app_commands.Choice(name=n, value=v) for n, v in (("aggiungi", "aggiungi"), ("togli", "togli"), ("elenco", "elenco"))])
    @richiedi(Livello.ADMIN)
    async def conteggio_traguardo(
        self, interaction: discord.Interaction, azione: app_commands.Choice[str], canale: discord.TextChannel | None = None,
        numero: app_commands.Range[int, 1, 999_999_999] | None = None, ogni: app_commands.Range[int, 1, 999_999_999] | None = None,
        ruolo: discord.Role | None = None, messaggio: app_commands.Range[str, 1, MAX_MESSAGGIO_TRAGUARDO] | None = None,
        traguardo: app_commands.Range[int, 1, 2_000_000_000] | None = None,
    ) -> None:
        if not await self._pronto(interaction):
            return
        guild = interaction.guild
        if azione.value == "elenco":
            if canale is None:
                await interaction.response.send_message(await testo_per(interaction, "coingames_indica_il_canale"), ephemeral=True)
                return
            righe = [
                await testo_per(interaction, "conteggio_riga_traguardo", id=g.id,
                                quando=str(g.numero) if g.numero else f"x{g.ogni}", ruolo=f"<@&{g.ruolo_id}>" if g.ruolo_id else "-",
                                messaggio=(g.messaggio or "-")[:80])
                for g in await counting_game_repo.traguardi(guild.id, canale.id)
            ]
            await interaction.response.send_message(
                "\n".join(righe)[:1900] or await testo_per(interaction, "conteggio_nessun_traguardo"),
                ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
            )
            return
        if azione.value == "togli":
            if traguardo is None:
                await interaction.response.send_message(await testo_per(interaction, "conteggio_indica_traguardo"), ephemeral=True)
                return
            tolto = await counting_game_repo.togli_traguardo(guild.id, traguardo)
            await interaction.response.send_message(
                await testo_per(interaction, "conteggio_traguardo_tolto" if tolto else "conteggio_traguardo_inesistente"), ephemeral=True
            )
            return
        if canale is None or (numero is None) == (ogni is None) or (ruolo is None and messaggio is None):
            await interaction.response.send_message(await testo_per(interaction, "conteggio_traguardo_incompleto"), ephemeral=True)
            return
        if await counting_game_repo.get(guild.id, canale.id) is None:
            await interaction.response.send_message(await testo_per(interaction, "conteggio_canale_non_attivo"), ephemeral=True)
            return
        if ruolo is not None:
            chiave = motivo_ruolo_non_assegnabile(
                posizione_ruolo=ruolo.position, gestito=ruolo.managed, di_base=ruolo.is_default(),
                posizione_bot=guild.me.top_role.position, bot_puo_gestire_ruoli=guild.me.guild_permissions.manage_roles,
            )
            if chiave is not None:
                await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)
                return
        try:
            nuovo = await counting_game_repo.aggiungi_traguardo(
                guild.id, canale.id, numero=numero, ogni=ogni, ruolo_id=ruolo.id if ruolo else None, messaggio=messaggio
            )
        except TroppiTraguardi:
            await interaction.response.send_message(await testo_per(interaction, "conteggio_troppi_traguardi"), ephemeral=True)
            return
        await interaction.response.send_message(await testo_per(interaction, "conteggio_traguardo_salvato", id=nuovo), ephemeral=True)

    @comando_di_gruppo("admin-giochi", nome="importa", descrizione="Porta in un canale i punteggi di un file CSV o JSON.", sottogruppo=_SG_ADMIN)
    @app_commands.describe(canale="Il canale del conteggio", file="CSV (user_id,giusti,sbagliati) o JSON, al massimo 1 MiB e 5.000 membri")
    @richiedi(Livello.ADMIN)
    async def conteggio_importa(self, interaction: discord.Interaction, canale: discord.TextChannel, file: discord.Attachment) -> None:
        if not await self._pronto(interaction):
            return
        if file.size > MAX_BYTE_IMPORT:
            await interaction.response.send_message(await testo_per(interaction, "conteggio_import_troppo_grande"), ephemeral=True)
            return
        if await counting_game_repo.get(interaction.guild.id, canale.id) is None:
            await interaction.response.send_message(await testo_per(interaction, "conteggio_canale_non_attivo"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            righe = leggi_importazione(await file.read(), file.filename or "")
        except ImportErrato as errore:
            await interaction.followup.send(await testo_per(interaction, str(errore)))
            return
        except discord.HTTPException:
            await interaction.followup.send(await testo_per(interaction, "conteggio_import_illeggibile"))
            return
        fatti = await counting_game_repo.importa_punteggi(interaction.guild.id, canale.id, righe)
        await interaction.followup.send(await testo_per(interaction, "conteggio_import_fatto", quanti=fatti, canale=canale.mention), allowed_mentions=_NESSUNA_MENZIONE)

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

    @comando_di_gruppo("giochi", nome="avvisami", descrizione="Ti avviso nel canale quando il conteggio arriva a un numero.", sottogruppo=_SG_GIOCHI)
    @app_commands.describe(numero="Il numero da aspettare", canale="Il canale (se il server ne ha uno solo si capisce da sé)", togli="Togli tutti i tuoi avvisi")
    async def conteggio_avvisami(
        self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 999_999_999] | None = None,
        canale: discord.TextChannel | None = None, togli: bool = False,
    ) -> None:
        if not await self._pronto(interaction):
            return
        guild_id = interaction.guild.id
        if togli:
            quanti = await counting_game_repo.togli_avvisi(guild_id, interaction.user.id)
            await interaction.response.send_message(await testo_per(interaction, "conteggio_avvisi_tolti", quanti=quanti), ephemeral=True)
            return
        stati = await counting_game_repo.elenco(guild_id)
        if canale is None and len(stati) == 1:
            canale_id = stati[0].channel_id
        elif canale is not None:
            canale_id = canale.id
        else:
            await interaction.response.send_message(await testo_per(interaction, "conteggio_scegli_il_canale"), ephemeral=True)
            return
        stato = next((x for x in stati if x.channel_id == canale_id), None)
        if stato is None or numero is None:
            await interaction.response.send_message(await testo_per(interaction, "conteggio_avviso_dati"), ephemeral=True)
            return
        if numero <= stato.current:
            await interaction.response.send_message(await testo_per(interaction, "conteggio_avviso_gia_superato"), ephemeral=True)
            return
        try:
            nuovo = await counting_game_repo.aggiungi_avviso(guild_id, canale_id, interaction.user.id, numero)
        except TroppiAvvisi:
            await interaction.response.send_message(await testo_per(interaction, "conteggio_troppi_avvisi"), ephemeral=True)
            return
        await interaction.response.send_message(
            await testo_per(interaction, "conteggio_avviso_salvato" if nuovo else "conteggio_avviso_gia_presente", numero=scrivi_numero(numero, stato.modo)),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ConteggioCog(bot))
