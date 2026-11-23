"""
cogs/fun/auto.py
================
Auto da collezione (/auto ...): catalogo, acquisto, garage personale, potenziamenti con monete, gara contro
il banco o contro un altro utente (anche con una puntata) e la foto della propria auto. La foto è un allegato
controllato come ogni immagine degli utenti: tipo dai primi byte, ricodifica in sandbox (D74); si conserva solo la
copia PNG ridotta, mai l'originale. Si può togliere (da chi l'ha messa e dallo staff con /admin-giochi auto togli-foto);
nei messaggi pubblici ha il bottone «Segnala» e con 3 persone sparisce, come le immagini di /immagini post.
Funzioni coperte: FUN-017
Dipende da: core/auto_logic.py, core/auto_image.py, core/repositories/auto_repo.py, core/immagini_pipeline.py
"""

from __future__ import annotations

import hashlib
import io
import logging
import random
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core import allegati_tipo_logic
from core import auto_logic as al
from core.auto_image import affianca, riduci_foto
from core.command_access import Livello, richiedi
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.database import db
from core.i18n import testo_per
from core.immagini_pipeline import esamina_allegato
from core.leveling_logic import controlla_puntata
from core.repositories.auto_repo import Esito, auto_repo
from core.repositories.immagini_segnalazioni_repo import SOGLIA_BLOCCO, immagini_segnalazioni_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.partite_repo import EsitoApertura, partite_repo
from core.repositories.sociale_repo import sociale_repo
from core.safe_image import run_image_task
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.auto")
NESSUNA_MENZIONE = discord.AllowedMentions.none()
RNG = random.SystemRandom()
SG_AUTO_ADMIN = ("auto", "Auto da collezione: foto del garage")
GIOCO = "gara_auto"
POSTA_MASSIMA = 100_000
ATTESA_RISPOSTA = 120
PAUSA_SECONDI = 10
MAX_UTENTI_NELLA_PAUSA = 500
SCADENZA_BOTTONE_SECONDI = 3600
MODULI = ("fun", "leveling")


def chiave_foto(guild_id: int, user_id: int, sha256: str) -> str:
    """La chiave con cui si segnala la foto: un'altra foto, un'altra chiave."""
    return f"auto:{guild_id}:{user_id}:{sha256[:16]}"


async def foto_visibile(guild_id: int, auto) -> bytes | None:
    """La foto dell'auto se c'è e non è stata nascosta dalle segnalazioni."""
    if not auto.con_foto:
        return None
    chiave = chiave_foto(guild_id, auto.user_id, auto.sha_foto)
    if chiave in await immagini_segnalazioni_repo.bloccati([chiave]):
        return None
    trovata = await auto_repo.foto(guild_id, auto.user_id, auto.modello)
    return trovata[0] if trovata else None


async def _completa_catalogo(interaction: discord.Interaction, digitato: str) -> list[app_commands.Choice[str]]:
    d = digitato.lower()
    return [app_commands.Choice(name=m.nome, value=m.chiave) for m in al.CATALOGO if d in m.nome.lower() or d in m.chiave][:25]


async def _completa_mie(interaction: discord.Interaction, digitato: str) -> list[app_commands.Choice[str]]:
    if interaction.guild is None:
        return []
    d = digitato.lower()
    mie = await auto_repo.garage(interaction.guild.id, interaction.user.id)
    return [app_commands.Choice(name=al.PER_CHIAVE[a.modello].nome, value=a.modello) for a in mie
            if a.modello in al.PER_CHIAVE and (d in al.PER_CHIAVE[a.modello].nome.lower() or d in a.modello)][:25]


def risolvi(testo: str) -> al.Modello | None:
    t = testo.strip().lower()
    return al.trova(t) or next((m for m in al.CATALOGO if m.nome.lower() == t), None)


def valutazione_di(a) -> int:
    return al.valutazione(al.PER_CHIAVE[a.modello], a.motore, a.assetto, a.gomme)


