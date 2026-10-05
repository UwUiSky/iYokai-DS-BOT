"""
core/ticket_logic.py
=======================
Logica pura per il sistema di ticket — stesso principio di
core/voice_temp_logic.py e affini: solo stringhe/numeri/int qui
dentro, niente oggetti discord.py. Il cog (cogs/tickets/tickets.py)
converte gli oggetti Discord veri in questi valori semplici prima di
chiamare queste funzioni.

Nota su SPEC.md §13.10/§13.11 (transcript automatico): la lettura dei
messaggi per costruirlo avviene via channel.history() (REST), che
restituisce il contenuto pieno indipendentemente dal Message Content
Intent — quell'intent è un privilegio del solo GATEWAY (eventi in
tempo reale), non della history REST governata dal normale permesso
READ_MESSAGE_HISTORY. Stessa assunzione già verificata e documentata
in core/spam_trap_logic.py per lo Spam Trap: qui si applica lo stesso
principio, non è una nuova scoperta.
"""

# DA FARE (issue #62, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §6 (Ticket).
# DA FARE (issue #84, fase F9): NF-13, Ticket: modulo, più pannelli,
#   chiusura automatica, voto. Vedi
#   revisione/02-piano/NUOVE_FUNZIONI.md.

from __future__ import annotations


def format_transcript_line(timestamp_str: str, author_display: str, content: str) -> str:
    """Una singola riga del transcript testuale di un ticket."""
    testo = content if content else "*(nessun testo — solo allegati/embed)*"
    return f"[{timestamp_str}] {author_display}: {testo}"


def build_transcript_text(
    header_lines: list[str], body_lines: list[str]
) -> str:
    """
    Assembla il transcript completo: intestazione (numero ticket,
    apertura, chiusura, ecc.) + le righe dei messaggi in ordine
    cronologico. Nessun messaggio nel canale -> corpo con un avviso
    esplicito, non una lista vuota silenziosa.
    """
    corpo = "\n".join(body_lines) if body_lines else "(nessun messaggio nel canale)"
    return "\n".join(header_lines) + "\n\n" + corpo + "\n"


def is_first_response(author_id: int, ticket_owner_id: int, author_is_bot: bool) -> bool:
    """
    SPEC.md §13.12: un messaggio conta come "prima risposta" se non è
    né dell'utente che ha aperto il ticket né di un bot (es. il
    messaggio di benvenuto automatico del bot stesso non deve mai
    contare come risposta di un operatore).
    """
    if author_is_bot:
        return False
    return author_id != ticket_owner_id


def merge_support_role_ids(
    legacy_role_id: int | None, extra_role_ids: list[int]
) -> list[int]:
    """
    SPEC.md §13.13: combina il vecchio ruolo di supporto singolo
    (retrocompatibilità — server già configurati prima di questa
    funzionalità) con la nuova lista configurabile, senza duplicati e
    preservando l'ordine di inserimento.
    """
    risultato: list[int] = []
    if legacy_role_id is not None:
        risultato.append(legacy_role_id)
    for role_id in extra_role_ids:
        if role_id not in risultato:
            risultato.append(role_id)
    return risultato


def format_duration_seconds(seconds: float | None) -> str:
    """
    Formatta una durata in secondi in una stringa leggibile
    (es. "2m 15s", "1h 4m") — "n/d" se non disponibile (nessun dato
    su cui calcolare una media, es. nessuna risposta ancora
    registrata).
    """
    if seconds is None:
        return "n/d"
    totale = int(round(seconds))
    ore, resto = divmod(totale, 3600)
    minuti, secondi = divmod(resto, 60)
    if ore > 0:
        return f"{ore}h {minuti}m"
    if minuti > 0:
        return f"{minuti}m {secondi}s"
    return f"{secondi}s"
