"""
core/backup_reminder_logic.py
=================================
Logica pura dei promemoria del Backup System — richiesta esplicita
dell'utente: un conto alla rovescia prima che un job in attesa del
click umano venga cancellato (timeout 24h, già esistente), e un
avviso quando tutti gli slot di iYokai Creator (max 10 server) sono
occupati.

Nessuna rete o Discord qui dentro — solo aritmetica su timestamp e
formattazione, interamente testabile senza nulla di esterno.
"""

from __future__ import annotations

from datetime import datetime, timedelta

TIMEOUT_HOURS = 24
REMINDER_THRESHOLD_HOURS = 2  # manda il promemoria quando restano
# meno di 2 ore alla scadenza — abbastanza margine perché la persona
# possa ancora agire, non così presto da sembrare prematuro.

MAX_CREATOR_GUILDS = 10  # limite reale di Discord per un bot non
# verificato — Creator deve restarci sempre sotto (SPEC.md §11.1).


def should_send_timeout_reminder(
    created_at: datetime,
    now: datetime,
    reminder_already_sent: bool,
    timeout_hours: int = TIMEOUT_HOURS,
    reminder_threshold_hours: int = REMINDER_THRESHOLD_HOURS,
) -> bool:
    """
    Vero se il job sta per scadere (meno di reminder_threshold_hours
    rimaste prima del timeout) e non è già stato mandato un
    promemoria per questo job — un solo promemoria per job, non uno
    ad ogni tick del worker (altrimenti spammerebbe la persona ogni
    60 secondi per ore).
    """
    if reminder_already_sent:
        return False

    scadenza = created_at + timedelta(hours=timeout_hours)
    tempo_rimanente = scadenza - now

    # Già scaduto (o scadrà esattamente ora) -> lascialo scadere per
    # davvero al prossimo expire_stale_jobs(), non ha senso un
    # promemoria per qualcosa che sta per sparire comunque in questo
    # stesso istante.
    return timedelta(0) < tempo_rimanente <= timedelta(hours=reminder_threshold_hours)


def format_time_remaining(
    created_at: datetime, now: datetime, timeout_hours: int = TIMEOUT_HOURS
) -> str:
    """
    "Xh Ym" prima della scadenza — o "scaduto" se il tempo è già
    passato (caso limite: il chiamante ha aspettato troppo a
    formattare dopo aver deciso di mandare il promemoria).
    """
    scadenza = created_at + timedelta(hours=timeout_hours)
    rimanente = scadenza - now

    secondi_rimanenti = rimanente.total_seconds()
    if secondi_rimanenti <= 0:
        return "scaduto"

    ore = int(secondi_rimanenti // 3600)
    minuti = int((secondi_rimanenti % 3600) // 60)
    return f"{ore}h {minuti}m"


def format_slot_wait_message(occupied_slots: int, max_slots: int = MAX_CREATOR_GUILDS) -> str:
    """
    Messaggio quando tutti gli slot di Creator sono occupati. Non
    una stima precisa di QUANDO si libererà uno slot (impossibile
    saperlo con certezza — dipende da quando altri amministratori
    cliccano i loro link, evento imprevedibile) — ma un limite
    massimo onesto: ogni slot occupato si libera entro il timeout di
    24h al più tardi, quindi lo diciamo esplicitamente invece di
    promettere una stima che non potremmo mantenere.
    """
    return (
        f"Tutti gli slot per la creazione di nuovi backup sono occupati "
        f"al momento ({occupied_slots}/{max_slots}). Il tuo backup partirà "
        f"automaticamente appena se ne libera uno — al più tardi entro "
        f"{TIMEOUT_HOURS} ore (i job bloccati scadono da soli dopo quel "
        f"tempo, liberando lo slot)."
    )
