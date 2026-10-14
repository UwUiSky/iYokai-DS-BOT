"""
core/fun_extra_logic.py
=======================
Logica pura delle voci piccole di /fun (FUN-023..048, #131): scelta a caso,
dadi in formato "3d6+2", numero in un intervallo, testo trasformato,
contenuti curati (preferiresti, argomenti, consigli, oggetti magici,
lanci, prese in giro gentili) e link "cercalo su Google".
Ogni funzione che usa il caso riceve un `random.Random` dal chiamante.
Niente rete, niente Discord. Funzioni coperte: SPEC §16 (16.1, 16.8).
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from urllib.parse import quote_plus

MAX_MESSAGGIO = 2000
MAX_DADI = 20
MAX_FACCE = 1000
MAX_MODIFICATORE = 1000
MAX_OPZIONI = 20

_FORMULA = re.compile(r"^\s*(\d{1,2})?\s*d\s*(\d{1,4})\s*(?:([+-])\s*(\d{1,5}))?\s*$", re.IGNORECASE)


@dataclass
class EsitoDadi:
    tiri: list[int] = field(default_factory=list)
    modificatore: int = 0
    totale: int = 0
    errore: str | None = None


def tira_formula(formula: str, rng: random.Random) -> EsitoDadi:
    """Formato `NdM`, `NdM+K`, `NdM-K`; N da 1 a 20, M da 2 a 1000, K fino a 1000."""
    m = _FORMULA.match(formula or "")
    if not m:
        return EsitoDadi(errore="Formula non valida. Esempi: `d20`, `3d6+2`.")
    quanti = int(m.group(1) or 1)
    facce = int(m.group(2))
    mod = int(m.group(4) or 0) * (-1 if m.group(3) == "-" else 1)
    if not 1 <= quanti <= MAX_DADI:
        return EsitoDadi(errore=f"Si tirano da 1 a {MAX_DADI} dadi.")
    if not 2 <= facce <= MAX_FACCE:
        return EsitoDadi(errore=f"I dadi hanno da 2 a {MAX_FACCE} facce.")
    if abs(mod) > MAX_MODIFICATORE:
        return EsitoDadi(errore=f"Il modificatore arriva al massimo a {MAX_MODIFICATORE}.")
    tiri = [rng.randint(1, facce) for _ in range(quanti)]
    return EsitoDadi(tiri=tiri, modificatore=mod, totale=sum(tiri) + mod)


@dataclass
class EsitoScelta:
    scelta: str | None = None
    errore: str | None = None


def scegli_tra(opzioni: str, rng: random.Random) -> EsitoScelta:
    """Opzioni separate da virgola, punto e virgola o barra verticale."""
    voci = [v.strip() for v in re.split(r"[,;|]", opzioni or "") if v.strip()]
    if len(voci) < 2:
        return EsitoScelta(errore="Scrivi almeno due opzioni, separate da virgola.")
    if len(voci) > MAX_OPZIONI:
        return EsitoScelta(errore=f"Al massimo {MAX_OPZIONI} opzioni.")
    return EsitoScelta(scelta=rng.choice(voci))


def numero_casuale(minimo: int, massimo: int, rng: random.Random) -> int | None:
    if minimo > massimo:
        return None
    return rng.randint(minimo, massimo)


# --- testo trasformato -------------------------------------------------

def _alfabeto(maiuscole: int, minuscole: int, buchi: dict[str, str] | None = None, cifre: int | None = None):
    mappa: dict[str, str] = {}
    for i in range(26):
        mappa[chr(65 + i)] = chr(maiuscole + i)
        mappa[chr(97 + i)] = chr(minuscole + i)
    if cifre is not None:
        for i in range(10):
            mappa[str(i)] = chr(cifre + i)
    mappa.update(buchi or {})
    return mappa


_SCRIPT = _alfabeto(0x1D49C, 0x1D4B6, {"B": "ℬ", "E": "ℰ", "F": "ℱ", "H": "ℋ", "I": "ℐ", "L": "ℒ",
                                       "M": "ℳ", "R": "ℛ", "e": "ℯ", "g": "ℊ", "o": "ℴ"})
_GRASSETTO_CORSIVO = _alfabeto(0x1D468, 0x1D482)
_FRAKTUR = _alfabeto(0x1D504, 0x1D51E, {"C": "ℭ", "H": "ℌ", "I": "ℑ", "R": "ℜ", "Z": "ℨ"})
_FRAKTUR_GRASSETTO = _alfabeto(0x1D56C, 0x1D586)
_DOPPIO = _alfabeto(0x1D538, 0x1D552, {"C": "ℂ", "H": "ℍ", "N": "ℕ", "P": "ℙ", "Q": "ℚ", "R": "ℝ", "Z": "ℤ"},
                    cifre=0x1D7D8)
_MAIUSCOLETTO = dict(zip("abcdefghijklmnopqrstuvwxyz", "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ"))
_KEYCAP = {str(i): f"{i}️⃣" for i in range(10)}


def _largo(testo: str) -> str:
    return "".join("　" if c == " " else chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in testo)


def _emoji(testo: str) -> str:
    out = []
    for c in testo.lower():
        if "a" <= c <= "z":
            out.append(chr(0x1F1E6 + ord(c) - 97))
        elif c in _KEYCAP:
            out.append(_KEYCAP[c])
        elif c == " ":
            out.append("  ")
        else:
            out.append(c)
    return " ".join(out).replace("   ", "  ")


def _owo(testo: str) -> str:
    t = re.sub(r"[rl]", "w", testo)
    t = re.sub(r"[RL]", "W", t)
    t = re.sub(r"n([aeiou])", r"ny\1", t)
    return f"{t} owo"


_MAPPE = {
    "corsivo": _SCRIPT, "corsivo-grassetto": _GRASSETTO_CORSIVO, "gotico": _FRAKTUR,
    "gotico-grassetto": _FRAKTUR_GRASSETTO, "doppio": _DOPPIO, "maiuscoletto": _MAIUSCOLETTO,
}
STILI_TESTO = ("largo", "corsivo", "corsivo-grassetto", "gotico", "gotico-grassetto", "doppio",
               "maiuscoletto", "emoji", "applauso", "separato", "owo")


def trasforma_testo(stile: str, testo: str, separatore: str = " ") -> str:
    """Restituisce il testo nello stile scelto, tagliato a 2000 caratteri."""
    if stile in _MAPPE:
        mappa = _MAPPE[stile]
        out = "".join(mappa.get(c, mappa.get(c.lower(), c) if stile == "maiuscoletto" else c) for c in testo)
    elif stile == "largo":
        out = _largo(testo)
    elif stile == "emoji":
        out = _emoji(testo)
    elif stile == "applauso":
        out = " 👏 ".join(testo.split())
    elif stile == "separato":
        out = (separatore or " ").join(testo.split())
    elif stile == "owo":
        out = _owo(testo)
    else:
        out = testo
    return out[:MAX_MESSAGGIO]


# --- contenuti curati -----------------------------------------------------

PREFERIRESTI = (
    ("saper volare", "essere invisibile"),
    ("non dover più dormire", "non dover più mangiare"),
    ("vivere in un videogioco", "vivere in un film"),
    ("avere sempre 5 minuti di anticipo", "avere sempre un'ora di ritardo ma niente stress"),
    ("parlare con gli animali", "capire ogni lingua del mondo"),
    ("avere un drago come animale domestico", "avere un robot maggiordomo"),
    ("rigiocare solo il tuo gioco preferito per sempre", "giocare ogni giorno a un gioco mai visto"),
    ("vivere sempre in estate", "vivere sempre in inverno"),
    ("viaggiare nel passato", "viaggiare nel futuro"),
    ("avere lag zero per sempre", "avere ping sempre uguale ma 50 FPS in più"),
    ("mangiare solo pizza", "mangiare solo pasta"),
    ("vincere alla lotteria", "trovare il lavoro dei tuoi sogni"),
)
ARGOMENTI = (
    "Qual è l'ultimo gioco che ti ha davvero sorpreso?",
    "Se potessi cenare con un personaggio di fantasia, chi sceglieresti?",
    "Qual è il posto più bello in cui sei stato?",
    "Qual è la cosa più strana che hai mangiato?",
    "Quale film o serie rivedresti ogni anno?",
    "Che superpotere inutile vorresti avere?",
    "Qual è la tua colonna sonora preferita per giocare?",
    "Qual è stato il tuo primo videogioco?",
    "Se domani fossi libero tutto il giorno, cosa faresti?",
    "Qual è la tua opinione impopolare più innocua?",
    "Mare o montagna? Perché?",
    "Quale abilità vorresti imparare quest'anno?",
)
CONSIGLI = (
    "Bevi un bicchiere d'acqua: non fa mai male.",
    "Fai una pausa di cinque minuti e stiracchiati.",
    "Salva spesso, soprattutto prima del boss.",
    "Scrivi la cosa importante adesso, non domani.",
    "Se qualcosa non funziona, spegni e riaccendi. Sul serio.",
    "Fai un complimento a qualcuno oggi.",
    "Dormi abbastanza: i riflessi ringraziano.",
    "Una cosa alla volta: la lista si accorcia da sola.",
    "Chiedi aiuto quando sei bloccato da più di venti minuti.",
    "Esci a prendere un po' d'aria prima del prossimo turno.",
)
_OGGETTI = ("Spada", "Anello", "Mantello", "Scudo", "Bastone", "Amuleto", "Elmo", "Stivali", "Libro", "Lanterna")
_MATERIE = ("Cenere Lunare", "Mille Ombre", "Tuono Silenzioso", "Vetro Antico", "Ultima Alba", "Bosco Rovesciato",
            "Brace Gentile", "Sabbia del Tempo", "Nebbia Dorata", "Eco di Cristallo")
_EFFETTI = (
    "Rende chi lo porta incredibilmente bravo a trovare le chiavi perdute.",
    "Una volta al giorno trasforma un errore in un'ottima scusa.",
    "Fa suonare una fanfara ogni volta che entri in una stanza. Non si può spegnere.",
    "Illumina il cammino, ma solo se sei di buon umore.",
    "Fa sempre trovare parcheggio. In ogni mondo.",
    "Mormora consigli di cucina nei momenti meno opportuni.",
    "Rende le tue battute leggermente più divertenti del dovuto.",
)
_LANCI = ("una ciabatta", "un cuscino", "un pesce fresco", "una pallina da ping pong", "un calzino spaiato",
          "un tortellino", "un'anatra di gomma", "una zolletta di zucchero", "un pacchetto di patatine",
          "un peluche gigante")
_PRESE_IN_GIRO = (
    "{t} è così lento nelle risposte che il ping lo guarda con compassione.",
    "{t} dice \"ancora una partita\" e poi è l'alba.",
    "{t} ha più schede aperte che amici in vocale.",
    "{t} perde sempre il mouse, anche quando è in mano.",
    "{t} ha un talento raro: sbagliare il tasto giusto al momento giusto.",
    "{t} ha detto \"arrivo subito\" e il tempo si è offeso.",
)


def preferiresti(rng: random.Random) -> str:
    a, b = rng.choice(PREFERIRESTI)
    return f"Preferiresti **{a}** oppure **{b}**?"


def argomento(rng: random.Random) -> str:
    return rng.choice(ARGOMENTI)


def consiglio(rng: random.Random) -> str:
    return rng.choice(CONSIGLI)


def oggetto_magico(rng: random.Random) -> str:
    return f"**{rng.choice(_OGGETTI)} di {rng.choice(_MATERIE)}**\n{rng.choice(_EFFETTI)}"


def lancia_oggetto(rng: random.Random) -> str:
    return rng.choice(_LANCI)


def presa_in_giro(rng: random.Random, nome: str = "{t}") -> str:
    return rng.choice(_PRESE_IN_GIRO).replace("{t}", nome)


def google_link(testo: str) -> str:
    return "https://www.google.com/search?q=" + quote_plus(testo.strip())
