"""
cogs/fun/carte.py
=================
Gioco di carte «Frasi a sorpresa» (#131, D70, B8): `/giochi carte avvia` e `/admin-giochi carte pacchetti`.
Sala d'attesa da 3 a 10 giocatori, mano di 7 carte aperta da un bottone (ogni clic è un messaggio nascosto nuovo,
quindi niente scadenza dei 15 minuti), risposte anonime numerate, scelta del giudice o voto di tutti.
Il pacchetto «adulti» è spento di base e parte solo in un canale con limite d'età.
Funzioni coperte: SPEC §16 (FUN-007, 008)
Dipende da: core/carte_logic.py, cogs/fun/_lobby.py, core/repositories/fun_impostazioni_repo.py
"""

from __future__ import annotations

import asyncio
import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

from cogs.fun._lobby import apri_lobby
from cogs.fun.entertainment import MODULE_FUN
from core import carte_logic as cl
from core import fun_gare_logic as gare
from core.command_access import Livello, richiedi
from core.command_groups import SOTTOGRUPPI, CogConGruppi, comando_di_gruppo
from core.database import db
from core.i18n import testo_per
from core.repositories.fun_gare_repo import fun_gare_repo
from core.repositories.fun_impostazioni_repo import fun_impostazioni_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.carte")

NESSUNA_MENZIONE = discord.AllowedMentions.none()
SECONDI_LOBBY = 60
SECONDI_GIOCATA = 60
SECONDI_SCELTA = 45
PAUSA_FRA_ROUND = 4


async def _attivo(interaction: discord.Interaction) -> bool:
    if interaction.guild is None:
        await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
        return False
    if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_FUN):
        await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
        return False
    return True


class MenuCarte(discord.ui.Select):
    def __init__(self, mano: list[str], segnaposto: str) -> None:
        opzioni = [discord.SelectOption(label=c[:100], value=str(i)) for i, c in enumerate(mano[: cl.CARTE_IN_MANO])]
        super().__init__(placeholder=segnaposto[:150], options=opzioni, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        vista: VistaCarte = self.view  # type: ignore[assignment]
        esito = vista.partita.gioca(interaction.user.id, int(self.values[0]))  # sincrona: una carta sola
        await interaction.response.edit_message(content=await testo_per(interaction, f"carte_gioca_{esito}"), view=None)
        if esito == "ok" and len(vista.partita.giocate) >= len(vista.partita.chi_gioca()):
            vista.evento.set()


class VistaCarte(BaseView):
    """La mano di chi ha cliccato: un menu con le sue carte, in un messaggio nascosto nuovo."""

    def __init__(self, partita: cl.PartitaCarte, evento: asyncio.Event, mano: list[str], segnaposto: str) -> None:
        super().__init__(timeout=SECONDI_GIOCATA)
        self.partita, self.evento = partita, evento
        self.add_item(MenuCarte(mano, segnaposto))


class VistaMano(BaseView):
    def __init__(self, partita: cl.PartitaCarte, evento: asyncio.Event, etichetta: str, segnaposto: str) -> None:
        super().__init__(timeout=SECONDI_GIOCATA + 15)
        self.partita, self.evento, self._segnaposto = partita, evento, segnaposto
        self.mano.label = etichetta[:45]

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="🃏")
    async def mano(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        p, u = self.partita, interaction.user.id
        if u not in p.giocatori:
            chiave = "carte_gioca_non_giocatore"
        elif u == p.giudice:
            chiave = "carte_gioca_giudice"
        elif u in p.giocate:
            chiave = "carte_gioca_gia"
        else:
            await interaction.response.send_message(
                await testo_per(interaction, "carte_scegli_carta"),
                view=VistaCarte(p, self.evento, p.mani[u], self._segnaposto), ephemeral=True,
            )
            return
        await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)