class SegnalaFotoView(BaseView):
    """Un bottone «Segnala» per ogni foto mostrata: una segnalazione per persona; con 3 persone la foto sparisce."""

    def __init__(self, foto: list[tuple[str, str]], etichetta: str) -> None:
        super().__init__(timeout=SCADENZA_BOTTONE_SECONDI)
        for chiave, nome in foto[:2]:
            b = discord.ui.Button(label=f"{etichetta} · {nome}"[:80], style=discord.ButtonStyle.secondary, emoji="🚩")
            b.callback = self._premuto(chiave)
            self.add_item(b)

    def _premuto(self, chiave: str):
        async def _cb(interaction: discord.Interaction) -> None:
            guild_id = interaction.guild.id if interaction.guild else 0
            totale = await immagini_segnalazioni_repo.segnala(chiave, interaction.user.id, guild_id)
            if totale >= SOGLIA_BLOCCO:
                await interaction.response.edit_message(content=await testo_per(interaction, "auto_foto_nascosta", pubblica=True), view=None, attachments=[])
                return
            await interaction.response.send_message(await testo_per(interaction, "immagini_post_segnalato"), ephemeral=True)
        return _cb


class GaraView(BaseView):
    """Sfida tra due utenti: solo lo sfidato accetta; corre con la sua auto più forte."""

    def __init__(self, cog: "AutoCog", guild_id: int, sfidante: discord.Member, sfidato: discord.Member, auto_sfidante, puntata: int, moneta: str) -> None:
        super().__init__(timeout=ATTESA_RISPOSTA)
        self.cog, self.guild_id, self.sfidante, self.sfidato, self.auto_sfidante, self.puntata, self.moneta = cog, guild_id, sfidante, sfidato, auto_sfidante, puntata, moneta
        self.fase = "attesa"
        for etichetta, stile, funzione in (("Accetta", discord.ButtonStyle.success, self._accetta), ("Rifiuta", discord.ButtonStyle.danger, self._rifiuta)):
            b = discord.ui.Button(label=etichetta, style=stile)
            b.callback = funzione
            self.add_item(b)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id not in (self.sfidante.id, self.sfidato.id):
            await interaction.response.send_message(await testo_per(interaction, "sfd_non_tuo"), ephemeral=True)
            return False
        return True

    async def _rifiuta(self, interaction: discord.Interaction) -> None:
        if self.fase != "attesa":
            await interaction.response.send_message(await testo_per(interaction, "leveling_gia_fatto"), ephemeral=True)
            return
        self.fase = "fine"
        self.stop()
        await interaction.response.edit_message(content=await testo_per(interaction, "sfd_rifiutato", pubblica=True), view=None)

    async def _accetta(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.sfidato.id:
            await interaction.response.send_message(await testo_per(interaction, "sfd_solo_sfidato"), ephemeral=True)
            return
        if self.fase != "attesa":  # nessun await tra controllo e segno
            await interaction.response.send_message(await testo_per(interaction, "leveling_gia_fatto"), ephemeral=True)
            return
        self.fase = "fine"
        self.stop()
        await interaction.response.defer()
        sue = await auto_repo.garage(self.guild_id, self.sfidato.id)
        mia = await auto_repo.auto(self.guild_id, self.sfidante.id, self.auto_sfidante.modello)  # potrebbe non essere più sua
        if not sue or mia is None:
            await interaction.edit_original_response(content=await testo_per(interaction, "auto_gara_senza_auto", pubblica=True), view=None, attachments=[])
            return
        sua = max(sue, key=valutazione_di)
        if self.puntata:
            attesa = (await leveling_settings_repo.get_config(self.guild_id)).impostazioni.attesa_gioco
            esito, chi = await partite_repo.apri_gruppo(self.guild_id, [self.sfidante.id, self.sfidato.id], GIOCO, self.puntata, attesa)
            if esito is not EsitoApertura.APERTA:  # nessuna moneta tolta a nessuno
                chiave = "tav_poche" if esito is EsitoApertura.POCHE else "tav_non_puo"
                await interaction.edit_original_response(
                    content=await testo_per(interaction, chiave, chi=f"<@{chi}>", moneta=self.moneta, pubblica=True), view=None, attachments=[],
                    allowed_mentions=NESSUNA_MENZIONE)
                return
        esito_gara = al.gara(al.statistiche(al.PER_CHIAVE[mia.modello], *mia.livelli), al.statistiche(al.PER_CHIAVE[sua.modello], *sua.livelli), RNG)
        vince = esito_gara.vincitore
        if self.puntata:
            try:
                if vince == 1:
                    rest = {self.sfidante.id: self.puntata * 2, self.sfidato.id: 0}
                else:
                    rest = {self.sfidante.id: 0, self.sfidato.id: self.puntata * 2}
                await partite_repo.chiudi_gruppo(self.guild_id, GIOCO, rest)
            except Exception:
                logger.exception("Chiusura della gara non riuscita")
        try:
            await auto_repo.registra_gara(self.guild_id, [(mia.id, vince == 1), (sua.id, vince == 2)])
        except Exception:
            logger.exception("Statistiche della gara non salvate")
        testo, file, vista = await self.cog.racconto(interaction, self.guild_id, (self.sfidante, mia), (self.sfidato, sua), esito_gara, self.puntata, self.moneta)
        await interaction.edit_original_response(content=testo, view=vista, attachments=[file] if file else [], allowed_mentions=NESSUNA_MENZIONE)

    async def on_timeout(self) -> None:
        self.fase = "fine"


class AutoCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._ultima: dict[int, float] = {}
        self._rimborsi.start()

    def cog_unload(self) -> None:
        self._rimborsi.cancel()
        togli_comandi_del_cog(self)

    @tasks.loop(minutes=5)
    async def _rimborsi(self) -> None:
        try:
            await partite_repo.rimborsa_scadute()
        except Exception:
            logger.exception("Giro dei rimborsi delle gare")

    @_rimborsi.before_loop
    async def _prima(self) -> None:
        await self.bot.wait_until_ready()
        try:  # all'avvio: le gare stanno in memoria, una puntata rimasta aperta è persa e si rimborsa
            await partite_repo.rimborsa_gioco(GIOCO)
        except Exception:
            logger.exception("Rimborso delle gare all'avvio")

    # ---------------------------------------------------------------- aiuti
    def _pausa(self, utente_id: int) -> int:
        ora = time.monotonic()
        resta = PAUSA_SECONDI - (ora - self._ultima.get(utente_id, -1e9))
        if resta > 0:
            return int(resta) + 1
        if len(self._ultima) >= MAX_UTENTI_NELLA_PAUSA:
            self._ultima = {u: t for u, t in self._ultima.items() if ora - t < PAUSA_SECONDI}
        self._ultima[utente_id] = ora
        return 0

    async def _pronto(self, interaction: discord.Interaction):
        """Le impostazioni dell'economia, o None dopo aver risposto (server, moduli)."""
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return None
        for modulo in MODULI:
            if not await db.is_module_active_for_guild(interaction.guild.id, modulo):
                await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
                return None
        return (await leveling_settings_repo.get_config(interaction.guild.id)).impostazioni

    async def _modello(self, interaction: discord.Interaction, testo: str) -> al.Modello | None:
        m = risolvi(testo)
        if m is None:
            await interaction.response.send_message(await testo_per(interaction, "auto_sconosciuta"), ephemeral=True)
        return m

    async def _nome_rarita(self, interaction, m: al.Modello) -> str:
        return await testo_per(interaction, f"auto_rar_{m.rarita}", pubblica=True)

    async def _scheda(self, interaction, m: al.Modello, a=None, moneta: str = "") -> str:
        v, ac, t = al.statistiche(m, *(a.livelli if a else (0, 0, 0)))
        riga = await testo_per(interaction, "auto_scheda", pubblica=True, nome=m.nome, rarita=await self._nome_rarita(interaction, m), v=v, a=ac, t=t)
        if a is not None:
            riga += "\n" + await testo_per(interaction, "auto_livelli", pubblica=True, motore=a.motore, assetto=a.assetto, gomme=a.gomme,
                                           max=al.LIVELLO_MASSIMO, corse=a.corse, vinte=a.vinte)
        return riga

    async def racconto(self, interaction, guild_id: int, uno, due, esito: al.Esito, puntata: int, moneta: str):
        """Il testo della gara, l'immagine con le foto (se ci sono e non nascoste) e il bottone per segnalarle."""
        (u1, a1), (u2, a2) = uno, due
        m1, m2 = al.PER_CHIAVE[a1.modello], al.PER_CHIAVE[a2.modello] if a2 else None
        nome2 = m2.nome if m2 else "?"
        righe = [await testo_per(interaction, "auto_gara_titolo", pubblica=True, u1=u1.mention if hasattr(u1, "mention") else str(u1), m1=m1.nome,
                                 u2=u2.mention if hasattr(u2, "mention") else str(u2), m2=nome2)]
        for prova, x, y, chi in esito.prove:
            righe.append(await testo_per(interaction, "auto_gara_prova", pubblica=True, prova=await testo_per(interaction, f"auto_prova_{prova}", pubblica=True),
                                         x=x, y=y, chi="🟢" if chi == 1 else "🔴"))
        vincente = u1 if esito.vincitore == 1 else u2
        nome_vincente = vincente.mention if hasattr(vincente, "mention") else str(vincente)
        righe.append(await testo_per(interaction, "auto_gara_vince", pubblica=True, chi=nome_vincente))
        if puntata:
            righe.append(await testo_per(interaction, "auto_gara_posta", pubblica=True, posta=puntata, moneta=moneta))
        f1 = await foto_visibile(guild_id, a1)
        f2 = await foto_visibile(guild_id, a2) if hasattr(u2, "id") and a2 else None
        file = vista = None
        if f1 or f2:
            try:
                png = await run_image_task(affianca, f1, f2, esito.vincitore)
                file = discord.File(io.BytesIO(png), filename="gara.png")
                foto = [(chiave_foto(guild_id, a.user_id, a.sha_foto), al.PER_CHIAVE[a.modello].nome) for a, f in ((a1, f1), (a2, f2)) if f]
                vista = SegnalaFotoView(foto, await testo_per(interaction, "auto_segnala", pubblica=True))
            except Exception:
                logger.warning("Immagine della gara non creata", exc_info=True)
        return "\n".join(righe), file, vista

    # ---------------------------------------------------------------- comandi
    @comando_di_gruppo("auto", nome="catalogo", descrizione="Le auto da collezione che puoi comprare.")
    async def catalogo(self, interaction: discord.Interaction) -> None:
        i = await self._pronto(interaction)
        if i is None:
            return
        righe = []
        for m in al.CATALOGO:
            righe.append(await testo_per(interaction, "auto_catalogo_riga", pubblica=True, nome=m.nome, rarita=await self._nome_rarita(interaction, m),
                                         prezzo=m.prezzo, moneta=i.currency_name, v=m.velocita, a=m.accelerazione, t=m.tenuta))
        await interaction.response.send_message("\n".join(righe), allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("auto", nome="compra", descrizione="Compra un'auto da collezione per il tuo garage.")
    @app_commands.describe(auto="Quale auto")
    @app_commands.autocomplete(auto=_completa_catalogo)
    async def compra(self, interaction: discord.Interaction, auto: app_commands.Range[str, 1, 60]) -> None:
        i = await self._pronto(interaction)
        if i is None:
            return
        m = await self._modello(interaction, auto)
        if m is None:
            return
        esito = await auto_repo.compra(interaction.guild.id, interaction.user.id, m.chiave)
        chiave = {Esito.OK: "auto_comprata", Esito.GIA: "auto_gia", Esito.POCHE: "auto_poche"}[esito]
        await interaction.response.send_message(
            await testo_per(interaction, chiave, pubblica=esito is Esito.OK, nome=m.nome, prezzo=m.prezzo, moneta=i.currency_name, chi=interaction.user.mention),
            ephemeral=esito is not Esito.OK, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("auto", nome="garage", descrizione="Le auto del tuo garage (o di un altro membro).")
    @app_commands.describe(membro="Di chi vuoi il garage (di base il tuo)")
    async def garage(self, interaction: discord.Interaction, membro: discord.Member | None = None) -> None:
        if await self._pronto(interaction) is None:
            return
        chi = membro or interaction.user
        mie = await auto_repo.garage(interaction.guild.id, chi.id)
        if not mie:
            await interaction.response.send_message(await testo_per(interaction, "auto_garage_vuoto", chi=chi.mention), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)
            return
        righe = [await testo_per(interaction, "auto_garage_titolo", pubblica=True, chi=chi.mention, n=len(mie))]
        for a in mie:
            if a.modello in al.PER_CHIAVE:
                m = al.PER_CHIAVE[a.modello]
                righe.append(await testo_per(interaction, "auto_garage_riga", pubblica=True, nome=m.nome, motore=a.motore, assetto=a.assetto, gomme=a.gomme,
                                             vinte=a.vinte, corse=a.corse, foto="📷" if a.con_foto else ""))
        await interaction.response.send_message("\n".join(righe)[:2000], allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("auto", nome="vedi", descrizione="La scheda di un'auto del garage, con la sua foto.")
    @app_commands.describe(auto="Quale auto", membro="Di chi (di base la tua)")
    @app_commands.autocomplete(auto=_completa_catalogo)
    async def vedi(self, interaction: discord.Interaction, auto: app_commands.Range[str, 1, 60], membro: discord.Member | None = None) -> None:
        i = await self._pronto(interaction)
        if i is None:
            return
        m = await self._modello(interaction, auto)
        if m is None:
            return
        chi = membro or interaction.user
        a = await auto_repo.auto(interaction.guild.id, chi.id, m.chiave)
        if a is None:
            await interaction.response.send_message(await testo_per(interaction, "auto_non_tua"), ephemeral=True)
            return
        await interaction.response.defer()
        testo = f"{chi.mention}\n" + await self._scheda(interaction, m, a, i.currency_name)
        png = await foto_visibile(interaction.guild.id, a)
        if png is None:
            await interaction.followup.send(testo, allowed_mentions=NESSUNA_MENZIONE)
            return
        vista = SegnalaFotoView([(chiave_foto(interaction.guild.id, chi.id, a.sha_foto), m.nome)], await testo_per(interaction, "auto_segnala", pubblica=True))
        await interaction.followup.send(testo, file=discord.File(io.BytesIO(png), filename="auto.png"), view=vista, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("auto", nome="potenzia", descrizione="Potenzia una parte della tua auto con le monete.")
    @app_commands.describe(auto="Quale auto", parte="Motore (velocità), assetto (tenuta) o gomme (accelerazione)")
    @app_commands.autocomplete(auto=_completa_mie)
    @app_commands.choices(parte=[app_commands.Choice(name="Motore", value="motore"), app_commands.Choice(name="Assetto", value="assetto"),
                                 app_commands.Choice(name="Gomme", value="gomme")])
    async def potenzia(self, interaction: discord.Interaction, auto: app_commands.Range[str, 1, 60], parte: app_commands.Choice[str]) -> None:
        i = await self._pronto(interaction)
        if i is None:
            return
        m = await self._modello(interaction, auto)
        if m is None:
            return
        esito, livello, costo = await auto_repo.potenzia(interaction.guild.id, interaction.user.id, m.chiave, parte.value)
        chiave = {Esito.OK: "auto_potenziata", Esito.MANCA: "auto_non_tua", Esito.MASSIMO: "auto_al_massimo", Esito.POCHE: "auto_poche_potenzia"}[esito]
        await interaction.response.send_message(
            await testo_per(interaction, chiave, pubblica=esito is Esito.OK, nome=m.nome, parte=parte.name, livello=livello, costo=costo, moneta=i.currency_name,
                            chi=interaction.user.mention), ephemeral=esito is not Esito.OK, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("auto", nome="gara", descrizione="Gara con una tua auto contro il banco o contro un membro, anche con una puntata.")
    @app_commands.describe(auto="Con quale auto corri", membro="Chi sfidi (vuoto = contro il banco)", puntata="Monete in palio (solo contro un membro)")
    @app_commands.autocomplete(auto=_completa_mie)
    async def gara(self, interaction: discord.Interaction, auto: app_commands.Range[str, 1, 60], membro: discord.Member | None = None,
                   puntata: app_commands.Range[int, 0, POSTA_MASSIMA] = 0) -> None:
        i = await self._pronto(interaction)
        if i is None:
            return
        guild = interaction.guild
        m = await self._modello(interaction, auto)
        if m is None:
            return
        mia = await auto_repo.auto(guild.id, interaction.user.id, m.chiave)
        if mia is None:
            await interaction.response.send_message(await testo_per(interaction, "auto_non_tua"), ephemeral=True)
            return
        if membro is not None:
            if membro.id == interaction.user.id or membro.bot:
                await interaction.response.send_message(await testo_per(interaction, "sfd_bersaglio"), ephemeral=True)
                return
            if await sociale_repo.ha_bloccato(membro.id, interaction.user.id) or await sociale_repo.ha_bloccato(interaction.user.id, membro.id):
                await interaction.response.send_message(await testo_per(interaction, "soc_bloccato"), ephemeral=True)
                return
            if not await auto_repo.garage(guild.id, membro.id):
                await interaction.response.send_message(await testo_per(interaction, "auto_avversario_senza_auto"), ephemeral=True)
                return
            if puntata:
                motivo = controlla_puntata(puntata, i)
                if motivo is not None:
                    await interaction.response.send_message(f"❌ {motivo}", ephemeral=True)
                    return
            view = GaraView(self, guild.id, interaction.user, membro, mia, puntata, i.currency_name)
            await interaction.response.send_message(
                await testo_per(interaction, "auto_gara_sfida", sfidante=interaction.user.mention, sfidato=membro.mention, nome=m.nome, posta=puntata,
                                moneta=i.currency_name, pubblica=True),
                view=view, allowed_mentions=discord.AllowedMentions(users=[membro]))
            return
        if puntata:  # contro il banco niente puntata: non nascono monete dal nulla
            await interaction.response.send_message(await testo_per(interaction, "auto_banco_senza_posta"), ephemeral=True)
            return
        resta = self._pausa(interaction.user.id)
        if resta:
            await interaction.response.send_message(await testo_per(interaction, "auto_aspetta", secondi=resta), ephemeral=True)
            return
        await interaction.response.defer()
        banco, mo, as_, go = al.avversario_del_banco(m.rarita, RNG)
        esito = al.gara(al.statistiche(m, *mia.livelli), al.statistiche(banco, mo, as_, go), RNG)
        await auto_repo.registra_gara(guild.id, [(mia.id, esito.vincitore == 1)])
        finta = type("AutoBanco", (), {"modello": banco.chiave, "user_id": 0, "con_foto": False, "sha_foto": None})()
        testo, file, vista = await self.racconto(interaction, guild.id, (interaction.user, mia), (await testo_per(interaction, "auto_banco", pubblica=True), finta), esito, 0, i.currency_name)
        if file is None:
            await interaction.followup.send(testo, allowed_mentions=NESSUNA_MENZIONE)
        else:
            await interaction.followup.send(testo, file=file, view=vista, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("auto", nome="foto", descrizione="Metti la foto della tua auto (solo l'immagine ricodificata si conserva).")
    @app_commands.describe(auto="Di quale auto è la foto", immagine="La foto (PNG, JPEG, GIF, WebP o BMP, fino a 8 MB)")
    @app_commands.autocomplete(auto=_completa_mie)
    async def foto(self, interaction: discord.Interaction, auto: app_commands.Range[str, 1, 60], immagine: discord.Attachment) -> None:
        if await self._pronto(interaction) is None:
            return
        m = await self._modello(interaction, auto)
        if m is None:
            return
        guild = interaction.guild
        if await auto_repo.auto(guild.id, interaction.user.id, m.chiave) is None:
            await interaction.response.send_message(await testo_per(interaction, "auto_non_tua"), ephemeral=True)
            return
        if immagine.size > al.DIMENSIONE_FOTO_MASSIMA:
            await interaction.response.send_message(await testo_per(interaction, "auto_foto_grande"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            dati = await immagine.read()
        except discord.HTTPException:
            await interaction.followup.send(await testo_per(interaction, "auto_foto_no"), ephemeral=True)
            return
        copia, decisione = await esamina_allegato(dati, immagine.filename, getattr(immagine, "content_type", None), guild.id)
        if copia is None or decisione.azione != allegati_tipo_logic.IMMAGINE:  # tipo falso, sospetta, non analizzata o non è un'immagine
            await interaction.followup.send(await testo_per(interaction, "auto_foto_no"), ephemeral=True)
            return
        try:
            png = await run_image_task(riduci_foto, copia[1])
        except Exception:
            await interaction.followup.send(await testo_per(interaction, "auto_foto_no"), ephemeral=True)
            return
        if not await auto_repo.imposta_foto(guild.id, interaction.user.id, m.chiave, png, hashlib.sha256(png).hexdigest()):
            await interaction.followup.send(await testo_per(interaction, "auto_non_tua"), ephemeral=True)
            return
        await interaction.followup.send(await testo_per(interaction, "auto_foto_ok", nome=m.nome), ephemeral=True)

    @comando_di_gruppo("auto", nome="foto-togli", descrizione="Toglie la foto di una tua auto.")
    @app_commands.describe(auto="Di quale auto")
    @app_commands.autocomplete(auto=_completa_mie)
    async def foto_togli(self, interaction: discord.Interaction, auto: app_commands.Range[str, 1, 60]) -> None:
        if await self._pronto(interaction) is None:
            return
        m = await self._modello(interaction, auto)
        if m is None:
            return
        n = await auto_repo.togli_foto(interaction.guild.id, interaction.user.id, m.chiave)
        await interaction.response.send_message(await testo_per(interaction, "auto_foto_tolta" if n else "auto_foto_non_c_era", nome=m.nome), ephemeral=True)

    @comando_di_gruppo("admin-giochi", nome="togli-foto", descrizione="Toglie la foto di un'auto di un membro (una o tutte).", sottogruppo=SG_AUTO_ADMIN)
    @app_commands.describe(utente="Di chi", auto="Quale auto (vuoto = tutte le sue foto)")
    @app_commands.autocomplete(auto=_completa_catalogo)
    @richiedi(Livello.ADMIN)
    async def togli_foto_staff(self, interaction: discord.Interaction, utente: discord.User, auto: app_commands.Range[str, 1, 60] | None = None) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        chiave = None
        if auto:
            m = await self._modello(interaction, auto)
            if m is None:
                return
            chiave = m.chiave
        n = await auto_repo.togli_foto(interaction.guild.id, utente.id, chiave)
        await interaction.response.send_message(await testo_per(interaction, "auto_foto_tolta_staff", n=n, chi=utente.mention), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoCog(bot))
