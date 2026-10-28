"""
core/ai_ricerca_logic.py
========================
Logica pura dell'assistente che cerca i comandi: scelta della strada (prima
regole e database, l'AI solo se serve), stato di ogni comando, comandi vicini
spiegati, scoperta delle attività del server, piano in più passi con i soli
comandi veri.
Funzioni coperte: SPEC §25.12, §25.25, §25.28–§25.31, §25.34, §25.101 (AI-R-006, AI-R-026, AI-R-029..032, AI-R-036, AI-R-108)
Dipende da: core/command_search_logic.py, core/ai_testi_logic.py
"""

from __future__ import annotations

import enum
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from core import command_search_logic as ricerca
from core.ai_testi_logic import estrai_json

MAX_PASSI = 5
MAX_ATTIVAZIONI = 3
SOGLIA_SICURA = 1.0
DISTACCO_SICURO = 0.3
MAX_PAROLE_RICERCA_SICURA = 3


# ---------------------------------------------------------------- strada
class Strada(enum.Enum):
    SCOPERTA = "scoperta"  # «cosa posso fare qui?»: elenco fisso, senza AI
    FAQ = "faq"  # la domanda è il titolo di una voce della base di conoscenza
    RICERCA = "ricerca"  # un solo comando evidente: basta la ricerca per parole
    AI = "ai"


@dataclass(frozen=True)
class Decisione:
    strada: Strada
    testo: str = ""  # per FAQ: il testo della voce


_SCOPERTA = re.compile(
    r"\b(cosa|che cosa|che)\s+(posso|si pu[oò]|c['’]?[eè])\s+(fare|da fare)|"
    r"\bwhat\s+(can|could)\s+i\s+do\b|\bwhat['’]?s\s+(there\s+)?to\s+do\b|"
    r"\b(attivit[aà]|funzioni|giochi|eventi)\s+(attiv[ei]|disponibil[ei]|del server)\b|"
    r"\bcosa\s+c['’]?[eè]\s+(qui|di|nel)\b",
    re.IGNORECASE,
)


def domanda_di_scoperta(domanda: str) -> bool:
    return bool(_SCOPERTA.search(domanda or ""))


def _parole(testo: str) -> frozenset[str]:
    return frozenset(ricerca._tokenizza(testo))


def faq_esatta(domanda: str, voci: Iterable[tuple[str, str]]) -> str | None:
    """Il testo della voce il cui titolo ha le stesse parole della domanda (a meno delle parole vuote)."""
    parole = _parole(domanda)
    if not parole:
        return None
    for titolo, testo in voci:
        if _parole(titolo) == parole:
            return testo
    return None


def ricerca_sicura(domanda: str, comandi: Sequence[ricerca.ComandoInfo]) -> bool:
    """Un comando solo, evidente: l'AI non serve (costa e non aggiunge nulla)."""
    pulita = domanda.strip().lstrip("/").strip()
    if not pulita:
        return False
    if len(_parole(pulita)) > MAX_PAROLE_RICERCA_SICURA and pulita.lower() not in {c.percorso for c in comandi}:
        return False
    punti = sorted((ricerca.punteggio(pulita, c) for c in comandi), reverse=True)
    if not punti or punti[0] < SOGLIA_SICURA:
        return False
    return len(punti) == 1 or punti[1] <= punti[0] - DISTACCO_SICURO


def scegli_strada(
    domanda: str, comandi: Sequence[ricerca.ComandoInfo], voci_faq: Iterable[tuple[str, str]] = ()
) -> Decisione:
    """Regole prima, database poi, AI per ultima (AI-R-006). L'ordine conta: ogni passo è più economico del successivo."""
    if domanda_di_scoperta(domanda):
        return Decisione(Strada.SCOPERTA)
    faq = faq_esatta(domanda, voci_faq)
    if faq is not None:
        return Decisione(Strada.FAQ, faq)
    if ricerca_sicura(domanda, comandi):
        return Decisione(Strada.RICERCA)
    return Decisione(Strada.AI)


# ---------------------------------------------------------------- stato di un comando
@dataclass(frozen=True)
class ContestoComando:
    """Ciò che serve a dire in che stato è un comando per chi lo chiede."""

    permesso: bool = True
    moduli_mancanti: tuple[str, ...] = ()  # moduli che il bot non conosce
    premium_bloccato: bool = False
    moduli_spenti: tuple[str, ...] = ()  # spenti dall'admin del server
    configurato: bool = False


@dataclass(frozen=True)
class StatoComando:
    codice: str
    etichetta: str
    modulo_da_attivare: str | None = None


ETICHETTE_STATO = {
    "permesso": "serve un permesso che non hai",
    "manca_modulo": "manca un modulo",
    "premium": "serve il premium",
    "spento": "spento in questo server",
    "configurato": "già configurato",
    "disponibile": "disponibile",
}


