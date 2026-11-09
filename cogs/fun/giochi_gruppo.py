"""
cogs/fun/giochi_gruppo.py
=========================
Giochi di gruppo (#131, D70, B7): `/giochi battitura`, `/giochi acronimi` e i testi di battitura del server
(`/admin-giochi battitura aggiungi|elenca|rimuovi`). Partite in memoria (una per canale), solo i punteggi in
`fun_punteggi`. Il testo della battitura è un'immagine; `on_message` legge solo il canale di una partita.
Funzioni coperte: SPEC §16 (FUN-010, 011, 012)
Dipende da: core/gruppo_logic.py, cogs/fun/_lobby.py, core/repositories/battitura_repo.py
"""

from __future__ import annotations

import asyncio
import io
import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

from cogs.fun._lobby import apri_lobby
from cogs.fun.entertainment import MODULE_FUN
from cogs.leveling._pagine import invia_lista
from core import fun_gare_logic as gare
from core import gruppo_logic as gl
from core.command_access import Livello, richiedi
from core.command_groups import SOTTOGRUPPI, CogConGruppi, comando_di_gruppo
from core.database import db
from core.i18n import testo_per
from core.repositories.battitura_repo import battitura_repo
from core.repositories.fun_gare_repo import fun_gare_repo
from core.safe_image import run_image_task
from core.ui_base import BaseModal, BaseView

logger = logging.getLogger("iyokai.giochi_gruppo")

NESSUNA_MENZIONE = discord.AllowedMentions.none()
SECONDI_SCRITTURA = 60
SECONDI_VOTO = 45
SECONDI_LOBBY = 45


async def _attivo(interaction: discord.Interaction) -> bool:
    if interaction.guild is None:
        await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
        return False
    if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_FUN):
        await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
        return False
    return True


# ---------------- acronimi: finestra e viste ----------------
class ModaleAcronimo(BaseModal):
    def __init__(self, partita: gl.PartitaAcronimi, evento: asyncio.Event, titolo: str, etichetta: str) -> None:
        super().__init__(title=titolo[:45])
        self.partita, self.evento = partita, evento
        self.frase = discord.ui.TextInput(label=etichetta[:45], max_length=gl.MAX_FRASE, required=True)
        self.add_item(self.frase)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        esito = self.partita.invia(interaction.user.id, self.frase.value)
        await interaction.response.send_message(await testo_per(interaction, f"acronimi_invio_{esito}"), ephemeral=True)
        if esito == "ok" and len(self.partita.frasi) >= len(self.partita.giocatori):
            self.evento.set()


