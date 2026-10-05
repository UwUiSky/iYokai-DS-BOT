"""
core/music_fleet.py
=======================
Gestore della flotta Music (SPEC.md §9.1/9.2). Il bot principale non
entra MAI in vocale per /play — instrada verso una delle 5 istanze
worker (client Discord separati con il proprio token, connessi allo
stesso Pool Lavalink condiviso — verificato prima di scrivere questo
file: wavelink.Pool è un singleton di processo, ogni Player si lega
al client Discord che lo crea, non serve una connessione Lavalink
separata per bot). Un solo processo Python con 6 connessioni gateway
concorrenti (1 principale + 5 worker), non 6 processi separati — per
non moltiplicare 6 volte l'overhead di interprete su una VM già
limitata.
"""

# DA FARE (issue #64, fase F2): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §8 (Musica).

from __future__ import annotations

import discord
from discord.ext import commands

from core.music_fleet_logic import TOTAL_WORKERS, find_free_worker
from core.repositories.music_session_repo import music_session_repo

# Permessi minimi richiesti a un'istanza worker per unirsi e parlare
# in un canale vocale — usati per generare il link d'invito quando
# manca a un server (SPEC.md §9, cap istanze concorrenti).
WORKER_INVITE_PERMISSIONS = discord.Permissions(view_channel=True, connect=True, speak=True)


class MusicFleet:
    def __init__(self, worker_bots: list[commands.Bot]) -> None:
        if len(worker_bots) != TOTAL_WORKERS:
            raise ValueError(
                f"Attesi {TOTAL_WORKERS} bot worker, ricevuti {len(worker_bots)}."
            )
        self._worker_bots = worker_bots

    def get_worker_bot(self, worker_index: int) -> commands.Bot:
        """worker_index è 1-based (worker 1..5) — coerente con
        core/music_fleet_logic.find_free_worker() e la colonna
        worker_index della tabella music_sessions."""
        return self._worker_bots[worker_index - 1]

    async def get_worker_for_guild(self, guild_id: int) -> tuple[int, commands.Bot] | None:
        """
        Sola lettura — la sessione già assegnata a questo server, se
        esiste, SENZA assegnarne una nuova. Usata dai comandi che
        agiscono su una riproduzione già in corso (skip, stop, queue,
        ecc.): se nessun worker è assegnato, quei comandi devono
        fallire pulitamente ("nessuna riproduzione in corso"), non
        avviare per sbaglio una sessione nuova su un worker libero.
        """
        worker_index = await music_session_repo.get_worker_for_guild(guild_id)
        if worker_index is None:
            return None
        return worker_index, self.get_worker_bot(worker_index)

    async def get_or_assign_worker_for_guild(
        self, guild_id: int
    ) -> tuple[int, commands.Bot] | None:
        """
        La sessione già assegnata a questo server, se esiste — così
        un secondo /play nello stesso server non salta a un worker
        diverso a caso. Altrimenti il primo worker libero E presente
        in questo server (escludere chi non è invitato qui PRIMA di
        assegnarlo — non dopo — evita di occupare per sempre uno slot
        in `music_sessions` per un worker che non potrà mai connettersi
        in questo server, un bug reale trovato mentre si costruiva la
        gestione del limite istanze), assegnato e registrato subito.
        None se non c'è nessun worker sia libero sia presente qui in
        questo momento.
        """
        worker_index = await music_session_repo.get_worker_for_guild(guild_id)
        if worker_index is not None:
            return worker_index, self.get_worker_bot(worker_index)

        non_presenti = await self.get_missing_worker_indices(guild_id)
        occupati = await music_session_repo.get_occupied_workers()
        libero = find_free_worker(occupati | non_presenti | self._worker_non_pronti())
        if libero is None:
            return None

        await music_session_repo.assign_worker(guild_id, libero)
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
            for i in range(1, TOTAL_WORKERS + 1)
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
            i for i in range(1, TOTAL_WORKERS + 1) if not self.get_worker_bot(i).is_ready()
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

    async def release_guild(self, guild_id: int) -> None:
        """Chiamata quando una sessione finisce (es. /disconnect) —
        libera il worker per il prossimo server che ne ha bisogno."""
        await music_session_repo.release_guild(guild_id)


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

    release_guild() su un server che non aveva un worker assegnato
    (es. la radio del bot principale, mai registrata nella flotta)
    non fa nulla — DELETE su una riga inesistente, innocuo.
    """
    guild = player.guild
    await player.disconnect()
    if guild is not None:
        await fleet.release_guild(guild.id)
