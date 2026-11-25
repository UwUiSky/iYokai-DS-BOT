"""
core/music_fleet.py
=======================
Gestore della flotta Music (SPEC.md §9.1/9.2). Il bot principale non
entra MAI in vocale per /music play — instrada verso una delle 5 istanze
worker (client Discord separati con il proprio token, connessi allo
stesso Pool Lavalink condiviso — verificato prima di scrivere questo
file: wavelink.Pool è un singleton di processo, ogni Player si lega
al client Discord che lo crea, non serve una connessione Lavalink
separata per bot). Un solo processo Python con 6 connessioni gateway
concorrenti (1 principale + 5 worker), non 6 processi separati — per
non moltiplicare 6 volte l'overhead di interprete su una VM già
limitata.
"""

# F2 (#64): M 8.1 un nodo per bot (core/music_nodes.py), M 8.6
# assegnazione per (server, canale vocale).

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import discord
from discord.ext import commands

from core.database import db
from core.music_settings_logic import load_music_settings
from core.music_fleet_logic import TOTAL_WORKERS
from core.repositories.music_session_repo import music_session_repo

# Permessi minimi richiesti a un'istanza worker per unirsi e parlare
# in un canale vocale — usati per generare il link d'invito quando
# manca a un server (SPEC.md §9, cap istanze concorrenti).
# use_soundboard: gli effetti sonori (NF-35) partono dal bot musicale del canale.
WORKER_INVITE_PERMISSIONS = discord.Permissions(
    view_channel=True, connect=True, speak=True, use_soundboard=True
)


logger = logging.getLogger("iyokai.music")

# Una sessione appena assegnata ha questo tempo per far entrare il bot nel canale prima che il controllo la liberi.
GRAZIA_SLOT_SECONDI = 90.0


async def _resta_a_coda_finita(guild_id: int) -> bool:
    """MUS-055: l'admin ha scelto che il bot resti nel canale a coda finita."""
    try:
        return (await load_music_settings(db, guild_id)).stay_when_queue_ends
    except Exception:
        logger.debug("Impostazioni musicali non leggibili (%s).", guild_id, exc_info=True)
        return False


