"""
cogs/utility/livelli_comandi.py
===============================
`/premium` e `/vip` (D57): due gruppi con pochi sotto-comandi fissi (`elenco`, `info`), l'elenco
a pagine. I comandi premium non si spostano qui: restano nel loro gruppo. I due gruppi esistono
nell'albero solo quando serve: finché nessuna funzione è premium o VIP non si registrano. Quando
un livello cambia (core/livelli_funzione.py) il cog li aggiunge o li toglie e chiede una sola
sincronizzazione, con attesa, per i limiti di Discord.
Funzioni coperte: D57, D56
Dipende da: core/livelli_funzione.py, core/command_sync.py
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core import livelli_funzione as livelli
from core.command_sync import SincronizzatoreDifferito, StatoSyncDatabase, sincronizza_all_avvio
from core.config import config
from core.database import db

logger = logging.getLogger(__name__)


LIVELLI_PREMIUM = (livelli.PREMIUM,)
LIVELLI_VIP = (livelli.VIP5, livelli.VIP20)


def _embed_pagina(titolo: str, livelli_scelti: tuple[str, ...], area: str | None, pagina: int) -> tuple[discord.Embed, list, int]:
    righe = livelli.righe_per_area(livelli_scelti, area)
    n = livelli.numero_pagine(righe)
    pagina = min(max(pagina, 0), n - 1)
    embed = discord.Embed(title=titolo[:256], description=livelli.testo_pagina(righe, pagina))
    embed.set_footer(text=f"Pagina {pagina + 1} di {n}" + (f" · area: {area}" if area else ""))
    return embed, livelli.voci_pagina(righe, pagina), pagina


class ElencoLivelliView(discord.ui.View):
    """Elenco a pagine: bottoni avanti e indietro, menu (al massimo 25 voci) per vedere una funzione."""

    def __init__(self, titolo: str, livelli_scelti: tuple[str, ...], area: str | None, autore_id: int, pagina: int = 0) -> None:
        super().__init__(timeout=300)
        self.titolo, self.livelli_scelti, self.area, self.autore_id = titolo, livelli_scelti, area, autore_id
        self.embed, voci, self.pagina = _embed_pagina(titolo, livelli_scelti, area, pagina)
        n = livelli.numero_pagine(livelli.righe_per_area(livelli_scelti, area))
        self.indietro.disabled = self.pagina <= 0
        self.avanti.disabled = self.pagina >= n - 1
        if voci:
            self.menu.options = [
                discord.SelectOption(label=nome[:100], value=str(i), description=", ".join(p for p in percorsi)[:100])
                for i, (_, nome, percorsi) in enumerate(voci[: livelli.MAX_SUGGERIMENTI])
            ]
            self._voci = voci
        else:
            self.remove_item(self.menu)
            self._voci = []

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.autore_id:
            await interaction.response.send_message("Questo elenco è di un altro utente.", ephemeral=True)
            return False
        return True

    async def _vai(self, interaction: discord.Interaction, pagina: int) -> None:
        vista = ElencoLivelliView(self.titolo, self.livelli_scelti, self.area, self.autore_id, pagina)
        await interaction.response.edit_message(embed=vista.embed, view=vista)

    @discord.ui.button(label="Indietro", style=discord.ButtonStyle.secondary, row=1)
    async def indietro(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._vai(interaction, self.pagina - 1)

    @discord.ui.button(label="Avanti", style=discord.ButtonStyle.secondary, row=1)
    async def avanti(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._vai(interaction, self.pagina + 1)

    @discord.ui.select(placeholder="Scegli una funzione", row=0, options=[discord.SelectOption(label="-", value="0")])
    async def menu(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        livello, nome, percorsi = self._voci[int(select.values[0])]
        testo = livelli.riga_voce(livello, nome, percorsi)
        await interaction.response.send_message(testo[:2000], ephemeral=True)


def _testo_info(livelli_scelti: tuple[str, ...]) -> str:
    etichette = ", ".join(livelli.ETICHETTE[x] for x in livelli_scelti)
    return (
        f"Le funzioni del livello {etichette} restano nel loro gruppo di comandi: "
        "quando le usi, il bot controlla il livello e ti dice se manca. "
        "Con `elenco` le vedi tutte, a pagine; con `area` scegli un gruppo di comandi."
    )


def _gruppo(nome: str, descrizione: str, livelli_scelti: tuple[str, ...]) -> app_commands.Group:
    gruppo = app_commands.Group(name=nome, description=descrizione, guild_only=True)
    titolo = f"Comandi {nome.upper() if nome == 'vip' else nome.capitalize()}"

    async def _completa_area(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return [app_commands.Choice(name=a, value=a) for a in livelli.aree_disponibili(livelli_scelti, current)]

    @gruppo.command(name="elenco", description="I comandi di questo livello, a pagine")
    @app_commands.describe(area="Solo i comandi di un gruppo (es. assistente)")
    @app_commands.autocomplete(area=_completa_area)
    async def elenco(interaction: discord.Interaction, area: app_commands.Range[str, 1, 32] | None = None) -> None:
        vista = ElencoLivelliView(titolo, livelli_scelti, area, interaction.user.id)
        await interaction.response.send_message(embed=vista.embed, view=vista, ephemeral=True)

    @gruppo.command(name="info", description="Come funzionano i livelli")
    async def info(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(_testo_info(livelli_scelti), ephemeral=True)

    return gruppo


def crea_gruppi() -> tuple[app_commands.Group, app_commands.Group]:
    return (
        _gruppo("premium", "Funzioni Premium: elenco e informazioni", LIVELLI_PREMIUM),
        _gruppo("vip", "Funzioni VIP 5 e VIP 20: elenco e informazioni", LIVELLI_VIP),
    )


class LivelliComandiCog(commands.Cog):
    def __init__(self, bot: commands.Bot, sincronizzatore: SincronizzatoreDifferito | None = None) -> None:
        self.bot = bot
        self._premium, self._vip = crea_gruppi()
        self.sincronizzatore = sincronizzatore or SincronizzatoreDifferito(self._sincronizza, pronto=bot.wait_until_ready)

    async def cog_load(self) -> None:
        try:
            await livelli.carica_livelli()
        except Exception:
            logger.exception("Livelli delle funzioni non letti: tutto gratuito")
        self.aggiorna_albero()  # prima della sync d'avvio: nessuna sync in più
        livelli.aggiungi_ascoltatore(self._al_cambio)

    async def cog_unload(self) -> None:
        livelli.togli_ascoltatore(self._al_cambio)
        self.sincronizzatore.ferma()
        for comando in (self._premium, self._vip):
            if self.bot.tree.get_command(comando.name) is comando:
                self.bot.tree.remove_command(comando.name)

    def aggiorna_albero(self) -> bool:
        """Mette o toglie `/premium` e `/vip` secondo i livelli. True se l'albero è cambiato."""
        cambiato = False
        for comando, serve in ((self._premium, livelli.serve_premium()), (self._vip, livelli.serve_vip())):
            presente = self.bot.tree.get_command(comando.name) is comando
            if serve and not presente:
                self.bot.tree.add_command(comando, override=True)
                cambiato = True
            elif not serve and presente:
                self.bot.tree.remove_command(comando.name)
                cambiato = True
        return cambiato

    def _al_cambio(self) -> None:
        if self.aggiorna_albero():
            self.sincronizzatore.richiedi()

    async def _sincronizza(self) -> None:
        guild_owner = None
        if config.MAIN_GUILD_ID and self.bot.tree.get_command("owner", guild=discord.Object(id=config.MAIN_GUILD_ID)):
            guild_owner = config.MAIN_GUILD_ID
        await sincronizza_all_avvio(
            self.bot.tree,
            guild_sviluppo_id=config.MAIN_GUILD_ID if config.is_development else None,
            guild_owner_id=guild_owner,
            stato=StatoSyncDatabase(db.pool),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LivelliComandiCog(bot))
