"""
core/message_log_logic.py
=========================
Prepara il testo dei log dei messaggi: tagli ai limiti di Discord,
regole su cosa ignorare, riepilogo di una cancellazione in blocco.
Solo stringhe e numeri, niente discord.py.
Funzioni coperte: SPEC §8.16 (NF-02)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.testo_limiti import CAMPO_MAX, tronca

# LIM-55: un allegato deve restare sotto i 10 MiB. Si lascia margine.
FILE_MAX_BYTE = 8 * 1024 * 1024
RIGA_BLOCCO_MAX = 500

GENERI_IGNORA = ("canale", "utente", "prefisso")
PREFISSO_MAX = 20
IGNORATI_MAX_PER_SERVER = 200


def senza_accento_grave(testo: str) -> str:
    """Un blocco di codice si chiude con tre accenti gravi: meglio neutralizzarli."""
    return testo.replace("```", "'''")


@dataclass(frozen=True)
class Ignorati:
    canali: frozenset[int] = field(default_factory=frozenset)
    utenti: frozenset[int] = field(default_factory=frozenset)
    prefissi: tuple[str, ...] = ()


def da_ignorare(
    ignorati: Ignorati,
    *,
    channel_id: int,
    author_id: int | None,
    testo: str | None,
    category_id: int | None = None,
    thread_parent_id: int | None = None,
) -> bool:
    """True se il messaggio non va nel log (canale, categoria, thread di un canale, utente, prefisso)."""
    if channel_id in ignorati.canali:
        return True
    if category_id is not None and category_id in ignorati.canali:
        return True
    if thread_parent_id is not None and thread_parent_id in ignorati.canali:
        return True
    if author_id is not None and author_id in ignorati.utenti:
        return True
    if testo and any(testo.startswith(p) for p in ignorati.prefissi):
        return True
    return False


def normalizza_prefisso(prefisso: str) -> str | None:
    """Il prefisso senza spazi ai bordi; None se vuoto o troppo lungo."""
    pulito = prefisso.strip()
    if not pulito or len(pulito) > PREFISSO_MAX:
        return None
    return pulito


def testo_allegati(nomi: list[str]) -> str:
    """Elenco dei nomi dei file allegati, entro un campo di embed."""
    if not nomi:
        return ""
    nomi_puliti = [n.replace("`", "'") for n in nomi]
    return tronca(", ".join(f"`{n}`" for n in nomi_puliti), CAMPO_MAX)


@dataclass(frozen=True)
class MessaggioArchiviato:
    message_id: int
    author_id: int | None
    author_nome: str
    testo: str
    quando: str  # già formattato (UTC ISO breve)


def riga_blocco(m: MessaggioArchiviato) -> str:
    testo = tronca(m.testo.replace("\n", " ⏎ "), RIGA_BLOCCO_MAX) or "(senza testo)"
    autore = f"{m.author_nome} ({m.author_id})" if m.author_id else "autore sconosciuto"
    return f"[{m.quando}] {autore} #{m.message_id}: {testo}"


def file_blocco(messaggi: list[MessaggioArchiviato], non_in_cache: int) -> bytes:
    """
    Testo del file allegato a una cancellazione in blocco, sotto FILE_MAX_BYTE.
    Se non c'è posto per tutte le righe, ci si ferma e lo si scrive in fondo.
    """
    intestazione = f"Messaggi cancellati: {len(messaggi) + non_in_cache} (in memoria: {len(messaggi)})\n\n"
    corpo: list[str] = []
    usati = len(intestazione.encode("utf-8"))
    omessi = 0
    for m in sorted(messaggi, key=lambda x: x.message_id):
        riga = riga_blocco(m) + "\n"
        peso = len(riga.encode("utf-8"))
        if usati + peso > FILE_MAX_BYTE - 200:
            omessi += 1
            continue
        usati += peso
        corpo.append(riga)
    coda = f"\n[{omessi} righe omesse per il limite di peso]\n" if omessi else ""
    return (intestazione + "".join(corpo) + coda).encode("utf-8")


def riepilogo_blocco(totale: int, in_memoria: int, channel_id: int) -> str:
    testo = f"**{totale}** messaggi cancellati in <#{channel_id}>."
    if in_memoria < totale:
        testo += f"\nDi {totale - in_memoria} non ho più il contenuto (troppo vecchi per la mia memoria)."
    return testo


def scegli_bersaglio(
    channel_id: int | None, user_id: int | None, prefisso: str | None
) -> tuple[str, str] | str:
    """
    Da cosa ha scelto chi usa /log ignora ricava (genere, valore). Se la scelta
    non va bene restituisce il messaggio da mostrare.
    """
    scelti = [x for x in (channel_id, user_id, prefisso) if x is not None]
    if len(scelti) != 1:
        return "Scegli una sola cosa: un canale, un utente oppure un prefisso."
    if channel_id is not None:
        return ("canale", str(channel_id))
    if user_id is not None:
        return ("utente", str(user_id))
    pulito = normalizza_prefisso(prefisso or "")
    if pulito is None:
        return f"Il prefisso deve avere da 1 a {PREFISSO_MAX} caratteri."
    return ("prefisso", pulito)


def testo_elenco_ignorati(ig: Ignorati) -> str:
    if not (ig.canali or ig.utenti or ig.prefissi):
        return "Il log dei messaggi non ignora niente."
    righe = []
    if ig.canali:
        righe.append("**Canali**: " + ", ".join(f"<#{c}>" for c in sorted(ig.canali)))
    if ig.utenti:
        righe.append("**Utenti**: " + ", ".join(f"<@{u}>" for u in sorted(ig.utenti)))
    if ig.prefissi:
        righe.append("**Prefissi**: " + ", ".join(f"`{p.replace('`', chr(39))}`" for p in ig.prefissi))
    return tronca("\n".join(righe), 1900)
