"""
cogs/fun/giochi_passi.py
========================
Giochi a più passi con incasso libero: /giochi sfide alto-basso (più alto o più basso) e /giochi sfide torre.
La puntata sta nel database (core/repositories/partite_repo.py): si chiude una sola volta e, se il bot si
ferma, torna a chi giocava. Solo chi gioca preme i bottoni; allo scadere del tempo si incassa quel che c'è.
Funzioni coperte: ECO-094, ECO-098
Dipende da: core/passi_logic.py
"""

from __future__ import annotations

import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

from cogs.fun.giochi_monete import PUNTATA_TETTO_ASSOLUTO
from cogs.fun.sfide import SG_SFIDE
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.database import db
from core.i18n import testo_per
from core.leveling_logic import controlla_puntata
from core.passi_logic import (
    TORRE_PROBABILITA, estrai_carta, incasso, indovinato, moltiplicatore_passo, passo_possibile,
    torre_crolla, torre_moltiplicatore,
)
from core.repositories.economia_repo import economia_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.partite_repo import EsitoApertura, partite_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.giochi_passi")
NESSUNA_MENZIONE = discord.AllowedMentions.none()
RNG = random.SystemRandom()
SIMBOLI = {1: "A", 11: "J", 12: "Q", 13: "K"}


class PartitaView(BaseView):
    """Base: chiusura unica, solo il giocatore, scadenza = incasso."""

    nome_gioco = ""

    def __init__(self, partita_id: int, guild_id: int, user_id: int, puntata: int, moneta: str) -> None:
        super().__init__(timeout=120)
        self.partita_id, self.guild_id, self.user_id, self.puntata, self.moneta = partita_id, guild_id, user_id, puntata, moneta
        self.finito = False
        self.messaggio: discord.Interaction | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(await testo_per(interaction, "bj_non_tua"), ephemeral=True)
            return False
        return True

    def ritorno_attuale(self) -> int:  # da ridefinire
        return 0

    def tavolo(self) -> str:  # da ridefinire
        return ""

    async def _concludi(self, interaction: discord.Interaction | None, ritorno: int, riga: str = "") -> None:
        if self.finito:  # nessun await tra controllo e segno
            return
        self.finito = True
        self.stop()
        for b in self.children:
            b.disabled = True
        chiusa = await partite_repo.chiudi(self.partita_id, self.guild_id, self.user_id, ritorno)
        if chiusa is None:
            esito, saldo = "bj_chiusa", 0
        else:
            _, saldo = chiusa
            try:
                await economia_repo.registra_partita(self.guild_id, self.user_id, self.nome_gioco, self.puntata, ritorno)
            except Exception:
                logger.warning("Statistiche non scritte", exc_info=True)
            esito = "bj_vinto" if ritorno > self.puntata else ("bj_pari" if ritorno == self.puntata else "bj_perso")
        origine = interaction or self.messaggio
        if origine is None:
            return
        testo = f"{self.tavolo()}\n{riga}\n\n" + await testo_per(
            origine, esito, importo=abs(ritorno - self.puntata), moneta=self.moneta, saldo=saldo, pubblica=True
        )
        try:
            if interaction is not None:
                await interaction.response.edit_message(content=testo, view=self, allowed_mentions=NESSUNA_MENZIONE)
            else:
                await self.messaggio.edit_original_response(content=testo, view=self)
        except discord.HTTPException:
            pass

    async def on_timeout(self) -> None:
        await self._concludi(None, self.ritorno_attuale())

    async def _gia_fatto(self, interaction: discord.Interaction) -> bool:
        if self.finito:
            await interaction.response.send_message(await testo_per(interaction, "leveling_gia_fatto"), ephemeral=True)
            return True
        return False


def _carta(c: int) -> str:
    return SIMBOLI.get(c, str(c))


