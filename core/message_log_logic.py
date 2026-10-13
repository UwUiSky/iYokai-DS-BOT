"""
core/message_log_logic.py
=========================
Prepara il testo dei log dei messaggi: tagli ai limiti di Discord,
regole su cosa ignorare, riepilogo di una cancellazione in blocco.
Solo stringhe e numeri, niente discord.py.
Funzioni coperte: SPEC §8.16 (NF-02)
"""

from __future__ import annotations

import functools
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from core.testo_limiti import CAMPO_MAX, tronca

# LIM-55: un allegato deve restare sotto i 10 MiB. Si lascia margine.
FILE_MAX_BYTE = 8 * 1024 * 1024
RIGA_BLOCCO_MAX = 500

GENERI_IGNORA = ("canale", "utente", "prefisso", "ruolo", "regex")
PREFISSO_MAX = 20
IGNORATI_MAX_PER_SERVER = 200

# LOG-024: un'espressione regolare scritta da un amministratore gira su OGNI messaggio.
# Python non ha un limite di tempo per `re`: si ammettono solo schemi dal costo basso.
REGEX_MAX_LUNGHEZZA = 100
REGEX_MAX_PER_SERVER = 5
REGEX_TESTO_MAX = 500
REGEX_MAX_RIPETIZIONI_ILLIMITATE = 2


def senza_accento_grave(testo: str) -> str:
    """Un blocco di codice si chiude con tre accenti gravi: meglio neutralizzarli."""
    return testo.replace("```", "'''")


@dataclass(frozen=True)
class Ignorati:
    canali: frozenset[int] = field(default_factory=frozenset)
    utenti: frozenset[int] = field(default_factory=frozenset)
    prefissi: tuple[str, ...] = ()
    ruoli: frozenset[int] = field(default_factory=frozenset)
    regex: tuple[str, ...] = ()


def _scansiona_schema(schema: str) -> tuple[int, bool]:
    """(ripetizioni senza limite, c'è un gruppo ripetuto) contando solo i simboli veri: né escape né dentro [ ]."""
    illimitate = 0
    gruppo_ripetuto = False
    i = 0
    in_classe = False
    while i < len(schema):
        c = schema[i]
        if c == "\\":
            i += 2
            continue
        if in_classe:
            in_classe = c != "]"
        elif c == "[":
            in_classe = True
        elif c in "*+":
            illimitate += 1
        elif c == "{" and re.match(r"\{\d+,\}", schema[i:]):
            illimitate += 1
        if not in_classe and c == ")" and i + 1 < len(schema) and schema[i + 1] in "*+{":
            gruppo_ripetuto = True
        i += 1
    return illimitate, gruppo_ripetuto


def regex_non_valida(schema: str) -> str | None:
    """
    None se lo schema si può usare nel log, altrimenti il motivo (per chi lo ha scritto).
    Niente gruppi ripetuti, riferimenti all'indietro, lookaround; al massimo due
    ripetizioni senza limite (`*`, `+`, `{n,}`): il costo resta quadratico su 500 caratteri.
    """
    if not schema or len(schema) > REGEX_MAX_LUNGHEZZA:
        return f"L'espressione deve avere da 1 a {REGEX_MAX_LUNGHEZZA} caratteri."
    if re.search(r"\\[1-9]|\(\?P=|\(\?[=!<]", schema):
        return "Riferimenti all'indietro e lookaround non sono ammessi."
    illimitate, gruppo_ripetuto = _scansiona_schema(schema)
    if gruppo_ripetuto:
        return "Un gruppo non può essere ripetuto con *, + o {}: rallenterebbe il bot."
    if illimitate > REGEX_MAX_RIPETIZIONI_ILLIMITATE:
        return f"Al massimo {REGEX_MAX_RIPETIZIONI_ILLIMITATE} ripetizioni senza limite (*, +): l'espressione è troppo costosa."
    try:
        re.compile(schema, re.IGNORECASE)
    except re.error as errore:
        return f"Espressione non valida: {errore}"
    return None


@functools.lru_cache(maxsize=256)
def _compilata(schema: str):
    try:
        return re.compile(schema, re.IGNORECASE)
    except re.error:
        return None


def corrisponde_regex(schemi: tuple[str, ...], testo: str) -> bool:
    """True se il testo (tagliato a 500 caratteri) corrisponde a uno degli schemi."""
    taglio = testo[:REGEX_TESTO_MAX]
    for schema in schemi:
        compilata = _compilata(schema)
        if compilata is not None and compilata.search(taglio):
            return True
    return False


def da_ignorare(
    ignorati: Ignorati,
    *,
    channel_id: int,
    author_id: int | None,
    testo: str | None,
    category_id: int | None = None,
    thread_parent_id: int | None = None,
    ruoli_autore: Iterable[int] = (),
) -> bool:
    """True se il messaggio non va nel log (canale, categoria, thread, utente, ruolo, prefisso, regex)."""
    if channel_id in ignorati.canali:
        return True
    if category_id is not None and category_id in ignorati.canali:
        return True
    if thread_parent_id is not None and thread_parent_id in ignorati.canali:
        return True
    if author_id is not None and author_id in ignorati.utenti:
        return True
    if ignorati.ruoli and not ignorati.ruoli.isdisjoint(ruoli_autore):
        return True
    if testo and any(testo.startswith(p) for p in ignorati.prefissi):
        return True
    if testo and ignorati.regex and corrisponde_regex(ignorati.regex, testo):
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
    channel_id: int | None,
    user_id: int | None,
    prefisso: str | None,
    role_id: int | None = None,
    regex: str | None = None,
) -> tuple[str, str] | str:
    """
    Da cosa ha scelto chi usa /log ignora ricava (genere, valore). Se la scelta
    non va bene restituisce il messaggio da mostrare.
    """
    scelti = [x for x in (channel_id, user_id, prefisso, role_id, regex) if x is not None]
    if len(scelti) != 1:
        return "Scegli una sola cosa: un canale, un utente, un ruolo, un prefisso oppure un'espressione."
    if channel_id is not None:
        return ("canale", str(channel_id))
    if user_id is not None:
        return ("utente", str(user_id))
    if role_id is not None:
        return ("ruolo", str(role_id))
    if regex is not None:
        motivo = regex_non_valida(regex)
        return motivo if motivo else ("regex", regex)
    pulito = normalizza_prefisso(prefisso or "")
    if pulito is None:
        return f"Il prefisso deve avere da 1 a {PREFISSO_MAX} caratteri."
    return ("prefisso", pulito)


def testo_elenco_ignorati(ig: Ignorati) -> str:
    if not (ig.canali or ig.utenti or ig.prefissi or ig.ruoli or ig.regex):
        return "Il log dei messaggi non ignora niente."
    righe = []
    if ig.canali:
        righe.append("**Canali**: " + ", ".join(f"<#{c}>" for c in sorted(ig.canali)))
    if ig.utenti:
        righe.append("**Utenti**: " + ", ".join(f"<@{u}>" for u in sorted(ig.utenti)))
    if ig.ruoli:
        righe.append("**Ruoli**: " + ", ".join(f"<@&{r}>" for r in sorted(ig.ruoli)))
    if ig.regex:
        righe.append("**Espressioni**: " + ", ".join(f"`{x.replace('`', chr(39))}`" for x in ig.regex))
    if ig.prefissi:
        righe.append("**Prefissi**: " + ", ".join(f"`{p.replace('`', chr(39))}`" for p in ig.prefissi))
    return tronca("\n".join(righe), 1900)
