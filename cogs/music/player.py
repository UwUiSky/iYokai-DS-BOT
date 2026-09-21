"""
cogs/music/player.py
=======================
Music (SPEC.md §9), via wavelink 3.x + Lavalink. Connessione a nodi
PUBBLICI gratuiti in fallback (decisione presa con l'utente — vedi
PROGRESS.md), non self-hosting di Lavalink sulla stessa VM del bot.

Limite onesto, dichiarato qui perché vale per l'intero file: non è
possibile testare in questo ambiente una connessione vera a un nodo
Lavalink né al gateway voce di Discord (nessun server del genere
raggiungibile dal sandbox di sviluppo). I test coprono quello che è
verificabile senza una connessione live — i controlli di guardia
(utente non in vocale, modulo disattivato) — e la logica pura in
core/music_logic.py. Il resto va verificato una volta distribuito.
"""

from __future__ import annotations

import asyncio
import logging

import discord
import wavelink
from discord import app_commands
from discord.ext import commands

from core.config import config
from core.database import db
from core.music_logic import (
    DEFAULT_PUBLIC_LAVALINK_NODES,
    LavalinkNodeConfig,
    build_queue_display,
    format_duration,
    parse_lavalink_nodes,
)
from core.premium import PremiumModule, registry

logger = logging.getLogger("iyokai.music")

MODULE_MUSIC = "music"
DEFAULT_VOLUME = 100