class MusicFleet:
    def __init__(self, worker_bots: list[commands.Bot]) -> None:
        if len(worker_bots) < TOTAL_WORKERS:
            raise ValueError(
                f"Attesi almeno {TOTAL_WORKERS} bot worker, ricevuti {len(worker_bots)}."
            )
        self._worker_bots = worker_bots

    @property
    def total_workers(self) -> int:
        """Quante istanze ci sono davvero (5 o più, da MUSIC_TOKEN_n)."""
        return len(self._worker_bots)

    @property
    def worker_bots(self) -> list[commands.Bot]:
        """Tutti i worker (una copia): serve a chi deve agire su ogni bot, come la blacklist."""
        return list(self._worker_bots)

    def get_worker_bot(self, worker_index: int) -> commands.Bot:
        """worker_index è 1-based (worker 1..5) — coerente con
        core/music_fleet_logic.find_free_worker() e la colonna
        worker_index della tabella music_sessions."""
        return self._worker_bots[worker_index - 1]

    async def get_worker_for_channel(
        self, guild_id: int, channel_id: int
    ) -> tuple[int, commands.Bot] | None:
        """
        Sola lettura — la sessione già assegnata a questo canale vocale,
        se esiste, SENZA assegnarne una nuova (M 8.6: un bot per canale,
        non per server). Usata dai comandi che agiscono su una
        riproduzione già in corso (skip, stop, queue, ecc.).
        """
        worker_index = await music_session_repo.get_worker_for_channel(guild_id, channel_id)
        if worker_index is None:
            return None
        return worker_index, self.get_worker_bot(worker_index)

    async def guild_has_session(self, guild_id: int) -> bool:
        """Il server ha una sessione in QUALCHE canale (per il messaggio giusto)."""
        return await music_session_repo.guild_has_session(guild_id)

    async def get_or_assign_worker_for_channel(
        self, guild_id: int, channel_id: int
    ) -> tuple[int, commands.Bot] | None:
        """
        La sessione già assegnata a questo canale, se esiste — così un
        secondo /music play nello stesso canale non salta a un worker
        diverso. Un ALTRO canale dello stesso server prende un altro
        worker (due canali, due bot, due code). Altrimenti il primo
        worker libero E presente in questo server (escludere chi non è
        invitato qui PRIMA di assegnarlo — non dopo — evita di occupare
        per sempre uno slot per un worker che non potrà mai connettersi
        qui). None se non c'è nessun worker sia libero sia presente.
        """
        worker_index = await music_session_repo.get_worker_for_channel(guild_id, channel_id)
        if worker_index is not None:
            return worker_index, self.get_worker_bot(worker_index)

        esclusi = await self.get_missing_worker_indices(guild_id) | self._worker_non_pronti()
        libero = await music_session_repo.assign_free_worker(
            guild_id, channel_id, esclusi, self.total_workers
        )
        if libero is None:
            return None
        return libero, self.get_worker_bot(libero)

    async def get_missing_worker_indices(self, guild_id: int) -> set[int]:
        """
        Gli indici (1-based) delle istanze worker NON invitate in
        questo server — usato sia per escluderle dall'assegnazione
        sopra sia per decidere il messaggio giusto quando nessun
        worker è disponibile (SPEC.md §9, cap istanze concorrenti):
        se qui manca almeno un'istanza delle 5, la soluzione è
        invitarla; se sono già tutte presenti ma tutte occupate
        altrove, la soluzione è un'estensione del limite globale.
        Le istanze non pronte (non partite) sono escluse: non c'è
        nulla da invitare.
        """
        return {
            i
            for i in range(1, self.total_workers + 1)
            if i not in self._worker_non_pronti()
            and self.get_worker_bot(i).get_guild(guild_id) is None
        }

    def _worker_non_pronti(self) -> set[int]:
        """
        Le istanze che non sono partite (es. token sbagliato) o non sono
        ancora pronte: non si possono assegnare e non si può costruire
        il loro link d'invito (`user` è None).
        """
        return {
            i for i in range(1, self.total_workers + 1) if not self.get_worker_bot(i).is_ready()
        }

    def build_invite_url(self, worker_index: int, guild_id: int) -> str:
        """Link d'invito per una singola istanza worker verso questo
        server specifico (`guild=`/`disable_guild_select=True` lo
        preseleziona e blocca la scelta), con i soli permessi vocali
        minimi che le serve — mai i permessi di amministratore."""
        worker_bot = self.get_worker_bot(worker_index)
        return discord.utils.oauth_url(
            worker_bot.user.id,
            permissions=WORKER_INVITE_PERMISSIONS,
            guild=discord.Object(id=guild_id),
            disable_guild_select=True,
            scopes=["bot"],
        )

    async def release_session(self, guild_id: int, channel_id: int, worker_index: int | None = None) -> None:
        """Chiamata quando una sessione finisce (es. /music disconnect) —
        libera il worker per il prossimo canale che ne ha bisogno.
        Con `worker_index` si libera solo se lo slot è ancora di quel worker."""
        await music_session_repo.release_session(guild_id, channel_id, worker_index)

    def indice_di(self, worker_bot) -> int | None:
        """L'indice (1-based) di un worker, o None se non è della flotta."""
        for i, bot in enumerate(self._worker_bots, start=1):
            if bot is worker_bot:
                return i
        return None

    @asynccontextmanager
    async def sessione(self, guild_id: int, channel_id: int, worker_bot, worker_guild):
        """
        Una richiesta musicale che ha preso uno slot: all'uscita, con qualunque esito (anche un errore
        imprevisto o l'annullamento), se il worker non è in vocale lo slot si libera. Se è in vocale
        resta: sotto un player che suona non si libera mai. Se il rilascio stesso fallisce (database
        giù) ci pensa `libera_slot_persi`.
        """
        try:
            yield
        finally:
            if worker_guild is not None and worker_guild.voice_client is None:
                try:
                    await asyncio.shield(self.release_session(guild_id, channel_id, self.indice_di(worker_bot)))
                except Exception:
                    logger.warning("Slot musicale %s/%s non rilasciato: lo libererà il controllo periodico.", guild_id, channel_id, exc_info=True)

    async def libera_slot_persi(self, *, grazia_secondi: float = GRAZIA_SLOT_SECONDI) -> int:
        """
        Controllo periodico: libera gli slot dei worker che non sono più in vocale in quel canale
        (errori, riavvii di un worker, player caduto con Lavalink). Una riga appena assegnata ha
        `grazia_secondi` di tempo per far entrare il bot. Restituisce quanti slot ha liberato.
        """
        adesso = datetime.now(timezone.utc)
        liberati = 0
        for riga in await music_session_repo.all_sessions():
            if (adesso - riga.assigned_at).total_seconds() < grazia_secondi:
                continue
            if not 1 <= riga.worker_index <= self.total_workers:
                continue
            worker = self.get_worker_bot(riga.worker_index)
            if not worker.is_ready():
                continue  # worker spento o in riconnessione: non si può sapere
            guild = worker.get_guild(riga.guild_id)
            voce = getattr(guild, "voice_client", None) if guild is not None else None
            canale = getattr(voce, "channel", None)
            if guild is not None and voce is not None and getattr(canale, "id", None) == riga.channel_id:
                continue  # sessione viva
            await music_session_repo.release_session(riga.guild_id, riga.channel_id, riga.worker_index)
            logger.warning("Slot musicale perso liberato: server %s, canale %s, worker %s.", riga.guild_id, riga.channel_id, riga.worker_index)
            liberati += 1
        return liberati


