"""
cogs/utility/livelli_comandi.py
===============================
`/premium` e `/vip`: elencano i comandi per livello di abbonamento (D57). I due comandi
esistono nell'albero solo quando serve: finché nessuna funzione è premium o VIP non si
registrano. Quando un livello cambia (core/livelli_funzione.py) il cog li aggiunge o li
toglie e chiede una sola sincronizzazione, con attesa, per i limiti di Discord.
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


async def _premium(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(livelli.testo_elenco((livelli.PREMIUM,)), ephemeral=True)


async def _vip(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(livelli.testo_elenco((livelli.VIP5, livelli.VIP20)), ephemeral=True)


def crea_comandi() -> tuple[app_commands.Command, app_commands.Command]:
    premium = app_commands.Command(name="premium", description="I comandi del livello Premium", callback=_premium)
    vip = app_commands.Command(name="vip", description="I comandi dei livelli VIP 5 e VIP 20", callback=_vip)
    return premium, vip


class LivelliComandiCog(commands.Cog):
    def __init__(self, bot: commands.Bot, sincronizzatore: SincronizzatoreDifferito | None = None) -> None:
        self.bot = bot
        self._premium, self._vip = crea_comandi()
        self.sincronizzatore = sincronizzatore or SincronizzatoreDifferito(self._sincronizza)

    async def cog_load(self) -> None:
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
