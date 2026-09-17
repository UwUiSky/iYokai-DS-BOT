"""
core/spam_trap_logic.py
==========================
Logica pura dello Spam Trap — stesso principio di core/permissions.py
e affini: solo numeri/date/stringhe qui dentro, niente discord.py.

Nota architetturale importante, da conoscere prima di leggere il
resto del modulo (cogs/security/spam_trap.py): la cattura del
contenuto del messaggio che scatta la trappola e il transcript NON
richiedono il Message Content Intent. Quell'intent è un privilegio
del GATEWAY (gli eventi in tempo reale tipo on_message) — una
chiamata REST esplicita come channel.fetch_message(id) restituisce
il contenuto pieno indipendentemente dall'intent, perché è governata
dal normale permesso READ_MESSAGE_HISTORY, non dal privilegio
gateway. Per questo l'indicizzazione (vedi
core/repositories/spam_trap_repo.py) salva SOLO id/canale/timestamp
di ogni messaggio — zero contenuto, zero intent — e il contenuto
viene recuperato via fetch esplicito solo nel momento in cui serve
davvero (utente bannato dalla trappola). Questa è un'assunzione sul
comportamento reale dell'API Discord che va verificata sul server di
test, non solo dedotta — annotato anche nel cog.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Un utente può fare appello al ban al massimo una volta ogni 24 ore,
# per evitare che qualcuno spammi il bot in DM cercando di forzare
# l'attenzione dello staff.
APPEAL_COOLDOWN_SECONDS = 24 * 3600

# Discord permette al ban nativo di cancellare automaticamente i
# messaggi degli ultimi N secondi (delete_message_seconds), MASSIMO
# 7 giorni. Oltre, serve la purge supplementare via indicizzazione.
BAN_NATIVE_DELETE_SECONDS = 7 * 86400

# Fino a dove risalire con la purge supplementare (oltre i 7 giorni
# già coperti dal ban nativo).
PURGE_LOOKBACK_DAYS = 30

# Discord accetta la cancellazione BULK (fino a 100 id in una sola
# chiamata) solo per messaggi più recenti di 14 giorni. Oltre, serve
# cancellare uno per uno.
BULK_DELETE_MAX_AGE_DAYS = 14


def can_appeal(last_appeal_at: datetime | None, now: datetime | None = None) -> bool:
    if last_appeal_at is None:
        return True
    current = now or datetime.now(timezone.utc)
    return (current - last_appeal_at).total_seconds() >= APPEAL_COOLDOWN_SECONDS


def partition_messages_for_deletion(
    message_records: list[tuple[int, datetime]], now: datetime | None = None
) -> tuple[list[int], list[int]]:
    """
    Riceve una lista di (message_id, created_at) — quelli restituiti
    dall'indicizzazione, già filtrati alla finestra 7-30 giorni (i
    più recenti di 7 giorni li ha già gestiti il ban nativo, vedi
    BAN_NATIVE_DELETE_SECONDS). Li divide in due liste:
    - bulk_eligible: più recenti di 14 giorni, cancellabili in blocco
      (fino a 100 alla volta) con channel.delete_messages()
    - individual: più vecchi di 14 giorni, Discord richiede una
      chiamata di cancellazione separata per ciascuno

    Passare a channel.delete_messages() anche un solo id più vecchio
    di 14 giorni fa fallire l'INTERA chiamata bulk, non solo quel
    messaggio — da qui la necessità di partizionare correttamente
    PRIMA di chiamare l'API, non scoprirlo da un errore HTTP.
    """
    current = now or datetime.now(timezone.utc)
    soglia = current - timedelta(days=BULK_DELETE_MAX_AGE_DAYS)

    bulk_eligible = [mid for mid, created_at in message_records if created_at >= soglia]
    individual = [mid for mid, created_at in message_records if created_at < soglia]
    return bulk_eligible, individual


def purge_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    """
    Restituisce (inizio, fine) della finestra su cui la purge
    supplementare deve cercare messaggi: da 30 giorni fa fino a 7
    giorni fa. I messaggi più recenti di 7 giorni sono già coperti
    dal delete_message_seconds del ban nativo — includerli di nuovo
    qui significherebbe tentare di cancellare due volte gli stessi
    messaggi (innocuo ma inutile: un secondo tentativo su un
    messaggio già cancellato fallisce silenziosamente per ciascun id,
    ma è comunque traffico e complessità evitabili).
    """
    current = now or datetime.now(timezone.utc)
    inizio = current - timedelta(days=PURGE_LOOKBACK_DAYS)
    fine = current - timedelta(seconds=BAN_NATIVE_DELETE_SECONDS)
    return inizio, fine


def diff_invite_uses(before: dict[str, int], after: dict[str, int]) -> str | None:
    """
    Confronta due istantanee {codice_invito: numero_utilizzi} e
    restituisce il codice il cui contatore è aumentato — cioè
    l'invito usato dal membro appena entrato.

    Restituisce None se:
    - nessun codice è aumentato (es. ingresso tramite vanity URL,
      che non è un invito normale)
    - PIÙ di un codice è aumentato (caso ambiguo raro — due persone
      entrate nello stesso istante con inviti diversi tra un fetch e
      l'altro): meglio dire "non determinato" che indovinare male
    - un codice nuovo appare in `after` ma non in `before` (invito
      creato e usato tra un fetch e l'altro — trattato come
      indeterminato per la stessa cautela)
    """
    aumentati = [
        code for code, uses in after.items()
        if code in before and uses > before[code]
    ]
    if len(aumentati) == 1:
        return aumentati[0]
    return None
