"""
core/dungeon_logic.py
=====================
Regole del dungeon di gruppo, senza Discord e senza database: classi per tema,
probabilità di riuscita secondo classi e livelli di chi vota, conteggio dei
voti, lettura e controllo delle storie scritte dall'AI (albero di stanze),
storia pronta per quando l'AI è ferma.
Funzioni coperte: SPEC §25.53–§25.55, §25.99 (AI-R-058..060, AI-R-106)
"""

from __future__ import annotations

import random
import re
from collections import Counter
from dataclasses import dataclass, field

from core.ai_testi_logic import estrai_json

PROVE = ("forza", "astuzia", "magia")
MAX_NODI = 12
MAX_SCELTE = 3
MAX_TESTO_NODO = 700
MAX_TESTO_SCELTA = 80
SECONDI_LOBBY = 60
SECONDI_VOTO = 90
MAX_STANZE = 8  # tetto alla lunghezza di una partita
_ID = re.compile(r"^[a-z0-9_]{1,24}$")

CLASSI: dict[str, tuple[tuple[str, str], ...]] = {
    "yokai": (("Samurai", "forza"), ("Ninja", "astuzia"), ("Miko", "magia")),
    "fantasy": (("Guerriero", "forza"), ("Ladro", "astuzia"), ("Mago", "magia")),
    "cyberpunk": (("Soldato", "forza"), ("Hacker", "astuzia"), ("Tecnomante", "magia")),
    "horror": (("Cacciatore", "forza"), ("Esploratore", "astuzia"), ("Medium", "magia")),
    "spazio": (("Marine", "forza"), ("Pilota", "astuzia"), ("Scienziato", "magia")),
    "pirati": (("Spadaccino", "forza"), ("Navigatore", "astuzia"), ("Cantastorie", "magia")),
}
LUOGHI = {
    "yokai": "un santuario avvolto dalla nebbia", "fantasy": "le rovine di un castello antico",
    "cyberpunk": "i sotterranei di una torre al neon", "horror": "una casa che non dovrebbe esistere",
    "spazio": "una stazione orbitale alla deriva", "pirati": "una grotta piena di casse e di ombre",
}


def classi_del_tema(tema: str | None) -> tuple[tuple[str, str], ...]:
    return CLASSI.get(tema or "", CLASSI["yokai"])


def prova_della_classe(tema: str | None, classe: str) -> str | None:
    return next((p for nome, p in classi_del_tema(tema) if nome == classe), None)


def probabilita_successo(prova: str, difficolta: int, giocatori: list[tuple[str | None, int]]) -> float:
    """
    La riuscita dipende da chi sta giocando adesso (AI-R-060): `giocatori` sono (prova della classe, livello).
    Chi ha la classe adatta pesa di più; i livelli alti pesano di più; la difficoltà (1-5) abbassa.
    """
    difficolta = max(1, min(5, difficolta))
    pesi = [(p, 1 + max(0, lv) / 20) for p, lv in giocatori]
    totale = sum(w for _, w in pesi)
    adatti = sum(w for p, w in pesi if p == prova)
    quota = adatti / totale if totale else 0.0
    livello_medio = (sum(lv for _, lv in giocatori) / len(giocatori)) if giocatori else 0
    prob = 0.75 - 0.1 * difficolta + 0.35 * quota + min(0.1, livello_medio / 300)
    return max(0.1, min(0.95, prob))


def riesce(prob: float, rng: random.Random | None = None) -> bool:
    return (rng or random).random() < prob


def scelta_vincente(voti: dict[int, int], numero_scelte: int, rng: random.Random | None = None) -> int:
    """La scelta più votata; a pari voti o senza voti decide la sorte tra quelle in testa (o tra tutte)."""
    rng = rng or random
    validi = [v for v in voti.values() if 0 <= v < numero_scelte]
    if not validi:
        return rng.randrange(numero_scelte)
    conta = Counter(validi)
    massimo = max(conta.values())
    return rng.choice(sorted(i for i, n in conta.items() if n == massimo))


# ---------------------------------------------------------------- storie
@dataclass(frozen=True)
class Scelta:
    testo: str
    prova: str
    difficolta: int
    successo: str
    fallimento: str