def stato_comando(ctx: ContestoComando) -> StatoComando:
    """Dal più grave al meno grave: permesso, modulo mancante, premium, spento, già configurato, disponibile."""
    if not ctx.permesso:
        codice = "permesso"
    elif ctx.moduli_mancanti:
        codice = "manca_modulo"
    elif ctx.premium_bloccato:
        codice = "premium"
    elif ctx.moduli_spenti:
        return StatoComando("spento", ETICHETTE_STATO["spento"], ctx.moduli_spenti[0])
    elif ctx.configurato:
        codice = "configurato"
    else:
        codice = "disponibile"
    return StatoComando(codice, ETICHETTE_STATO[codice])


def riga_con_stato(menzione: str, stato: StatoComando) -> str:
    return f"{menzione} — {stato.etichetta}"


def moduli_da_proporre(stati: Iterable[StatoComando], massimo: int = MAX_ATTIVAZIONI) -> list[str]:
    """I moduli spenti da offrire con un bottone «Attiva» (senza doppioni, al massimo 3)."""
    visti: list[str] = []
    for s in stati:
        if s.modulo_da_attivare and s.modulo_da_attivare not in visti:
            visti.append(s.modulo_da_attivare)
    return visti[:massimo]


# ---------------------------------------------------------------- comandi vicini
# (comando, ((vicino, in cosa è diverso), ...)): l'AI serve solo a capire la domanda,
# le differenze sono scritte qui e non cambiano da una risposta all'altra.
COMANDI_VICINI: dict[str, tuple[tuple[str, str], ...]] = {
    "modban ban": (
        ("modban tempban", "il ban dura per un tempo scelto e poi il membro può rientrare"),
        ("modban softban", "banna e sbanna subito: cancella i messaggi recenti, il membro può rientrare"),
        ("mod timeout", "non lo allontana: gli toglie solo la parola fino a 28 giorni"),
    ),
    "modban tempban": (
        ("modban ban", "il ban è permanente"),
        ("mod timeout", "il membro resta nel server ma non può scrivere"),
    ),
    "modban softban": (
        ("modban ban", "il ban resta finché qualcuno non lo toglie"),
        ("modban kick", "espelle senza cancellare i messaggi"),
    ),
    "modban kick": (
        ("modban ban", "il membro non può tornare con un invito"),
        ("modban softban", "cancella anche i messaggi recenti"),
    ),
    "mod timeout": (
        ("mod mute", "usa un ruolo dedicato invece del timeout di Discord"),
        ("mod warn", "solo un avviso, nessun blocco"),
    ),
    "mod mute": (("mod timeout", "usa il timeout di Discord, con una durata massima di 28 giorni"),),
    "mod warn": (
        ("mod nota aggiungi", "una nota riservata allo staff, il membro non la vede"),
        ("mod timeout", "oltre all'avviso gli toglie la parola"),
    ),
    "mod clear": (
        ("mod slowmode", "non cancella: rallenta chi scrive"),
        ("mod lock", "non cancella: blocca la scrittura nel canale"),
    ),
    "mod lock": (
        ("mod slowmode", "il canale resta aperto ma a ritmo lento"),
        ("mod blocco attiva", "blocca tutto il server, non un canale solo"),
    ),
    "mod blocco attiva": (
        ("mod lock", "blocca un canale solo"),
        ("security panico attiva", "il panico applica anche le regole d'emergenza"),
    ),
    "security panico attiva": (("mod blocco attiva", "blocca il server senza le regole d'emergenza"),),
    "utility report": (("ticket apri", "apre una conversazione con lo staff invece di una segnalazione"),),
    "ticket apri": (("utility report", "segnala un utente, senza aprire una conversazione"),),
    "automod parole add": (
        ("automod odio parola", "gestisce le parole d'odio, anche quelle lecite"),
        ("automod filtri messaggi", "conta messaggi ripetuti, link e menzioni"),
    ),
    "log cerca utente": (("mod caso storico", "mostra solo le sanzioni, non tutti gli eventi"),),
    "mod caso storico": (("log cerca utente", "mostra tutti gli eventi del registro, non solo le sanzioni"),),
    "utility ai riassumi": (("utility ai spiega", "spiega un solo messaggio, non un canale"),),
    "utility ai spiega": (("utility ai riassumi", "riassume gli ultimi messaggi di un canale"),),
}


def vicini_di(percorso: str, esistenti: Mapping[str, ricerca.ComandoInfo], gia_citati: Iterable[str] = ()) -> list[tuple[ricerca.ComandoInfo, str]]:
    """I comandi vicini che esistono davvero e non sono già nella risposta, con la frase di differenza (al massimo 3)."""
    escludi = set(gia_citati) | {percorso}
    trovati = []
    for vicino, frase in COMANDI_VICINI.get(percorso, ()):
        if vicino in esistenti and vicino not in escludi:
            trovati.append((esistenti[vicino], frase))
    return trovati[:3]


def testo_vicini(righe: Sequence[tuple[str, str]]) -> str:
    """«Alternative» per l'embed: (menzione, frase) in elenco. Vuoto se non ce ne sono."""
    if not righe:
        return ""
    return "\n".join(f"- {m}: {frase}" for m, frase in righe)


