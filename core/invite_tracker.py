"""
core/invite_tracker.py
=========================
Cache in memoria degli inviti attivi di ogni server, per poter
rispondere alla domanda "con quale invito è entrato questo membro?"
al momento di on_member_join.

Riusabile: costruito per lo Spam Trap (SPEC.md §7.3, serve il
"codice invito usato + creatore dell'invito" nel log del ban), ma
la stessa infrastruttura serve anche al futuro modulo Verify
(SPEC.md §4.1, "Invite tracker" è elencato lì). Non duplicare
quando si scriverà Verify: importare questo modulo.

Solo la CLASSE DI SERVIZIO vive qui — niente discord.ext.commands.Cog,
niente listener. Il collegamento agli eventi Discord reali (on_ready,
on_guild_join, on_invite_create, on_invite_delete) vive in un Cog
sotto cogs/ (cogs/security/invite_sync.py), perché core/cog_manager.py
scopre e carica automaticamente SOLO i moduli dentro il pacchetto
`cogs` — un Cog definito qui in core/ non verrebbe mai caricato.
Stessa separazione già in uso per core/scheduler.py e
core/memory_guard.py (servizio in core/, avviato esplicitamente da
main.py; qui invece serve un Cog perché servono listener di eventi,
non un tasks.loop periodico).

**`resolve_join_invite()` — perché esiste accanto a `find_used_invite()`**
(bug evitato durante lo sviluppo di SPEC.md §8.8, PROGRESS.md Fase
70): `find_used_invite()` FA un fetch + diff + aggiorna la propria
istantanea ad ogni chiamata — chiamarlo due volte per lo STESSO join
(es. da Spam Trap E da un modulo di logging, entrambi nel proprio
`on_member_join`) farebbe sì che la seconda chiamata veda già
aggiornata l'istantanea dalla prima, calcoli un diff vuoto e
restituisca `None`. `resolve_join_invite(guild, member_id)` risolve
questo: memorizza il risultato per la coppia (server, membro) e, se
chiamato più volte per la stessa coppia — anche in concorrenza, dato
che `discord.py` non garantisce un ordine tra i listener di Cog
diversi sullo stesso evento — fa il lavoro reale una sola volta (un
`asyncio.Lock` per coppia) e restituisce la STESSA risposta a tutti.
Ogni nuovo modulo che deve sapere "con quale invito è entrato questo
membro" chiama questo metodo, mai `find_used_invite()` direttamente.

**Ingressi insieme nello stesso server.** Gli ingressi di un server si
risolvono uno alla volta (un `asyncio.Lock` per server). La regola è
"giusto o sconosciuto": se è salito il contatore di un solo invito e
gli usi bastano per tutti quelli che stanno entrando insieme, l'invito
è di tutti (caso tipico: un raid da un solo invito); gli usi in più
restano "in sospeso" per pochi secondi per gli ingressi che arrivano
subito dopo. Se gli usi sono meno delle persone, o sono saliti più
inviti, non si indovina: risultato `None`.

Limiti onesti (già noti, non scoperti a sorpresa):
- Non funziona con i join tramite vanity URL (non è un invito con
  un codice tracciabile nello stesso modo)
- Richiede il permesso MANAGE_GUILD per leggere guild.invites()
- Chi entra dal vanity URL entro pochi secondi da un raid può
  risultare entrato con l'invito del raid
Affidabilità pratica: alta ma non totale, coerente con quanto già
notato nello schema di progetto originale (~90%).
"""

# DA FARE (issue #98, fase F13): NF-27, Inviti: comando e classifica.
#   Vedi revisione/02-piano/NUOVE_FUNZIONI.md.

from __future__ import annotations

import asyncio
import logging
import time

import discord

from core.bounded_cache import BoundedCache
from core.spam_trap_logic import diff_invite_uses

logger = logging.getLogger("iyokai.invite_tracker")

# Limite di server tracciati contemporaneamente. Oltre questo numero,
# il server usato meno di recente viene scartato (politica LRU —
# vedi core/bounded_cache.py): un server lasciato dal bot, o
# semplicemente rimasto a lungo senza join, libera spazio da solo,
# senza bisogno di un evento on_guild_remove esplicito che lo
# rimuova. 5000 è ampiamente sopra le necessità attuali e lascia
# margine fino a quando il progetto non si avvicina davvero
# all'obiettivo dei 10.000 server dichiarato nel piano originale.
DEFAULT_MAX_TRACKED_GUILDS = 5000

