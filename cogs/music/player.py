"""
cogs/music/player.py
=======================
Music (SPEC.md §9), via wavelink 3.x + Lavalink. Caricato SOLO sul
bot principale — le 5 istanze worker (core/music_worker_bot.py) non
hanno nessun comando proprio, esistono solo per avere una propria
connessione voce.

Architettura chiarita dall'utente: un solo punto di ingresso comandi
(qui, sul bot principale). Per /music play e i comandi che agiscono su una
riproduzione, il bot principale non entra MAI in vocale lui stesso —
instrada verso una delle 5 istanze worker tramite core/music_fleet.py
(quella già assegnata a questo server, o la prima libera). Il bot
principale entra in vocale SOLO per /owner radio (streaming 24/7
dalla playlist personale dell'utente) — un comando completamente
separato dal resto.

Nodi Lavalink (D10, F2): ogni bot (principale + 5 worker) ha il SUO
nodo per ogni server Lavalink (core/music_nodes.py): un nodo è legato a
un solo utente bot. Nodi pubblici solo da LAVALINK_NODES (.env), nodo
locale/self-hostato per ultimo; ogni player nasce sul nodo del suo bot
(`wavelink.Player(nodes=[nodo])`) e la ricerca usa quel nodo.

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

# M 8.1-8.8, 8.11, 8.14-8.17 fatti qui. Canale richieste e playlist (NF-19)
# in cogs/music/request_channel.py e cogs/music/playlist.py; effetti sonori
# (NF-35) in cogs/fun/soundboard.py: usano MusicCog.accoda e i controlli comuni.

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Coroutine
from datetime import datetime, timezone
from pathlib import Path

import discord
import wavelink
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.config import config
from core.database import db
from core.main_radio_logic import RadioTrackInfo, compute_current_position, next_track_index
from core.music_fleet import MusicFleet, handle_worker_voice_update
from core.music_logic import (
    EMBED_DESCRIPTION_LIMIT,
    MAX_PLAYLIST_TRACKS,
    MSG_QUERY_RIFIUTATA,
    MSG_TEMPO_SCADUTO,
    QUERY_RIFIUTATA,
    QUERY_SPOTIFY,
    QUERY_URL,
    LavalinkNodeConfig,
    classify_query,
    build_progress_bar,
    build_queue_display,
    format_duration,
    is_safe_local_filename,
    is_spotify_query,
    local_identifier,
    local_path_for_node,
    local_path_from_identifier,
    paginate_lines,
    parse_lavalink_nodes,
    truncate_playlist_tracks,
    truncate_title,
    voice_join_problem,
)
from core.music_nodes import MAIN_KEY, MusicNodeManager, worker_key
from core.music_queue_logic import (
    MAX_HISTORY_SHOWN,
    format_share,
    own_shuffle_order,
    previous_track_position,
    requester_of,
    share_by_user,
)
from core.music_radio_view import RadioListView, pagina_embed
from core.music_request_logic import allegato_audio
from core.music_settings_logic import (
    channel_not_allowed,
    clamp_volume,
    idle_seconds,
    load_music_settings,
    msg_brano_troppo_lungo,
    site_not_allowed,
    title_blocked,
    track_too_long,
)
from core.premium import PremiumModule, guild_has_premium_access, registry
from core.repositories.main_radio_repo import main_radio_repo
from core.safe_http import url_e_sicuro

logger = logging.getLogger("iyokai.music")

MODULE_MUSIC = "music"

# Sotto-gruppi di /music e di /owner (un solo livello).
SG_LOOP = ("loop", "Ripete la traccia corrente o l'intera coda.")
SG_VOLUME = ("volume", "Controlla il volume della riproduzione (0-200, come Discord).")
# Brani suonati in un canale vuoto prima di uscire (valore predefinito di wavelink).
CANALE_VUOTO_BRANI_DEFAULT = 3

SG_NONSTOP = ("nonstop", "Riproduzione continua in loop sulla sessione musicale attiva.")
RADIO = ("radio", "Radio 24/7 condivisa del bot principale, playlist personale")


MSG_ALTRO_CANALE = (
    "Il music bot è in un altro canale vocale: devi essere nel suo stesso canale "
    "per usare questo comando."
)
MSG_NESSUN_NODO = (
    "Nessun nodo Lavalink è collegato in questo momento per questo music bot. "
    "Riprova tra poco; se continua, avvisa lo staff del bot."
)


def crea_gestore_nodi() -> MusicNodeManager:
    """
    Nodi pubblici SOLO da LAVALINK_NODES (.env) — nel codice non ce n'è
    nessuno (LIM-54) — e il nodo locale/self-hostato (LAVALINK_HOST/
    PORT/PASSWORD), che nella scelta viene sempre per ultimo (LIM-42).
    """
    pubblici = parse_lavalink_nodes(config.LAVALINK_NODES)
    locale = LavalinkNodeConfig(
        uri=f"http://{config.LAVALINK_HOST}:{config.LAVALINK_PORT}",
        password=config.LAVALINK_PASSWORD,
    )
    return MusicNodeManager(pubblici, locale)


def chiave_del_bot(bot) -> str:
    """'main' per il bot principale, 'w<N>' per il worker N."""
    indice = getattr(bot, "worker_index", None)
    return worker_key(indice) if isinstance(indice, int) else MAIN_KEY


def _troppo_lungo(traccia, impostazioni) -> bool:
    return track_too_long(
        getattr(traccia, "length", 0), impostazioni, getattr(traccia, "is_stream", False)
    )


def crea_cartella_locale() -> None:
    """M 8.4 / #45: la cartella degli inediti viene creata se manca."""
    if not config.MAIN_RADIO_LOCAL_FOLDER:
        return
    try:
        Path(config.MAIN_RADIO_LOCAL_FOLDER).mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.warning("Impossibile creare la cartella inediti della radio.", exc_info=True)


class MusicCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Task lanciati senza aspettarli. asyncio tiene solo un
        # riferimento debole ai task: senza questo insieme Python
        # potrebbe eliminarli prima che finiscano.
        self.task_in_background: set[asyncio.Task] = set()
        # Server in cui la radio si sta avviando (comando o ingresso del
        # bot in vocale): evita un secondo avvio dallo stesso evento.
        self._radio_in_avvio: set[int] = set()
        self._lock_canali: dict[tuple[int, int], asyncio.Lock] = {}

    async def cog_load(self) -> None:
        await super().cog_load()
        crea_cartella_locale()

    async def cog_unload(self) -> None:
        await super().cog_unload()
        gestore: MusicNodeManager | None = getattr(self.bot, "music_nodes", None)
        if gestore is not None:
            await gestore.close()  # M 8.2: chiusura del Pool allo spegnimento

    def avvia_in_background(self, coroutine: Coroutine) -> asyncio.Task:
        """Lancia un task e ne tiene il riferimento finché non finisce."""
        task = asyncio.create_task(coroutine)
        self.task_in_background.add(task)
        task.add_done_callback(self.task_in_background.discard)
        return task

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
                "Un amministratore può attivarlo con /admin setup attiva.",
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
        self,
        guild_id: int,
        *,
        auto_assign: bool,
        interaction: discord.Interaction | None = None,
        membro: discord.Member | None = None,
    ) -> tuple[discord.Guild | None, str | None]:
        """(guild_del_worker, None) o (None, messaggio_errore). Vedi `_get_worker`."""
        _bot, worker_guild, errore = await self._get_worker(
            guild_id, auto_assign=auto_assign, interaction=interaction, membro=membro
        )
        return worker_guild, errore

    async def _get_worker(
        self,
        guild_id: int,
        *,
        auto_assign: bool,
        interaction: discord.Interaction | None = None,
        membro: discord.Member | None = None,
    ) -> tuple[commands.Bot | None, discord.Guild | None, str | None]:
        """
        (bot_del_worker, guild_del_worker, None) o (None, None, errore).

        M 8.6: la sessione è per (server, canale vocale): si cerca quella
        del canale in cui si trova l'utente. auto_assign=True (solo
        /music play) assegna un worker libero se il canale non ne ha già
        uno; auto_assign=False (tutti gli altri comandi) non assegna
        nulla. M 8.7: un utente in un canale diverso da quello del player
        non trova la sessione e viene rifiutato con un messaggio chiaro.
        `interaction` serve sempre: dà il canale dell'utente (e, con
        auto_assign, distingue admin e non admin nel messaggio di
        istanze esaurite). `membro` sostituisce l'utente dell'interazione
        quando la richiesta arriva da un messaggio (canale richieste, NF-19).
        """
        fleet: MusicFleet = self.bot.music_fleet
        utente = membro if membro is not None else getattr(interaction, "user", None)
        voce = getattr(utente, "voice", None)
        canale = getattr(voce, "channel", None)
        canale_id = getattr(canale, "id", 0) or 0

        if auto_assign:
            assegnazione = await fleet.get_or_assign_worker_for_channel(guild_id, canale_id)
            if assegnazione is None:
                errore_assenza = await self._messaggio_istanze_esaurite(
                    fleet, guild_id, interaction, membro=membro
                )
                return None, None, errore_assenza
        else:
            assegnazione = await fleet.get_worker_for_channel(guild_id, canale_id)
            if assegnazione is None:
                if await fleet.guild_has_session(guild_id):
                    return None, None, MSG_ALTRO_CANALE
                return None, None, "Non c'è nessuna sessione musicale attiva su questo server."

        _worker_index, worker_bot = assegnazione
        worker_guild = worker_bot.get_guild(guild_id)
        if worker_guild is None:
            # Il bot è stato rimosso dal server DOPO l'assegnazione: va
            # rilasciato subito, o lo slot in music_sessions resterebbe
            # occupato per sempre.
            if auto_assign:
                await fleet.release_session(guild_id, canale_id)
            return None, None, (
                "Il music bot assegnato a questo server non risulta invitato qui. "
                "Contatta lo staff del bot."
            )
        return worker_bot, worker_guild, None

    async def _messaggio_istanze_esaurite(
        self,
        fleet: MusicFleet,
        guild_id: int,
        interaction: discord.Interaction | None,
        membro: discord.Member | None = None,
    ) -> str:
        """
        Messaggio quando NESSUN worker è assegnabile a questo server
        (SPEC.md §9, cap istanze concorrenti) — due scenari distinti,
        entrambi confermati esplicitamente dall'utente:

        1. Questo server non ha ancora invitato tutte le 5 istanze —
           la soluzione è invitarne altre (link generati al volo,
           solo per chi ha permessi di admin — a un non-admin si dice
           solo di chiedere all'admin, senza esporre i link).
        2. Questo server ha già tutte e 5 le istanze ma sono tutte
           occupate altrove in questo momento — non c'è nulla da
           invitare qui, serve un'estensione del limite GLOBALE:
           l'unica via è un ticket nel server ufficiale iYokai.
        """
        non_presenti = await fleet.get_missing_worker_indices(guild_id)
        # getattr con default: alcuni percorsi (es. DM, o oggetti
        # finti nei test) possono non avere permessi calcolabili —
        # trattati semplicemente come non-admin, mai un errore.
        utente = membro if membro is not None else getattr(interaction, "user", None)
        permessi = getattr(utente, "guild_permissions", None)
        è_admin = bool(permessi and permessi.manage_guild)

        if non_presenti:
            if è_admin:
                link = "\n".join(
                    f"- Istanza {i}: {fleet.build_invite_url(i, guild_id)}"
                    for i in sorted(non_presenti)[:8]  # tetto: il messaggio resta sotto i 2000 caratteri
                )
                return (
                    "Nessuna istanza musicale libera in questo server in questo "
                    f"momento — questo server non ha ancora invitato tutte le "
                    f"{fleet.total_workers} istanze disponibili. Puoi invitarne altre:\n"
                    f"{link}\n"
                    f"Se in futuro vi servissero più di {fleet.total_workers} istanze contemporanee, "
                    "apri un ticket nel server ufficiale iYokai per richiedere "
                    "l'estensione del limite."
                )
            return (
                "Nessuna istanza musicale libera in questo server in questo "
                "momento. Chiedi a un admin di invitare le altre istanze del "
                "bot musicale disponibili per questo server."
            )

        if è_admin:
            return (
                f"Tutte le {fleet.total_workers} istanze musicali di questo server sono "
                "al momento occupate su altri server. Se capita spesso, apri un "
                "ticket nel server ufficiale iYokai per richiedere un'estensione "
                "del limite di istanze."
            )
        return (
            "Tutte le istanze musicali disponibili sono al momento occupate "
            "altrove. Se capita spesso, chiedi a un admin di aprire un ticket "
            "con lo staff del bot per richiedere più istanze."
        )

    async def _cerca(
        self, query: str, nodo: wavelink.Node, nodo_locale: wavelink.Node | None = None
    ) -> tuple[wavelink.Search | None, wavelink.Node]:
        """
        LIM-42/43: la ricerca gira su un nodo SCELTO (quello del bot che
        suonerà), mai su "il meno carico di tutto il Pool". I link di
        Spotify (`spotify:`) non diventano una ricerca su YouTube Music.
        Se una query Spotify non dà nulla sui nodi pubblici, si ritenta
        UNA volta sul nodo locale del plugin LavaSrc (SPEC.md §9.5).
        Restituisce anche il nodo che ha risposto: il player deve nascere
        lì, perché le tracce dei plugin si suonano solo dove il plugin c'è.
        """
        risultati = await self._cerca_su(query, nodo)
        if risultati or not is_spotify_query(query):
            return risultati, nodo
        if nodo_locale is None or nodo_locale is nodo:
            return risultati, nodo
        return await self._cerca_su(query, nodo_locale), nodo_locale

    @staticmethod
    async def _cerca_su(query: str, nodo: wavelink.Node) -> wavelink.Search | None:
        """
        Mai una query grezza scritta da un utente: URL http(s) e URI Spotify
        validi vanno cosi' come sono; qualunque altro testo diventa SEMPRE
        `ytmsearch:<testo>`. Percorsi, `//host/...`, `local:` e simili sono
        rifiutati prima (classify_query): con `sources.local` attivo
        farebbero leggere i file di Lavalink.
        """
        tipo = classify_query(query)
        if tipo == QUERY_RIFIUTATA:
            return None
        if tipo == QUERY_SPOTIFY:
            return await wavelink.Pool.fetch_tracks(query.strip(), node=nodo)
        if tipo == QUERY_URL:
            # Lavalink (sources.http) scaricherebbe da dentro la rete del
            # server: niente 127.0.0.1, 10.x, metadati cloud (SSRF).
            if not await url_e_sicuro(query.strip()):
                logger.info("URL musicale rifiutato (non pubblico): %s", query.strip()[:80])
                return None
            return await wavelink.Playable.search(query.strip(), node=nodo)
        return await wavelink.Pool.fetch_tracks(f"ytmsearch:{query.strip()}", node=nodo)

    async def _entra_in_canale(
        self, canale, nodo: wavelink.Node, volume: int | None = None, sordo: bool = True
    ) -> tuple[wavelink.Player | None, str | None]:
        """
        Entra in un canale vocale con un player sul nodo scelto. LIM-34:
        canale palco, canale pieno e tempo scaduto hanno un messaggio
        chiaro invece di un errore muto. (player, None) o (None, errore).
        """
        me = getattr(getattr(canale, "guild", None), "me", None)
        permessi = canale.permissions_for(me) if me is not None else None
        problema = voice_join_problem(
            is_stage=isinstance(canale, discord.StageChannel),
            user_limit=getattr(canale, "user_limit", 0) or 0,
            presenti=len(getattr(canale, "members", [])),
            puo_superare_limite=bool(
                permessi and (permessi.administrator or permessi.move_members)
            ),
        )
        if problema:
            return None, problema
        try:
            # MUS-056: il bot entra "sordo" (non riceve l'audio degli altri);
            # non per gli effetti sonori (NF-35): un bot sordo non manda suoni.
            player = await canale.connect(
                cls=functools.partial(wavelink.Player, nodes=[nodo]), self_deaf=sordo
            )
        except (asyncio.TimeoutError, wavelink.exceptions.ChannelTimeoutException):
            return None, MSG_TEMPO_SCADUTO
        except discord.Forbidden:
            return None, "Non ho il permesso di entrare in questo canale vocale."
        except (discord.ClientException, discord.HTTPException):
            logger.exception("Ingresso nel canale vocale %s non riuscito.", canale.id)
            return None, "Non riesco a entrare nel canale vocale. Riprova tra poco."
        player.autoplay = wavelink.AutoPlayMode.partial
        if volume is not None:  # volume massimo del server anche all'ingresso (MUS-047)
            await player.set_volume(volume)
        return player, None

    # ================================================================
    # Comandi (instradati verso un worker)
    # ================================================================
    @comando_di_gruppo("music", nome="play", descrizione="Riproduce una canzone o playlist.")
    @app_commands.describe(
        query="Nome della canzone, URL, o termine di ricerca",
        in_cima="Metti il brano in cima alla coda, subito dopo quello in corso",
        allegato="Un file audio o video da suonare al posto della ricerca",
    )
    @app_commands.rename(in_cima="in-cima")
    async def play(
        self,
        interaction: discord.Interaction,
        query: app_commands.Range[str, 1, 300] | None = None,
        in_cima: bool = False,
        allegato: discord.Attachment | None = None,
    ) -> None:
        if not await self._controlli_base(interaction):
            return
        if allegato is not None:  # MUS-009: file allegato al comando
            if not allegato_audio(allegato.content_type):
                await interaction.response.send_message(
                    "L'allegato deve essere un file audio o video.", ephemeral=True
                )
                return
            query = allegato.url
        if not query:
            await interaction.response.send_message(
                "Scrivi un titolo o un link, oppure allega un file audio.", ephemeral=True
            )
            return

        await interaction.response.defer()
        await self.accoda(
            interaction.guild, interaction.user, query, interaction.followup.send,
            in_cima=in_cima, interaction=interaction,
        )

    async def accoda(
        self,
        guild: discord.Guild,
        membro: discord.Member,
        query: str,
        rispondi,
        *,
        in_cima: bool = False,
        interaction: discord.Interaction | None = None,
        cerca=None,
    ) -> int | None:
        """
        Mette in coda `query` nel canale vocale di `membro` (worker assegnato o
        il primo libero). Usato da /music play, dal canale richieste (NF-19) e
        dal caricamento di una playlist salvata. `rispondi(testo)` manda la
        risposta; `cerca(nodo, nodo_locale)` sostituisce la ricerca (playlist
        salvate). Restituisce il canale vocale se il brano è in coda, se no None.
        """
        impostazioni = await load_music_settings(db, guild.id)
        canale_id = getattr(getattr(membro.voice, "channel", None), "id", 0)
        rifiuto = channel_not_allowed(canale_id, impostazioni)  # MUS-059
        if rifiuto:
            await rispondi(rifiuto)
            return None

        if cerca is None and classify_query(query) == QUERY_RIFIUTATA:
            await rispondi(MSG_QUERY_RIFIUTATA)
            return None
        sito_no = site_not_allowed(query, impostazioni) if cerca is None else None  # MUS-064
        if sito_no:
            await rispondi(sito_no)
            return None

        worker_bot, worker_guild, errore = await self._get_worker(
            guild.id, auto_assign=True, interaction=interaction, membro=membro
        )
        if errore:
            await rispondi(errore)
            return None

        # Due richieste insieme nello stesso canale: una alla volta, cosi' la
        # seconda trova il player gia' creato dalla prima (niente doppio connect, niente
        # slot rilasciato sotto un bot che suona).
        async with self._lock_canale(guild.id, canale_id):
            esito = await self._play_nel_canale(
                guild.id, membro.id, query, in_cima, impostazioni, worker_bot, worker_guild,
                canale_id, rispondi, cerca,
            )
        return canale_id if esito else None

    def _lock_canale(self, guild_id: int, canale_id: int) -> asyncio.Lock:
        return self._lock_canali.setdefault((guild_id, canale_id), asyncio.Lock())

    async def _rilascia_se_libero(self, worker_guild, guild_id: int, canale_id: int) -> None:
        """Libera lo slot SOLO se il bot non e' in vocale (mai sotto un player che suona)."""
        if worker_guild.voice_client is None:
            await self.bot.music_fleet.release_session(guild_id, canale_id)

    async def _play_nel_canale(
        self, guild_id, utente_id, query, in_cima, impostazioni, worker_bot, worker_guild,
        canale_id, rispondi, cerca=None,
    ) -> bool:
        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
        nuova_sessione = player is None
        gestore: MusicNodeManager | None = getattr(self.bot, "music_nodes", None)
        chiave = chiave_del_bot(worker_bot)

        # D10: il player vive sul nodo del SUO bot; la ricerca gira sullo stesso.
        nodo = player.node if player is not None else (gestore.node_for(chiave) if gestore else None)
        if nodo is None:
            await self._rilascia_se_libero(worker_guild, guild_id, canale_id)
            await rispondi(MSG_NESSUN_NODO)
            return False

        nodo_locale = gestore.locale_di(chiave) if (gestore and nuova_sessione) else None
        try:
            if cerca is not None:
                risultati, nodo = await cerca(nodo, nodo_locale)
            else:
                risultati, nodo = await self._cerca(query, nodo, nodo_locale)
        except wavelink.exceptions.WavelinkException:
            logger.warning("Ricerca musicale fallita sul nodo %s.", nodo.identifier, exc_info=True)
            risultati = None
        if not risultati:
            await self._rilascia_se_libero(worker_guild, guild_id, canale_id)
            await rispondi("Nessun risultato trovato per questa ricerca.")
            return False

        # MUS-044: i brani oltre la durata massima non entrano in coda.
        scartate_lunghe = 0
        tracce_playlist: list = []
        if isinstance(risultati, wavelink.Playlist):
            candidate = truncate_playlist_tracks(risultati, MAX_PLAYLIST_TRACKS)
            tracce_playlist = [
                t for t in candidate
                if not _troppo_lungo(t, impostazioni) and not title_blocked(t.title, impostazioni)
            ]
            scartate_lunghe = len(candidate) - len(tracce_playlist)
            if not tracce_playlist:
                await self._rilascia_se_libero(worker_guild, guild_id, canale_id)
                await rispondi(
                    "Nessun brano della playlist rispetta le regole del server "
                    "(durata massima o parole non ammesse)."
                    if impostazioni.banned_words
                    else f"Nessun brano della playlist rispetta la durata massima di "
                    f"{impostazioni.max_track_minutes} minuti."
                )
                return False
        elif title_blocked(risultati[0].title, impostazioni):  # MUS-062
            await self._rilascia_se_libero(worker_guild, guild_id, canale_id)
            await rispondi("Questo brano contiene parole non ammesse da questo server.")
            return False
        elif _troppo_lungo(risultati[0], impostazioni):
            await self._rilascia_se_libero(worker_guild, guild_id, canale_id)
            await rispondi(
                msg_brano_troppo_lungo(risultati[0].title, risultati[0].length, impostazioni)
            )
            return False

        if player is None:
            canale_worker = worker_guild.get_channel(canale_id)
            if canale_worker is None:
                await self._rilascia_se_libero(worker_guild, guild_id, canale_id)
                await rispondi(
                    "Non riesco a raggiungere il tuo canale vocale dall'istanza assegnata "
                    "— il music bot potrebbe non avere accesso a questo canale."
                )
                return False
            player, errore = await self._entra_in_canale(
                canale_worker, nodo, volume=min(100, impostazioni.max_volume)
            )
            if errore:
                await self._rilascia_se_libero(worker_guild, guild_id, canale_id)
                await rispondi(errore)
                return False
            attesa = idle_seconds(impostazioni)  # MUS-054
            if attesa is not None:
                player.inactive_timeout = attesa

        if isinstance(risultati, wavelink.Playlist):
            tracce_totali = len(risultati)
            tracce_da_aggiungere = tracce_playlist
            for t in tracce_da_aggiungere:
                t.extras = {"requester_id": utente_id}  # MUS-036/027/030
            if in_cima:  # MUS-021
                for t in reversed(tracce_da_aggiungere):
                    player.queue.put_at(0, t)
            else:
                await player.queue.put_wait(tracce_da_aggiungere)
            if tracce_totali > MAX_PLAYLIST_TRACKS:
                await rispondi(
                    f"📃 Aggiunta la playlist **{truncate_title(risultati.name, 200)}** — "
                    f"{MAX_PLAYLIST_TRACKS} tracce su {tracce_totali} totali "
                    f"(limite massimo per singola playlist)."
                )
            else:
                await rispondi(
                    f"📃 Aggiunta la playlist **{truncate_title(risultati.name, 200)}** ({tracce_totali} tracce) alla coda."
                    + (
                        f" ({scartate_lunghe} oltre la durata massima non aggiunte.)"
                        if scartate_lunghe and not impostazioni.banned_words
                        else f" ({scartate_lunghe} non ammesse dalle regole del server.)"
                        if scartate_lunghe
                        else ""
                    )
                )
        else:
            traccia = risultati[0]
            traccia.extras = {"requester_id": utente_id}
            if in_cima:
                player.queue.put_at(0, traccia)
            else:
                await player.queue.put_wait(traccia)
            await rispondi(
                f"➕ Aggiunta **{truncate_title(traccia.title, 200)}** "
                f"({format_duration(traccia.length)}) alla coda."
            )

        if not player.playing and not player.queue.is_empty:
            prossima = await player.queue.get_wait()
            await player.play(prossima)
        return True

    @comando_di_gruppo("music", nome="skip", descrizione="Salta la traccia in riproduzione.")
    async def skip(self, interaction: discord.Interaction) -> None:
        if not await self._controlli_base(interaction):
            return

        worker_guild, errore = await self._get_worker_guild(
            interaction.guild.id, auto_assign=False, interaction=interaction
        )
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
        if player is None or not player.playing:
            await interaction.response.send_message(
                "Non c'è nessuna traccia in riproduzione.", ephemeral=True
            )
            return

        await interaction.response.defer()  # M 8.16: Lavalink puo' metterci piu' di 3 secondi
        await player.skip()
        await interaction.followup.send("⏭️ Traccia saltata.")

    @comando_di_gruppo("music", nome="stop", descrizione="Ferma la riproduzione e svuota la coda.")
    async def stop(self, interaction: discord.Interaction) -> None:
        if not await self._controlli_base(interaction):
            return

        worker_guild, errore = await self._get_worker_guild(
            interaction.guild.id, auto_assign=False, interaction=interaction
        )
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
        if player is None:
            await interaction.response.send_message(
                "Non sono connesso a nessun canale vocale.", ephemeral=True
            )
            return

        await interaction.response.defer()  # M 8.16
        player.queue.clear()
        await player.stop()
        await interaction.followup.send("⏹️ Riproduzione fermata, coda svuotata.")

    @comando_di_gruppo("music", nome="pause", descrizione="Mette in pausa la riproduzione.")
    async def pause(self, interaction: discord.Interaction) -> None:
        if not await self._controlli_base(interaction):
            return

        worker_guild, errore = await self._get_worker_guild(
            interaction.guild.id, auto_assign=False, interaction=interaction
        )
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
        if player is None or not player.playing:
            await interaction.response.send_message(
                "Non c'è nessuna traccia in riproduzione.", ephemeral=True
            )
            return

        await interaction.response.defer()  # M 8.16
        await player.pause(True)
        await interaction.followup.send("⏸️ Messo in pausa.")

    @comando_di_gruppo("music", nome="resume", descrizione="Riprende la riproduzione in pausa.")
    async def resume(self, interaction: discord.Interaction) -> None:
        if not await self._controlli_base(interaction):
            return

        worker_guild, errore = await self._get_worker_guild(
            interaction.guild.id, auto_assign=False, interaction=interaction
        )
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
        if player is None or not player.paused:
            await interaction.response.send_message(
                "Non c'è nessuna riproduzione in pausa.", ephemeral=True
            )
            return

        await interaction.response.defer()  # M 8.16
        await player.pause(False)
        await interaction.followup.send("▶️ Ripreso.")

    @comando_di_gruppo("music", nome="queue", descrizione="Mostra la coda di riproduzione.")
    async def queue_command(self, interaction: discord.Interaction) -> None:
        if not await self._controlli_base(interaction):
            return

        worker_guild, errore = await self._get_worker_guild(
            interaction.guild.id, auto_assign=False, interaction=interaction
        )
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
        titolo_attuale = player.current.title if player and player.current else None
        titoli_in_coda = [truncate_title(t.title, 150) for t in player.queue] if player else []

        embed = discord.Embed(
            title="🎵 Coda di riproduzione",
            description=build_queue_display(titolo_attuale, titoli_in_coda)[
                :EMBED_DESCRIPTION_LIMIT
            ],
            color=discord.Color.blurple(),
        )
        if player and len(player.queue) > 0:  # MUS-036
            quote = share_by_user([requester_of(t) for t in player.queue])
            if quote:
                embed.add_field(name="Chi ha messo cosa", value=format_share(quote), inline=False)
        await interaction.response.send_message(embed=embed)

    @comando_di_gruppo("music", nome="clear-queue", descrizione="Svuota la coda, senza toccare la traccia in riproduzione.")
    async def clear_queue(self, interaction: discord.Interaction) -> None:
        # NON "clear": nome già usato da /mod clear (cancella
        # messaggi) — un doppione avrebbe fatto fallire la REGISTRAZIONE
        # dell'intero MusicCog in silenzio (bug reale trovato qui:
        # core/cog_manager.load_all_cogs cattura e LOGGA ogni eccezione
        # di setup() per singolo cog, non la fa mai risalire — un
        # comando musicale con nome duplicato avrebbe disattivato
        # l'intero modulo Music senza che nessuno lo notasse finché
        # qualcuno non avesse controllato i log).
        if not await self._controlli_base(interaction):
            return

        worker_guild, errore = await self._get_worker_guild(
            interaction.guild.id, auto_assign=False, interaction=interaction
        )
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
        if player is None:
            await interaction.response.send_message(
                "Non sono connesso a nessun canale vocale.", ephemeral=True
            )
            return

        if player.queue.is_empty:
            await interaction.response.send_message("La coda è già vuota.", ephemeral=True)
            return

        tracce_rimosse = len(player.queue)
        player.queue.clear()
        await interaction.response.send_message(
            f"🗑️ Coda svuotata ({tracce_rimosse} tracce rimosse). "
            "La traccia in riproduzione non è stata toccata."
        )

    @comando_di_gruppo("music", nome="shuffle", descrizione="Mescola l'ordine delle tracce in coda.")
    @app_commands.describe(solo_miei="Mescola soltanto i brani che hai messo tu")
    @app_commands.rename(solo_miei="solo-miei")
    async def shuffle(self, interaction: discord.Interaction, solo_miei: bool = False) -> None:
        if not await self._controlli_base(interaction):
            return

        worker_guild, errore = await self._get_worker_guild(
            interaction.guild.id, auto_assign=False, interaction=interaction
        )
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
        if player is None:
            await interaction.response.send_message(
                "Non sono connesso a nessun canale vocale.", ephemeral=True
            )
            return

        if len(player.queue) < 2:
            await interaction.response.send_message(
                "Non c'è abbastanza in coda da mescolare.", ephemeral=True
            )
            return

        if solo_miei:  # MUS-039
            tracce = list(player.queue)
            ordine = own_shuffle_order([requester_of(t) for t in tracce], interaction.user.id)
            if ordine == list(range(len(tracce))):
                await interaction.response.send_message(
                    "Non hai abbastanza brani tuoi in coda da mescolare.", ephemeral=True
                )
                return
            # senza nessun await in mezzo: nessun altro comando vede la coda vuota
            player.queue.clear()
            player.queue.put([tracce[i] for i in ordine])
            await interaction.response.send_message("🔀 Ho mescolato i tuoi brani in coda.")
            return

        player.queue.shuffle()
        await interaction.response.send_message("🔀 Coda mescolata.")

    @comando_di_gruppo(
        "music",
        nome="track",
        descrizione="Attiva/disattiva la ripetizione della traccia corrente.",
        sottogruppo=SG_LOOP,
    )
    async def loop_track(self, interaction: discord.Interaction) -> None:
        if not await self._controlli_base(interaction):
            return

        worker_guild, errore = await self._get_worker_guild(
            interaction.guild.id, auto_assign=False, interaction=interaction
        )
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
        if player is None:
            await interaction.response.send_message(
                "Non sono connesso a nessun canale vocale.", ephemeral=True
            )
            return

        # Stesso campo (player.queue.mode) usato anche da /music loop queue
        # e da /music nonstop on: attivare questo disattiva sempre l'altro, non
        # si sommano — sono due modalità mutuamente esclusive della
        # stessa coda, non due loop indipendenti.
        if player.queue.mode == wavelink.QueueMode.loop:
            player.queue.mode = wavelink.QueueMode.normal
            await interaction.response.send_message("Loop traccia disattivato.")
        else:
            player.queue.mode = wavelink.QueueMode.loop
            await interaction.response.send_message("🔂 Loop traccia attivato: la traccia corrente si ripete.")

    @comando_di_gruppo(
        "music",
        nome="queue",
        descrizione="Attiva/disattiva la ripetizione dell'intera coda.",
        sottogruppo=SG_LOOP,
    )
    async def loop_queue(self, interaction: discord.Interaction) -> None:
        if not await self._controlli_base(interaction):
            return

        worker_guild, errore = await self._get_worker_guild(
            interaction.guild.id, auto_assign=False, interaction=interaction
        )
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
        if player is None:
            await interaction.response.send_message(
                "Non sono connesso a nessun canale vocale.", ephemeral=True
            )
            return

        if player.queue.mode == wavelink.QueueMode.loop_all:
            player.queue.mode = wavelink.QueueMode.normal
            await interaction.response.send_message("Loop coda disattivato.")
        else:
            player.queue.mode = wavelink.QueueMode.loop_all
            await interaction.response.send_message("🔁 Loop coda attivato: l'intera coda si ripete.")

    @comando_di_gruppo("music", nome="nowplaying", descrizione="Mostra la traccia in riproduzione con una barra di avanzamento.")
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        if not await self._controlli_base(interaction):
            return

        worker_guild, errore = await self._get_worker_guild(
            interaction.guild.id, auto_assign=False, interaction=interaction
        )
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
        if player is None or player.current is None:
            await interaction.response.send_message(
                "Nessuna traccia in riproduzione.", ephemeral=True
            )
            return

        traccia = player.current
        barra = build_progress_bar(player.position, traccia.length)
        righe = [
            f"{barra}",
            f"{format_duration(player.position)} / {format_duration(traccia.length)}",
        ]
        if player.queue.mode == wavelink.QueueMode.loop:
            righe.append("🔂 Loop traccia attivo")
        elif player.queue.mode == wavelink.QueueMode.loop_all:
            righe.append("🔁 Loop coda attivo")

        tracce_in_coda = len(player.queue)
        if tracce_in_coda > 0:
            righe.append(f"📃 {tracce_in_coda} altre tracce in coda")

        embed = discord.Embed(
            title=truncate_title(f"🎵 {traccia.title}"),
            description="\n".join(righe),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed)

    @comando_di_gruppo(
        "music",
        nome="set",
        descrizione="Imposta il volume a un valore specifico (0-200).",
        sottogruppo=SG_VOLUME,
    )
    @app_commands.describe(level="Livello del volume, da 0 a 200")
    async def volume_set(
        self, interaction: discord.Interaction, level: app_commands.Range[int, 0, 200]
    ) -> None:
        if not await self._controlli_base(interaction):
            return

        worker_guild, errore = await self._get_worker_guild(
            interaction.guild.id, auto_assign=False, interaction=interaction
        )
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
        if player is None:
            await interaction.response.send_message(
                "Non sono connesso a nessun canale vocale.", ephemeral=True
            )
            return

        await interaction.response.defer()  # M 8.16
        impostazioni = await load_music_settings(db, interaction.guild.id)
        livello = clamp_volume(level, impostazioni)  # MUS-047
        await player.set_volume(livello)
        limite = " (il massimo scelto dal server)" if livello < level else ""
        await interaction.followup.send(f"🔊 Volume impostato a {livello}{limite}.")

    @comando_di_gruppo(
        "music",
        nome="up",
        descrizione="Aumenta il volume.",
        sottogruppo=SG_VOLUME,
    )
    @app_commands.describe(amount="Quanto aumentare (default 10)")
    async def volume_up(
        self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 200] = 10
    ) -> None:
        if not await self._controlli_base(interaction):
            return

        worker_guild, errore = await self._get_worker_guild(
            interaction.guild.id, auto_assign=False, interaction=interaction
        )
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
        if player is None:
            await interaction.response.send_message(
                "Non sono connesso a nessun canale vocale.", ephemeral=True
            )
            return

        await interaction.response.defer()  # M 8.16
        impostazioni = await load_music_settings(db, interaction.guild.id)
        # MUS-047: mai oltre il massimo, ma "alza" non abbassa mai (volume gia' sopra il massimo)
        nuovo_volume = max(player.volume, clamp_volume(player.volume + amount, impostazioni))
        await player.set_volume(nuovo_volume)
        await interaction.followup.send(f"🔊 Volume aumentato a {nuovo_volume}.")

    @comando_di_gruppo(
        "music",
        nome="down",
        descrizione="Diminuisce il volume.",
        sottogruppo=SG_VOLUME,
    )
    @app_commands.describe(amount="Quanto diminuire (default 10)")
    async def volume_down(
        self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 200] = 10
    ) -> None:
        if not await self._controlli_base(interaction):
            return

        worker_guild, errore = await self._get_worker_guild(
            interaction.guild.id, auto_assign=False, interaction=interaction
        )
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
        if player is None:
            await interaction.response.send_message(
                "Non sono connesso a nessun canale vocale.", ephemeral=True
            )
            return

        await interaction.response.defer()  # M 8.16
        nuovo_volume = max(0, player.volume - amount)
        await player.set_volume(nuovo_volume)
        await interaction.followup.send(f"🔉 Volume diminuito a {nuovo_volume}.")

    @comando_di_gruppo("music", nome="disconnect", descrizione="Disconnette il music bot dal canale vocale.")
    async def disconnect(self, interaction: discord.Interaction) -> None:
        if not await self._controlli_base(interaction):
            return

        worker_guild, errore = await self._get_worker_guild(
            interaction.guild.id, auto_assign=False, interaction=interaction
        )
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return

        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
        if player is None:
            await interaction.response.send_message(
                "Non sono connesso a nessun canale vocale.", ephemeral=True
            )
            return

        await interaction.response.defer()  # M 8.16
        canale_id = player.channel.id if player.channel is not None else 0
        await player.disconnect()
        fleet: MusicFleet = self.bot.music_fleet
        await fleet.release_session(
            interaction.guild.id, canale_id or interaction.user.voice.channel.id
        )
        await interaction.followup.send("👋 Disconnesso.")

    # ================================================================
    # Catalogo MUS (issue #126): entrare, saltare, togliere, tornare indietro
    # ================================================================
    async def _giocatore_attivo(self, interaction: discord.Interaction):
        """Controlli comuni dei comandi sulla coda: il player del canale dell'utente, o None
        (e la risposta d'errore è già partita)."""
        if not await self._controlli_base(interaction):
            return None
        worker_guild, errore = await self._get_worker_guild(
            interaction.guild.id, auto_assign=False, interaction=interaction
        )
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return None
        player: wavelink.Player | None = worker_guild.voice_client  # type: ignore[assignment]
        if player is None:
            await interaction.response.send_message(
                "Non sono connesso a nessun canale vocale.", ephemeral=True
            )
            return None
        return player

    @comando_di_gruppo(
        "music", nome="join", descrizione="Fa entrare il music bot nel tuo canale, senza suonare."
    )
    async def join(self, interaction: discord.Interaction) -> None:
        # MUS-020
        if not await self._controlli_base(interaction):
            return
        await interaction.response.defer()
        impostazioni = await load_music_settings(db, interaction.guild.id)
        rifiuto = channel_not_allowed(
            getattr(getattr(interaction.user.voice, "channel", None), "id", 0), impostazioni
        )  # MUS-059
        if rifiuto:
            await interaction.followup.send(rifiuto)
            return
        worker_bot, worker_guild, errore = await self._get_worker(
            interaction.guild.id, auto_assign=True, interaction=interaction
        )
        if errore:
            await interaction.followup.send(errore)
            return
        canale_id = interaction.user.voice.channel.id
        if worker_guild.voice_client is not None:
            await interaction.followup.send("Il music bot è già nel tuo canale vocale.")
            return
        gestore: MusicNodeManager | None = getattr(self.bot, "music_nodes", None)
        nodo = gestore.node_for(chiave_del_bot(worker_bot)) if gestore else None
        if nodo is None:
            await self.bot.music_fleet.release_session(interaction.guild.id, canale_id)
            await interaction.followup.send(MSG_NESSUN_NODO)
            return
        canale_worker = worker_guild.get_channel(canale_id)
        if canale_worker is None:
            await self.bot.music_fleet.release_session(interaction.guild.id, canale_id)
            await interaction.followup.send(
                "Non riesco a raggiungere il tuo canale vocale dall'istanza assegnata."
            )
            return
        player, errore = await self._entra_in_canale(canale_worker, nodo)
        if errore:
            await self.bot.music_fleet.release_session(interaction.guild.id, canale_id)
            await interaction.followup.send(errore)
            return
        await interaction.followup.send("🎧 Sono entrato nel canale. Usa /music play per suonare.")

    @comando_di_gruppo("music", nome="skipto", descrizione="Salta direttamente al brano numero N della coda.")
    @app_commands.describe(numero="Posizione nella coda (1 = il prossimo brano)")
    async def skipto(
        self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 10000]
    ) -> None:
        # MUS-029
        player = await self._giocatore_attivo(interaction)
        if player is None:
            return
        if numero > len(player.queue):
            await interaction.response.send_message(
                f"La coda ha {len(player.queue)} brani: il numero {numero} non c'è.", ephemeral=True
            )
            return
        saltati = [player.queue[i] for i in range(numero - 1)]
        for _ in saltati:
            player.queue.delete(0)
        if saltati and player.queue.mode == wavelink.QueueMode.loop_all:
            player.queue.put(saltati)  # in loop-all i brani saltati vanno in fondo, non persi
        titolo = truncate_title(player.queue[0].title, 150)
        await interaction.response.defer()
        await player.skip()
        await interaction.followup.send(f"⏭️ Salto a **{titolo}**.")

    @comando_di_gruppo("music", nome="previous", descrizione="Torna al brano precedente.")
    async def previous(self, interaction: discord.Interaction) -> None:
        # MUS-031
        player = await self._giocatore_attivo(interaction)
        if player is None:
            return
        storico = player.queue.history
        posizione = (
            previous_track_position(len(storico), player.current is not None)
            if storico is not None
            else None
        )
        if posizione is None:
            await interaction.response.send_message(
                "Non c'è un brano precedente.", ephemeral=True
            )
            return
        precedente = storico[posizione]
        await interaction.response.defer()
        if player.current is not None:
            # il brano in corso torna in cima alla coda e lascia lo storico: cosi' il
            # precedente di "precedente" e' ancora il brano prima, senza avanti-indietro
            player.queue.put_at(0, player.current)
            storico.delete(len(storico) - 1)
        # add_history=False: il brano ripreso e' gia' (o torna a essere) l'ultimo dello storico
        await player.play(precedente, add_history=False)
        await interaction.followup.send(f"⏮️ Torno a **{truncate_title(precedente.title, 150)}**.")

    @comando_di_gruppo("music", nome="history", descrizione="Mostra gli ultimi brani già suonati.")
    async def history(self, interaction: discord.Interaction) -> None:
        # MUS-032
        player = await self._giocatore_attivo(interaction)
        if player is None:
            return
        storico = list(player.queue.history or [])
        if player.current is not None and storico:
            storico = storico[:-1]  # l'ultimo è il brano in corso
        recenti = list(reversed(storico))[:MAX_HISTORY_SHOWN]
        if not recenti:
            await interaction.response.send_message(
                "Non è ancora stato suonato nessun brano prima di questo.", ephemeral=True
            )
            return
        righe = [f"{i}. {truncate_title(t.title, 150)}" for i, t in enumerate(recenti, start=1)]
        embed = discord.Embed(
            title="🕘 Già suonati",
            description="\n".join(righe)[:EMBED_DESCRIPTION_LIMIT],
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed)

    # ================================================================
    # /music nonstop — loop 24/7 sul worker attivo (SPEC.md §9.10, parte)
    # ================================================================
    @comando_di_gruppo(
        "music",
        nome="on",
        descrizione="Attiva il loop continuo sulla coda attuale.",
        sottogruppo=SG_NONSTOP,
    )
    async def nonstop_on(self, interaction: discord.Interaction) -> None:
        if not await self._controlli_base(interaction):
            return

        worker_guild, errore = await self._get_worker_guild(
            interaction.guild.id, auto_assign=False, interaction=interaction
        )
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
        if not await guild_has_premium_access(interaction.guild.id, MODULE_MUSIC, bot=self.bot):
            # D30: un worker fermo in un canale vuoto è tolto a tutti i server. Senza premium
            # il loop c'è, ma a canale vuoto il bot esce come sempre.
            await interaction.response.send_message(
                "🔁 Loop continuo attivato sulla coda attuale. Se il canale resta vuoto esco "
                "comunque: restare 24/7 senza ascoltatori è una funzione premium."
            )
            return
        # LIM-44: il 24/7 resta anche se il canale si svuota (come la radio).
        player.is_nonstop = True
        player.inactive_channel_tokens = None
        await interaction.response.send_message("🔁 Loop continuo 24/7 attivato sulla coda attuale.")

    @comando_di_gruppo(
        "music",
        nome="off",
        descrizione="Disattiva il loop continuo.",
        sottogruppo=SG_NONSTOP,
    )
    async def nonstop_off(self, interaction: discord.Interaction) -> None:
        if not await self._controlli_base(interaction):
            return

        worker_guild, errore = await self._get_worker_guild(
            interaction.guild.id, auto_assign=False, interaction=interaction
        )
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
        player.is_nonstop = False
        player.inactive_channel_tokens = CANALE_VUOTO_BRANI_DEFAULT
        await interaction.response.send_message("Loop continuo disattivato.")

    # ================================================================
    # /owner radio — radio condivisa SOLO sul bot principale,
    # playlist personale (SPEC.md §9.11). Non instradata: il bot
    # principale entra in vocale lui stesso, comando distinto da
    # tutto il resto. "Condivisa" significa che ogni server dove è
    # attiva sente la STESSA cosa nello STESSO punto — vedi core/
    # main_radio_logic.py per l'idea dell'orologio condiviso che
    # rende possibile questo senza coordinare i player tra loro in
    # tempo reale.
    # ================================================================
    def _nodo_della_radio(self, locale_richiesto: bool) -> tuple[wavelink.Node | None, str | None]:
        """
        Il nodo del bot principale per la radio. I brani locali si
        leggono SOLO dal nodo locale (nessun nodo pubblico vede il
        filesystem di questa macchina): se la playlist ne ha, il player
        nasce lì. (nodo, None) o (None, messaggio).
        """
        gestore: MusicNodeManager | None = getattr(self.bot, "music_nodes", None)
        if gestore is None:
            return None, MSG_NESSUN_NODO
        if locale_richiesto:
            nodo = gestore.locale_di(MAIN_KEY)
            if nodo is None:
                return None, (
                    "La playlist ha brani locali ma il nodo Lavalink locale non è collegato "
                    "(o è sotto la versione 4.2.0). Vedi deploy/lavalink/README.md."
                )
            return nodo, None
        nodo = gestore.node_for(MAIN_KEY)
        return (nodo, None) if nodo is not None else (None, MSG_NESSUN_NODO)

    async def _resolve_radio_track(
        self, identifier: str, nodo: wavelink.Node | None = None
    ) -> wavelink.Playable | None:
        """
        BUG-10 / LIM-43: un identificatore "local:<percorso>" va al nodo
        locale con il percorso visto dal NODO (`Pool.fetch_tracks`, mai
        `Playable.search`, che lo trasformerebbe in una ricerca su YouTube
        Music). Tutto il resto passa dal nodo scelto per la radio.
        """
        gestore: MusicNodeManager | None = getattr(self.bot, "music_nodes", None)
        percorso = local_path_from_identifier(identifier)
        try:
            if percorso is not None:
                nodo_locale = gestore.locale_di(MAIN_KEY) if gestore else None
                if nodo_locale is None:
                    return None
                risultati = await wavelink.Pool.fetch_tracks(percorso, node=nodo_locale)
            else:
                nodo = nodo or (gestore.node_for(MAIN_KEY) if gestore else None)
                if nodo is None:
                    return None
                risultati = await self._cerca_su(identifier, nodo)
        except wavelink.exceptions.WavelinkException:
            logger.warning("Brano della radio non risolto (%s).", identifier[:80], exc_info=True)
            return None

        if not risultati:
            return None
        if isinstance(risultati, wavelink.Playlist):
            return risultati[0] if len(risultati) > 0 else None
        return risultati[0]

    @comando_di_gruppo(
        "owner",
        nome="add-track",
        descrizione="Aggiunge una traccia alla playlist della radio.",
        sottogruppo=RADIO,
    )
    @app_commands.describe(
        query="URL o ricerca (YouTube, Spotify, SoundCloud...)",
        label="Nome descrittivo per /owner radio list-tracks (facoltativo)",
    )
    async def nonstop_main_add_track(
        self, interaction: discord.Interaction, query: str, label: str | None = None
    ) -> None:
        if query.strip().startswith("local:"):
            await interaction.response.send_message(
                "Per i file della cartella inediti usa /owner radio add-local.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        traccia = await self._resolve_radio_track(query)
        if traccia is None:
            await interaction.followup.send("Nessun risultato trovato per questa ricerca.")
            return

        track_id = await main_radio_repo.add_track(
            identifier=query,
            duration_ms=traccia.length,
            label=truncate_title(label or traccia.title, 200),
            added_by=interaction.user.id,
        )
        await interaction.followup.send(
            f"✅ Aggiunta **{truncate_title(label or traccia.title, 200)}** "
            f"alla playlist della radio (ID `{track_id}`)."
        )

    @comando_di_gruppo(
        "owner",
        nome="add-local",
        descrizione="Aggiunge un file dalla cartella inediti alla playlist della radio.",
        sottogruppo=RADIO,
    )
    @app_commands.describe(
        filename="Nome del file nella cartella inediti (MAIN_RADIO_LOCAL_FOLDER)",
        label="Nome descrittivo per /owner radio list-tracks (facoltativo)",
    )
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

        # SEC-5 / #45: il nome deve essere un nome di file semplice, e il
        # percorso risolto deve restare DENTRO la cartella inediti.
        cartella = Path(config.MAIN_RADIO_LOCAL_FOLDER).resolve()
        if not is_safe_local_filename(filename) or not (
            (cartella / filename).resolve().is_relative_to(cartella)
        ):
            await interaction.response.send_message(
                "Nome file non valido.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        # M 8.4: il percorso è quello che vede il NODO Lavalink (con Docker
        # è il punto di montaggio), non quello del bot.
        radice_nodo = config.LAVALINK_LOCAL_ROOT or config.MAIN_RADIO_LOCAL_FOLDER
        identificatore = local_identifier(local_path_for_node(radice_nodo, filename))

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

    @comando_di_gruppo(
        "owner",
        nome="remove-track",
        descrizione="Rimuove una traccia dalla playlist della radio.",
        sottogruppo=RADIO,
    )
    @app_commands.describe(track_id="ID della traccia (vedi /owner radio list-tracks)")
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

    @comando_di_gruppo(
        "owner",
        nome="list-tracks",
        descrizione="Mostra la playlist della radio.",
        sottogruppo=RADIO,
    )
    async def nonstop_main_list_tracks(self, interaction: discord.Interaction) -> None:
        tracce = await main_radio_repo.list_tracks()
        if not tracce:
            await interaction.response.send_message(
                "La playlist della radio è vuota. Usa /owner radio add-track o add-local.",
                ephemeral=True,
            )
            return

        righe = [
            f"`{t.id}` **{truncate_title(t.label, 150)}** ({format_duration(t.duration_ms)})"
            for t in tracce
        ]
        pagine = paginate_lines(righe)  # M 8.15: descrizione entro 4096, a pagine
        view = RadioListView(pagine, interaction.user.id) if len(pagine) > 1 else None
        kwargs = {"view": view} if view is not None else {}
        await interaction.response.send_message(
            embed=pagina_embed(pagine, 0), ephemeral=True, **kwargs
        )

    @comando_di_gruppo(
        "owner",
        nome="start",
        descrizione="Entra nella radio condivisa, nel punto in cui si trova ora.",
        sottogruppo=RADIO,
    )
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
                "La radio è già attiva su questo server. Usa /owner radio stop per fermarla prima.",
                ephemeral=True,
            )
            return

        if not await main_radio_repo.list_tracks():
            await interaction.response.send_message(
                "La playlist della radio è vuota. Usa /owner radio add-track o add-local prima.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        messaggio = await self._avvia_radio(guild, interaction.user.voice.channel)
        await interaction.followup.send(messaggio)

    async def _avvia_radio(self, guild: discord.Guild, canale) -> str:
        """
        Avvia la radio condivisa in `canale` dal punto in cui si trova ora
        e restituisce il messaggio per l'utente. Usata dal comando e
        dall'ingresso del bot principale in vocale (M 8.8, #45).
        """
        if guild.id in self._radio_in_avvio:
            return "La radio si sta già avviando su questo server."
        self._radio_in_avvio.add(guild.id)
        try:
            return await self._avvia_radio_interna(guild, canale)
        finally:
            self._radio_in_avvio.discard(guild.id)

    async def _avvia_radio_interna(self, guild: discord.Guild, canale) -> str:
        tracce_db = await main_radio_repo.list_tracks()
        if not tracce_db:
            return "La playlist della radio è vuota. Usa /owner radio add-track o add-local prima."

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
            return "Stato della radio incoerente (playlist cambiata nel frattempo?). Riprova."

        nodo, errore_nodo = self._nodo_della_radio(
            any(local_path_from_identifier(t.identifier) is not None for t in tracce_db)
        )
        if nodo is None:
            return errore_nodo

        traccia_corrente_db = tracce_db[posizione.track_index]
        traccia_corrente = await self._resolve_radio_track(traccia_corrente_db.identifier, nodo)
        if traccia_corrente is None:
            return (
                f"Impossibile risolvere la traccia attuale della radio "
                f"(**{truncate_title(traccia_corrente_db.label, 150)}**) — "
                "verifica che sia ancora disponibile."
            )

        player, errore = await self._entra_in_canale(canale, nodo)
        if errore:
            return errore
        # M 8.5 / LIM-44: la radio 24/7 non lascia il canale se resta vuoto
        # (né il controllo memoria né l'evento "inattivo" la toccano).
        player.is_radio = True
        player.inactive_channel_tokens = None

        # Il resto della playlist DOPO la traccia attuale, in ordine,
        # con loop (next_track_index, M 8.17) — così una volta finita la
        # traccia corrente il player prosegue da solo lungo la stessa
        # playlist condivisa.
        indice = posizione.track_index
        for _ in range(1, len(tracce_db)):
            indice = next_track_index(indice, len(tracce_db))
            traccia_futura = await self._resolve_radio_track(tracce_db[indice].identifier, nodo)
            if traccia_futura is not None:
                await player.queue.put_wait(traccia_futura)
        player.queue.mode = wavelink.QueueMode.loop_all

        await player.play(traccia_corrente, start=posizione.elapsed_ms_in_track)

        return (
            f"🔴 Radio avviata: **{truncate_title(traccia_corrente_db.label, 150)}**, "
            f"a {format_duration(posizione.elapsed_ms_in_track)}."
        )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        """
        M 8.8 / #45: quando il bot PRINCIPALE si ritrova in un canale
        vocale senza un player (messo lì a mano da un admin, o rimasto
        dopo un riavvio), la radio parte da sola dal punto giusto.
        Solo il principale: i worker non caricano questo cog. Se il bot è
        entrato con /owner radio start il player esiste già e non si
        fa nulla. Se esce, lo stato condiviso non si tocca.
        """
        if self.bot.user is None or member.id != self.bot.user.id:
            return
        if after.channel is None or member.guild.voice_client is not None:
            return
        if member.guild.id in self._radio_in_avvio:
            return
        if not await db.is_module_active_for_guild(member.guild.id, MODULE_MUSIC):
            return
        self.avvia_in_background(self._avvia_radio_da_ingresso(member.guild, after.channel))

    async def _avvia_radio_da_ingresso(self, guild: discord.Guild, canale) -> None:
        try:
            esito = await self._avvia_radio(guild, canale)
            logger.info("Radio avviata all'ingresso del bot in vocale (%s): %s", guild.id, esito)
        except Exception:
            logger.exception("Avvio automatico della radio fallito (%s).", guild.id)

    @comando_di_gruppo(
        "owner",
        nome="stop",
        descrizione="Esce dalla radio su questo server.",
        sottogruppo=RADIO,
    )
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
            category="music",
            description="Riproduzione musicale via Lavalink (play, coda, controlli, multi-istanza).",
            premium_capable=False,
        )
    )
    cog = MusicCog(bot)
    # I nodi si creano e si collegano in background (un task per nodo,
    # M 8.2): setup() ritorna subito anche se Lavalink è irraggiungibile.
    bot.music_nodes = crea_gestore_nodi()
    await bot.add_cog(cog)
    cog.avvia_in_background(_connetti_lavalink_in_background(bot))


