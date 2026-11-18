"""
core/music_mondo_view.py
========================
Vista a pagine della radio dal mondo (MUS-010): un menu a tendina con le stazioni della pagina
(al massimo PER_PAGINA, mai oltre 25) e due bottoni per cambiare pagina. La usa solo chi ha dato il comando.
Funzioni coperte: SPEC §9 (catalogo MUS-010)
Dipende da: core/music_radio_mondo.py
"""

from __future__ import annotations

import discord

from core.i18n import t
from core.music_radio_mondo import MAX_PAGINE, PaginaStazioni
from core.ui_base import BaseView


def intestazione_pagina(nome: str, pagina: int, dati: PaginaStazioni, lingua: str) -> str:
    """Il messaggio sopra il menu (entro 2000 caratteri: nome al massimo 60, nessun altro testo libero)."""
    return t("mondo_radio_intestazione", lingua, nome=nome, pagina=pagina + 1)


class RadioMondoView(BaseView):
    """`cerca(nome, pagina)` dà una PaginaStazioni o None; `avvia(interaction, stazione)` mette in coda."""

    def __init__(self, utente_id: int, nome: str, pagina: int, dati: PaginaStazioni, lingua: str, cerca, avvia) -> None:
        super().__init__(timeout=180)
        self.utente_id, self.nome, self.pagina, self.dati = utente_id, nome, pagina, dati
        self.lingua, self._cerca, self._avvia = lingua, cerca, avvia
        self._ricostruisci()

    def _ricostruisci(self) -> None:
        self.clear_items()
        if self.dati.stazioni:
            menu = discord.ui.Select(
                placeholder=t("mondo_radio_placeholder", self.lingua)[:150],
                options=[
                    discord.SelectOption(label=s.nome[:100], description=s.dettaglio[:100], value=str(i))
                    for i, s in enumerate(self.dati.stazioni[:25])
                ],
            )
            menu.callback = self._scelta
            self.add_item(menu)
        prec = discord.ui.Button(label=t("mondo_radio_precedente", self.lingua)[:80],
                                 style=discord.ButtonStyle.secondary, disabled=self.pagina <= 0)
        succ = discord.ui.Button(label=t("mondo_radio_successiva", self.lingua)[:80],
                                 style=discord.ButtonStyle.secondary,
                                 disabled=not self.dati.ha_altre or self.pagina + 1 >= MAX_PAGINE)
        prec.callback, succ.callback = self._precedente, self._successiva
        self.add_item(prec)
        self.add_item(succ)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.utente_id:
            await interaction.response.send_message(t("mondo_radio_di_altri", self.lingua), ephemeral=True)
            return False
        return await super().interaction_check(interaction)

    async def _cambia(self, interaction: discord.Interaction, nuova: int) -> None:
        await interaction.response.defer()
        dati = await self._cerca(self.nome, nuova)
        if dati is None:
            await interaction.followup.send(t("mondo_radio_errore", self.lingua), ephemeral=True)
            return
        self.pagina, self.dati = nuova, dati
        self._ricostruisci()
        await interaction.edit_original_response(content=intestazione_pagina(self.nome, nuova, dati, self.lingua), view=self)

    async def _precedente(self, interaction: discord.Interaction) -> None:
        await self._cambia(interaction, max(0, self.pagina - 1))

    async def _successiva(self, interaction: discord.Interaction) -> None:
        await self._cambia(interaction, self.pagina + 1)

    async def _scelta(self, interaction: discord.Interaction) -> None:
        try:
            stazione = self.dati.stazioni[int(interaction.data["values"][0])]
        except (KeyError, IndexError, ValueError, TypeError):
            await interaction.response.send_message(t("mondo_radio_errore", self.lingua), ephemeral=True)
            return
        await self._avvia(interaction, stazione)


class GenereView(BaseView):
    """
    MUS-014: prima il menu dei generi, poi quello delle playlist del genere scelto (entrambi al massimo 25 voci).
    `gruppi` e' il risultato di `raggruppa`; `avvia(interaction, voce)` mette la playlist in coda.
    """

    def __init__(self, utente_id: int, gruppi: dict, lingua: str, avvia) -> None:
        super().__init__(timeout=180)
        self.utente_id, self.gruppi, self.lingua, self._avvia = utente_id, gruppi, lingua, avvia
        self.genere: str | None = None
        self._ricostruisci()

    def intestazione(self) -> str:
        if self.genere is None:
            return t("mondo_genere_scegli", self.lingua)
        return t("mondo_genere_playlist_di", self.lingua, genere=self.genere)

    def _ricostruisci(self) -> None:
        self.clear_items()
        if self.genere is None:
            opzioni = [
                discord.SelectOption(label=g[:100], description=t("mondo_genere_quante", self.lingua, n=len(v))[:100], value=str(i))
                for i, (g, v) in enumerate(list(self.gruppi.items())[:25])
            ]
            menu = discord.ui.Select(placeholder=t("mondo_genere_placeholder_genere", self.lingua)[:150], options=opzioni)
            menu.callback = self._scelto_genere
        else:
            voci = self.gruppi[self.genere][:25]
            opzioni = [discord.SelectOption(label=v.titolo[:100], value=str(i)) for i, v in enumerate(voci)]
            menu = discord.ui.Select(placeholder=t("mondo_genere_placeholder_playlist", self.lingua)[:150], options=opzioni)
            menu.callback = self._scelta_playlist
        self.add_item(menu)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.utente_id:
            await interaction.response.send_message(t("mondo_radio_di_altri", self.lingua), ephemeral=True)
            return False
        return await super().interaction_check(interaction)

    @staticmethod
    def _indice(interaction: discord.Interaction, massimo: int) -> int | None:
        try:
            i = int(interaction.data["values"][0])
        except (KeyError, IndexError, ValueError, TypeError):
            return None
        return i if 0 <= i < massimo else None

    async def _scelto_genere(self, interaction: discord.Interaction) -> None:
        nomi = list(self.gruppi)[:25]
        i = self._indice(interaction, len(nomi))
        if i is None:
            await interaction.response.send_message(t("mondo_radio_errore", self.lingua), ephemeral=True)
            return
        self.genere = nomi[i]
        self._ricostruisci()
        await interaction.response.edit_message(content=self.intestazione(), view=self)

    async def _scelta_playlist(self, interaction: discord.Interaction) -> None:
        voci = self.gruppi.get(self.genere or "", [])[:25]
        i = self._indice(interaction, len(voci))
        if i is None:
            await interaction.response.send_message(t("mondo_radio_errore", self.lingua), ephemeral=True)
            return
        await self._avvia(interaction, voci[i])