# Per quanti secondi gli usi di un invito già visti ma non ancora
# attribuiti (raid: il contatore sale di 5 in un colpo) restano validi
# per gli ingressi che arrivano subito dopo.
DURATA_USI_IN_SOSPESO = 10


class InviteTracker:
    def __init__(
        self, max_tracked_guilds: int = DEFAULT_MAX_TRACKED_GUILDS, orologio=time.monotonic
    ) -> None:
        self._orologio = orologio
        # {guild_id: {invite_code: uses}}
        self._cache: BoundedCache[int, dict[str, int]] = BoundedCache(max_tracked_guilds)
        # {guild_id: {invite_code: inviter_id}} — per risalire a chi
        # ha creato l'invito usato, richiesto dal log dello Spam Trap.
        self._inviters: BoundedCache[int, dict[str, int | None]] = BoundedCache(
            max_tracked_guilds
        )
        # Risultato già risolto per una coppia (guild_id, member_id) —
        # vedi resolve_join_invite(). Dimensione più ampia dei server
        # tracciati: qui la chiave è per SINGOLO JOIN, non per server,
        # ma il dato è irrilevante dopo pochi secondi (letto una
        # manciata di volte subito dopo il join) — l'eviction LRU
        # basta, non serve una scadenza esplicita.
        self._join_results: BoundedCache[tuple[int, int], tuple[str, int | None] | None] = (
            BoundedCache(max_tracked_guilds * 4)
        )
        # Un lock per SERVER: gli ingressi di un server si risolvono
        # uno alla volta, così ognuno confronta contatori coerenti.
        # Lock e insieme dei membri "in corso" esistono solo mentre
        # c'è almeno un ingresso da risolvere per quel server.
        self._guild_locks: dict[int, asyncio.Lock] = {}
        self._in_corso: dict[int, set[int]] = {}
        # {guild_id: (codice, usi rimasti, scadenza)} — usi di un
        # invito già visti e non ancora attribuiti (vedi nota in cima).
        self._in_sospeso: BoundedCache[int, tuple[str, int, float]] = BoundedCache(
            max_tracked_guilds
        )

    async def refresh_guild(self, guild: discord.Guild) -> None:
        """
        Rilegge tutti gli inviti attivi di un server e aggiorna la
        cache. Va chiamato: all'avvio del bot per ogni server (in
        on_ready), e ogni volta che un invito viene creato o
        eliminato (on_invite_create/on_invite_delete) per tenere la
        cache coerente senza dover rileggere tutto ad ogni join.
        """
        try:
            invites = await guild.invites()
        except discord.Forbidden:
            logger.warning(
                "Permessi insufficienti (serve Manage Server) per leggere "
                "gli inviti del server %s: l'invite tracking non funzionerà "
                "su questo server.",
                guild.id,
            )
            self._cache.set(guild.id, {})
            self._inviters.set(guild.id, {})
            return
        except discord.HTTPException:
            logger.warning(
                "Errore temporaneo leggendo gli inviti del server %s.", guild.id
            )
            return

        self._cache.set(guild.id, {invite.code: invite.uses or 0 for invite in invites})
        self._inviters.set(
            guild.id,
            {
                invite.code: (invite.inviter.id if invite.inviter else None)
                for invite in invites
            },
        )

    async def find_used_invite(
        self, guild: discord.Guild
    ) -> tuple[str, int | None] | None:
        """
        Da chiamare in on_member_join, DOPO che il membro è già
        entrato. Rilegge lo stato attuale degli inviti, lo confronta
        con l'ultima istantanea in cache (diff_invite_uses, logica
        pura testata separatamente), aggiorna la cache per il
        prossimo join, e restituisce (codice_invito, id_creatore) o
        None se non determinabile.
        """
        prima = dict(self._cache.get(guild.id, {}) or {})

        try:
            invites_attuali = await guild.invites()
        except (discord.Forbidden, discord.HTTPException):
            return None

        dopo = {invite.code: invite.uses or 0 for invite in invites_attuali}
        inviters_dopo = {
            invite.code: (invite.inviter.id if invite.inviter else None)
            for invite in invites_attuali
        }

        # Aggiorna la cache per il prossimo join, a prescindere dal
        # risultato di questo.
        self._cache.set(guild.id, dopo)
        self._inviters.set(guild.id, inviters_dopo)

        codice = diff_invite_uses(prima, dopo)
        if codice is None:
            return None
        return codice, inviters_dopo.get(codice)

    async def resolve_join_invite(
        self, guild: discord.Guild, member_id: int
    ) -> tuple[str, int | None] | None:
        """
        Punto d'ingresso SICURO per "con quale invito è entrato
        questo membro?", pensato per essere chiamato da PIÙ moduli
        indipendenti sullo stesso join (Spam Trap, il Logging
        Avanzato, in futuro Verify) senza che si pestino i piedi —
        vedi la nota architetturale in cima al file per il bug che
        risolve rispetto a chiamare `find_used_invite()` direttamente
        da più posti.

        La prima chiamata per una coppia (guild_id, member_id) fa il
        lavoro reale; ogni chiamata successiva per la STESSA coppia
        (anche se in corso contemporaneamente, grazie al lock)
        restituisce lo stesso risultato già calcolato, senza un
        secondo fetch/diff.
        """
        key = (guild.id, member_id)
        if key in self._join_results:
            return self._join_results.get(key)

        # Nessun `await` tra queste righe e l'attesa del lock: chi
        # sta già lavorando vede subito che c'è un altro ingresso.
        in_corso = self._in_corso.setdefault(guild.id, set())
        in_corso.add(member_id)
        lock = self._guild_locks.setdefault(guild.id, asyncio.Lock())
        try:
            async with lock:
                # Un altro chiamante potrebbe aver già risolto questa
                # stessa coppia mentre aspettavamo il lock.
                if key in self._join_results:
                    return self._join_results.get(key)

                risultato = await self._risolvi(guild, member_id, in_corso)
                self._join_results.set(key, risultato)
                return risultato
        finally:
            in_corso.discard(member_id)
            if not in_corso:
                self._in_corso.pop(guild.id, None)
                self._guild_locks.pop(guild.id, None)

    def _usi_in_sospeso(self, guild_id: int) -> tuple[str, int] | None:
        sospeso = self._in_sospeso.get(guild_id)
        if sospeso is None:
            return None
        codice, usi, scadenza = sospeso
        if usi <= 0 or self._orologio() > scadenza:
            self._in_sospeso.delete(guild_id)
            return None
        return codice, usi

    async def _risolvi(
        self, guild: discord.Guild, member_id: int, in_corso: set[int]
    ) -> tuple[str, int | None] | None:
        """
        Un ingresso, dentro il lock del server. Vedi "Ingressi insieme"
        in cima al file per la regola.
        """
        prima = dict(self._cache.get(guild.id, {}) or {})
        try:
            invites_attuali = await guild.invites()
        except (discord.Forbidden, discord.HTTPException):
            return None

        dopo = {invite.code: invite.uses or 0 for invite in invites_attuali}
        inviters_dopo = {
            invite.code: (invite.inviter.id if invite.inviter else None)
            for invite in invites_attuali
        }
        self._cache.set(guild.id, dopo)
        self._inviters.set(guild.id, inviters_dopo)

        # Usi nuovi per invito. Un invito che prima non c'era non
        # conta (stessa prudenza di diff_invite_uses).
        usi = {
            codice: dopo[codice] - prima[codice]
            for codice in dopo
            if codice in prima and dopo[codice] > prima[codice]
        }
        sospeso = self._usi_in_sospeso(guild.id)
        if sospeso is not None:
            usi[sospeso[0]] = usi.get(sospeso[0], 0) + sospeso[1]

        if len(usi) != 1:
            return None  # nessun invito, oppure più di uno: non si indovina

        (codice, disponibili), = usi.items()
        # Gli altri ingressi dello stesso server arrivati nel frattempo.
        altri = len(in_corso - {member_id})
        if disponibili < 1 + altri:
            # Meno usi che persone entrate insieme: qualcuno è entrato
            # senza invito tracciabile, e non si può sapere chi.
            self._in_sospeso.delete(guild.id)
            return None

        if disponibili > 1:
            self._in_sospeso.set(
                guild.id, (codice, disponibili - 1, self._orologio() + DURATA_USI_IN_SOSPESO)
            )
        else:
            self._in_sospeso.delete(guild.id)
        return codice, inviters_dopo.get(codice)


# Istanza unica, condivisa da tutto il progetto — coerente con
# core/scheduler.py, core/memory_guard.py.
invite_tracker = InviteTracker()
