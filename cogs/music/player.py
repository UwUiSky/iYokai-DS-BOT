"""
cogs/music/player.py
=======================
Music (SPEC.md §9), via wavelink 3.x + Lavalink. Caricato SOLO sul
bot principale — le 5 istanze worker (core/music_worker_bot.py) non
hanno nessun comando proprio, esistono solo per avere una propria
connessione voce.

Architettura chiarita dall'utente: un solo punto di ingresso comandi
(qui, sul bot principale). Per /play e i comandi che agiscono su una
riproduzione, il bot principale non entra MAI in vocale lui stesso —
instrada verso una delle 5 istanze worker tramite core/music_fleet.py
(quella già assegnata a questo server, o la prima libera). Il bot
principale entra in vocale SOLO per /nonstop-main (streaming 24/7
dalla playlist personale dell'utente) — un comando completamente
separato dal resto.

Connessione a nodi Lavalink PUBBLICI gratuiti in cascata, con il
nodo locale/self-hostato dell'utente sempre per ultimo (decisione
presa con l'utente — vedi PROGRESS.md, core/music_logic.py per la
provenienza dei nodi pubblici).

wavelink gestisce da solo l'avanzamento automatico della coda
(player.autoplay = AutoPlayMode.partial, impostato a ogni nuova
connessione) — verificato nel sorgente di wavelink prima di scrivere
questo file: wavelink/websocket.py chiama player._auto_play_event()
DIRETTAMENTE come metodo Python sul player, non tramite il sistema
di listener di discord.py, quindi funziona correttamente per ogni
player indipendentemente da quale dei 6 bot lo possiede — non serve
un listener on_wavelink_track_end duplicato su ognuno dei 6 client.

Limite onesto, dichiarato qui perché vale per l'intero file: non è
possibile testare in questo ambiente una connessione vera a un nodo
Lavalink, al gateway voce di Discord, né avviare per davvero 6
client Discord concorrenti (servono 6 token veri). I test coprono
quello che è verificabile senza — i controlli di guardia, il
routing verso il worker giusto (con bot finti), la logica pura. Il
resto va verificato una volta distribuito, con le credenziali vere.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import discord
import wavelink
from discord import app_commands
from discord.ext import commands

from core.config import config
from core.database import db
from core.main_radio_logic import RadioTrackInfo, compute_current_position
from core.music_fleet import MusicFleet
from core.music_logic import (
    DEFAULT_PUBLIC_LAVALINK_NODES,
    LavalinkNodeConfig,
    build_queue_display,
    format_duration,
    parse_lavalink_nodes,
)
from core.premium import PremiumModule, registry
from core.repositories.main_radio_repo import main_radio_repo

logger = logging.getLogger("iyokai.music")

MODULE_MUSIC = "music"


LOCAL_NODE_IDENTIFIER = "iyokai-local-node"  # identificatore fisso
# per poter ritrovare SPECIFICAMENTE il nodo locale/self-hostato
# (l'unico che può avere accesso al filesystem di questa macchina —
# vedi _resolve_local_track più sotto), non uno qualunque scelto a
# caso da wavelink.Pool tra tutti i nodi configurati.


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

    nodi = [wavelink.Node(uri=nodo.uri, password=nodo.password) for nodo in nodi_config]
    nodi.append(
        wavelink.Node(
            identifier=LOCAL_NODE_IDENTIFIER,
            uri=uri_locale,
            password=config.LAVALINK_PASSWORD,
        )
    )
    return nodi


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ================================================================
    # Controlli condivisi e instradamento verso il worker giusto
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

    async def _get_worker_guild(
        self, guild_id: int, *, auto_assign: bool
    ) -> tuple[discord.Guild | None, str | None]:
        """
        Restituisce (guild_del_worker, None) in caso di successo, o
        (None, messaggio_errore) altrimenti. auto_assign=True (usato
        solo da /play) assegna un nuovo worker libero se il server
        non ne ha già uno; auto_assign=False (tutti gli altri
        comandi) non assegna nulla — se non c'è una sessione già
        attiva, quei comandi devono fallire pulitamente, non avviarne
        una nuova per sbaglio.
        """
        fleet: MusicFleet = self.bot.music_fleet

        if auto_assign:
            assegnazione = await fleet.get_or_assign_worker_for_guild(guild_id)
            errore_assenza = (
                "Tutti i music bot sono al momento occupati su altri server. "
                "Riprova tra poco."
            )
        else:
            assegnazione = await fleet.get_worker_for_guild(guild_id)
            errore_assenza = "Non c'è nessuna sessione musicale attiva su questo server."

        if assegnazione is None:
            return None, errore_assenza

        _worker_index, worker_bot = assegnazione
        worker_guild = worker_bot.get_guild(guild_id)
        if worker_guild is None:
            return None, (
                "Il music bot assegnato a questo server non risulta invitato qui. "
                "Contatta lo staff del bot."
            )
        return worker_guild, None

    # ================================================================
    # Comandi (instradati verso un worker)
    # ================================================================
    @app_commands.command(name="play", description="Riproduce una canzone o playlist.")
    @app_commands.describe(query="Nome della canzone, URL, o termine di ricerca")
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        if not await self._controlli_base(interaction):
            return

        await interaction.response.defer()

        worker_guild, errore = await self._get_worker_guild(interaction.guild.id, auto_assign=True)
        if errore:
            await interaction.followup.send(errore)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
        if player is None:
            canale_worker = worker_guild.get_channel(interaction.user.voice.channel.id)
            if canale_worker is None:
                await interaction.followup.send(
                    "Non riesco a raggiungere il tuo canale vocale dall'istanza assegnata "
                    "— il music bot potrebbe non avere accesso a questo canale."
                )
                return
            player = await canale_worker.connect(cls=wavelink.Player)
            player.autoplay = wavelink.AutoPlayMode.partial

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

        worker_guild, errore = await self._get_worker_guild(interaction.guild.id, auto_assign=False)
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
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

        worker_guild, errore = await self._get_worker_guild(interaction.guild.id, auto_assign=False)
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
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

        worker_guild, errore = await self._get_worker_guild(interaction.guild.id, auto_assign=False)
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
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

        worker_guild, errore = await self._get_worker_guild(interaction.guild.id, auto_assign=False)
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
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

        worker_guild, errore = await self._get_worker_guild(interaction.guild.id, auto_assign=False)
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
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

        worker_guild, errore = await self._get_worker_guild(interaction.guild.id, auto_assign=False)
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
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

        worker_guild, errore = await self._get_worker_guild(interaction.guild.id, auto_assign=False)
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
        if player is None:
            await interaction.response.send_message(
                "Non sono connesso a nessun canale vocale.", ephemeral=True
            )
            return

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

        worker_guild, errore = await self._get_worker_guild(interaction.guild.id, auto_assign=False)
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
        if player is None:
            await interaction.response.send_message(
                "Non sono connesso a nessun canale vocale.", ephemeral=True
            )
            return

        nuovo_volume = max(0, player.volume - amount)
        await player.set_volume(nuovo_volume)
        await interaction.response.send_message(f"🔉 Volume diminuito a {nuovo_volume}.")

    @app_commands.command(name="disconnect", description="Disconnette il music bot dal canale vocale.")
    async def disconnect(self, interaction: discord.Interaction) -> None:
        if not await self._controlli_base(interaction):
            return

        worker_guild, errore = await self._get_worker_guild(interaction.guild.id, auto_assign=False)
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
        if player is None:
            await interaction.response.send_message(
                "Non sono connesso a nessun canale vocale.", ephemeral=True
            )
            return

        await player.disconnect()
        fleet: MusicFleet = self.bot.music_fleet
        await fleet.release_guild(interaction.guild.id)
        await interaction.response.send_message("👋 Disconnesso.")

    # ================================================================
    # /nonstop — loop 24/7 sul worker attivo (SPEC.md §9.10, parte)
    # ================================================================
    nonstop_group = app_commands.Group(
        name="nonstop",
        description="Riproduzione continua in loop sulla sessione musicale attiva.",
    )

    @nonstop_group.command(name="on", description="Attiva il loop continuo sulla coda attuale.")
    async def nonstop_on(self, interaction: discord.Interaction) -> None:
        if not await self._controlli_base(interaction):
            return

        worker_guild, errore = await self._get_worker_guild(interaction.guild.id, auto_assign=False)
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
        if player is None:
            await interaction.response.send_message(
                "Non sono connesso a nessun canale vocale.", ephemeral=True
            )
            return

        player.queue.mode = wavelink.QueueMode.loop_all
        await interaction.response.send_message("🔁 Loop continuo attivato sulla coda attuale.")

    @nonstop_group.command(name="off", description="Disattiva il loop continuo.")
    async def nonstop_off(self, interaction: discord.Interaction) -> None:
        if not await self._controlli_base(interaction):
            return

        worker_guild, errore = await self._get_worker_guild(interaction.guild.id, auto_assign=False)
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
        if player is None:
            await interaction.response.send_message(
                "Non sono connesso a nessun canale vocale.", ephemeral=True
            )
            return

        player.queue.mode = wavelink.QueueMode.normal
        await interaction.response.send_message("Loop continuo disattivato.")

    # ================================================================
    # /nonstop-main — radio condivisa SOLO sul bot principale,
    # playlist personale (SPEC.md §9.11). Non instradata: il bot
    # principale entra in vocale lui stesso, comando distinto da
    # tutto il resto. "Condivisa" significa che ogni server dove è
    # attiva sente la STESSA cosa nello STESSO punto — vedi core/
    # main_radio_logic.py per l'idea dell'orologio condiviso che
    # rende possibile questo senza coordinare i player tra loro in
    # tempo reale.
    # ================================================================
    nonstop_main_group = app_commands.Group(
        name="nonstop-main",
        description="[Admin] Radio 24/7 condivisa del bot principale, playlist personale.",
    )

    async def _resolve_radio_track(self, identifier: str) -> wavelink.Playable | None:
        """
        Gli identificatori "local:..." vanno risolti SOLO tramite il
        nodo locale/self-hostato (LOCAL_NODE_IDENTIFIER) — nessun
        nodo pubblico ha accesso al filesystem di questa macchina,
        verificato prima di progettare questa feature. Tutto il
        resto (URL/ricerche su piattaforme pubbliche) può passare
        per qualunque nodo disponibile, wavelink sceglie da solo.
        """
        if identifier.startswith("local:"):
            nodo_locale = wavelink.Pool.get_node(LOCAL_NODE_IDENTIFIER)
            risultati = await wavelink.Playable.search(identifier, node=nodo_locale)
        else:
            risultati = await wavelink.Playable.search(identifier)

        if not risultati:
            return None
        if isinstance(risultati, wavelink.Playlist):
            return risultati[0] if len(risultati) > 0 else None
        return risultati[0]

    @nonstop_main_group.command(
        name="add-track", description="[Admin] Aggiunge una traccia alla playlist della radio."
    )
    @app_commands.describe(
        query="URL o ricerca (YouTube, Spotify, SoundCloud...)",
        label="Nome descrittivo per /nonstop-main list-tracks (facoltativo)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def nonstop_main_add_track(
        self, interaction: discord.Interaction, query: str, label: str | None = None
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        traccia = await self._resolve_radio_track(query)
        if traccia is None:
            await interaction.followup.send("Nessun risultato trovato per questa ricerca.")
            return

        track_id = await main_radio_repo.add_track(
            identifier=query,
            duration_ms=traccia.length,
            label=label or traccia.title,
            added_by=interaction.user.id,
        )
        await interaction.followup.send(
            f"✅ Aggiunta **{label or traccia.title}** alla playlist della radio (ID `{track_id}`)."
        )

    @nonstop_main_group.command(
        name="add-local",
        description="[Admin] Aggiunge un file dalla cartella inediti alla playlist della radio.",
    )
    @app_commands.describe(
        filename="Nome del file nella cartella inediti (MAIN_RADIO_LOCAL_FOLDER)",
        label="Nome descrittivo per /nonstop-main list-tracks (facoltativo)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def nonstop_main_add_local(
        self, interaction: discord.Interaction, filename: str, label: str | None = None
    ) -> None:
        if not config.MAIN_RADIO_LOCAL_FOLDER:
            await interaction.response.send_message(
                "MAIN_RADIO_LOCAL_FOLDER non è configurata — nessuna cartella inediti "
                "impostata su questa istanza.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        percorso_completo = f"{config.MAIN_RADIO_LOCAL_FOLDER.rstrip('/')}/{filename}"
        identificatore = f"local:{percorso_completo}"

        traccia = await self._resolve_radio_track(identificatore)
        if traccia is None:
            await interaction.followup.send(
                f"Impossibile trovare o leggere `{filename}` nella cartella inediti — "
                f"verifica che il nodo Lavalink locale sia attivo e che il file esista lì."
            )
            return

        track_id = await main_radio_repo.add_track(
            identifier=identificatore,
            duration_ms=traccia.length,
            label=label or filename,
            added_by=interaction.user.id,
        )
        await interaction.followup.send(
            f"✅ Aggiunto **{label or filename}** alla playlist della radio (ID `{track_id}`)."
        )

    @nonstop_main_group.command(
        name="remove-track", description="[Admin] Rimuove una traccia dalla playlist della radio."
    )
    @app_commands.describe(track_id="ID della traccia (vedi /nonstop-main list-tracks)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def nonstop_main_remove_track(
        self, interaction: discord.Interaction, track_id: int
    ) -> None:
        rimossa = await main_radio_repo.remove_track(track_id)
        if rimossa:
            await interaction.response.send_message("Traccia rimossa.", ephemeral=True)
        else:
            await interaction.response.send_message(
                "Nessuna traccia trovata con questo ID.", ephemeral=True
            )

    @nonstop_main_group.command(
        name="list-tracks", description="[Admin] Mostra la playlist della radio."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def nonstop_main_list_tracks(self, interaction: discord.Interaction) -> None:
        tracce = await main_radio_repo.list_tracks()
        if not tracce:
            await interaction.response.send_message(
                "La playlist della radio è vuota. Usa /nonstop-main add-track o add-local.",
                ephemeral=True,
            )
            return

        righe = [
            f"`{t.id}` **{t.label}** ({format_duration(t.duration_ms)})" for t in tracce
        ]
        embed = discord.Embed(
            title="📻 Playlist della radio",
            description="\n".join(righe),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @nonstop_main_group.command(
        name="start", description="[Admin] Entra nella radio condivisa, nel punto in cui si trova ora."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def nonstop_main_start(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return
        if not isinstance(interaction.user, discord.Member) or interaction.user.voice is None:
            await interaction.response.send_message(
                "Devi essere in un canale vocale per usare questo comando.", ephemeral=True
            )
            return

        if guild.voice_client is not None:
            await interaction.response.send_message(
                "La radio è già attiva su questo server. Usa /nonstop-main stop per fermarla prima.",
                ephemeral=True,
            )
            return

        tracce_db = await main_radio_repo.list_tracks()
        if not tracce_db:
            await interaction.response.send_message(
                "La playlist della radio è vuota. Usa /nonstop-main add-track o add-local prima.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        adesso = datetime.now(timezone.utc)
        stato = await main_radio_repo.get_state()
        if stato is None:
            # Nessuno ha mai avviato la radio - QUESTO server diventa
            # il riferimento dell'orologio condiviso, da zero.
            await main_radio_repo.set_state(track_index=0, track_started_at=adesso, is_active=True)
            indice_riferimento, inizio_riferimento = 0, adesso
        else:
            if not stato.is_active:
                await main_radio_repo.set_state(
                    track_index=stato.track_index, track_started_at=stato.track_started_at, is_active=True
                )
            indice_riferimento, inizio_riferimento = stato.track_index, stato.track_started_at

        tracce_info = [
            RadioTrackInfo(identifier=t.identifier, duration_ms=t.duration_ms) for t in tracce_db
        ]
        posizione = compute_current_position(tracce_info, indice_riferimento, inizio_riferimento, adesso)
        if posizione is None:
            await interaction.followup.send(
                "Stato della radio incoerente (playlist cambiata nel frattempo?). Riprova."
            )
            return

        traccia_corrente_db = tracce_db[posizione.track_index]
        traccia_corrente = await self._resolve_radio_track(traccia_corrente_db.identifier)
        if traccia_corrente is None:
            await interaction.followup.send(
                f"Impossibile risolvere la traccia attuale della radio "
                f"(**{traccia_corrente_db.label}**) — verifica che sia ancora disponibile."
            )
            return

        player: wavelink.Player = await interaction.user.voice.channel.connect(cls=wavelink.Player)
        player.autoplay = wavelink.AutoPlayMode.partial

        # Il resto della playlist DOPO la traccia attuale, in ordine,
        # con loop — così una volta finita la traccia corrente il
        # player prosegue da solo lungo la stessa playlist condivisa.
        indici_successivi = [
            (posizione.track_index + i) % len(tracce_db) for i in range(1, len(tracce_db))
        ]
        for indice in indici_successivi:
            traccia_futura = await self._resolve_radio_track(tracce_db[indice].identifier)
            if traccia_futura is not None:
                await player.queue.put_wait(traccia_futura)
        player.queue.mode = wavelink.QueueMode.loop_all

        await player.play(traccia_corrente, start=posizione.elapsed_ms_in_track)

        await interaction.followup.send(
            f"🔴 Radio avviata: **{traccia_corrente_db.label}**, "
            f"a {format_duration(posizione.elapsed_ms_in_track)}."
        )

    @nonstop_main_group.command(name="stop", description="[Admin] Esce dalla radio su questo server.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def nonstop_main_stop(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        player: wavelink.Player | None = guild.voice_client  # type: ignore[assignment]
        if player is None:
            await interaction.response.send_message(
                "La radio non è attiva su questo server.", ephemeral=True
            )
            return

        # NON tocchiamo lo stato condiviso qui: la radio "continua a
        # trasmettere" concettualmente (l'orologio condiviso avanza
        # comunque col tempo reale) anche se questo server smette di
        # ascoltare — esattamente come una vera stazione radio non si
        # ferma solo perché un ascoltatore spegne la radiolina.
        player.queue.clear()
        await player.disconnect()
        await interaction.response.send_message("👋 Uscito dalla radio.")


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_MUSIC,
            display_name="Music",
            description="Riproduzione musicale via Lavalink (play, coda, controlli, multi-istanza).",
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
