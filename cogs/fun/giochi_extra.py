"""
cogs/fun/giochi_extra.py
========================
Giochi piccoli del gruppo /giochi (#131, D70): `/giochi minato`, `/giochi dado`, `/giochi spinner`,
`/giochi mazzo` e `/admin-giochi punteggi azzera`. Nessuna puntata e nessuna moneta: i giochi di fortuna
non si monetizzano.
Funzioni coperte: SPEC §16 (FUN-003, 009, 015, 016, 018)
Dipende da: core/fun_piccoli_logic.py, core/fun_gare_logic.py, core/repositories/fun_gare_repo.py
"""

from __future__ import annotations

import asyncio
import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

from cogs.fun.entertainment import MODULE_FUN
from core import fun_piccoli_logic as piccoli
from core import fun_gare_logic as gare
from core.command_access import Livello, puo_usare, richiedi
from core.command_groups import SOTTOGRUPPI, CogConGruppi, comando_di_gruppo
from core.database import db
from core.i18n import testo_per
from core.repositories.fun_gare_repo import fun_gare_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.giochi_extra")

NESSUNA_MENZIONE = discord.AllowedMentions.none()
SECONDI_VISTA = 120
SECONDI_FRA_MODIFICHE = 3  # Discord: al massimo una modifica ogni pochi secondi sullo stesso messaggio
_FOTOGRAMMI = ("🌀", "🔄", "🔁", "🔃")