async def _connetti_lavalink_in_background(bot: commands.Bot) -> None:
    """
    D10: un nodo per ogni bot (principale + 5 worker) e per ogni server
    Lavalink. Ogni nodo ha un task suo con tentativi limitati: un nodo
    morto non blocca gli altri (M 8.2). I task li tiene il gestore e li
    ferma `cog_unload`.
    """
    gestore: MusicNodeManager = bot.music_nodes
    try:
        task_principale = gestore.avvia(bot, MAIN_KEY)
        flotta = getattr(bot, "music_fleet", None)
        for worker in getattr(flotta, "worker_bots", []):
            gestore.avvia(worker, chiave_del_bot(worker))
            worker.add_listener(
                functools.partial(_su_voce_del_worker, flotta, worker), "on_voice_state_update"
            )
        await avvisa_se_manca_il_nodo_locale(gestore, task_principale)
    except Exception:
        logger.exception(
            "Avvio dei nodi Lavalink interrotto in modo inatteso — "
            "Music resterà non funzionante finché un nodo non sarà raggiungibile."
        )


async def _su_voce_del_worker(flotta, worker, member, before, after) -> None:
    await handle_worker_voice_update(flotta, worker, member, before, after)


ATTESA_AVVISO_NODO_LOCALE = 60.0  # secondi


async def avvisa_se_manca_il_nodo_locale(
    gestore: MusicNodeManager, task_principale, attesa: float = ATTESA_AVVISO_NODO_LOCALE
) -> None:
    """
    #45/#47: con la cartella inediti impostata, il nodo locale serve — se
    non è collegato dopo `attesa` secondi, WARNING. L'attesa è limitata: i
    task di collegamento riprovano all'infinito (in background, a parte) e
    non vanno mai aspettati fino in fondo; qui non vengono cancellati.
    """
    if not config.MAIN_RADIO_LOCAL_FOLDER:
        return
    if task_principale:
        await asyncio.wait(task_principale, timeout=attesa)
    if gestore.locale_di(MAIN_KEY) is None:
        logger.warning(
            "MAIN_RADIO_LOCAL_FOLDER è impostata ma il nodo Lavalink locale non è collegato "
            "(o è sotto la 4.2.0): i brani inediti della radio non si potranno suonare. "
            "Vedi deploy/lavalink/README.md."
        )
