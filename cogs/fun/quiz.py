"""
cogs/fun/quiz.py
================
Quiz a domande (#131, D70, B6): `/giochi quiz avvia|classifica` e `/admin-giochi quiz carica|elenca|rimuovi|regole`.
Una partita per canale, risposte con 4 bottoni, una risposta a testa, punti scritti con una sola INSERT.
Domande integrate (videogiochi, cultura, scienza) e domande caricate dal server.
Funzioni coperte: SPEC §16 (FUN-001, 002, 004, 005, 006)
Dipende da: core/quiz_logic.py, core/repositories/quiz_repo.py, core/repositories/fun_gare_repo.py
"""

from __future__ import annotations

import asyncio
import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

from cogs.fun.entertainment import MODULE_FUN
from cogs.leveling._pagine import invia_lista
from core import fun_gare_logic as gare
from core import quiz_logic as q
from core.command_access import Livello, richiedi
from core.command_groups import SOTTOGRUPPI, CogConGruppi, comando_di_gruppo
from core.database import db
from core.i18n import testo_per
from core.repositories.fun_gare_repo import fun_gare_repo
from core.repositories.quiz_repo import quiz_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.quiz")

NESSUNA_MENZIONE = discord.AllowedMentions.none()
PAUSA_FRA_DOMANDE = 3
GARA = "quiz"


class BottoneRisposta(discord.ui.Button):
    def __init__(self, indice: int) -> None:
        super().__init__(label=q.LETTERE[indice], style=discord.ButtonStyle.primary)
        self.indice = indice

    async def callback(self, interaction: discord.Interaction) -> None:
        vista: VistaDomanda = self.view  # type: ignore[assignment]
        if vista.partita.indice != vista.indice:  # clic arrivato (dopo il controllo blacklist) a domanda già chiusa
            await interaction.response.send_message(await testo_per(interaction, "quiz_risposta_tardi"), ephemeral=True)
            return
        nuova = vista.partita.rispondi(interaction.user.id, self.indice)  # sincrona: niente doppio conteggio
        chiave = "quiz_risposta_registrata" if nuova else "quiz_risposta_gia"
        await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)


class VistaDomanda(BaseView):
    def __init__(self, partita: q.PartitaQuiz) -> None:
        super().__init__(timeout=partita.regole.secondi + 15)
        self.partita, self.indice = partita, partita.indice
        for i in range(q.N_RISPOSTE):
            self.add_item(BottoneRisposta(i))

    def spegni(self) -> None:
        for voce in self.children:
            voce.disabled = True  # type: ignore[attr-defined]
        self.stop()


def descrizione_domanda(d: q.DomandaMescolata) -> str:
    righe = [f"**{q.LETTERE[i]}.** {r}" for i, r in enumerate(d.risposte)]
    return f"**{d.testo}**\n\n" + "\n".join(righe)


async def _attivo(interaction: discord.Interaction) -> bool:
    if interaction.guild is None:
        await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
        return False
    if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_FUN):
        await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
        return False
    return True


class QuizCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._rng = random.Random()
        self._attive: set[int] = set()  # canali con una partita in corso
        self._compiti: set[asyncio.Task] = set()

    async def cog_load(self) -> None:
        await super().cog_load()

    async def cog_unload(self) -> None:
        for compito in list(self._compiti):
            compito.cancel()
        await super().cog_unload()

    # ---------------- partita ----------------
    async def _gioca(self, interaction: discord.Interaction, canale, partita: q.PartitaQuiz) -> None:
        guild_id, settimana = interaction.guild.id, gare.periodo_settimana()
        bot_id = self.bot.user.id if self.bot.user else 0
        try:
            while not partita.finita:
                dom = partita.corrente
                if partita.regole.bot_gioca and bot_id:
                    q.fai_giocare_bot(partita, bot_id, self._rng)
                titolo = await testo_per(interaction, "quiz_domanda_titolo", pubblica=True, n=partita.indice + 1, tot=len(partita.domande))
                embed = discord.Embed(title=titolo[:256], description=descrizione_domanda(dom), color=discord.Color.blurple())
                embed.set_footer(text=(await testo_per(interaction, "quiz_domanda_tempo", pubblica=True, secondi=partita.regole.secondi))[:2048])
                vista = VistaDomanda(partita)
                messaggio = await canale.send(embed=embed, view=vista, allowed_mentions=NESSUNA_MENZIONE)
                await asyncio.sleep(partita.regole.secondi)
                vista.spegni()
                giusti = partita.chiudi_domanda()
                for u in giusti:
                    await fun_gare_repo.aggiungi_punti(guild_id, GARA, settimana, u, partita.regole.punti)
                corpo = descrizione_domanda(dom)
                if partita.regole.mostra_risposta:
                    corpo += "\n\n" + await testo_per(interaction, "quiz_risposta_giusta", pubblica=True, lettera=q.LETTERE[dom.giusta], testo=dom.risposte[dom.giusta])
                corpo += "\n" + await testo_per(interaction, "quiz_indovinato", pubblica=True, n=len(giusti))
                embed.description = corpo[:4000]
                try:
                    await messaggio.edit(embed=embed, view=vista)
                except discord.HTTPException:
                    logger.info("Messaggio del quiz non più modificabile.")
                await asyncio.sleep(PAUSA_FRA_DOMANDE)
            classifica = q.classifica_partita(partita.punti)
            corpo = gare.testo_classifica(classifica) or await testo_per(interaction, "quiz_nessun_punto", pubblica=True)
            fine = discord.Embed(title=(await testo_per(interaction, "quiz_fine", pubblica=True))[:256], description=corpo, color=discord.Color.gold())
            await canale.send(embed=fine, allowed_mentions=NESSUNA_MENZIONE)
        except asyncio.CancelledError:
            raise
        except discord.HTTPException:
            logger.warning("Quiz interrotto nel canale %s: il messaggio non parte.", getattr(canale, "id", 0))
        finally:
            self._attive.discard(canale.id)

    @comando_di_gruppo("giochi", nome="avvia", descrizione="Avvia un quiz a domande nel canale.", sottogruppo=SOTTOGRUPPI["giochi quiz"])
    @app_commands.describe(
        domande="Quante domande, da 3 a 15 (di base 5)",
        tema="Da dove prendere le domande (di base: tutte)",
        punti="Punti per ogni risposta giusta, da 1 a 50 (di base: regole del server)",
        secondi="Secondi per domanda, da 10 a 120 (di base: regole del server)",
    )
    @app_commands.choices(
        tema=[
            app_commands.Choice(name="Videogiochi", value="videogiochi"),
            app_commands.Choice(name="Cultura", value="cultura"),
            app_commands.Choice(name="Scienza", value="scienza"),
            app_commands.Choice(name="Domande del server", value="server"),
            app_commands.Choice(name="Tutte", value="tutte"),
        ]
    )
    async def quiz_avvia(
        self,
        interaction: discord.Interaction,
        domande: app_commands.Range[int, 3, 15] = 5,
        tema: app_commands.Choice[str] | None = None,
        punti: app_commands.Range[int, 1, 50] | None = None,
        secondi: app_commands.Range[int, 10, 120] | None = None,
    ) -> None:
        if not await _attivo(interaction):
            return
        canale = interaction.channel
        if not isinstance(canale, discord.abc.Messageable) or canale is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        if canale.id in self._attive:  # segnato prima di ogni await: due comandi insieme non fanno due partite
            await interaction.response.send_message(await testo_per(interaction, "quiz_gia_in_corso"), ephemeral=True)
            return
        self._attive.add(canale.id)
        try:
            await interaction.response.defer()
            valore = tema.value if tema is not None else "tutte"
            if valore == "server":
                pool = await quiz_repo.domande(interaction.guild.id)
            elif valore == "tutte":
                pool = q.domande_integrate() + await quiz_repo.domande(interaction.guild.id)
            else:
                pool = q.domande_integrate(valore)
            if len(pool) < q.DOMANDE_PARTITA[0]:
                self._attive.discard(canale.id)
                await interaction.followup.send(await testo_per(interaction, "quiz_poche_domande", minimo=q.DOMANDE_PARTITA[0]), ephemeral=True)
                return
            regole = await quiz_repo.regole(interaction.guild.id)
            if punti is not None:
                regole.punti = punti
            if secondi is not None:
                regole.secondi = secondi
            partita = q.PartitaQuiz(q.scegli(pool, domande, self._rng), regole)
            await interaction.followup.send(await testo_per(interaction, "quiz_inizio", pubblica=True, n=len(partita.domande), secondi=regole.secondi))
        except BaseException:
            self._attive.discard(canale.id)
            raise
        compito = asyncio.create_task(self._gioca(interaction, canale, partita))
        self._compiti.add(compito)
        compito.add_done_callback(self._compiti.discard)

    @comando_di_gruppo("giochi", nome="classifica", descrizione="Classifica del quiz: questa settimana o di sempre.", sottogruppo=SOTTOGRUPPI["giochi quiz"])
    @app_commands.describe(vista="Quale classifica (di base: questa settimana)")
    @app_commands.choices(vista=[app_commands.Choice(name="Questa settimana", value="settimana"), app_commands.Choice(name="Di sempre", value="sempre")])
    async def quiz_classifica(self, interaction: discord.Interaction, vista: app_commands.Choice[str] | None = None) -> None:
        if not await _attivo(interaction):
            return
        sempre = vista is not None and vista.value == "sempre"
        if sempre:
            righe = await fun_gare_repo.classifica_sempre(interaction.guild.id, GARA)
        else:
            righe = await fun_gare_repo.classifica(interaction.guild.id, GARA, gare.periodo_settimana())
        chiave = "quiz_classifica_sempre" if sempre else "quiz_classifica_settimana"
        corpo = gare.testo_classifica(righe) or await testo_per(interaction, "quiz_nessun_punto", pubblica=True)
        embed = discord.Embed(title=(await testo_per(interaction, chiave, pubblica=True))[:256], description=corpo, color=discord.Color.gold())
        await interaction.response.send_message(embed=embed, allowed_mentions=NESSUNA_MENZIONE)

    # ---------------- admin ----------------
    @comando_di_gruppo("admin-giochi", nome="carica", descrizione="Carica domande per il quiz da un file CSV o JSON.", sottogruppo=SOTTOGRUPPI["admin-giochi quiz"])
    @app_commands.describe(file="CSV (domanda, giusta, 3 sbagliate, tema) o JSON, al massimo 100 KB e 300 domande per server")
    @richiedi(Livello.ADMIN)
    async def quiz_carica(self, interaction: discord.Interaction, file: discord.Attachment) -> None:
        if not await _attivo(interaction):
            return
        if file.size > q.MAX_BYTE_FILE:
            await interaction.response.send_message(await testo_per(interaction, "quiz_file_grande"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            domande = q.leggi_file(await file.read(), file.filename or "")
        except q.FileErrato as errore:
            await interaction.followup.send(await testo_per(interaction, str(errore)))
            return
        except discord.HTTPException:
            await interaction.followup.send(await testo_per(interaction, "quiz_file_illeggibile"))
            return
        if not await quiz_repo.aggiungi(interaction.guild.id, interaction.user.id, domande):
            await interaction.followup.send(await testo_per(interaction, "quiz_file_troppe", massimo=q.MAX_DOMANDE_SERVER))
            return
        await interaction.followup.send(await testo_per(interaction, "quiz_file_caricato", n=len(domande)))

    @comando_di_gruppo("admin-giochi", nome="elenca", descrizione="Le domande del quiz caricate dal server.", sottogruppo=SOTTOGRUPPI["admin-giochi quiz"])
    @richiedi(Livello.ADMIN)
    async def quiz_elenca(self, interaction: discord.Interaction) -> None:
        if not await _attivo(interaction):
            return
        voci = await quiz_repo.elenco(interaction.guild.id)
        if not voci:
            await interaction.response.send_message(await testo_per(interaction, "quiz_elenco_vuoto"), ephemeral=True)
            return
        righe = [f"`{i}` {('[' + t + '] ') if t else ''}{d}"[:100] for i, t, d in voci]
        await invia_lista(interaction, await testo_per(interaction, "quiz_elenco_titolo"), righe, discord.Color.blurple(), ephemeral=True)

    @comando_di_gruppo("admin-giochi", nome="rimuovi", descrizione="Toglie una domanda caricata dal server.", sottogruppo=SOTTOGRUPPI["admin-giochi quiz"])
    @app_commands.describe(numero="Il numero della domanda (lo vedi in elenca)")
    @richiedi(Livello.ADMIN)
    async def quiz_rimuovi(self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 2_000_000_000]) -> None:
        if not await _attivo(interaction):
            return
        fatto = await quiz_repo.rimuovi(interaction.guild.id, numero)
        await interaction.response.send_message(await testo_per(interaction, "quiz_rimossa" if fatto else "quiz_non_trovata"), ephemeral=True)

    @comando_di_gruppo("admin-giochi", nome="regole", descrizione="Regole del quiz: punti, tempo, risposta mostrata, il bot gioca.", sottogruppo=SOTTOGRUPPI["admin-giochi quiz"])
    @app_commands.describe(
        punti="Punti per risposta giusta, da 1 a 50", secondi="Secondi per domanda, da 10 a 120",
        mostra_risposta="Mostrare la risposta giusta a fine domanda", bot_gioca="Il bot gioca e compare in classifica",
    )
    @richiedi(Livello.ADMIN)
    async def quiz_regole(
        self,
        interaction: discord.Interaction,
        punti: app_commands.Range[int, 1, 50] | None = None,
        secondi: app_commands.Range[int, 10, 120] | None = None,
        mostra_risposta: bool | None = None,
        bot_gioca: bool | None = None,
    ) -> None:
        if not await _attivo(interaction):
            return
        if punti is None and secondi is None and mostra_risposta is None and bot_gioca is None:
            regole = await quiz_repo.regole(interaction.guild.id)
        else:
            regole = await quiz_repo.imposta_regole(interaction.guild.id, punti, secondi, mostra_risposta, bot_gioca)
        sì = await testo_per(interaction, "quiz_si")
        no = await testo_per(interaction, "quiz_no")
        await interaction.response.send_message(
            await testo_per(
                interaction, "quiz_regole_attuali", punti=regole.punti, secondi=regole.secondi,
                mostra=sì if regole.mostra_risposta else no, bot=sì if regole.bot_gioca else no,
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(QuizCog(bot))