async def handle_inactive_player(player, fleet: MusicFleet) -> None:
    """
    Gestore condiviso di "wavelink_inactive_player" (SPEC.md §9.9,
    auto-leave su canale vuoto — il timeout stesso, 300s di default,
    è già gestito internamente da wavelink/Lavalink tramite Node.
    inactive_player_timeout; qui serve solo REAGIRE all'evento:
    disconnettersi e liberare il worker nella flotta). Registrato
    identicamente su TUTTI e 6 i bot (main + 5 worker) in main.py —
    lo stesso player finito inattivo potrebbe appartenere a
    qualunque dei 6 client, dato che ognuno ha la propria
    connessione voce indipendente.

    release_session() su un canale senza worker assegnato
    (es. la radio del bot principale, mai registrata nella flotta)
    non fa nulla — DELETE su una riga inesistente, innocuo.
    """
    if getattr(player, "is_radio", False) or getattr(player, "is_nonstop", False):
        # LIM-44: la radio e il loop 24/7 non lasciano il canale per inattività.
        return
    guild = player.guild
    canale = player.channel
    umani = [m for m in getattr(canale, "members", []) if not getattr(m, "bot", False)]
    if guild is not None and umani and await _resta_a_coda_finita(guild.id):
        return  # MUS-055: resta a coda finita, ma solo se in canale c'e' ancora qualcuno
    await player.disconnect()
    if guild is not None and canale is not None:
        await fleet.release_session(guild.id, canale.id)


async def handle_worker_voice_update(fleet: MusicFleet, bot, member, before, after) -> None:
    """
    Listener `on_voice_state_update` dei bot worker: se il worker viene scollegato a
    mano esce dal canale -> la sessione si libera; se viene spostato in un altro
    canale la riga lo segue. Senza questo lo slot resterebbe occupato per sempre.
    """
    utente = getattr(bot, "user", None)
    if utente is None or member.id != utente.id or before.channel is None:
        return
    guild_id = member.guild.id
    if after.channel is None:
        await fleet.release_session(guild_id, before.channel.id)
    elif after.channel.id != before.channel.id:
        await music_session_repo.move_session(guild_id, before.channel.id, after.channel.id)
