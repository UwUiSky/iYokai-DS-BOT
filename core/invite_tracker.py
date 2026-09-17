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

import logging

import discord

from core.spam_trap_logic import diff_invite_uses

logger = logging.getLogger("iyokai.invite_tracker")


class InviteTracker:
    def __init__(self) -> None:
        # {guild_id: {invite_code: uses}}
        self._cache: dict[int, dict[str, int]] = {}
        # {guild_id: {invite_code: inviter_id}} — per risalire a chi
        # ha creato l'invito usato, richiesto dal log dello Spam Trap.
        self._inviters: dict[int, dict[str, int | None]] = {}

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
            self._cache[guild.id] = {}
            self._inviters[guild.id] = {}
            return
        except discord.HTTPException:
            logger.warning(
                "Errore temporaneo leggendo gli inviti del server %s.", guild.id
            )
            return

        self._cache[guild.id] = {invite.code: invite.uses or 0 for invite in invites}
        self._inviters[guild.id] = {
            invite.code: (invite.inviter.id if invite.inviter else None)
            for invite in invites
        }

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
        prima = dict(self._cache.get(guild.id, {}))

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
        self._cache[guild.id] = dopo
        self._inviters[guild.id] = inviters_dopo

        codice = diff_invite_uses(prima, dopo)
        if codice is None:
            return None
        return codice, inviters_dopo.get(codice)


# Istanza unica, condivisa da tutto il progetto — coerente con
# core/scheduler.py, core/memory_guard.py.
invite_tracker = InviteTracker()
