"""
cogs/fun/_combattimento.py
==========================
Il combattimento a più giocatori della sala (/sala combattimento, ECO-105): turni con bottoni (un bottone per ogni
avversario ancora in piedi, pozione e scudo se gli oggetti sono ammessi), chi non muove in tempo esce. A partita
iniziata nessuno annulla (Annulla vale solo nella sala d'attesa): restano il timeout e l'errore, che rimborsano. Le monete le muove solo `SalaCog` (puntate tolte e chiuse in gruppo).
Funzioni coperte: ECO-105
Dipende da: core/combattimento_logic.py, cogs/fun/sala.py (chi lo chiama)
"""

from __future__ import annotations

import asyncio
import time

import discord

from core import combattimento_logic as cb
from core.i18n import testo_per
from core.ui_base import BaseView

NESSUNA_MENZIONE = discord.AllowedMentions.none()
SECONDI_TURNO = 30
PAUSA = 1  # secondi tra un controllo dei tempi e il successivo


class VistaCombattimento(BaseView):
    """Solo chi gioca preme; solo chi è di turno muove. Partita chiusa = nessuna mossa in più."""

    def __init__(self, tv, comb: cb.Combattimento, nomi: dict[int, str], host_id: int, testi: dict[str, str]) -> None:
        super().__init__(timeout=None)
        self.tv, self.comb, self.nomi, self.host_id, self.testi = tv, comb, nomi, host_id, testi
        self.giocatori = set(comb.vite)
        self.ultima_mossa = time.monotonic()
        self.cambiata = asyncio.Event()
        self.ultimo_testo = ""
        self.finita = False  # impostato nello stesso istante della mossa finale, prima di ogni await
        self.ricostruisci()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id not in self.giocatori:
            await interaction.response.send_message(await testo_per(interaction, "sala_non_giochi"), ephemeral=True)
            return False
        return True

    def ricostruisci(self) -> None:
        self.clear_items()
        for n, u in enumerate(self.comb.vivi):
            b = discord.ui.Button(label=f"⚔ {self.nomi[u]}"[:80], style=discord.ButtonStyle.danger, row=n // 4)
            b.callback = self.attacca_a(u)
            self.add_item(b)
        if self.comb.oggetti:
            for chiave, azione, emoji in (("pozione", self._pozione, "🧪"), ("scudo", self._scudo, "🛡")):
                b = discord.ui.Button(label=self.testi.get(chiave, chiave)[:80], emoji=emoji, style=discord.ButtonStyle.success, row=2)
                b.callback = azione
                self.add_item(b)

    # nessun await tra il controllo del turno e la mossa: due clic non muovono due volte
    def attacca_a(self, bersaglio: int):
        async def callback(interaction: discord.Interaction) -> None:
            if self.finita:
                await self._chiusa(interaction)
                return
            esito = self.comb.attacca(interaction.user.id, bersaglio)
            await self._dopo(interaction, esito, bersaglio)
        return callback

    async def _chiusa(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(await testo_per(interaction, "cmb_chiusa"), ephemeral=True)

    async def _pozione(self, interaction: discord.Interaction) -> None:
        if self.finita:
            await self._chiusa(interaction)
            return
        await self._dopo(interaction, self.comb.usa_pozione(interaction.user.id), None)

    async def _scudo(self, interaction: discord.Interaction) -> None:
        if self.finita:
            await self._chiusa(interaction)
            return
        await self._dopo(interaction, self.comb.usa_scudo(interaction.user.id), None)

    async def _dopo(self, interaction: discord.Interaction, esito: str, bersaglio: int | None) -> None:
        if esito == "non_turno":
            await interaction.response.send_message(await testo_per(interaction, "sala_non_tuo_turno"), ephemeral=True)
            return
        if esito in ("bersaglio_no", "no_oggetti", "gia_usata", "gia_usato", "piena"):
            await interaction.response.send_message(await testo_per(interaction, f"cmb_{esito}"), ephemeral=True)
            return
        self.ultima_mossa = time.monotonic()
        finito = self.comb.vincitori is not None
        if finito:  # chiusa subito: nessun await tra la mossa vincente e questo flag
            self.finita = True
        self.ultimo_testo = await testo_per(
            interaction, f"cmb_{esito}", pubblica=True, chi=f"<@{interaction.user.id}>", bersaglio=f"<@{bersaglio}>" if bersaglio else ""
        )
        self.ricostruisci()
        if finito:
            self.stop()
        await interaction.response.edit_message(
            content=await self.testo(interaction), view=None if finito else self, allowed_mentions=NESSUNA_MENZIONE
        )
        self.cambiata.set()

    async def testo(self, interaction: discord.Interaction) -> str:
        vite = "\n".join(
            f"{'💀' if u not in self.comb.vivi else '❤' * self.comb.vite[u]} {self.nomi[u]}{' 🛡' if u in self.comb.scudo else ''}"
            for u in self.comb.vite
        )
        if self.comb.vincitori is not None:
            chiave, valori = "cmb_fine", {"vincitori": " ".join(f"<@{u}>" for u in self.comb.vincitori)}
        else:
            chiave, valori = "cmb_turno", {"chi": f"<@{self.comb.di_turno}>", "secondi": SECONDI_TURNO, "mosse": self.comb.mosse_max - self.comb.mosse}
        corpo = await testo_per(interaction, chiave, pubblica=True, vite=vite, **valori)
        return f"{self.ultimo_testo}\n{corpo}"[:2000]


async def gioca_combattimento(tv) -> dict[int, int]:
    """Il motore della sala: restituisce quanto riceve ciascuno alla chiusura (rimborso a tutti se scade)."""
    regole = tv.regole
    comb = cb.Combattimento(list(tv.giocatori), regole.vite, regole.giri, regole.oggetti, tv.rng)
    nomi = {}
    for u in tv.giocatori:
        membro = tv.interaction.guild.get_member(u)
        nomi[u] = (getattr(membro, "display_name", None) or f"#{u}")[:20]
    testi = {k: await tv.t(f"cmb_b_{k}") for k in ("pozione", "scudo")}
    vista = VistaCombattimento(tv, comb, nomi, tv.interaction.user.id, testi)
    msg = await tv.invia(await vista.testo(tv.interaction), vista)
    while comb.vincitori is None and not tv.scaduto():
        await asyncio.sleep(PAUSA)
        if comb.vincitori is None and time.monotonic() - vista.ultima_mossa > SECONDI_TURNO:
            lento = comb.di_turno
            comb.esci(lento)
            vista.ultima_mossa = time.monotonic()
            vista.ultimo_testo = await tv.t("sala_lento", chi=f"<@{lento}>")
            vista.ricostruisci()
            finito = comb.vincitori is not None
            if finito:
                vista.finita = True
                vista.stop()
            await tv.modifica(msg, await vista.testo(tv.interaction), None if finito else vista)
    vista.finita = True
    vista.stop()
    vincitori = comb.vincitori
    if vincitori is None:
        await tv.modifica(msg, await tv.t("sala_tempo_finito"))
        return {u: tv.puntata for u in tv.giocatori}
    return cb.ripartisci_piatto(list(tv.giocatori), tv.puntata, vincitori)
