"""
cogs/utility/ping.py
======================
QUESTO FILE È IL MODELLO DI RIFERIMENTO per ogni futuro cog.

Non fa niente di speciale (un comando /ping), ma mostra per intero
il pattern che TUTTI i cog del progetto devono seguire:

  1. Registrazione nel PremiumRegistry (anche se il modulo è gratis
     per sempre, si registra comunque con premium_capable=False,
     così compare nella lista del pannello owner)
  2. Come funziona il controllo "il server ha questo modulo attivo?"
     — che è il sostituto del "carica/scarica il cog per server"
     della bozza iniziale, che sul serio non è possibile (vedi nota
     più sotto)
  3. Dove va il decorator @requires_module quando un domani il
     modulo diventerà premium-capable

NOTA IMPORTANTE sul perché il check è così e non "carica solo i cog
del server X": in discord.py un'estensione (load_extension) viene
caricata UNA VOLTA nel processo, non per singolo server — un bot è
connesso a migliaia di server con lo stesso processo Python, non ha
"un'istanza per server" da scaricare selettivamente. Il modo corretto
di ottenere lo stesso risultato (un modulo attivo solo dove il server
lo ha scelto) è: il cog è sempre caricato, ma ogni suo comando
controlla per primo se il server ha quel modulo attivo, e se non lo
ha, si comporta come se il comando non esistesse.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.premium import PremiumModule, registry


# Nome univoco di questo modulo, usato ovunque nel file: nella
# registrazione premium, nel controllo "è attivo per questo server",
# nel pannello di setup. Sceglierlo con cura, perché cambiarlo dopo
# significa una migration sui dati salvati (vedi guild_config.modules).
MODULE_NAME = "utility_ping"


class PingCog(commands.Cog):
    """
    Un singolo comando di test. Ogni cog reale del progetto avrà
    più comandi, ma la struttura della classe resta questa.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _is_enabled_here(self, guild_id: int) -> bool:
        """
        Helper privato: il server ha attivato questo modulo dal
        pannello di setup? Ogni cog reale avrà un metodo identico
        a questo (o lo erediterà da una classe base comune, quando
        il numero di cog lo giustificherà).
        """
        return await db.is_module_active_for_guild(guild_id, MODULE_NAME)

    @app_commands.command(
        name="ping",
        description="Controlla se iYokai Main è online e la sua latenza.",
    )
    async def ping(self, interaction: discord.Interaction) -> None:
        # Passo 1: il modulo è attivo su questo server?
        # (per un comando così basilare avrebbe senso lasciarlo
        # sempre attivo di default, ma il controllo è mostrato qui
        # per completezza del modello — ogni cog VERO lo farà così)
        if interaction.guild is not None:
            enabled = await self._is_enabled_here(interaction.guild.id)
            if not enabled:
                await interaction.response.send_message(
                    "Questo modulo non è attivo su questo server. "
                    "Un amministratore può attivarlo con /setup.",
                    ephemeral=True,
                )
                return

        # Passo 2: logica vera e propria del comando
        latency_ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(
            f"Pong! Latenza: {latency_ms}ms"
        )

        # Se in futuro questo diventasse un modulo premium, la riga
        # sopra "if not enabled: return" resterebbe INVARIATA: la
        # gestione premium si aggiunge con il decorator
        # @requires_module(MODULE_NAME) sulla definizione del metodo,
        # non modificando la logica interna. Esempio (commentato,
        # non attivo, solo per mostrare dove andrebbe):
        #
        #   @app_commands.command(...)
        #   @requires_module(MODULE_NAME)
        #   async def ping(self, interaction): ...


async def setup(bot: commands.Bot) -> None:
    """
    Punto di ingresso richiesto da discord.py per caricare il cog.
    Qui avviene anche la registrazione nel PremiumRegistry: ogni
    cog SI AUTO-REGISTRA al momento del proprio caricamento, così
    main.py non deve conoscere la lista di tutti i moduli premium
    esistenti — la scopre dai cog stessi.
    """
    registry.register(
        PremiumModule(
            name=MODULE_NAME,
            display_name="Ping",
            description="Comando di test per la latenza del bot.",
            premium_capable=False,  # questo resterà SEMPRE gratis
        )
    )
    await bot.add_cog(PingCog(bot))
