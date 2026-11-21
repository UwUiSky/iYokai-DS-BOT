"""
core/anti_automazione.py
========================
Controllo anti-automazione nei comandi di guadagno (ECO-158): con una probabilità scelta dal server (di base spento)
il comando si ferma e chiede di premere il bottone con il risultato giusto di una somma semplice; chi risponde
bene è «verificato» per 10 minuti e può ripetere il comando. Niente moneta si muove prima della verifica.
Funzioni coperte: ECO-158
"""

from __future__ import annotations

import random
import time

import discord

from core.i18n import testo_per
from core.ui_base import BaseView

RNG = random.SystemRandom()
DURATA_VERIFICA = 600.0
MAX_VERIFICATI = 5000
_verificati: dict[tuple[int, int], float] = {}


def somma_con_scelte(rng: random.Random) -> tuple[str, list[int], int]:
    """(domanda, tre risposte mescolate, risposta giusta). Le risposte sbagliate sono sempre diverse tra loro e dalla giusta."""
    a, b = rng.randint(2, 9), rng.randint(2, 9)
    giusta = a + b
    sbagliate = set()
    while len(sbagliate) < 2:
        v = giusta + rng.choice((-3, -2, -1, 1, 2, 3))
        if v != giusta and v > 0:
            sbagliate.add(v)
    scelte = [giusta, *sbagliate]
    rng.shuffle(scelte)
    return f"{a} + {b}", scelte, giusta


def e_verificato(guild_id: int, user_id: int, adesso: float | None = None) -> bool:
    scade = _verificati.get((guild_id, user_id))
    return scade is not None and (adesso if adesso is not None else time.monotonic()) < scade


def segna_verificato(guild_id: int, user_id: int) -> None:
    if len(_verificati) >= MAX_VERIFICATI:
        _verificati.clear()
    _verificati[(guild_id, user_id)] = time.monotonic() + DURATA_VERIFICA


class SfidaView(BaseView):
    def __init__(self, guild_id: int, user_id: int, scelte: list[int], giusta: int) -> None:
        super().__init__(timeout=60)
        self.guild_id, self.user_id, self.giusta = guild_id, user_id, giusta
        self.usata = False
        for n in scelte:
            b = discord.ui.Button(label=str(n), style=discord.ButtonStyle.secondary)
            b.callback = self._risposta(n)
            self.add_item(b)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(await testo_per(interaction, "bj_non_tua"), ephemeral=True)
            return False
        return True

    def _risposta(self, valore: int):
        async def _cb(interaction: discord.Interaction) -> None:
            if self.usata:  # un solo tentativo per sfida
                await interaction.response.send_message(await testo_per(interaction, "leveling_gia_fatto"), ephemeral=True)
                return
            self.usata = True
            self.stop()
            for b in self.children:
                b.disabled = True
            if valore == self.giusta:
                segna_verificato(self.guild_id, self.user_id)
                testo = await testo_per(interaction, "aut_ok")
            else:
                testo = await testo_per(interaction, "aut_no")
            await interaction.response.edit_message(content=testo, view=self)
        return _cb


async def serve_controllo(interaction: discord.Interaction, per_mille: int, rng: random.Random = RNG) -> bool:
    """
    Vero (dopo aver risposto con la sfida) se il comando deve fermarsi. Falso se si può procedere: controllo spento,
    persona già verificata o tiro fortunato. Solo nei server.
    """
    if per_mille <= 0 or interaction.guild is None:
        return False
    g, u = interaction.guild.id, interaction.user.id
    if e_verificato(g, u) or rng.randint(1, 1000) > per_mille:
        return False
    domanda, scelte, giusta = somma_con_scelte(rng)
    await interaction.response.send_message(
        await testo_per(interaction, "aut_sfida", domanda=domanda), view=SfidaView(g, u, scelte, giusta), ephemeral=True
    )
    return True
