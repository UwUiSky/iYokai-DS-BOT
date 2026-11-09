"""
cogs/fun/telefono.py
====================
Il telefono tra server: `/fun telefono chiama|riaggancia|segnala` e `/admin-giochi telefono canale|consenso|blocca|registro`.
Spento di base, consenso doppio (l'admin lo accende, il server chiamato accetta con i bottoni). I messaggi del canale
passano all'altro server con un webhook, senza menzioni e con gli allegati come soli indirizzi.
Funzioni coperte: SPEC §16 (FUN-079, FUN-080; B12 di #131)
Dipende da: core/telefono_logic.py, core/repositories/telefono_repo.py
"""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.fun.entertainment import MODULE_FUN
from core import telefono_logic as tl
from core.automod_parole_opzioni import trova_nel_testo
from core.command_access import Livello, richiedi
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.config_impostazioni import imposta_impostazione
from core.database import db
from core.fun_servizi_logic import SCHEDA_FUN, SETTING_TELEFONO, acceso
from core.i18n import testo_per, testo_guild
from core.repositories.blacklist_repo import blacklist_repo
from core.repositories.telefono_repo import TIPO_SERVER, TIPO_UTENTE, telefono_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.telefono")
NESSUNA_MENZIONE = discord.AllowedMentions.none()
SCELTE_EFFETTO = [app_commands.Choice(name=e, value=e) for e in tl.EFFETTI]


class SquilloView(BaseView):
    """«Chiamata in arrivo»: Accetta o Rifiuta. Chi preme deve poter gestire il server."""

    def __init__(self, cog: "TelefonoCog", chiamante: int, chiamato: int, et_accetta: str, et_rifiuta: str) -> None:
        super().__init__(timeout=tl.ATTESA_RISPOSTA_SECONDI)
        self.cog, self.chiamante, self.chiamato = cog, chiamante, chiamato
        self.messaggio: discord.Message | None = None
        ok = discord.ui.Button(label=et_accetta[:80], style=discord.ButtonStyle.success)
        no = discord.ui.Button(label=et_rifiuta[:80], style=discord.ButtonStyle.danger)
        ok.callback, no.callback = self._accetta, self._rifiuta
        self.add_item(ok)
        self.add_item(no)

    async def _puo(self, interaction: discord.Interaction) -> bool:
        permessi = getattr(interaction.user, "guild_permissions", None)
        if permessi is None or not (permessi.manage_guild or permessi.administrator):
            await interaction.response.send_message(await testo_per(interaction, "telefono_serve_gestione"), ephemeral=True)
            return False
        return True

    async def _accetta(self, interaction: discord.Interaction) -> None:
        if not await self._puo(interaction):
            return
        self.stop()
        await interaction.response.edit_message(view=None)
        await self.cog.connetti(self.chiamante, self.chiamato)

    async def _rifiuta(self, interaction: discord.Interaction) -> None:
        if not await self._puo(interaction):
            return
        self.stop()
        await interaction.response.edit_message(view=None)
        await self.cog.rifiuta(self.chiamante, self.chiamato)

    async def on_timeout(self) -> None:
        if self.messaggio is not None:
            try:
                await self.messaggio.edit(view=None)
            except discord.HTTPException:
                pass
        await self.cog.rifiuta(self.chiamante, self.chiamato)


class TelefonoCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._pausa = tl.PausaUtenti()
        self._webhook: dict[int, discord.Webhook] = {}

    async def cog_load(self) -> None:
        await super().cog_load()
        self.controllo.start()
        self._avvio = asyncio.get_running_loop().create_task(self._pulizia_avvio())

    async def cog_unload(self) -> None:
        self.controllo.cancel()
        self._avvio.cancel()
        chiamate, squilli = await tl.centralino.svuota()
        for chiamata in chiamate:
            await self._chiudi_dopo(chiamata, tl.FINE_RIAVVIO)
        await super().cog_unload()

    async def _pulizia_avvio(self) -> None:
        """Toglie i webhook rimasti da una chiamata interrotta dal riavvio."""
        try:
            await self.bot.wait_until_ready()
        except RuntimeError:
            return
        for guild_id, webhook_id in await telefono_repo.webhook_rimasti():
            try:
                await (await self.bot.fetch_webhook(webhook_id)).delete(reason="Telefono: chiamata interrotta")
            except discord.HTTPException:
                pass
            await telefono_repo.segna_webhook(guild_id, None)

    # --- controlli comuni ---
    def _canale(self, guild_id: int, canale_id: int) -> discord.TextChannel | None:
        guild = self.bot.get_guild(guild_id)
        canale = guild.get_channel(canale_id) if guild else None
        return canale if isinstance(canale, discord.TextChannel) else None

    async def _puo_ricevere(self, chiamante: int, guild_id: int, bloccano_chiamante: set[int]) -> bool:
        if guild_id in bloccano_chiamante or await telefono_repo.bloccato(chiamante, TIPO_SERVER, guild_id):
            return False
        if await blacklist_repo.is_guild_blacklisted(guild_id):
            return False
        return await acceso(guild_id, SETTING_TELEFONO) and await db.is_module_active_for_guild(guild_id, MODULE_FUN)

    async def _candidati(self, chiamante: int, canali: dict[int, int]) -> list[int]:
        bloccano = await telefono_repo.server_che_bloccano(chiamante)
        out = []
        for guild_id in canali:
            if guild_id == chiamante or self._canale(guild_id, canali[guild_id]) is None:
                continue
            if await self._puo_ricevere(chiamante, guild_id, bloccano):
                out.append(guild_id)
        return out

    # --- /fun telefono ---
    @comando_di_gruppo("fun", nome="chiama", descrizione="Chiama un altro server a caso (spento di base).", sottogruppo=("telefono", "Telefono tra server: chiama, riaggancia, segnala"))
    @app_commands.describe(effetto="Come cambiare i tuoi messaggi mentre parli")
    @app_commands.choices(effetto=SCELTE_EFFETTO)
    @app_commands.checks.cooldown(1, 30, key=lambda i: i.guild_id)
    async def chiama(self, interaction: discord.Interaction, effetto: app_commands.Choice[str] | None = None) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        if not await db.is_module_active_for_guild(guild.id, MODULE_FUN):
            await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
            return
        if not await acceso(guild.id, SETTING_TELEFONO):
            await interaction.response.send_message(await testo_per(interaction, "telefono_spento"), ephemeral=True)
            return
        canali = await telefono_repo.canali()
        if guild.id not in canali:
            await interaction.response.send_message(await testo_per(interaction, "telefono_senza_canale"), ephemeral=True)
            return
        if await telefono_repo.bloccato(guild.id, TIPO_UTENTE, interaction.user.id):
            await interaction.response.send_message(await testo_per(interaction, "telefono_utente_bloccato"), ephemeral=True)
            return
        if await blacklist_repo.is_user_blacklisted(interaction.user.id):
            await interaction.response.send_message(await testo_per(interaction, "telefono_utente_bloccato"), ephemeral=True)
            return
        if tl.centralino.occupato(guild.id):
            await interaction.response.send_message(await testo_per(interaction, "telefono_occupato"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        squillo = await tl.centralino.suona(
            guild.id, await self._candidati(guild.id, canali), canali, effetto.value if effetto else "nessuno", interaction.user.id
        )
        if squillo is None:
            await interaction.followup.send(await testo_per(interaction, "telefono_nessuno"), ephemeral=True)
            return
        destinazione = self._canale(squillo.chiamato, squillo.canali[squillo.chiamato])
        vista = SquilloView(
            self, guild.id, squillo.chiamato,
            await testo_guild(squillo.chiamato, "telefono_accetta"), await testo_guild(squillo.chiamato, "telefono_rifiuta"),
        )
        try:
            vista.messaggio = await destinazione.send(
                await testo_guild(squillo.chiamato, "telefono_in_arrivo", durata=tl.DURATA_MAX_SECONDI // 60),
                view=vista, allowed_mentions=NESSUNA_MENZIONE,
            )
        except discord.HTTPException:
            await tl.centralino.annulla_squillo(guild.id)
            await interaction.followup.send(await testo_per(interaction, "telefono_nessuno"), ephemeral=True)
            return
        await interaction.followup.send(await testo_per(interaction, "telefono_squilla", secondi=tl.ATTESA_RISPOSTA_SECONDI), ephemeral=True)

    @comando_di_gruppo("fun", nome="riaggancia", descrizione="Chiudi la chiamata in corso.", sottogruppo=("telefono", "Telefono tra server: chiama, riaggancia, segnala"))
    async def riaggancia(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        gid = interaction.guild.id
        if await tl.centralino.annulla_squillo(gid) is not None:
            await interaction.response.send_message(await testo_per(interaction, "telefono_annullata"), ephemeral=True)
            return
        chiamata = tl.centralino.chiamata_di(gid)
        if chiamata is None:
            await interaction.response.send_message(await testo_per(interaction, "telefono_nessuna_chiamata"), ephemeral=True)
            return
        permessi = interaction.user.guild_permissions
        if interaction.user.id != chiamata.chi_chiama and not (permessi.manage_messages or permessi.manage_guild):
            await interaction.response.send_message(await testo_per(interaction, "telefono_serve_gestione"), ephemeral=True)
            return
        await interaction.response.send_message(await testo_per(interaction, "telefono_chiusa"), ephemeral=True)
        await self.chiudi(gid, tl.FINE_RIAGGANCIATA)

    @comando_di_gruppo("fun", nome="segnala", descrizione="Segnala la chiamata, blocca l'altro server e riaggancia.", sottogruppo=("telefono", "Telefono tra server: chiama, riaggancia, segnala"))
    async def segnala(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        gid = interaction.guild.id
        chiamata = tl.centralino.chiamata_di(gid)
        if chiamata is None:
            await interaction.response.send_message(await testo_per(interaction, "telefono_nessuna_chiamata"), ephemeral=True)
            return
        permessi = interaction.user.guild_permissions
        if interaction.user.id != chiamata.chi_chiama and not (permessi.manage_messages or permessi.manage_guild):
            await interaction.response.send_message(await testo_per(interaction, "telefono_serve_gestione"), ephemeral=True)
            return
        chiamata.segnalata = True
        await telefono_repo.blocca(gid, TIPO_SERVER, chiamata.altro(gid))
        await interaction.response.send_message(await testo_per(interaction, "telefono_segnalata"), ephemeral=True)
        await self.chiudi(gid, tl.FINE_RIAGGANCIATA)

    # --- /admin-giochi telefono ---
    @comando_di_gruppo("admin-giochi", nome="canale", descrizione="Il canale del telefono del server.", sottogruppo=("telefono", "Telefono tra server: canale, consenso, blocchi, registro"))
    @app_commands.describe(canale="Il canale dove parla il telefono")
    @richiedi(Livello.ADMIN)
    async def admin_canale(self, interaction: discord.Interaction, canale: discord.TextChannel) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        permessi = canale.permissions_for(interaction.guild.me)
        if not (permessi.view_channel and permessi.send_messages and permessi.manage_webhooks):
            await interaction.response.send_message(await testo_per(interaction, "telefono_permessi"), ephemeral=True)
            return
        await telefono_repo.imposta_canale(interaction.guild.id, canale.id)
        await interaction.response.send_message(await testo_per(interaction, "telefono_canale_ok", canale=canale.mention), ephemeral=True)

    @comando_di_gruppo("admin-giochi", nome="consenso", descrizione="Accende o spegne il telefono: spento di base.", sottogruppo=("telefono", "Telefono tra server: canale, consenso, blocchi, registro"))
    @app_commands.describe(attivo="Sì: il server può chiamare e ricevere chiamate (ogni chiamata va accettata)")
    @richiedi(Livello.ADMIN)
    async def admin_consenso(self, interaction: discord.Interaction, attivo: bool) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        await imposta_impostazione(interaction.guild, SCHEDA_FUN, SETTING_TELEFONO, "1" if attivo else "0", interaction.user.id)
        await interaction.response.send_message(await testo_per(interaction, "telefono_consenso_si" if attivo else "telefono_consenso_no"), ephemeral=True)
        if not attivo:
            await tl.centralino.annulla_squillo(interaction.guild.id)
            await self.chiudi(interaction.guild.id, tl.FINE_SPENTO)

    @comando_di_gruppo("admin-giochi", nome="blocca", descrizione="Blocca o sblocca una persona o un altro server dal telefono.", sottogruppo=("telefono", "Telefono tra server: canale, consenso, blocchi, registro"))
    @app_commands.describe(utente="La persona da bloccare", server_id="L'ID dell'altro server da bloccare", sblocca="Sì: toglie il blocco")
    @richiedi(Livello.ADMIN)
    async def admin_blocca(
        self, interaction: discord.Interaction, utente: discord.User | None = None,
        server_id: app_commands.Range[str, 5, 25] | None = None, sblocca: bool = False,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        gid = interaction.guild.id
        bersagli: list[tuple[str, int]] = []
        if utente is not None:
            bersagli.append((TIPO_UTENTE, utente.id))
        if server_id is not None:
            if not server_id.isdigit():
                await interaction.response.send_message(await testo_per(interaction, "telefono_id_non_valido"), ephemeral=True)
                return
            bersagli.append((TIPO_SERVER, int(server_id)))
        if not bersagli:
            elenco = await telefono_repo.elenco_blocchi(gid)
            riga = "\n".join(f"{t}: {b}" for t, b in elenco) or await testo_per(interaction, "telefono_nessun_blocco")
            await interaction.response.send_message(riga[:1900], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)
            return
        for tipo, bersaglio in bersagli:
            await (telefono_repo.sblocca if sblocca else telefono_repo.blocca)(gid, tipo, bersaglio)
        await interaction.response.send_message(await testo_per(interaction, "telefono_sbloccato" if sblocca else "telefono_bloccato"), ephemeral=True)

    @comando_di_gruppo("admin-giochi", nome="registro", descrizione="Le ultime chiamate del server: solo server, ora e durata.", sottogruppo=("telefono", "Telefono tra server: canale, consenso, blocchi, registro"))
    @richiedi(Livello.ADMIN)
    async def admin_registro(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        righe = []
        for r in await telefono_repo.registro(interaction.guild.id, 10):
            altro = self.bot.get_guild(r["altro"])
            nome = tl.pulisci_nome(altro.name if altro else str(r["altro"]))
            righe.append(f"{discord.utils.format_dt(r['iniziata_il'], 'f')} · {nome} · {r['durata_secondi'] // 60} min · {r['fine']}"
                         + (" 🚩" if r["segnalata"] else ""))
        testo = "\n".join(righe) or await testo_per(interaction, "telefono_registro_vuoto")
        await interaction.response.send_message(testo[:1900], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    # --- chiamata: collegare, inoltrare, chiudere ---
    async def rifiuta(self, chiamante: int, chiamato: int) -> None:
        squillo = await tl.centralino.annulla_squillo(chiamante, chiamato)
        if squillo is None:
            return
        canale = self._canale(chiamante, squillo.canali[chiamante])
        if canale is not None:
            try:
                await canale.send(await testo_guild(chiamante, "telefono_rifiutata"), allowed_mentions=NESSUNA_MENZIONE)
            except discord.HTTPException:
                pass

    async def connetti(self, chiamante: int, chiamato: int) -> None:
        chiamata = await tl.centralino.risposto(chiamante, chiamato)
        if chiamata is None:
            return
        try:
            for gid in (chiamata.a, chiamata.b):
                canale = self._canale(gid, chiamata.canali[gid])
                if canale is None:
                    raise discord.HTTPException(response=None, message="canale sparito")  # type: ignore[arg-type]
                await self._prepara_webhook(chiamata, gid, canale)
        except (discord.HTTPException, AttributeError, TypeError):
            logger.warning("Telefono: webhook non creato, chiamata chiusa")
            await self.chiudi(chiamante, tl.FINE_ERRORE)
            return
        chiamata.pronta = True
        for gid in (chiamata.a, chiamata.b):
            canale = self._canale(gid, chiamata.canali[gid])
            if canale is not None:
                await canale.send(await testo_guild(gid, "telefono_collegati"), allowed_mentions=NESSUNA_MENZIONE)

    async def _prepara_webhook(self, chiamata: tl.Chiamata, gid: int, canale: discord.TextChannel) -> None:
        webhook = await canale.create_webhook(name=tl.NOME_WEBHOOK, reason="Telefono tra server")
        self._webhook[gid] = webhook
        await telefono_repo.segna_webhook(gid, webhook.id)
        coda: asyncio.Queue = asyncio.Queue(maxsize=tl.CODA_MAX)
        chiamata.code[gid] = coda
        chiamata.lavoratori.append(asyncio.create_task(self._lavora(chiamata, gid, webhook, coda)))

    async def _lavora(self, chiamata: tl.Chiamata, gid: int, webhook: discord.Webhook, coda: asyncio.Queue) -> None:
        """Manda i messaggi in coda con il ritmo del webhook. Su 10015 o 403 la chiamata si chiude, senza riprovare."""
        altro = chiamata.altro(gid)
        while True:
            testo, nome, avatar, solo_adulti = await coda.get()
            destinazione = self._canale(gid, chiamata.canali[gid])
            if destinazione is None or tl.adulti_bloccato(solo_adulti, destinazione.is_nsfw()):
                continue  # il canale è cambiato mentre il messaggio aspettava
            try:
                await webhook.send(testo, username=nome, avatar_url=avatar, allowed_mentions=NESSUNA_MENZIONE)
            except (discord.NotFound, discord.Forbidden):
                asyncio.create_task(self.chiudi(gid, tl.FINE_ERRORE))
                return
            except discord.HTTPException:
                chiamata.errori += 1
                if chiamata.errori >= tl.ERRORI_MAX:
                    asyncio.create_task(self.chiudi(altro, tl.FINE_ERRORE))
                    return
            await asyncio.sleep(tl.PAUSA_INVIO_SECONDI)

    async def chiudi(self, guild_id: int, fine: str) -> None:
        chiamata = await tl.centralino.termina(guild_id)
        if chiamata is not None:
            await self._chiudi_dopo(chiamata, fine, avvisa=True)

    async def _chiudi_dopo(self, chiamata: tl.Chiamata, fine: str, avvisa: bool = False) -> None:
        chiamata.pronta = False
        for lavoratore in chiamata.lavoratori:
            lavoratore.cancel()
        durata = int(tl.centralino._ora() - chiamata.inizio)
        for gid in (chiamata.a, chiamata.b):
            webhook = self._webhook.pop(gid, None)
            if webhook is not None:
                try:
                    await webhook.delete(reason="Telefono: chiamata finita")
                except discord.HTTPException:
                    pass
            await telefono_repo.segna_webhook(gid, None)
            canale = self._canale(gid, chiamata.canali[gid])
            if avvisa and canale is not None:
                try:
                    await canale.send(await testo_guild(gid, "telefono_finita"), allowed_mentions=NESSUNA_MENZIONE)
                except discord.HTTPException:
                    pass
        await telefono_repo.registra(chiamata.a, chiamata.b, chiamata.iniziata_il, durata, fine, chiamata.segnalata)

    @tasks.loop(seconds=30)
    async def controllo(self) -> None:
        for chiamata, motivo in tl.centralino.scadute():
            await self.chiudi(chiamata.a, motivo)
        for chiamata in tl.centralino.chiamate():  # il consenso può essere tolto anche da /config o dal pannello
            if not (await acceso(chiamata.a, SETTING_TELEFONO) and await acceso(chiamata.b, SETTING_TELEFONO)):
                await self.chiudi(chiamata.a, tl.FINE_SPENTO)

    @controllo.before_loop
    async def _prima(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot or message.webhook_id is not None:
            return
        chiamata = tl.centralino.chiamata_di(message.guild.id)
        if chiamata is None or not chiamata.pronta or message.channel.id != chiamata.canali.get(message.guild.id):
            return
        if message.type not in (discord.MessageType.default, discord.MessageType.reply):
            return
        await self._inoltra(message, chiamata)

    async def _inoltra(self, message: discord.Message, chiamata: tl.Chiamata) -> None:
        gid = message.guild.id
        altro = chiamata.altro(gid)
        destinazione = self._canale(altro, chiamata.canali[altro])
        coda = chiamata.code.get(altro)
        if destinazione is None or coda is None:
            return
        if tl.adulti_bloccato(message.channel.is_nsfw(), destinazione.is_nsfw()):
            return
        if await blacklist_repo.is_user_blacklisted(message.author.id) or await telefono_repo.bloccato(gid, TIPO_UTENTE, message.author.id):
            return
        effetto = chiamata.effetti.get(gid, "nessuno")
        nome = tl.nome_mittente(message.author.display_name, message.guild.name)
        # Gli allegati passano solo verso canali con limite d'età: un'immagine per adulti non si riconosce da qui.
        indirizzi = [a.url for a in message.attachments] if destinazione.is_nsfw() else []
        base = tl.prepara_testo(message.content, indirizzi, "nessuno")  # i filtri guardano il testo prima dell'effetto
        if base is None or tl.testo_su_minori(nome, base) or await trova_nel_testo(altro, f"{nome}\n{base}") is not None:
            return
        testo = tl.prepara_testo(message.content, indirizzi, effetto)
        if not self._pausa.passa(message.author.id):
            return
        tl.centralino.tocca(chiamata)
        try:
            coda.put_nowait((testo, nome, message.author.display_avatar.url, message.channel.is_nsfw() or bool(indirizzi)))
        except asyncio.QueueFull:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TelefonoCog(bot))