@dataclass(frozen=True)
class Nodo:
    id: str
    testo: str
    finale: bool = False
    esito: str = "neutro"
    scelte: tuple[Scelta, ...] = ()


@dataclass(frozen=True)
class Storia:
    titolo: str
    inizio: str
    nodi: tuple[Nodo, ...]

    def nodo(self, id_nodo: str) -> Nodo | None:
        return next((n for n in self.nodi if n.id == id_nodo), None)

    def rami_mancanti(self) -> list[str]:
        """Gli id a cui puntano le scelte ma che non hanno ancora una stanza: l'AI scrive solo questi."""
        presenti = {n.id for n in self.nodi}
        mancanti: list[str] = []
        for n in self.nodi:
            for s in n.scelte:
                for dest in (s.successo, s.fallimento):
                    if dest not in presenti and dest not in mancanti:
                        mancanti.append(dest)
        return mancanti


def _pulisci(testo, massimo: int) -> str:
    return re.sub(r"[`<>@]|https?://\S+", "", str(testo or "")).strip()[:massimo]


def _id(valore, predefinito: str = "") -> str:
    pulito = re.sub(r"[^a-z0-9_]+", "_", str(valore or "").strip().lower()).strip("_")[:24]
    return pulito if _ID.match(pulito) else predefinito


def _leggi_scelta(grezza, id_padre: str, indice: int) -> Scelta | None:
    if not isinstance(grezza, dict):
        return None
    testo = _pulisci(grezza.get("testo"), MAX_TESTO_SCELTA)
    if not testo:
        return None
    prova = str(grezza.get("prova") or "").lower()
    if prova not in PROVE:
        prova = PROVE[indice % len(PROVE)]
    try:
        difficolta = max(1, min(5, int(grezza.get("difficolta") or 2)))
    except (TypeError, ValueError):
        difficolta = 2
    succ = _id(grezza.get("successo"), f"{id_padre}_{indice}s")
    fall = _id(grezza.get("fallimento"), f"{id_padre}_{indice}f")
    return Scelta(testo, prova, difficolta, succ, fall)


def leggi_nodo(grezzo, id_forzato: str | None = None) -> Nodo | None:
    if not isinstance(grezzo, dict):
        return None
    id_nodo = id_forzato or _id(grezzo.get("id"))
    testo = _pulisci(grezzo.get("testo"), MAX_TESTO_NODO)
    if not id_nodo or not testo:
        return None
    esito = str(grezzo.get("esito") or "neutro").lower()
    if esito not in ("vittoria", "sconfitta", "neutro"):
        esito = "neutro"
    scelte_grezze = grezzo.get("scelte") if isinstance(grezzo.get("scelte"), list) else []
    scelte = tuple(s for s in (_leggi_scelta(g, id_nodo, i) for i, g in enumerate(scelte_grezze[:MAX_SCELTE])) if s)
    finale = bool(grezzo.get("finale")) or len(scelte) < 2  # una stanza senza scelte vere chiude la storia
    return Nodo(id_nodo, testo, finale, esito if finale else "neutro", () if finale else scelte)


def leggi_storia(testo: str) -> Storia | None:
    """Storia dell'AI resa sicura: al massimo 12 stanze, 3 scelte per stanza, testi puliti, almeno un finale."""
    dati = estrai_json(testo)
    if not dati or not isinstance(dati.get("nodi"), list):
        return None
    titolo = _pulisci(dati.get("titolo"), 80) or "Dungeon senza nome"
    nodi: list[Nodo] = []
    for g in dati["nodi"][:MAX_NODI]:
        n = leggi_nodo(g)
        if n is not None and all(n.id != x.id for x in nodi):
            nodi.append(n)
    inizio = _id(dati.get("inizio"), nodi[0].id if nodi else "")
    if not nodi or all(n.id != inizio for n in nodi) or not any(n.finale for n in nodi):
        return None
    return Storia(titolo, inizio, tuple(nodi))


