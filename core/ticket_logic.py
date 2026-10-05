"""
core/ticket_logic.py
=======================
Logica pura per il sistema di ticket — stesso principio di
core/voice_temp_logic.py e affini: solo stringhe/numeri/int qui
dentro, niente oggetti discord.py. Il cog (cogs/tickets/tickets.py)
converte gli oggetti Discord veri in questi valori semplici prima di
chiamare queste funzioni.

Nota su SPEC.md §13.10/§13.11 (transcript automatico): i messaggi si
leggono con channel.history(). Senza l'intent Message Content Discord
consegna testo e allegati vuoti, anche da lì (BUG-5): in quel caso il
transcript lo dice in testa (MESSAGE_CONTENT_WARNING).
Funzioni coperte: SPEC §13.2, §13.10, §13.11, §13.12, §13.13
"""

# DA FARE (issue #62, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §6 (Ticket).
# DA FARE (issue #84, fase F9): NF-13, Ticket: modulo, più pannelli,
#   chiusura automatica, voto. Vedi
#   revisione/02-piano/NUOVE_FUNZIONI.md.

from __future__ import annotations

import re

# Limiti di un menu a tendina di Discord (LIM-6): 25 opzioni, etichetta
# di 100 caratteri. Una voce fuori limite blocca il menu per tutti.
MAX_TICKET_CATEGORIES = 25
MAX_CATEGORY_LABEL_LENGTH = 100
# La più lunga è un'emoji personalizzata animata: <a:nome(32):id(20)>.
MAX_EMOJI_LENGTH = 64

_CUSTOM_EMOJI = re.compile(r"<a?:[A-Za-z0-9_]{2,32}:\d{15,20}>")
# Le emoji Unicode composte (famiglie, bandiere) arrivano a una
# quindicina di caratteri.
_MAX_UNICODE_EMOJI_LENGTH = 16
# Da qui in su stanno i simboli usati dalle emoji; © e ® sono le sole
# eccezioni più in basso.
_FIRST_SYMBOL_CODEPOINT = 0x203C


def looks_like_emoji(text: str) -> bool:
    """
    True se `text` sembra un'emoji usabile in un menu: una
    personalizzata (<:nome:id>) oppure un'emoji Unicode. È un
    controllo prudente fatto senza chiedere a Discord: scarta lettere,
    spazi e numeri soli ("ciao", ":smile:", "1"). L'ultima parola
    resta a Discord quando il menu viene mostrato.
    """
    if _CUSTOM_EMOJI.fullmatch(text):
        return True
    if not text or len(text) > _MAX_UNICODE_EMOJI_LENGTH:
        return False
    if any(ch.isalpha() or ch.isspace() for ch in text):
        return False
    return any(ord(ch) >= _FIRST_SYMBOL_CODEPOINT or ch in "©®" for ch in text)


def truncate_label(label: str, limit: int = MAX_CATEGORY_LABEL_LENGTH) -> str:
    """Taglia un'etichetta al limite di Discord, con "…" se tagliata."""
    if len(label) <= limit:
        return label
    return label[: limit - 1] + "…"


MESSAGE_CONTENT_WARNING = (
    "ATTENZIONE: il bot non ha l'intent Message Content, quindi Discord "
    "non gli consegna il testo dei messaggi. Questo transcript è incompleto."
)


def format_transcript_line(
    timestamp_str: str,
    author_display: str,
    content: str,
    attachment_names: list[str] | None = None,
) -> str:
    """Una singola riga del transcript testuale di un ticket."""
    testo = content if content else "*(nessun testo — solo allegati/embed)*"
    riga = f"[{timestamp_str}] {author_display}: {testo}"
    if attachment_names:
        riga += f" [allegati: {', '.join(attachment_names)}]"
    return riga


def split_text_by_size(text: str, max_bytes: int) -> list[str]:
    """
    Divide un testo in pezzi che, in UTF-8, pesano al massimo
    `max_bytes` ciascuno (LIM-55: un file allegato deve restare sotto
    i 10 MiB). Taglia a fine riga; solo una riga più lunga del limite
    viene spezzata a metà. I pezzi, riuniti, danno il testo di partenza.
    """
    pezzi: list[str] = []
    corrente: list[str] = []
    peso = 0

    def chiudi() -> None:
        nonlocal corrente, peso
        if corrente:
            pezzi.append("".join(corrente))
        corrente, peso = [], 0

    for riga in text.splitlines(keepends=True):
        for frammento in _split_long_line(riga, max_bytes):
            peso_frammento = len(frammento.encode("utf-8"))
            if peso + peso_frammento > max_bytes:
                chiudi()
            corrente.append(frammento)
            peso += peso_frammento
    chiudi()
    return pezzi or [""]


def _split_long_line(line: str, max_bytes: int) -> list[str]:
    """Una riga entro il limite resta intera; una più lunga viene spezzata."""
    if len(line.encode("utf-8")) <= max_bytes:
        return [line]
    # Un carattere pesa al massimo 4 byte: così ogni pezzo sta nel limite.
    passo = max(1, max_bytes // 4)
    return [line[inizio : inizio + passo] for inizio in range(0, len(line), passo)]


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
