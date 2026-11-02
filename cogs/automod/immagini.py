"""
cogs/automod/immagini.py
========================
Filtro delle immagini sospette (D62): ogni allegato immagine di un server con il filtro acceso passa
dal percorso unico (core/immagini_pipeline.py: byte, libreria, quarantena, sandbox) e l'esito si applica
con cancella, avviso o timeout, DM all'autore e riga nel log (senza ripubblicare il file). Vale per
tutti, staff e canali o ruoli esenti compresi: un account staff rubato e' il caso tipico (D63). In piu' il
comando dell'owner `/owner immagini-trappola` per la libreria condivisa (D39 per le immagini).
Funzioni coperte: SPEC §6 (D62)
Dipende da: core/immagini_pipeline.py, core/immagini_azione_logic.py, core/immagini_trappola_service.py
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.moderation._shared import post_to_mod_log, try_dm
from core import bot_roles
from core import automod_regole_service as regole_service
from core.automod_azioni import Bersaglio, esegui_azioni
from core.automod_contesto import contesto_da_messaggio
from core.automod_regole_logic import azioni_da_json, condizioni_ok
from core import immagini_azione_logic as azioni
from core import immagini_opzioni as opzioni_immagini
from core import immagini_quarantena as quarantena
from core import immagini_trappola_logic as lg
from core.bot_ready import attendi_bot_pronto
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.config import config
from core.database import db
from core.i18n import lingua_risposta, t, testo_per
from core.immagini_byte_logic import MALEVOLA, estensione_di, tipo_atteso
from core.immagini_coda import coda_immagini
from core.immagini_pipeline import EsitoImmagine, analizza_immagine, impronte
from core.immagini_trappola_service import libreria_immagini
from core.safe_image import MAX_IMAGE_BYTES

logger = logging.getLogger("iyokai.immagini")

REGOLA_IMMAGINI = "immagini_sospette"  # regola di sistema: azioni, condizioni e interruttore stanno in automod_regole

MODULE_AUTOMOD = "automod"
MAX_ALLEGATI_PER_MESSAGGIO = 4
MAX_VOCI_ELENCO = 15
AZIONI_LIBRERIA = [
    app_commands.Choice(name="elenca", value="elenca"),
    app_commands.Choice(name="approva", value="approva"),
    app_commands.Choice(name="rifiuta", value="rifiuta"),
    app_commands.Choice(name="aggiungi", value="aggiungi"),
]


def e_allegato_immagine(allegato: discord.Attachment) -> bool:
    """Un allegato che il filtro deve guardare: estensione o content-type di un'immagine."""
    tipo = (allegato.content_type or "").lower()
    return tipo.startswith("image/") or tipo_atteso(allegato.filename, allegato.content_type) is not None or estensione_di(
        allegato.filename
    ) in ("bmp", "avif", "heic", "tiff", "svg")


class ImmaginiCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._pulizia = tasks.loop(minutes=15)(self._giro_pulizia)
        self._pulizia.before_loop(self._prima)

    async def cog_load(self) -> None:
        await super().cog_load()
        self._pulizia.start()

    async def cog_unload(self) -> None:
        self._pulizia.cancel()
        await super().cog_unload()

    async def _prima(self) -> None:
        await attendi_bot_pronto(self.bot)

    async def _giro_pulizia(self) -> None:
        try:
            tolti = await quarantena.pulisci()
            if tolti:
                logger.info("Quarantena: %d file tolti", tolti)
        except Exception:
            logger.warning("Pulizia della quarantena non riuscita", exc_info=True)

    # ------------------------------------------------------------------ messaggi

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        guild = message.guild
        if guild is None or message.author.bot or not message.attachments or not isinstance(message.author, discord.Member):
            return
        allegati = [a for a in message.attachments if e_allegato_immagine(a)][:MAX_ALLEGATI_PER_MESSAGGIO]
        if not allegati:
            return
        try:
            opzioni = await opzioni_immagini.leggi(guild.id)
            if not opzioni.attivo or not await db.is_module_active_for_guild(guild.id, MODULE_AUTOMOD):
                return
            await self._controlla(message, allegati, opzioni)
        except Exception:
            logger.exception("Filtro immagini: errore imprevisto")

    async def _controlla(self, message: discord.Message, allegati, opzioni) -> None:
        membro, guild = message.author, message.guild
        for allegato in allegati:
            if allegato.size > MAX_IMAGE_BYTES:
                continue
            try:
                dati = await allegato.read()
            except discord.HTTPException:
                continue
            esito = await analizza_immagine(dati, allegato.filename, allegato.content_type, guild.id)
            adesso = discord.utils.utcnow()
            nel_server = (adesso - membro.joined_at).total_seconds() / 86400 if membro.joined_at else None
            decisione = azioni.decidi(
                esito,
                opzioni,
                a_rischio=azioni.autore_a_rischio((adesso - membro.created_at).total_seconds() / 86400, nel_server),
            )
            if esito.da_segnalare:
                dettaglio = ",".join(esito.motivi)
                await libreria_immagini.segnala(esito.sha256, esito.dhash, dettaglio, guild.id, guild.owner_id, guild.member_count or 0)
            if decisione == azioni.Decisione():
                continue
            await self._applica(message, esito, decisione, opzioni)
            if decisione.cancella:
                return

    async def _applica(self, message: discord.Message, esito: EsitoImmagine, d: azioni.Decisione, opzioni) -> None:
        """Le azioni passano dal motore unico (core/automod_azioni.py, regola di sistema «immagini_sospette»)."""
        guild, membro = message.guild, message.author
        lingua = await lingua_risposta(guild.id, pubblica=True)
        regola = await regole_service.regola_effettiva(guild.id, REGOLA_IMMAGINI, azioni_da_json(self._azioni(d, esito, lingua)))
        eseguite: list[str] = []
        if regola.attiva and (regola.id is None or condizioni_ok(
                regola.condizioni, contesto_da_messaggio(message, nostro_bot=lambda u: bot_roles.e_un_nostro_bot(u, self.bot)))):
            # Nessuna esenzione di base (D63): il filtro controlla anche lo staff. Lo scudo dei protetti vale solo per le sanzioni.
            motivo = t("amimg_motivo_audit", lingua)[:200]
            nomi = await esegui_azioni(
                regola.azioni if regola.id is not None and regola.azioni else azioni_da_json(self._azioni(d, esito, lingua)),
                Bersaglio(guild=guild, motivo=motivo, regola_chiave=REGOLA_IMMAGINI, regola_nome=motivo, membro=membro,
                          messaggio=message, canale=message.channel, canale_log_id=opzioni.canale_log_id, senza_scudo=True),
            )
            etichette = {"delete": "amimg_azione_cancellato", "mute": "amimg_azione_timeout", "avviso_canale": "amimg_azione_avvisato"}
            eseguite = [t(etichette[n], lingua, minuti=d.timeout_minuti or 0) for n in nomi if n in etichette]
        if d.log:
            await self._log(message, esito, eseguite, lingua, opzioni)
        if d.avvisa_owner and coda_immagini.puo_avvisare():
            await self._avvisa_owner(lingua)

    def _azioni(self, d: azioni.Decisione, esito: EsitoImmagine, lingua: str) -> list[dict]:
        """La decisione del filtro nel formato delle azioni AutoMod (ordine fisso: DM, cancella, timeout, avviso)."""
        fuori: list[dict] = []
        if d.dm:
            fuori.append({"t": "dm", "testo": t(d.dm, lingua, server="{server}", motivo=self._motivi(esito, lingua),
                                                minuti=d.timeout_minuti or 0)[:1000]})
        if d.cancella:
            fuori.append({"t": "cancella"})
        if d.timeout_minuti:
            fuori.append({"t": "timeout", "secondi": d.timeout_minuti * 60})
        if d.avvisa_nel_canale:
            fuori.append({"t": "avviso_canale", "testo": t("amimg_avviso_canale", lingua, utente="{utente}")[:300], "dopo_s": 30})
        return fuori

    @staticmethod
    def _motivi(esito: EsitoImmagine, lingua: str) -> str:
        etichette = []
        for codice in esito.motivi or ((esito.non_analizzata,) if esito.non_analizzata else ()):
            testo = t(f"amimg_motivo_{codice}", lingua)
            etichette.append(codice if testo == f"amimg_motivo_{codice}" else testo)
        return ", ".join(etichette)[:300]

    async def _log(self, message: discord.Message, esito: EsitoImmagine, eseguite: list[str], lingua: str, opzioni) -> None:
        """Una riga nel log: autore, canale, impronta, motivo e azione. Mai il file."""
        if esito.non_analizzata == "coda_piena":
            titolo = t("amimg_log_non_analizzata_coda", lingua)
        elif esito.non_analizzata:
            titolo = t("amimg_log_non_analizzata_sandbox", lingua)
        else:
            titolo = t("amimg_log_malevola" if esito.verdetto == MALEVOLA else "amimg_log_sospetta", lingua)
        embed = discord.Embed(title=titolo, color=discord.Color.red() if esito.verdetto == MALEVOLA else discord.Color.orange())
        embed.add_field(name=t("amimg_campo_autore", lingua), value=f"{message.author.mention} (`{message.author.id}`)", inline=True)
        embed.add_field(name=t("amimg_campo_canale", lingua), value=getattr(message.channel, "mention", "?"), inline=True)
        if esito.sha256:
            embed.add_field(name=t("amimg_campo_impronta", lingua), value=f"`{esito.sha256[:16]}`", inline=True)
        embed.add_field(name=t("amimg_campo_motivo", lingua), value=self._motivi(esito, lingua) or "-", inline=False)
        embed.add_field(name=t("amimg_campo_azione", lingua), value=", ".join(eseguite) or t("amimg_azione_nessuna", lingua), inline=False)
        if esito.modo_sandbox == "ridotta":
            embed.set_footer(text=t("amimg_sandbox_ridotta", lingua))
        canale = guild_canale(message.guild, opzioni.canale_log_id)
        if canale is not None:
            try:
                await canale.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
                return
            except (discord.Forbidden, discord.HTTPException):
                pass
        await post_to_mod_log(message.guild, embed)

    async def _avvisa_owner(self, lingua: str) -> None:
        try:
            utente = self.bot.get_user(config.OWNER_ID) or await self.bot.fetch_user(config.OWNER_ID)
            await utente.send(t("amimg_owner_coda_piena", "it", in_coda=coda_immagini.in_coda))
        except (discord.HTTPException, AttributeError):
            logger.warning("Coda immagini piena: owner non raggiungibile")

    # ------------------------------------------------------------------ comando dell'owner

    @comando_di_gruppo(
        "owner",
        nome="immagini-trappola",
        descrizione="Solo proprietario del bot: libreria delle immagini trappola.",
    )
    @app_commands.describe(
        azione="Cosa fare",
        impronta="SHA-256 (o i primi 6 caratteri, per approva e rifiuta)",
        immagine="L'immagine da aggiungere (con aggiungi)",
    )
    @app_commands.choices(azione=AZIONI_LIBRERIA)
    async def libreria(
        self,
        interaction: discord.Interaction,
        azione: app_commands.Choice[str],
        impronta: app_commands.Range[str, 6, 64] | None = None,
        immagine: discord.Attachment | None = None,
    ) -> None:
        if interaction.user.id != config.OWNER_ID:
            await interaction.response.send_message(await testo_per(interaction, "amimg_owner_solo_proprietario"), ephemeral=True)
            return
        if azione.value == "aggiungi":
            await interaction.response.defer(ephemeral=True)
            testo = await self._aggiungi(interaction, impronta, immagine)
            await interaction.followup.send(testo[:1900], ephemeral=True)
            return
        await interaction.response.send_message((await self._libreria(interaction, azione.value, impronta))[:1900], ephemeral=True)

    async def _libreria(self, interaction: discord.Interaction, azione: str, impronta: str | None) -> str:
        if azione == "elenca":
            conti = await libreria_immagini.conta()
            righe = [f"{s}: {conti.get(s, 0)}" for s in lg.STATI]
            for stato in (lg.CONDIVISA, lg.CANDIDATA):
                righe += [f"[{stato}] `{v.sha256[:16]}` {v.motivo[:60]}" for v in await libreria_immagini.elenca(stato, MAX_VOCI_ELENCO // 2)]
            return "\n".join(righe)
        if not impronta:
            return await testo_per(interaction, "amimg_owner_serve_impronta")
        stato = lg.APPROVATA if azione == "approva" else lg.RIFIUTATA
        esito = await libreria_immagini.imposta_stato(impronta, stato)
        chiave = {"ok": "amimg_owner_approvata" if stato == lg.APPROVATA else "amimg_owner_rifiutata"}.get(esito, f"amimg_owner_{esito}")
        return await testo_per(interaction, chiave)

    async def _aggiungi(self, interaction: discord.Interaction, impronta: str | None, immagine: discord.Attachment | None) -> str:
        if immagine is not None:
            if immagine.size > MAX_IMAGE_BYTES:
                return await testo_per(interaction, "amimg_owner_troppo_grande")
            sha, dhash = await impronte(await immagine.read())
        else:
            sha, dhash = lg.sha_valido(impronta or ""), None
            if sha is None:
                return await testo_per(interaction, "amimg_owner_serve_impronta")
        await libreria_immagini.aggiungi(sha, dhash, "owner")
        return await testo_per(interaction, "amimg_owner_aggiunta", impronta=sha[:16], percettiva="si" if dhash is not None else "no")


def guild_canale(guild: discord.Guild, canale_id: int | None):
    canale = guild.get_channel(canale_id) if canale_id else None
    return canale if isinstance(canale, discord.abc.Messageable) else None


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ImmaginiCog(bot))