def istruzioni_storia(tema_testo: str) -> str:
    return (
        "Scrivi un dungeon di gruppo a bivi, coerente con l'ambientazione"
        + (f" ({tema_testo})" if tema_testo else "")
        + ". Rispondi SOLO con JSON: "
        '{"titolo": "...", "inizio": "id", "nodi": [{"id": "a_z_0_9", "testo": "max 500 caratteri", '
        '"finale": false, "esito": "vittoria|sconfitta|neutro", "scelte": [{"testo": "max 70 caratteri", '
        '"prova": "forza|astuzia|magia", "difficolta": 1-5, "successo": "id", "fallimento": "id"}]}]}. '
        f"Al massimo {MAX_NODI} stanze, da 2 a 3 scelte per stanza non finale, almeno un finale di vittoria e uno di sconfitta, "
        "ogni scelta porta a stanze che esistono. Non citare persone reali né utenti."
    )


def istruzioni_nodo(tema_testo: str, cronologia: list[str]) -> str:
    cammino = " -> ".join(cronologia[-6:]) or "inizio"
    return (
        "Continua un dungeon di gruppo scrivendo la prossima stanza"
        + (f" (ambientazione: {tema_testo})" if tema_testo else "")
        + f". Strada fatta finora: {cammino}. Rispondi SOLO con JSON: "
        '{"testo": "max 500 caratteri", "finale": false, "esito": "vittoria|sconfitta|neutro", '
        '"scelte": [{"testo": "max 70 caratteri", "prova": "forza|astuzia|magia", "difficolta": 1-5}]}. '
        "Da 2 a 3 scelte se non è un finale. Non citare persone reali né utenti."
    )


def nodo_finale_locale(id_nodo: str, esito: str = "neutro") -> Nodo:
    testo = {
        "vittoria": "Il gruppo supera l'ultima prova ed esce dal dungeon. Ce l'avete fatta!",
        "sconfitta": "Il buio si chiude alle vostre spalle. Per questa volta il dungeon vince.",
        "neutro": "Il cammino si perde nell'ombra. Il gruppo torna indietro, stanco ma salvo.",
    }[esito]
    return Nodo(id_nodo, testo, True, esito)


def storia_pronta(tema: str | None) -> Storia:
    """La storia per quando l'AI è ferma e la libreria è vuota: stessa trama, ambientata nel tema."""
    luogo = LUOGHI.get(tema or "", LUOGHI["yokai"])
    S = Scelta
    return Storia(
        "La porta nell'ombra", "inizio",
        (
            Nodo("inizio", f"Il gruppo arriva a {luogo}. Davanti a voi ci sono due strade: una porta socchiusa e un corridoio con una luce.",
                 scelte=(S("Forzare la porta", "forza", 2, "porta", "trappola"), S("Seguire la luce", "astuzia", 2, "luce", "trappola"),
                         S("Leggere i segni sul muro", "magia", 2, "luce", "trappola"))),
            Nodo("porta", "Oltre la porta c'è una sala con un guardiano di pietra che si sveglia.",
                 scelte=(S("Affrontarlo", "forza", 3, "vittoria", "sconfitta"), S("Aggirarlo di nascosto", "astuzia", 3, "vittoria", "sconfitta"),
                         S("Spezzare l'incantesimo che lo muove", "magia", 3, "vittoria", "sconfitta"))),
            Nodo("luce", "La luce viene da un forziere circondato da simboli strani. Qualcosa osserva da dietro.",
                 scelte=(S("Aprire il forziere", "forza", 2, "vittoria", "trappola"), S("Disinnescare i simboli", "magia", 3, "vittoria", "trappola"))),
            Nodo("trappola", "Il pavimento cede: siete in una fossa buia. Tocca a chi sa cavarsela.",
                 scelte=(S("Arrampicarsi", "forza", 3, "luce", "sconfitta"), S("Cercare un passaggio", "astuzia", 3, "porta", "sconfitta"))),
            Nodo("vittoria", f"Il gruppo trova il tesoro nascosto e lascia {luogo} con la testa alta.", True, "vittoria"),
            Nodo("sconfitta", f"Il gruppo viene respinto fuori da {luogo}. Magari la prossima volta.", True, "sconfitta"),
        ),
    )


def riassunto_per_storia(cronologia: list[str]) -> str:
    return " -> ".join(cronologia[-8:])


@dataclass
class StatoVoto:
    """Fotografia dei voti di una stanza, per l'aggiornamento del messaggio."""

    scelte: tuple[str, ...]
    voti: dict[int, int] = field(default_factory=dict)

    def conteggio(self) -> list[int]:
        return [sum(1 for v in self.voti.values() if v == i) for i in range(len(self.scelte))]