class BottoneScelta(discord.ui.Button):
    def __init__(self, indice: int) -> None:
        super().__init__(label=str(indice + 1), style=discord.ButtonStyle.secondary, row=indice // 5)
        self.indice = indice

    async def callback(self, interaction: discord.Interaction) -> None:
        vista: VistaScelta = self.view  # type: ignore[assignment]
        p = vista.partita
        esito = p.scegli(interaction.user.id, self.indice)
        await interaction.response.send_message(await testo_per(interaction, f"carte_scelta_{esito}"), ephemeral=True)
        if p.scelte_fatte() >= p.votanti():
            vista.evento.set()


class VistaScelta(BaseView):
    def __init__(self, partita: cl.PartitaCarte, evento: asyncio.Event, quante: int) -> None:
        super().__init__(timeout=SECONDI_SCELTA + 15)
        self.partita, self.evento = partita, evento
        for i in range(min(quante, cl.MAX_GIOCATORI)):
            self.add_item(BottoneScelta(i))


class CarteCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._rng = random.Random()
        self._attive: set[int] = set()
        self._compiti: set[asyncio.Task] = set()

    async def cog_load(self) -> None:
        await super().cog_load()

    async def cog_unload(self) -> None:
        for compito in list(self._compiti):
            compito.cancel()
        await super().cog_unload()

    async def _lobby(self, interaction: discord.Interaction, **kw) -> list[int] | None:
        return await apri_lobby(interaction, cl.MIN_GIOCATORI, cl.MAX_GIOCATORI, "carte_intro", SECONDI_LOBBY, **kw)

    @comando_di_gruppo("giochi", nome="avvia", descrizione="Gioco di carte: completa la frase con la carta più divertente.", sottogruppo=SOTTOGRUPPI["giochi carte"])
    @app_commands.describe(
        pacchetto="Quali carte usare (di base: tutte quelle accese nel server)",
        punti="Punti per vincere, da 2 a 10 (di base 5)",
        modo="Chi sceglie la risposta migliore (di base: un giudice a turno)",
    )
    @app_commands.choices(
        pacchetto=[
            app_commands.Choice(name="Tutti", value="tutti"), app_commands.Choice(name="Base", value="base"),
            app_commands.Choice(name="Nerd", value="nerd"), app_commands.Choice(name="Gamer", value="gamer"),
            app_commands.Choice(name="Adulti (solo canali con limite d'età)", value="adulti"),
        ],
        modo=[app_commands.Choice(name="Giudice a turno", value="giudice"), app_commands.Choice(name="Voto di tutti", value="voto")],
    )
    async def carte_avvia(
        self,
        interaction: discord.Interaction,
        pacchetto: app_commands.Choice[str] | None = None,
        punti: app_commands.Range[int, cl.PUNTI_MIN, cl.PUNTI_MAX] = 5,
        modo: app_commands.Choice[str] | None = None,
    ) -> None:
        if not await _attivo(interaction):
            return
        canale = interaction.channel
        if canale is None or not isinstance(canale, discord.abc.Messageable):
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        if canale.id in self._attive:  # segnato prima di ogni await
            await interaction.response.send_message(await testo_per(interaction, "gruppo_gia_in_corso"), ephemeral=True)
            return
        self._attive.add(canale.id)
        try:
            testo_pacchetti, adulti_ok = await fun_impostazioni_repo.carte(interaction.guild.id)
            con_limite = bool(getattr(canale, "is_nsfw", lambda: False)())
            scelta = pacchetto.value if pacchetto is not None else "tutti"
            accesi = [p for p in cl.pacchetti_attivi(scelta, adulti_ok, con_limite) if p == cl.PACCHETTO_ADULTI or p in cl.pacchetti_dal_testo(testo_pacchetti)]
            if not accesi:
                chiave = "carte_adulti_no" if scelta == cl.PACCHETTO_ADULTI else "carte_pacchetto_spento"
                await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)
                self._attive.discard(canale.id)
                return
            await interaction.response.defer()
        except BaseException:
            self._attive.discard(canale.id)
            raise
        self._lancia(self._gioca(interaction, canale, accesi, punti, modo.value if modo is not None else "giudice"))

    def _lancia(self, coro) -> None:
        compito = asyncio.create_task(coro)
        self._compiti.add(compito)
        compito.add_done_callback(self._compiti.discard)

    async def _attendi(self, evento: asyncio.Event, secondi: int) -> None:
        try:
            await asyncio.wait_for(evento.wait(), secondi)
        except TimeoutError:
            pass

    async def _gioca(self, interaction: discord.Interaction, canale, pacchetti: list[str], punti: int, modo: str) -> None:
        guild_id = interaction.guild.id
        try:
            giocatori = await self._lobby(interaction, punti=punti, modo=await testo_per(interaction, f"carte_modo_{modo}", pubblica=True))
            if not giocatori:
                await canale.send(await testo_per(interaction, "gruppo_annullato", pubblica=True))
                return
            nere, bianche = cl.mazzi(pacchetti, self._rng)
            if len(bianche) < cl.bianche_necessarie(len(giocatori)):
                await canale.send(await testo_per(interaction, "carte_poche", pubblica=True, n=len(giocatori)))
                return
            partita = cl.PartitaCarte(giocatori, punti, modo, nere, bianche, self._rng)
            etichetta = await testo_per(interaction, "carte_mie", pubblica=True)
            segnaposto = await testo_per(interaction, "carte_scegli_carta", pubblica=True)
            while not partita.finita():
                nera = partita.nuovo_round()
                evento = asyncio.Event()
                vista = VistaMano(partita, evento, etichetta, segnaposto)
                if modo == "giudice":
                    testa = await testo_per(interaction, "carte_round_giudice", pubblica=True, n=partita.round, giudice=f"<@{partita.giudice}>", secondi=SECONDI_GIOCATA)
                else:
                    testa = await testo_per(interaction, "carte_round_voto", pubblica=True, n=partita.round, secondi=SECONDI_GIOCATA)
                embed = discord.Embed(description=nera[:4000], color=discord.Color.dark_grey())
                await canale.send(testa[:2000], embed=embed, view=vista, allowed_mentions=discord.AllowedMentions(users=[discord.Object(partita.giudice)]) if partita.giudice else NESSUNA_MENZIONE)
                await self._attendi(evento, SECONDI_GIOCATA)
                vista.stop()
                if len(partita.giocate) < (1 if modo == "giudice" else 2):
                    await canale.send(await testo_per(interaction, "carte_round_vuoto", pubblica=True))
                    continue
                risposte = partita.apri_scelta()
                evento = asyncio.Event()
                scelta_v = VistaScelta(partita, evento, len(risposte))
                elenco = "\n".join(f"**{i + 1}.** {cl.riempi(nera, r)}" for i, r in enumerate(risposte))
                chiave = "carte_scelta_giudice" if modo == "giudice" else "carte_scelta_voto"
                titolo = await testo_per(interaction, chiave, pubblica=True, secondi=SECONDI_SCELTA)
                await canale.send(embed=discord.Embed(title=titolo[:256], description=elenco[:4000], color=discord.Color.blurple()), view=scelta_v, allowed_mentions=NESSUNA_MENZIONE)
                await self._attendi(evento, SECONDI_SCELTA)
                scelta_v.stop()
                vincitore = partita.chiudi_round()
                if vincitore is None:
                    await canale.send(await testo_per(interaction, "carte_round_vuoto", pubblica=True))
                else:
                    frase = cl.riempi(nera, partita.giocate[vincitore])
                    await canale.send(
                        (await testo_per(interaction, "carte_round_vinto", pubblica=True, vincitore=f"<@{vincitore}>", frase=frase))[:2000],
                        allowed_mentions=NESSUNA_MENZIONE,
                    )
                await asyncio.sleep(PAUSA_FRA_ROUND)
            settimana = gare.periodo_settimana()
            for u, p in partita.punti.items():
                await fun_gare_repo.aggiungi_punti(guild_id, "carte", settimana, u, p)
            classifica = sorted(partita.punti.items(), key=lambda r: (-r[1], r[0]))
            corpo = gare.testo_classifica(classifica) or await testo_per(interaction, "quiz_nessun_punto", pubblica=True)
            embed = discord.Embed(title=(await testo_per(interaction, "carte_fine", pubblica=True))[:256], description=corpo, color=discord.Color.gold())
            await canale.send(embed=embed, allowed_mentions=NESSUNA_MENZIONE)
        except asyncio.CancelledError:
            raise
        except discord.HTTPException:
            logger.warning("Partita di carte interrotta nel canale %s.", getattr(canale, "id", 0))
        finally:
            self._attive.discard(canale.id)

    @comando_di_gruppo("admin-giochi", nome="pacchetti", descrizione="Quali pacchetti di carte sono accesi nel server.", sottogruppo=SOTTOGRUPPI["admin-giochi carte"])
    @app_commands.describe(
        base="Pacchetto base", nerd="Pacchetto nerd", gamer="Pacchetto gamer",
        adulti="Pacchetto adulti (spento di base, parte solo in un canale con limite d'età)",
    )
    @richiedi(Livello.ADMIN)
    async def carte_pacchetti(
        self, interaction: discord.Interaction, base: bool | None = None, nerd: bool | None = None,
        gamer: bool | None = None, adulti: bool | None = None,
    ) -> None:
        if not await _attivo(interaction):
            return
        testo, _ = await fun_impostazioni_repo.carte(interaction.guild.id)
        accesi = set(cl.pacchetti_dal_testo(testo))
        for nome, valore in (("base", base), ("nerd", nerd), ("gamer", gamer)):
            if valore is True:
                accesi.add(nome)
            elif valore is False:
                accesi.discard(nome)
        if not accesi:
            await interaction.response.send_message(await testo_per(interaction, "carte_serve_uno"), ephemeral=True)
            return
        nuovo = ",".join(p for p in cl.PACCHETTI if p in accesi)
        testo, adulti_ok = await fun_impostazioni_repo.imposta_carte(interaction.guild.id, nuovo, adulti)
        sì, no = await testo_per(interaction, "quiz_si"), await testo_per(interaction, "quiz_no")
        await interaction.response.send_message(
            await testo_per(interaction, "carte_pacchetti_attuali", pacchetti=testo.replace(",", ", "), adulti=sì if adulti_ok else no), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CarteCog(bot))
