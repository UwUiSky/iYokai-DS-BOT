"""
core/music_cerca_view.py
========================
Menu di scelta della ricerca (MUS-013): fino a 10 risultati in un menu, legato a chi ha cercato e con scadenza.
Funzioni coperte: SPEC §9 (catalogo MUS-013)
Dipende da: core/music_logic.py (format_duration, truncate_title)
"""

from __future__ import annotations

from dataclasses import dataclass

import discord

from core.i18n import t
from core.music_logic import format_duration, truncate_title

MAX_RISULTATI = 10
SCADENZA_SECONDI = 60.0


@dataclass(frozen=True)
class Risultato:
    titolo: str
    autore: str
    durata_ms: int
    link: str


def risultati_da_tracce(tracce, filtro=None) -> list[Risultato]:
    """Al massimo 10 risultati con un link; `filtro(traccia)` falso = scartata (parole vietate, durata)."""
    fuori: list[Risultato] = []
    for tr in tracce:
        link = getattr(tr, "uri", None)
        if not link or (filtro is not None and not filtro(tr)):
            continue
        fuori.append(Risultato(str(tr.title or "?"), str(getattr(tr, "author", "") or ""), int(tr.length or 0), link))
        if len(fuori) >= MAX_RISULTATI:
            break
    return fuori


class CercaView(discord.ui.View):
    """Un menu con i risultati. Lo usa solo chi ha cercato; dopo la scadenza si spegne."""

    def __init__(self, utente_id: int, risultati: list[Risultato], lingua: str, avvia) -> None:
        super().__init__(timeout=SCADENZA_SECONDI)
        self.utente_id = utente_id
        self.risultati = risultati[:MAX_RISULTATI]
        self.lingua = lingua
        self.avvia = avvia  # async (interaction, Risultato)
        self.messaggio: discord.Message | None = None
        self.scelto = False
        opzioni = [
            discord.SelectOption(
                label=truncate_title(f"{n}. {r.titolo}", 100),
                description=truncate_title(f"{r.autore} · {format_duration(r.durata_ms)}", 100),
                value=str(n - 1),
            )
            for n, r in enumerate(self.risultati, 1)
        ]
        menu = discord.ui.Select(placeholder=t("music_cerca_segnaposto", lingua), options=opzioni, min_values=1, max_values=1)
        menu.callback = self._scelto
        self.add_item(menu)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.utente_id:
            return True
        await interaction.response.send_message(t("music_cerca_non_tuo", self.lingua), ephemeral=True)
        return False

    async def _scelto(self, interaction: discord.Interaction) -> None:
        if self.scelto:  # un solo brano per ricerca, anche con due clic insieme
            await interaction.response.send_message(t("music_cerca_gia_scelto", self.lingua), ephemeral=True)
            return
        self.scelto = True
        try:
            indice = int(interaction.data["values"][0])
            risultato = self.risultati[indice]
        except (KeyError, IndexError, ValueError, TypeError):
            self.scelto = False
            await interaction.response.send_message(t("music_cerca_non_valida", self.lingua), ephemeral=True)
            return
        self.stop()
        for voce in self.children:
            voce.disabled = True
        await self.avvia(interaction, risultato)
        if self.messaggio is not None:
            try:
                await self.messaggio.edit(view=self)
            except discord.HTTPException:
                pass

    async def on_timeout(self) -> None:
        for voce in self.children:
            voce.disabled = True
        if self.messaggio is not None and not self.scelto:
            try:
                await self.messaggio.edit(content=t("music_cerca_scaduta", self.lingua), view=self)
            except discord.HTTPException:
                pass
