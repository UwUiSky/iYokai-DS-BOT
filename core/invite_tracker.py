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

Limiti onesti (già noti, non scoperti a sorpresa):
- Non funziona con i join tramite vanity URL (non è un invito con
  un codice tracciabile nello stesso modo)
- Richiede il permesso MANAGE_GUILD per leggere guild.invites()
- Se due persone entrano nello stesso istante con inviti diversi tra
  un fetch e l'altro, il caso è ambiguo e diff_invite_uses()
  (core/spam_trap_logic.py) restituisce None piuttosto che indovinare
Affidabilità pratica: alta ma non totale, coerente con quanto già
notato nello schema di progetto originale (~90%).
"""

from __future__ import annotations

import asyncio
import logging

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


class InviteTracker:
    def __init__(self, max_tracked_guilds: int = DEFAULT_MAX_TRACKED_GUILDS) -> None:
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
        # Un lock per coppia (guild_id, member_id) mentre la
        # risoluzione è in corso, per far sì che chiamate concorrenti
        # per lo STESSO join aspettino il risultato invece di
        # innescare ciascuna il proprio diff (che si pesterebbero i
        # piedi, vedi nota in cima al file).
        self._join_locks: dict[tuple[int, int], asyncio.Lock] = {}

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

        lock = self._join_locks.setdefault(key, asyncio.Lock())
        async with lock:
            # Un altro chiamante potrebbe aver già risolto questa
            # stessa coppia mentre aspettavamo il lock.
            if key in self._join_results:
                return self._join_results.get(key)

            risultato = await self.find_used_invite(guild)
            self._join_results.set(key, risultato)
            self._join_locks.pop(key, None)
            return risultato


# Istanza unica, condivisa da tutto il progetto — coerente con
# core/scheduler.py, core/memory_guard.py.
invite_tracker = InviteTracker()