def _build_lavalink_nodes() -> list[wavelink.Node]:
    """
    Ordine deciso con l'utente: nodi PUBBLICI gratuiti in cascata per
    primi (DEFAULT_PUBLIC_LAVALINK_NODES — verificati con una ricerca,
    vedi core/music_logic.py per la provenienza e l'avviso di
    riverificarli periodicamente), eventuali nodi extra configurati
    in LAVALINK_NODES, e il nodo locale/self-hostato dell'utente
    (LAVALINK_HOST/PORT/PASSWORD) SEMPRE per ultimo — provato solo se
    tutti i nodi pubblici sopra falliscono o non rispondono, così non
    si carica inutilmente la macchina che ospita anche il bot stesso
    quando un nodo pubblico basta.
    """
    nodi_config: list[LavalinkNodeConfig] = list(
        parse_lavalink_nodes(DEFAULT_PUBLIC_LAVALINK_NODES)
    )
    nodi_config.extend(parse_lavalink_nodes(config.LAVALINK_NODES))

    uri_locale = f"http://{config.LAVALINK_HOST}:{config.LAVALINK_PORT}"
    nodi_config.append(LavalinkNodeConfig(uri=uri_locale, password=config.LAVALINK_PASSWORD))

    return [wavelink.Node(uri=nodo.uri, password=nodo.password) for nodo in nodi_config]


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ================================================================
    # Eventi wavelink
    # ================================================================
    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload) -> None:
        logger.info("Nodo Lavalink pronto: %s", payload.node.uri)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload) -> None:
        player = payload.player
        if player is None:
            return
        if not player.queue.is_empty:
            prossima = await player.queue.get_wait()
            await player.play(prossima)

    # ================================================================
    # Comandi
    # ================================================================
    async def _controlli_base(self, interaction: discord.Interaction) -> bool:
        """
        Vero se l'utente può usare i comandi musicali qui: dentro un
        server, con il modulo attivo, in un canale vocale. Condiviso
        da tutti i comandi che agiscono su una riproduzione — non
        duplicato in ognuno.
        """
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return False

        if not await db.is_module_active_for_guild(guild.id, MODULE_MUSIC):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /setup.",
                ephemeral=True,
            )
            return False

        if not isinstance(interaction.user, discord.Member) or interaction.user.voice is None:
            await interaction.response.send_message(
                "Devi essere in un canale vocale per usare questo comando.", ephemeral=True
            )
            return False

        return True

    @app_commands.command(name="play", description="Riproduce una canzone o playlist.")
    @app_commands.describe(query="Nome della canzone, URL, o termine di ricerca")
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        if not await self._controlli_base(interaction):
            return

        await interaction.response.defer()

        player: wavelink.Player | None = interaction.guild.voice_client  # type: ignore[assignment]
        if player is None:
            player = await interaction.user.voice.channel.connect(cls=wavelink.Player)

        risultati = await wavelink.Playable.search(query)
        if not risultati:
            await interaction.followup.send("Nessun risultato trovato per questa ricerca.")
            return

        if isinstance(risultati, wavelink.Playlist):
            await player.queue.put_wait(risultati)
            await interaction.followup.send(
                f"📃 Aggiunta la playlist **{risultati.name}** ({len(risultati)} tracce) alla coda."
            )
        else:
            traccia = risultati[0]
            await player.queue.put_wait(traccia)
            await interaction.followup.send(
                f"➕ Aggiunta **{traccia.title}** ({format_duration(traccia.length)}) alla coda."
            )

        if not player.playing and not player.queue.is_empty:
            prossima = await player.queue.get_wait()
            await player.play(prossima)

    @app_commands.command(name="skip", description="Salta la traccia in riproduzione.")
    async def skip(self, interaction: discord.Interaction) -> None:
        if not await self._controlli_base(interaction):
            return

        player: wavelink.Player | None = interaction.guild.voice_client  # type: ignore[assignment]
        if player is None or not player.playing:
            await interaction.response.send_message(
                "Non c'è nessuna traccia in riproduzione.", ephemeral=True
            )
            return

        await player.skip()
        await interaction.response.send_message("⏭️ Traccia saltata.")

    @app_commands.command(name="stop", description="Ferma la riproduzione e svuota la coda.")
    async def stop(self, interaction: discord.Interaction) -> None:
        if not await self._controlli_base(interaction):
            return

        player: wavelink.Player | None = interaction.guild.voice_client  # type: ignore[assignment]
        if player is None:
            await interaction.response.send_message(
                "Non sono connesso a nessun canale vocale.", ephemeral=True
            )
            return

        player.queue.clear()
        await player.stop()
        await interaction.response.send_message("⏹️ Riproduzione fermata, coda svuotata.")

    @app_commands.command(name="pause", description="Mette in pausa la riproduzione.")
    async def pause(self, interaction: discord.Interaction) -> None:
        if not await self._controlli_base(interaction):
            return

        player: wavelink.Player | None = interaction.guild.voice_client  # type: ignore[assignment]
        if player is None or not player.playing:
            await interaction.response.send_message(
                "Non c'è nessuna traccia in riproduzione.", ephemeral=True
            )
            return

        await player.pause(True)
        await interaction.response.send_message("⏸️ Messo in pausa.")

    @app_commands.command(name="resume", description="Riprende la riproduzione in pausa.")
    async def resume(self, interaction: discord.Interaction) -> None:
        if not await self._controlli_base(interaction):
            return

        player: wavelink.Player | None = interaction.guild.voice_client  # type: ignore[assignment]
        if player is None or not player.paused:
            await interaction.response.send_message(
                "Non c'è nessuna riproduzione in pausa.", ephemeral=True
            )
            return

        await player.pause(False)
        await interaction.response.send_message("▶️ Ripreso.")

    @app_commands.command(name="queue", description="Mostra la coda di riproduzione.")
    async def queue_command(self, interaction: discord.Interaction) -> None:
        if not await self._controlli_base(interaction):
            return

        player: wavelink.Player | None = interaction.guild.voice_client  # type: ignore[assignment]
        titolo_attuale = player.current.title if player and player.current else None
        titoli_in_coda = [t.title for t in player.queue] if player else []

        embed = discord.Embed(
            title="🎵 Coda di riproduzione",
            description=build_queue_display(titolo_attuale, titoli_in_coda),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed)

    volume_group = app_commands.Group(
        name="volume", description="Controlla il volume della riproduzione (0-200, come Discord)."
    )

    @volume_group.command(name="set", description="Imposta il volume a un valore specifico (0-200).")
    @app_commands.describe(level="Livello del volume, da 0 a 200")
    async def volume_set(
        self, interaction: discord.Interaction, level: app_commands.Range[int, 0, 200]
    ) -> None:
        if not await self._controlli_base(interaction):
            return

        player: wavelink.Player | None = interaction.guild.voice_client  # type: ignore[assignment]
        if player is None:
            await interaction.response.send_message(
                "Non sono connesso a nessun canale vocale.", ephemeral=True
            )
            return

        await player.set_volume(level)
        await interaction.response.send_message(f"🔊 Volume impostato a {level}.")

    @volume_group.command(name="up", description="Aumenta il volume.")
    @app_commands.describe(amount="Quanto aumentare (default 10)")
    async def volume_up(
        self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 200] = 10
    ) -> None:
        if not await self._controlli_base(interaction):
            return

        player: wavelink.Player | None = interaction.guild.voice_client  # type: ignore[assignment]
        if player is None:
            await interaction.response.send_message(
                "Non sono connesso a nessun canale vocale.", ephemeral=True
            )
            return

        # min(200, ...) qui invece di lasciare fare tutto a set_volume():
        # wavelink accetta fino a 1000 e si limiterebbe a troncare in
        # silenzio, ma il messaggio di risposta deve mostrare il
        # valore REALMENTE applicato (max 200, la scala di Discord),
        # non un numero che poi non corrisponde a quello impostato.
        nuovo_volume = min(200, player.volume + amount)
        await player.set_volume(nuovo_volume)
        await interaction.response.send_message(f"🔊 Volume aumentato a {nuovo_volume}.")

    @volume_group.command(name="down", description="Diminuisce il volume.")
    @app_commands.describe(amount="Quanto diminuire (default 10)")
    async def volume_down(
        self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 200] = 10
    ) -> None:
        if not await self._controlli_base(interaction):
            return

        player: wavelink.Player | None = interaction.guild.voice_client  # type: ignore[assignment]
        if player is None:
            await interaction.response.send_message(
                "Non sono connesso a nessun canale vocale.", ephemeral=True
            )
            return

        nuovo_volume = max(0, player.volume - amount)
        await player.set_volume(nuovo_volume)
        await interaction.response.send_message(f"🔉 Volume diminuito a {nuovo_volume}.")

    @app_commands.command(name="disconnect", description="Disconnette il bot dal canale vocale.")
    async def disconnect(self, interaction: discord.Interaction) -> None:
        if not await self._controlli_base(interaction):
            return

        player: wavelink.Player | None = interaction.guild.voice_client  # type: ignore[assignment]
        if player is None:
            await interaction.response.send_message(
                "Non sono connesso a nessun canale vocale.", ephemeral=True
            )
            return

        await player.disconnect()
        await interaction.response.send_message("👋 Disconnesso.")


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_MUSIC,
            display_name="Music",
            description="Riproduzione musicale via Lavalink (play, coda, controlli).",
            premium_capable=False,
        )
    )
    await bot.add_cog(MusicCog(bot))

    # wavelink.Pool.connect() NON fallisce rapidamente se un nodo è
    # irraggiungibile — verificato con un test diretto: ritenta
    # all'infinito al proprio interno e la await non ritorna mai (né
    # solleva), quindi un try/except attorno a un await diretto qui
    # non serve a nulla e bloccherebbe l'intero avvio del bot (load_
    # all_cogs aspetta ogni setup() in sequenza) se Lavalink fosse
    # anche solo temporaneamente irraggiungibile. Lanciato come task
    # in background invece: setup() ritorna subito, la connessione
    # (coi suoi ritentativi) continua per conto suo.
    asyncio.create_task(_connetti_lavalink_in_background(bot))


async def _connetti_lavalink_in_background(bot: commands.Bot) -> None:
    try:
        await wavelink.Pool.connect(nodes=_build_lavalink_nodes(), client=bot)
    except Exception:
        logger.exception(
            "Connessione a Lavalink interrotta in modo inatteso — "
            "Music resterà non funzionante finché un nodo non sarà raggiungibile."
        )
