"""
cogs.utility._command_search_views.py
====================================
Interfaccia del pannello di -cerca-comando (issue #147): bottoni delle
categorie (a pagine), elenco dei comandi di una categoria, bottone wiki.

Limiti rispettati: al massimo 20 bottoni categoria (righe 0-3) più frecce e
wiki nella riga 4 = 23 componenti (massimo 25), 5 bottoni per riga, 5 righe.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import discord

from core import command_search_logic as logica
from core.ui_base import BaseView

TIMEOUT = 300
PER_RIGA = 5
ETICHETTA_WIKI = "Apri nella wiki"


@dataclass
class DatiPannello:
    """Una fotografia presa all'apertura del pannello (valida per i 5 minuti di vita dei bottoni)."""

    categorie: list[str]
    comandi: dict[str, list[logica.ComandoInfo]]
    ids: dict[str, int]
    ultimo: str | None
    in_dm: bool
    wiki_base: str | None = None
    lingua: str = "it"
    extra: dict = field(default_factory=dict)

    def embed(self) -> discord.Embed:
        return logica.embed_pannello(self.ultimo, self.ids, in_dm=self.in_dm, lingua=self.lingua)


def bottone_wiki(wiki_base: str | None, percorso: str | None = None) -> discord.ui.Button | None:
    url = logica.url_wiki(wiki_base, percorso)
    if url is None:
        return None
    return discord.ui.Button(label=ETICHETTA_WIKI, style=discord.ButtonStyle.link, url=url)


class _Categoria(discord.ui.Button):
    def __init__(self, dati: DatiPannello, nome: str, riga: int) -> None:
        super().__init__(label=nome[:80], style=discord.ButtonStyle.secondary, row=riga)
        self.dati = dati
        self.nome = nome

    async def callback(self, interaction: discord.Interaction) -> None:
        view = CategoriaView(self.dati, self.nome, 0)
        await interaction.response.edit_message(embed=view.embed, view=view)


class _Freccia(discord.ui.Button):
    def __init__(self, etichetta: str, destinazione: int, abilitata: bool, costruisci) -> None:
        super().__init__(label=etichetta, style=discord.ButtonStyle.primary, row=4, disabled=not abilitata)
        self.destinazione = destinazione
        self.costruisci = costruisci

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.costruisci(self.destinazione)
        await interaction.response.edit_message(embed=view.embed, view=view)


class PannelloView(BaseView):
    def __init__(self, dati: DatiPannello, indice: int = 0) -> None:
        super().__init__(timeout=TIMEOUT)
        self.dati = dati
        nomi, indice, totale = logica.pagina(dati.categorie, indice, logica.CATEGORIE_PER_PAGINA)
        self.embed = dati.embed()
        for posizione, nome in enumerate(nomi):
            self.add_item(_Categoria(dati, nome, posizione // PER_RIGA))
        if totale > 1:
            costruisci = lambda n: PannelloView(dati, n)  # noqa: E731
            self.add_item(_Freccia("◀", indice - 1, indice > 0, costruisci))
            self.add_item(_Freccia("▶", indice + 1, indice < totale - 1, costruisci))
        wiki = bottone_wiki(dati.wiki_base)
        if wiki is not None:
            wiki.row = 4
            self.add_item(wiki)


class _Indietro(discord.ui.Button):
    def __init__(self, dati: DatiPannello) -> None:
        super().__init__(label="Indietro", style=discord.ButtonStyle.secondary, row=1)
        self.dati = dati

    async def callback(self, interaction: discord.Interaction) -> None:
        view = PannelloView(self.dati)
        await interaction.response.edit_message(embed=view.embed, view=view)


class CategoriaView(BaseView):
    def __init__(self, dati: DatiPannello, nome: str, indice: int) -> None:
        super().__init__(timeout=TIMEOUT)
        comandi = dati.comandi.get(nome, [])
        self.embed, indice, totale = logica.embed_categoria(nome, comandi, dati.ids, indice, dati.lingua)
        if totale > 1:
            costruisci = lambda n: CategoriaView(dati, nome, n)  # noqa: E731
            for etichetta, dest, ok in (("◀", indice - 1, indice > 0), ("▶", indice + 1, indice < totale - 1)):
                freccia = _Freccia(etichetta, dest, ok, costruisci)
                freccia.row = 0
                self.add_item(freccia)
        self.add_item(_Indietro(dati))
        wiki = bottone_wiki(dati.wiki_base, nome if nome != "generali" else None)
        if wiki is not None:
            wiki.row = 1
            self.add_item(wiki)


class RisultatiView(BaseView):
    """Sotto i risultati di una ricerca: solo il bottone wiki del primo risultato."""

    def __init__(self, wiki_base: str | None, percorso: str) -> None:
        super().__init__(timeout=TIMEOUT)
        wiki = bottone_wiki(wiki_base, percorso)
        if wiki is not None:
            self.add_item(wiki)