class VistaSpinner(BaseView):
    """Un solo bottone «Gira», solo per chi ha dato il comando; un solo giro per messaggio."""

    def __init__(self, autore_id: int, guild_id: int, rng: random.Random, etichetta: str) -> None:
        super().__init__(timeout=SECONDI_VISTA)
        self.autore_id, self.guild_id, self._rng = autore_id, guild_id, rng
        self._partito = False
        self.gira.label = etichetta[:45]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.autore_id:
            await interaction.response.send_message(await testo_per(interaction, "fun_solo_chi_gioca"), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Gira", style=discord.ButtonStyle.primary, emoji="🌀")
    async def gira(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._partito:  # segnato prima di ogni await: un doppio clic non fa due giri
            return
        self._partito = True
        self.stop()
        secondi = gare.durata_spinner(self._rng)
        if not await fun_gare_repo.registra_giro(self.guild_id, interaction.user.id, gare.periodo_settimana(), secondi):
            await interaction.response.edit_message(
                content=await testo_per(interaction, "fun_spinner_attesa", pubblica=True), view=None
            )
            return
        await interaction.response.edit_message(
            content=await testo_per(interaction, "fun_spinner_gira", pubblica=True, secondi=secondi), view=None
        )
        trascorsi = 0
        while trascorsi < secondi:
            passo = min(SECONDI_FRA_MODIFICHE, secondi - trascorsi)
            await asyncio.sleep(passo)
            trascorsi += passo
            if trascorsi < secondi:
                try:
                    await interaction.edit_original_response(content=f"{_FOTOGRAMMI[(trascorsi // SECONDI_FRA_MODIFICHE) % 4]} {secondi - trascorsi}s")
                except discord.HTTPException:
                    break
        classifica = await fun_gare_repo.classifica(self.guild_id, "spinner", gare.periodo_settimana())
        testo = await testo_per(interaction, "fun_spinner_fine", pubblica=True, secondi=secondi)
        try:
            await interaction.edit_original_response(
                content=f"{testo}\n{gare.testo_classifica(classifica, 's')}"[:2000], allowed_mentions=NESSUNA_MENZIONE
            )
        except discord.HTTPException:
            logger.info("Messaggio dello spinner non più modificabile.")


class ConfermaAzzera(BaseView):
    """Due tasti, un solo clic valido, solo per chi ha dato il comando; il livello si ricontrolla al clic."""

    def __init__(self, autore_id: int, guild_id: int, gara: str | None) -> None:
        super().__init__(timeout=60)
        self.autore_id, self.guild_id, self.gara = autore_id, guild_id, gara
        self._chiuso = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.autore_id:
            await interaction.response.send_message(await testo_per(interaction, "conteggio_non_e_tuo"), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Conferma", style=discord.ButtonStyle.danger)
    async def conferma(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._chiuso:
            return
        self._chiuso = True
        self.stop()
        if not await puo_usare(interaction, Livello.ADMIN):
            await interaction.response.edit_message(content=await testo_per(interaction, "conteggio_non_e_tuo"), view=None)
            return
        righe = await fun_gare_repo.azzera(self.guild_id, self.gara)
        logger.info("Punteggi azzerati: server %s, gara %s, righe %s, da %s.", self.guild_id, self.gara or "tutte", righe, interaction.user.id)
        await interaction.response.edit_message(
            content=await testo_per(interaction, "fun_punteggi_azzerati", righe=righe), view=None
        )

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def annulla(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._chiuso:
            return
        self._chiuso = True
        self.stop()
        await interaction.response.edit_message(content=await testo_per(interaction, "fun_punteggi_annullato"), view=None)


class GiochiExtraCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._rng = random.Random()

    async def _modulo_attivo(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_FUN):
            await interaction.response.send_message(
                await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True
            )
            return False
        return True

    @comando_di_gruppo("giochi", nome="minato", descrizione="Campo minato: tocca gli spoiler ed evita le mine.")
    @app_commands.describe(difficolta="Quanto è grande il campo (di base: facile)")
    @app_commands.choices(
        difficolta=[
            app_commands.Choice(name="Facile (5x5)", value="facile"),
            app_commands.Choice(name="Medio (7x7)", value="medio"),
            app_commands.Choice(name="Difficile (9x9)", value="difficile"),
        ]
    )
    async def minato(
        self, interaction: discord.Interaction, difficolta: app_commands.Choice[str] | None = None
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return
        livello = difficolta.value if difficolta is not None else "facile"
        campo = piccoli.crea_minato(livello, self._rng)
        mine = piccoli.MINATO_LIVELLI[livello][1]
        intestazione = await testo_per(interaction, "fun_minato_intro", pubblica=True, mine=mine)
        await interaction.response.send_message(
            f"{intestazione}\n{piccoli.testo_minato(campo)}"[: piccoli.MAX_MESSAGGIO],
            allowed_mentions=NESSUNA_MENZIONE,
        )

    @comando_di_gruppo("giochi", nome="dado", descrizione="Un tiro al giorno da 1 a 100 e la classifica del server.")
    @app_commands.describe(vista="Quale classifica mostrare (di base: oggi)")
    @app_commands.choices(
        vista=[
            app_commands.Choice(name="Oggi", value="oggi"),
            app_commands.Choice(name="Ieri", value="ieri"),
            app_commands.Choice(name="Sempre", value="sempre"),
        ]
    )
    async def dado(self, interaction: discord.Interaction, vista: app_commands.Choice[str] | None = None) -> None:
        if not await self._modulo_attivo(interaction):
            return
        guild_id, valore_vista = interaction.guild.id, vista.value if vista is not None else "oggi"
        oggi = gare.periodo_giorno()
        nuovo = await fun_gare_repo.prova_dado(guild_id, interaction.user.id, oggi, self._rng.randint(1, gare.DADO_FACCE))
        if nuovo is not None:
            esito = await testo_per(interaction, "fun_dado_tiro", pubblica=True, valore=nuovo)
        else:
            gia = await fun_gare_repo.tiro_del_giorno(guild_id, interaction.user.id, oggi)
            esito = await testo_per(interaction, "fun_dado_gia", pubblica=True, valore=gia or 0)
        if valore_vista == "sempre":
            righe = await fun_gare_repo.classifica_sempre(guild_id, "dado")
        else:
            righe = await fun_gare_repo.classifica(guild_id, "dado", gare.periodo_giorno(giorni_fa=1 if valore_vista == "ieri" else 0))
        titolo = await testo_per(interaction, f"fun_dado_vista_{valore_vista}", pubblica=True)
        corpo = gare.testo_classifica(righe) or await testo_per(interaction, "fun_classifica_vuota", pubblica=True)
        embed = discord.Embed(title=titolo[:256], description=corpo, color=discord.Color.gold())
        await interaction.response.send_message(f"{interaction.user.mention} {esito}"[:2000], embed=embed, allowed_mentions=discord.AllowedMentions(users=[interaction.user]))

    @comando_di_gruppo("giochi", nome="spinner", descrizione="Fai girare lo spinner: vince chi lo fa girare più a lungo.")
    async def spinner(self, interaction: discord.Interaction) -> None:
        if not await self._modulo_attivo(interaction):
            return
        etichetta = await testo_per(interaction, "fun_spinner_bottone", pubblica=True)
        await interaction.response.send_message(
            await testo_per(interaction, "fun_spinner_intro", pubblica=True),
            view=VistaSpinner(interaction.user.id, interaction.guild.id, self._rng, etichetta),
        )

    @comando_di_gruppo("giochi", nome="mazzo", descrizione="Un mazzo di 52 carte per il server: pesca, rimescola, controlla.")
    @app_commands.describe(azione="Cosa fare (di base: pesca)", quante="Quante carte pescare, da 1 a 10")
    @app_commands.choices(
        azione=[
            app_commands.Choice(name="Pesca", value="pesca"),
            app_commands.Choice(name="Rimescola", value="rimescola"),
            app_commands.Choice(name="Carte restanti", value="restanti"),
        ]
    )
    async def mazzo(
        self,
        interaction: discord.Interaction,
        azione: app_commands.Choice[str] | None = None,
        quante: app_commands.Range[int, 1, gare.MAX_PESCA] = 1,
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return
        guild_id, cosa = interaction.guild.id, azione.value if azione is not None else "pesca"
        if cosa == "rimescola":
            await fun_gare_repo.rimescola(guild_id, self._rng)
            testo = await testo_per(interaction, "fun_mazzo_rimescolato", pubblica=True)
        elif cosa == "restanti":
            testo = await testo_per(interaction, "fun_mazzo_restanti", pubblica=True, n=await fun_gare_repo.carte_restanti(guild_id))
        else:
            carte, resto = await fun_gare_repo.pesca(guild_id, quante, self._rng)
            if not carte:
                testo = await testo_per(interaction, "fun_mazzo_finito", pubblica=True)
            else:
                elenco = " ".join(f"`{gare.carta_testo(c)}`" for c in carte)
                testo = await testo_per(interaction, "fun_mazzo_pescate", pubblica=True, carte=elenco, n=resto)
        await interaction.response.send_message(testo[:2000], allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("admin-giochi", nome="azzera", descrizione="Azzera i punteggi di una gara (con conferma).", sottogruppo=SOTTOGRUPPI["admin-giochi punteggi"])
    @app_commands.describe(gara="Quale gara azzerare")
    @app_commands.choices(
        gara=[app_commands.Choice(name="Dado", value="dado"), app_commands.Choice(name="Spinner", value="spinner"), app_commands.Choice(name="Tutte", value="tutte")]
    )
    @richiedi(Livello.ADMIN)
    async def punteggi_azzera(self, interaction: discord.Interaction, gara: app_commands.Choice[str]) -> None:
        if not await self._modulo_attivo(interaction):
            return
        vista = ConfermaAzzera(interaction.user.id, interaction.guild.id, None if gara.value == "tutte" else gara.value)
        await interaction.response.send_message(
            await testo_per(interaction, "fun_punteggi_domanda", gara=gara.name), view=vista, ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GiochiExtraCog(bot))