# ---------------------------------------------------------------- scoperta
GRUPPI_ATTIVITA: tuple[tuple[str, str], ...] = (
    ("fun", "Giochi e divertimento"),
    ("level", "Livelli, monete e negozio"),
    ("clan", "Clan"),
    ("music", "Musica"),
    ("utility", "Strumenti per tutti"),
    ("ticket", "Assistenza"),
)


def elenco_scoperta(
    comandi: Sequence[ricerca.ComandoInfo], eventi: Sequence[str] = (), per_gruppo: int = 3
) -> str:
    """
    «Cosa posso fare qui?»: gli eventi in corso e, per ogni area, qualche comando che la persona
    può usare. Elenco fisso: funziona anche con l'AI ferma (AI-R-032).
    """
    righe: list[str] = []
    if eventi:
        righe.append("**In corso adesso**")
        righe += [f"- {e}" for e in eventi]
    for gruppo, titolo in GRUPPI_ATTIVITA:
        propri = [c for c in comandi if c.gruppo == gruppo][:per_gruppo]
        if propri:
            righe.append(f"**{titolo}**")
            righe += [f"- /{c.percorso}: {c.descrizione}" for c in propri]
    return "\n".join(righe) if righe else "Per ora non trovo attività da proporti: prova `-cerca-comando`."


# ---------------------------------------------------------------- piano in più passi
_COMPOSTA = re.compile(r"\b(poi|e poi|quindi|inoltre|and then|and also)\b|,\s*(e|and)\b|\bchi (entra|arriva|scrive)\b|\bwhen (someone|a user)\b", re.IGNORECASE)


def richiesta_composta(domanda: str) -> bool:
    """La domanda descrive un risultato in più parti ("chi entra riceve il ruolo e un messaggio")."""
    return len(domanda) >= 40 and bool(_COMPOSTA.search(domanda))


ISTRUZIONI_PIANO = (
    "Scomponi la richiesta in passi, ognuno è UN comando dell'elenco. Rispondi SOLO con JSON: "
    '{"passi": [{"comando": "percorso senza barra", "valori": "cosa inserire", "modulo": "nome del modulo da accendere o vuoto"}]}. '
    f"Al massimo {MAX_PASSI} passi, solo comandi dell'elenco."
)


@dataclass(frozen=True)
class Passo:
    comando: ricerca.ComandoInfo
    valori: str
    modulo: str | None


def leggi_piano(testo: str, comandi: Sequence[ricerca.ComandoInfo]) -> list[Passo]:
    """I passi dell'AI resi sicuri: solo comandi veri e visibili alla persona, senza doppioni, al massimo 5."""
    dati = estrai_json(testo)
    if not dati or not isinstance(dati.get("passi"), list):
        return []
    per_percorso = {c.percorso: c for c in comandi}
    passi: list[Passo] = []
    for grezzo in dati["passi"]:
        if not isinstance(grezzo, dict):
            continue
        percorso = str(grezzo.get("comando") or "").strip().lstrip("/").lower()
        comando = per_percorso.get(percorso)
        if comando is None or any(p.comando is comando for p in passi):
            continue
        valori = re.sub(r"[`<>@]", "", str(grezzo.get("valori") or "")).strip()[:200]
        modulo = str(grezzo.get("modulo") or "").strip().lower()[:40] or None
        passi.append(Passo(comando, valori, modulo))
        if len(passi) >= MAX_PASSI:
            break
    return passi


def moduli_del_piano(passi: Sequence[Passo], validi: Iterable[str]) -> list[str]:
    """I moduli da accendere per il piano: quelli dichiarati dai passi o dal comando, solo se esistono."""
    validi = set(validi)
    trovati: list[str] = []
    for p in passi:
        for m in ((p.modulo,) if p.modulo else ()) + tuple(p.comando.moduli):
            if m in validi and m not in trovati:
                trovati.append(m)
    return trovati


def testo_piano(passi: Sequence[Passo], menzioni: Mapping[str, str]) -> str:
    return "\n".join(
        f"{i}. {menzioni.get(p.comando.percorso, '/' + p.comando.percorso)}" + (f" — {p.valori}" if p.valori else "")
        for i, p in enumerate(passi, 1)
    )


# ---------------------------------------------------------------- istruzioni per l'AI
def elenco_per_ai(comandi: Sequence[ricerca.ComandoInfo], spenti: Mapping[str, str] | None = None, massimo: int = 200) -> str:
    """Il registro dei comandi letto dall'AI; i comandi di un modulo spento portano l'avviso."""
    spenti = spenti or {}
    righe = []
    for c in comandi[:massimo]:
        riga = f"/{c.percorso} — {c.descrizione}"
        if c.percorso in spenti:
            riga += f" (modulo {spenti[c.percorso]} spento nel server)"
        righe.append(riga)
    return "\n".join(righe)


ISTRUZIONI_STATO = (
    " Se un comando è segnato come spento, dillo e suggerisci di accendere il modulo. "
    "Rispondi nella lingua della domanda."
)