class VistaScrivi(BaseView):
    def __init__(self, partita: gl.PartitaAcronimi, evento: asyncio.Event, etichetta: str, titolo: str, campo: str) -> None:
        super().__init__(timeout=SECONDI_SCRITTURA + 15)
        self.partita, self.evento, self._titolo, self._campo = partita, evento, titolo, campo
        self.scrivi.label = etichetta[:45]

    @discord.ui.button(style=discord.ButtonStyle.primary)
    async def scrivi(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id not in self.partita.giocatori:
            await interaction.response.send_message(await testo_per(interaction, "acronimi_invio_non_giocatore"), ephemeral=True)
        elif interaction.user.id in self.partita.frasi:
            await interaction.response.send_message(await testo_per(interaction, "acronimi_invio_gia"), ephemeral=True)
        else:
            await interaction.response.send_modal(ModaleAcronimo(self.partita, self.evento, self._titolo, self._campo))


class MenuVoto(discord.ui.Select):
    def __init__(self, frasi: list[str], segnaposto: str) -> None:
        opzioni = [discord.SelectOption(label=f"{i + 1}. {f}"[:100], value=str(i)) for i, f in enumerate(frasi[: gl.MAX_GIOCATORI])]
        super().__init__(placeholder=segnaposto[:150], options=opzioni, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        vista: VistaVoto = self.view  # type: ignore[assignment]
        esito = vista.partita.vota(interaction.user.id, int(self.values[0]))
        await interaction.response.send_message(await testo_per(interaction, f"acronimi_voto_{esito}"), ephemeral=True)
        if len(vista.partita.voti) >= len(vista.partita.giocatori):
            vista.evento.set()


class VistaVoto(BaseView):
    def __init__(self, partita: gl.PartitaAcronimi, evento: asyncio.Event, frasi: list[str], segnaposto: str) -> None:
        super().__init__(timeout=SECONDI_VOTO + 15)
        self.partita, self.evento = partita, evento
        self.add_item(MenuVoto(frasi, segnaposto))


class GiochiGruppoCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._rng = random.Random()
        self._attive: set[int] = set()
        self._battitura: dict[int, gl.PartitaBattitura] = {}
        self._eventi: dict[int, asyncio.Event] = {}
        self._compiti: set[asyncio.Task] = set()

    async def cog_load(self) -> None:
        await super().cog_load()

    async def cog_unload(self) -> None:
        for compito in list(self._compiti):
            compito.cancel()
        await super().cog_unload()

    def _lancia(self, coro) -> None:
        compito = asyncio.create_task(coro)
        self._compiti.add(compito)
        compito.add_done_callback(self._compiti.discard)

    async def _lobby(self, interaction: discord.Interaction, canale, minimo: int, massimo: int, chiave_intro: str, **kw) -> list[int] | None:
        """Mostra la sala d'attesa. Restituisce i giocatori, None se non bastano."""
        return await apri_lobby(interaction, minimo, massimo, chiave_intro, SECONDI_LOBBY, **kw)

    async def _canale_libero(self, interaction: discord.Interaction):
        canale = interaction.channel
        if canale is None or not isinstance(canale, discord.abc.Messageable):
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return None
        if canale.id in self._attive:  # segnato prima di ogni await: due comandi insieme non fanno due partite
            await interaction.response.send_message(await testo_per(interaction, "gruppo_gia_in_corso"), ephemeral=True)
            return None
        self._attive.add(canale.id)
        return canale

    # ---------------- battitura ----------------
    @comando_di_gruppo("giochi", nome="battitura", descrizione="Gara di battitura: copia il testo mostrato nell'immagine.")
    @app_commands.describe(durata="Secondi a disposizione, da 20 a 120 (di base 60)")
    async def battitura(self, interaction: discord.Interaction, durata: app_commands.Range[int, 20, 120] = 60) -> None:
        if not await _attivo(interaction):
            return
        canale = await self._canale_libero(interaction)
        if canale is None:
            return
        try:
            await interaction.response.defer()
            self._lancia(self._gioca_battitura(interaction, canale, durata))
        except BaseException:
            self._attive.discard(canale.id)
            raise

    async def _gioca_battitura(self, interaction: discord.Interaction, canale, durata: int) -> None:
        guild_id = interaction.guild.id
        try:
            giocatori = await self._lobby(interaction, canale, 1, gl.MAX_GIOCATORI, "battitura_intro", secondi=durata)
            if not giocatori:
                await canale.send(await testo_per(interaction, "gruppo_annullato", pubblica=True))
                return
            testi = gl.testi_integrati() + [t for _, t in await battitura_repo.elenco(guild_id)]
            testo = self._rng.choice(testi)
            png = await run_image_task(gl.disegna_testo, testo)
            partita = gl.PartitaBattitura(testo, discord.utils.utcnow(), set(giocatori))
            evento = self._eventi[canale.id] = asyncio.Event()
            self._battitura[canale.id] = partita
            messaggio = await canale.send(
                await testo_per(interaction, "battitura_via", pubblica=True, secondi=durata),
                file=discord.File(io.BytesIO(png), filename="testo.png"), allowed_mentions=NESSUNA_MENZIONE,
            )
            partita.inizio = messaggio.created_at  # il tempo parte dal messaggio, non dall'orologio del bot
            try:
                await asyncio.wait_for(evento.wait(), durata)
            except TimeoutError:
                pass
            classifica = partita.classifica()
            settimana = gare.periodo_settimana()
            for u, wpm in classifica:
                await fun_gare_repo.registra_massimo(guild_id, "battitura", settimana, u, wpm)
            corpo = gare.testo_classifica(classifica, " WPM") or await testo_per(interaction, "battitura_nessuno", pubblica=True)
            embed = discord.Embed(title=(await testo_per(interaction, "battitura_fine", pubblica=True))[:256], description=corpo, color=discord.Color.gold())
            await canale.send(embed=embed, allowed_mentions=NESSUNA_MENZIONE)
        except asyncio.CancelledError:
            raise
        except discord.HTTPException:
            logger.warning("Battitura interrotta nel canale %s.", getattr(canale, "id", 0))
        finally:
            self._attive.discard(canale.id)
            self._battitura.pop(canale.id, None)
            self._eventi.pop(canale.id, None)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        partita = self._battitura.get(message.channel.id)  # solo il canale di una partita: nient'altro si legge
        if partita is None or message.author.bot or message.author.id not in partita.partecipanti:
            return
        if partita.valuta(message.author.id, message.content, message.created_at) is None:
            return
        try:
            await message.add_reaction("✅")
        except discord.HTTPException:
            pass
        if partita.finita and (evento := self._eventi.get(message.channel.id)):
            evento.set()

    # ---------------- acronimi ----------------
    @comando_di_gruppo("giochi", nome="acronimi", descrizione="Inventa frasi che seguono le lettere date e vota la migliore.")
    @app_commands.describe(giocatori="Quanti giocatori al massimo, da 3 a 10 (di base 6)", turni="Quanti turni, da 1 a 5 (di base 3)")
    async def acronimi(
        self, interaction: discord.Interaction, giocatori: app_commands.Range[int, 3, 10] = 6, turni: app_commands.Range[int, 1, 5] = 3
    ) -> None:
        if not await _attivo(interaction):
            return
        canale = await self._canale_libero(interaction)
        if canale is None:
            return
        try:
            await interaction.response.defer()
            self._lancia(self._gioca_acronimi(interaction, canale, giocatori, turni))
        except BaseException:
            self._attive.discard(canale.id)
            raise

    async def _attendi(self, evento: asyncio.Event, secondi: int) -> None:
        try:
            await asyncio.wait_for(evento.wait(), secondi)
        except TimeoutError:
            pass

    async def _gioca_acronimi(self, interaction: discord.Interaction, canale, massimo: int, turni: int) -> None:
        guild_id = interaction.guild.id
        try:
            giocatori = await self._lobby(interaction, canale, gl.MIN_GIOCATORI_ACRONIMI, massimo, "acronimi_intro", turni=turni, minimo=gl.MIN_GIOCATORI_ACRONIMI)
            if not giocatori:
                await canale.send(await testo_per(interaction, "gruppo_annullato", pubblica=True))
                return
            partita = gl.PartitaAcronimi(giocatori, turni)
            while not partita.finita:
                lettere = partita.nuovo_turno(self._rng)
                evento = asyncio.Event()
                titolo = await testo_per(interaction, "acronimi_turno", pubblica=True, n=partita.turno, tot=turni)
                vista = VistaScrivi(
                    partita, evento, await testo_per(interaction, "acronimi_scrivi", pubblica=True),
                    await testo_per(interaction, "acronimi_finestra", pubblica=True), ".".join(lettere),
                )
                await canale.send(
                    f"**{titolo}**\n" + await testo_per(interaction, "acronimi_lettere", pubblica=True, lettere=" . ".join(lettere), secondi=SECONDI_SCRITTURA),
                    view=vista, allowed_mentions=NESSUNA_MENZIONE,
                )
                await self._attendi(evento, SECONDI_SCRITTURA)
                vista.stop()
                if len(partita.frasi) < 2:
                    await canale.send(await testo_per(interaction, "acronimi_poche_frasi", pubblica=True), allowed_mentions=NESSUNA_MENZIONE)
                    continue
                frasi = partita.apri_voto(self._rng)
                evento = asyncio.Event()
                voto = VistaVoto(partita, evento, frasi, await testo_per(interaction, "acronimi_vota", pubblica=True))
                elenco = "\n".join(f"**{i + 1}.** {f}" for i, f in enumerate(frasi))
                await canale.send(
                    embed=discord.Embed(title=(await testo_per(interaction, "acronimi_voto_titolo", pubblica=True, secondi=SECONDI_VOTO))[:256], description=elenco[:4000], color=discord.Color.blurple()),
                    view=voto, allowed_mentions=NESSUNA_MENZIONE,
                )
                await self._attendi(evento, SECONDI_VOTO)
                voto.stop()
                punti_turno = partita.chiudi_turno()
                righe = [f"**{i + 1}.** <@{a}>: {f} ({punti_turno.get(a, 0)})"[:200] for i, (a, f) in enumerate((a, partita.frasi[a]) for a in partita.ordine)]
                await canale.send("\n".join(righe)[:2000], allowed_mentions=NESSUNA_MENZIONE)
            settimana = gare.periodo_settimana()
            for u, p in partita.punti.items():
                await fun_gare_repo.aggiungi_punti(guild_id, "acronimi", settimana, u, p)
            classifica = sorted(partita.punti.items(), key=lambda r: (-r[1], r[0]))
            corpo = gare.testo_classifica(classifica) or await testo_per(interaction, "quiz_nessun_punto", pubblica=True)
            embed = discord.Embed(title=(await testo_per(interaction, "acronimi_fine", pubblica=True))[:256], description=corpo, color=discord.Color.gold())
            await canale.send(embed=embed, allowed_mentions=NESSUNA_MENZIONE)
        except asyncio.CancelledError:
            raise
        except discord.HTTPException:
            logger.warning("Acronimi interrotto nel canale %s.", getattr(canale, "id", 0))
        finally:
            self._attive.discard(canale.id)

    # ---------------- testi di battitura del server ----------------
    @comando_di_gruppo("admin-giochi", nome="aggiungi", descrizione="Aggiunge un testo per la battitura (finestra).", sottogruppo=SOTTOGRUPPI["admin-giochi battitura"])
    @richiedi(Livello.ADMIN)
    async def battitura_aggiungi(self, interaction: discord.Interaction) -> None:
        if not await _attivo(interaction):
            return
        await interaction.response.send_modal(
            ModaleTestoBattitura(await testo_per(interaction, "battitura_finestra"), await testo_per(interaction, "battitura_campo"))
        )

    @comando_di_gruppo("admin-giochi", nome="elenca", descrizione="I testi di battitura del server.", sottogruppo=SOTTOGRUPPI["admin-giochi battitura"])
    @richiedi(Livello.ADMIN)
    async def battitura_elenca(self, interaction: discord.Interaction) -> None:
        if not await _attivo(interaction):
            return
        voci = await battitura_repo.elenco(interaction.guild.id)
        if not voci:
            await interaction.response.send_message(await testo_per(interaction, "battitura_elenco_vuoto"), ephemeral=True)
            return
        await invia_lista(interaction, await testo_per(interaction, "battitura_elenco_titolo"), [f"`{i}` {t}"[:100] for i, t in voci], discord.Color.blurple(), ephemeral=True)

    @comando_di_gruppo("admin-giochi", nome="rimuovi", descrizione="Toglie un testo di battitura.", sottogruppo=SOTTOGRUPPI["admin-giochi battitura"])
    @app_commands.describe(numero="Il numero del testo (lo vedi in elenca)")
    @richiedi(Livello.ADMIN)
    async def battitura_rimuovi(self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 2_000_000_000]) -> None:
        if not await _attivo(interaction):
            return
        fatto = await battitura_repo.rimuovi(interaction.guild.id, numero)
        await interaction.response.send_message(await testo_per(interaction, "battitura_rimosso" if fatto else "battitura_non_trovato"), ephemeral=True)


class ModaleTestoBattitura(BaseModal):
    def __init__(self, titolo: str, etichetta: str) -> None:
        super().__init__(title=titolo[:45])
        self.testo = discord.ui.TextInput(
            label=etichetta[:45], style=discord.TextStyle.paragraph, min_length=gl.MIN_TESTO, max_length=gl.MAX_TESTO, required=True
        )
        self.add_item(self.testo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        testo = " ".join(self.testo.value.split())
        if interaction.guild is None or not gl.testo_valido(testo):
            await interaction.response.send_message(
                await testo_per(interaction, "battitura_testo_non_valido", minimo=gl.PAROLE_MIN, massimo=gl.PAROLE_MAX), ephemeral=True
            )
            return
        nuovo = await battitura_repo.aggiungi(interaction.guild.id, interaction.user.id, testo)
        chiave, extra = ("battitura_aggiunto", {"id": nuovo}) if nuovo else ("battitura_troppi", {"massimo": gl.TETTO_TESTI_SERVER})
        await interaction.response.send_message(await testo_per(interaction, chiave, **extra), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GiochiGruppoCog(bot))
