"""
cogs/fun/blackjack.py
=====================
Blackjack contro il banco (/giochi sfide blackjack): chiedi carta, stai, raddoppia, arrenditi. La puntata
si toglie all'apertura e la partita sta nel database (core/repositories/partite_repo.py): si chiude una
sola volta e, se il bot si ferma, la puntata torna a chi giocava. Solo chi gioca preme i bottoni.
Funzioni coperte: ECO-088, ECO-089
Dipende da: core/blackjack_logic.py
"""

from __future__ import annotations

import logging
import random

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.fun.giochi_monete import PUNTATA_TETTO_ASSOLUTO
from cogs.fun.sfide import SG_SFIDE
from core.blackjack_logic import (
    e_blackjack, gioca_banco, mostra, nuovo_mazzo, restituzione, restituzione_resa, valore,
)
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.database import db
from core.i18n import testo_per
from core.leveling_logic import controlla_puntata
from core.repositories.economia_repo import economia_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.partite_repo import EsitoApertura, partite_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.blackjack")
NESSUNA_MENZIONE = discord.AllowedMentions.none()
RNG = random.SystemRandom()


class BlackjackView(BaseView):
    def __init__(self, partita_id: int, guild_id: int, user_id: int, puntata: int, moneta: str) -> None:
        super().__init__(timeout=120)
        self.partita_id, self.guild_id, self.user_id, self.puntata, self.moneta = partita_id, guild_id, user_id, puntata, moneta
        self.mazzo = nuovo_mazzo(RNG)
        self.giocatore = [self.mazzo.pop(), self.mazzo.pop()]
        self.banco = [self.mazzo.pop(), self.mazzo.pop()]
        self.finito = False
        self.messaggio: discord.Interaction | None = None  # l'interazione del comando, per modificare il messaggio

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(await testo_per(interaction, "bj_non_tua"), ephemeral=True)
            return False
        return True

    def tavolo(self, nascondi: bool = True) -> str:
        banco = f"{mostra(self.banco[:1])} ?" if nascondi else f"{mostra(self.banco)} ({valore(self.banco)})"
        return f"Banco: {banco}\nTu: {mostra(self.giocatore)} ({valore(self.giocatore)})\nPuntata: {self.puntata} {self.moneta}"

    async def _concludi(self, interaction: discord.Interaction | None, resa: bool = False) -> None:
        if self.finito:  # nessun await tra controllo e segno
            return
        self.finito = True
        self.stop()
        if resa:
            ritorno = restituzione_resa(self.puntata)
        else:
            if valore(self.giocatore) <= 21:
                gioca_banco(self.banco, self.mazzo)
            ritorno = restituzione(self.giocatore, self.banco, self.puntata)
        chiusa = await partite_repo.chiudi(self.partita_id, self.guild_id, self.user_id, ritorno)
        for b in self.children:
            b.disabled = True
        if chiusa is None:  # già chiusa (rimborsata): niente da pagare
            esito = "bj_chiusa"
            saldo = 0
        else:
            puntata, saldo = chiusa
            self.puntata = puntata
            try:
                await economia_repo.registra_partita(self.guild_id, self.user_id, "blackjack", puntata, ritorno)
            except Exception:
                logger.warning("Statistiche blackjack non scritte", exc_info=True)
            esito = "bj_vinto" if ritorno > puntata else ("bj_pari" if ritorno == puntata else "bj_perso")
            if resa:
                esito = "bj_resa"
        origine = interaction or self.messaggio
        if origine is None:
            return
        testo = self.tavolo(nascondi=False) + "\n\n" + await testo_per(
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
        await self._concludi(None)  # tempo scaduto: il giocatore sta

    @discord.ui.button(label="Carta", style=discord.ButtonStyle.primary)
    async def carta(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.finito:
            await interaction.response.send_message(await testo_per(interaction, "leveling_gia_fatto"), ephemeral=True)
            return
        self.giocatore.append(self.mazzo.pop())
        self.togli_prime_mosse()
        if valore(self.giocatore) >= 21:
            await self._concludi(interaction)
            return
        await interaction.response.edit_message(content=self.tavolo(), view=self)

    @discord.ui.button(label="Stai", style=discord.ButtonStyle.secondary)
    async def stai(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.finito:
            await interaction.response.send_message(await testo_per(interaction, "leveling_gia_fatto"), ephemeral=True)
            return
        await self._concludi(interaction)

    @discord.ui.button(label="Raddoppia", style=discord.ButtonStyle.success)
    async def raddoppia(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.finito or len(self.giocatore) != 2:
            await interaction.response.send_message(await testo_per(interaction, "leveling_gia_fatto"), ephemeral=True)
            return
        if not await partite_repo.raddoppia(self.partita_id, self.guild_id, self.user_id):
            await interaction.response.send_message(await testo_per(interaction, "bj_no_raddoppio"), ephemeral=True)
            return
        self.puntata *= 2
        self.giocatore.append(self.mazzo.pop())
        await self._concludi(interaction)

    @discord.ui.button(label="Arrenditi", style=discord.ButtonStyle.danger)
    async def arrenditi(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.finito or len(self.giocatore) != 2:
            await interaction.response.send_message(await testo_per(interaction, "leveling_gia_fatto"), ephemeral=True)
            return
        await self._concludi(interaction, resa=True)

    def togli_prime_mosse(self) -> None:
        """Raddoppio e resa valgono solo sulle prime due carte."""
        for b in self.children:
            if b.label in ("Raddoppia", "Arrenditi"):
                b.disabled = True


class BlackjackCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._rimborsi.start()

    def cog_unload(self) -> None:
        self._rimborsi.cancel()
        togli_comandi_del_cog(self)

    @tasks.loop(minutes=5)
    async def _rimborsi(self) -> None:
        try:
            await partite_repo.rimborsa_scadute()
        except Exception:
            logger.exception("Giro dei rimborsi delle partite abbandonate")

    @_rimborsi.before_loop
    async def _prima(self) -> None:
        await self.bot.wait_until_ready()
        try:  # all'avvio: le partite rimaste aperte da un riavvio tornano a chi giocava
            await partite_repo.rimborsa_scadute()
        except Exception:
            logger.exception("Rimborso all'avvio")

    @comando_di_gruppo("giochi", nome="blackjack", descrizione="Blackjack contro il banco: carta, stai, raddoppia, arrenditi.", sottogruppo=SG_SFIDE)
    @app_commands.describe(puntata="Quante monete puntare")
    async def blackjack(self, interaction: discord.Interaction, puntata: app_commands.Range[int, 1, PUNTATA_TETTO_ASSOLUTO]) -> None:
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
        ap = await partite_repo.apri(guild.id, interaction.user.id, "blackjack", puntata, i.attesa_gioco)
        if ap.esito is not EsitoApertura.APERTA:
            chiave = {"gia_aperta": "bj_gia_aperta", "pausa": "coingames_piano_aspetta_ancora_secondi_tra", "poche": "bj_poche"}[ap.esito.value]
            await interaction.response.send_message(await testo_per(interaction, chiave, resto=i.attesa_gioco, coins_total=0, puntata=puntata), ephemeral=True)
            return
        view = BlackjackView(ap.partita_id, guild.id, interaction.user.id, puntata, i.currency_name)
        view.messaggio = interaction
        await interaction.response.send_message(view.tavolo(), view=view, allowed_mentions=NESSUNA_MENZIONE)
        if e_blackjack(view.giocatore) or e_blackjack(view.banco):
            await view._concludi(None)  # naturale: si chiude subito


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BlackjackCog(bot))