class AltoBassoView(PartitaView):
    nome_gioco = "alto-basso"

    def __init__(self, *a) -> None:
        super().__init__(*a)
        self.carta = estrai_carta(RNG)
        self.moltiplicatore = 1.0
        self.indovinate = 0
        self._aggiorna_bottoni()

    def ritorno_attuale(self) -> int:
        return incasso(self.puntata, self.moltiplicatore) if self.indovinate else 0

    def tavolo(self) -> str:
        return f"🃏 Carta: **{_carta(self.carta)}** · risposte giuste: {self.indovinate} · incasso: {self.ritorno_attuale()} {self.moneta}"

    def _aggiorna_bottoni(self) -> None:
        self.alto.disabled = not passo_possibile(self.carta, "alto")
        self.basso.disabled = not passo_possibile(self.carta, "basso")
        self.incassa.disabled = self.indovinate == 0

    async def _passo(self, interaction: discord.Interaction, scelta: str) -> None:
        if await self._gia_fatto(interaction):
            return
        nuova = estrai_carta(RNG)
        if not indovinato(self.carta, nuova, scelta):
            vecchia, self.carta = self.carta, nuova
            await self._concludi(interaction, 0, f"Era **{_carta(nuova)}** dopo {_carta(vecchia)}.")
            return
        self.moltiplicatore *= moltiplicatore_passo(self.carta, scelta)
        self.carta = nuova
        self.indovinate += 1
        self._aggiorna_bottoni()
        if self.alto.disabled and self.basso.disabled:  # nessuna mossa possibile: si incassa
            await self._concludi(interaction, self.ritorno_attuale())
            return
        await interaction.response.edit_message(content=self.tavolo(), view=self)

    @discord.ui.button(label="Più alta", style=discord.ButtonStyle.primary)
    async def alto(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._passo(interaction, "alto")

    @discord.ui.button(label="Più bassa", style=discord.ButtonStyle.primary)
    async def basso(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._passo(interaction, "basso")

    @discord.ui.button(label="Incassa", style=discord.ButtonStyle.success)
    async def incassa(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if await self._gia_fatto(interaction):
            return
        await self._concludi(interaction, self.ritorno_attuale())


class TorreView(PartitaView):
    nome_gioco = "torre"

    def __init__(self, *a) -> None:
        super().__init__(*a)
        self.piani = 0
        self.incassa.disabled = True

    def ritorno_attuale(self) -> int:
        return incasso(self.puntata, torre_moltiplicatore(self.piani)) if self.piani else 0

    def tavolo(self) -> str:
        return f"🗼 Piano **{self.piani}**/{len(TORRE_PROBABILITA)} · incasso: {self.ritorno_attuale()} {self.moneta}"

    @discord.ui.button(label="Sali", style=discord.ButtonStyle.primary)
    async def sali(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if await self._gia_fatto(interaction):
            return
        if torre_crolla(self.piani + 1, RNG):
            self.piani += 1
            await self._concludi(interaction, 0, "💥 La torre è crollata!")
            return
        self.piani += 1
        self.incassa.disabled = False
        if self.piani >= len(TORRE_PROBABILITA):  # in cima: si incassa da soli
            await self._concludi(interaction, self.ritorno_attuale(), "🏆 Sei in cima!")
            return
        await interaction.response.edit_message(content=self.tavolo(), view=self)

    @discord.ui.button(label="Incassa", style=discord.ButtonStyle.success)
    async def incassa(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if await self._gia_fatto(interaction):
            return
        await self._concludi(interaction, self.ritorno_attuale())


class GiochiPassiCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def cog_unload(self) -> None:
        togli_comandi_del_cog(self)

    async def _avvia(self, interaction: discord.Interaction, gioco: str, classe, puntata: int) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        for modulo in ("fun", "leveling"):
            if not await db.is_module_active_for_guild(guild.id, modulo):
                await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
                return
        i = (await leveling_settings_repo.get_config(guild.id)).impostazioni
        motivo = controlla_puntata(puntata, i)
        if motivo is not None:
            await interaction.response.send_message(f"❌ {motivo}", ephemeral=True)
            return
        ap = await partite_repo.apri(guild.id, interaction.user.id, gioco, puntata, i.attesa_gioco)
        if ap.esito is not EsitoApertura.APERTA:
            chiave = {"gia_aperta": "bj_gia_aperta", "pausa": "coingames_piano_aspetta_ancora_secondi_tra", "poche": "bj_poche"}[ap.esito.value]
            await interaction.response.send_message(await testo_per(interaction, chiave, resto=i.attesa_gioco, coins_total=0, puntata=puntata), ephemeral=True)
            return
        view = classe(ap.partita_id, guild.id, interaction.user.id, puntata, i.currency_name)
        view.messaggio = interaction
        await interaction.response.send_message(view.tavolo(), view=view, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("giochi", nome="alto-basso", descrizione="Più alta o più bassa? Il premio cresce a ogni risposta giusta.", sottogruppo=SG_SFIDE)
    @app_commands.describe(puntata="Quante monete puntare")
    async def alto_basso(self, interaction: discord.Interaction, puntata: app_commands.Range[int, 1, PUNTATA_TETTO_ASSOLUTO]) -> None:
        await self._avvia(interaction, "alto-basso", AltoBassoView, puntata)

    @comando_di_gruppo("giochi", nome="torre", descrizione="Sali la torre: ogni piano rende di più, ma può crollare.", sottogruppo=SG_SFIDE)
    @app_commands.describe(puntata="Quante monete puntare")
    async def torre(self, interaction: discord.Interaction, puntata: app_commands.Range[int, 1, PUNTATA_TETTO_ASSOLUTO]) -> None:
        await self._avvia(interaction, "torre", TorreView, puntata)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GiochiPassiCog(bot))
