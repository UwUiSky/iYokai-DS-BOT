"""
core/spiriti_logic.py
=====================
Spirito Yokai (affinità che cresce con l'attività, solo conteggi) e frammenti di lore da collezionare:
formule, nomi per tema, condizioni di sblocco e testi pronti per quando l'AI è ferma.
Funzioni coperte: SPEC §25.71, §25.72 (AI-R-078, AI-R-079)

È una lettura del comportamento: parte solo su richiesta della persona e non serve mai a permessi o moderazione.
"""

from __future__ import annotations

from dataclasses import dataclass

ASSI = ("scrittura", "voce", "costanza", "monete")
# a quanto ogni asse arriva al 100 % (ultimi 30 giorni; le monete sono il saldo)
SOGLIE = {"scrittura": 300, "voce": 600, "costanza": 20, "monete": 2000}
LEGAMI = ("Sconosciuto", "Conoscente", "Compagno", "Amico", "Custode", "Eletto")

SPIRITI: dict[str, tuple[tuple[str, str], ...]] = {
    "yokai": (("Kitsune", "astuto e parlatore"), ("Kappa", "sereno e ascoltatore"), ("Tengu", "tenace e costante"), ("Tanuki", "fortunato e giocoso")),
    "fantasy": (("Fata", "chiacchierina e gentile"), ("Gufo Antico", "saggio e silenzioso"), ("Drago Piccolo", "tenace e fiero"), ("Folletto", "furbo e fortunato")),
    "cyberpunk": (("Cipher", "veloce e loquace"), ("Eco", "calmo e attento"), ("Sentinella", "costante e solida"), ("Broker", "scaltro e fortunato")),
    "horror": (("Sussurro", "sempre a bisbigliare"), ("Veglia", "silenziosa e attenta"), ("Custode del Faro", "paziente e costante"), ("Corvo", "ammassa tesori")),
    "spazio": (("Segnale", "parla con tutti"), ("Onda", "ascolta le stelle"), ("Faro", "sempre acceso"), ("Cometa", "porta fortuna")),
    "pirati": (("Pappagallo", "parla senza sosta"), ("Sirena", "canta nel vocale"), ("Timoniere", "fermo sulla rotta"), ("Scrigno", "pieno di monete")),
}


def spiriti_del_tema(tema: str | None) -> tuple[tuple[str, str], ...]:
    return SPIRITI.get(tema or "", SPIRITI["yokai"])


@dataclass(frozen=True)
class Misure:
    messaggi: int = 0
    minuti_voce: int = 0
    giorni_attivi: int = 0
    monete: int = 0

    def per_asse(self) -> dict[str, int]:
        return {"scrittura": self.messaggi, "voce": self.minuti_voce, "costanza": self.giorni_attivi, "monete": self.monete}


def affinita(m: Misure) -> dict[str, float]:
    """Per ogni asse da 0 a 1."""
    return {asse: min(1.0, max(0, valore) / SOGLIE[asse]) for asse, valore in m.per_asse().items()}


def spirito_dominante(aff: dict[str, float]) -> int | None:
    """L'indice (in `ASSI`) dell'asse più alto; a pari valore il primo. None se la persona non ha ancora fatto nulla."""
    migliore = max(range(len(ASSI)), key=lambda i: (aff[ASSI[i]], -i))
    return migliore if aff[ASSI[migliore]] >= 0.02 else None


def livello_legame(aff: dict[str, float]) -> int:
    """Da 0 a 5: la media dei quattro assi."""
    return min(5, int(sum(aff.values()) / len(ASSI) * 6))


def titolo(spirito: str, livello: int) -> str:
    return f"{LEGAMI[max(0, min(5, livello))]} di {spirito}"


def barra(valore: float, larghezza: int = 10) -> str:
    pieni = round(max(0.0, min(1.0, valore)) * larghezza)
    return "█" * pieni + "░" * (larghezza - pieni)


# ---------------------------------------------------------------- frammenti
@dataclass(frozen=True)
class Frammento:
    codice: str
    nome: str
    come: str
    asse: str | None = None  # None: lo sblocca un altro gioco (boss, dungeon)
    soglia: int = 0


FRAMMENTI: tuple[Frammento, ...] = (
    Frammento("voce_antica", "La voce antica", "scrivi 50 messaggi in 30 giorni", "scrittura", 50),
    Frammento("eco", "L'eco lontana", "stai 60 minuti in vocale in 30 giorni", "voce", 60),
    Frammento("costanza", "Il filo mai spezzato", "sii attivo in 5 giorni diversi", "costanza", 5),
    Frammento("tesoro", "Il tesoro nascosto", "arriva a 500 monete", "monete", 500),
    Frammento("trofeo_boss", "Il trofeo del mostro", "colpisci un World Boss fino alla sua sconfitta"),
    Frammento("dungeon", "La mappa del dungeon", "vinci un dungeon di gruppo"),
)
CODICI = tuple(f.codice for f in FRAMMENTI)


def frammenti_da_sbloccare(m: Misure, gia: set[str]) -> list[Frammento]:
    valori = m.per_asse()
    return [f for f in FRAMMENTI if f.asse and f.codice not in gia and valori[f.asse] >= f.soglia]


def testo_frammento(f: Frammento, luogo: str) -> str:
    return {
        "voce_antica": f"Una voce antica sussurra, tra le parole di {luogo}: «chi parla, resta».",
        "eco": f"Un'eco lontana attraversa {luogo}: «chi ascolta, trova».",
        "costanza": f"Un filo sottile corre per {luogo}: «chi ritorna, non si perde».",
        "tesoro": f"Sotto una pietra di {luogo} luccica qualcosa: «chi risparmia, ritrova».",
        "trofeo_boss": f"Dal mostro caduto resta un pezzo di storia, a {luogo}: «chi combatte insieme, vince».",
        "dungeon": f"Sulla mappa di {luogo} qualcuno ha disegnato una strada sola: «chi sceglie insieme, arriva».",
    }[f.codice]


def storia_finale_pronta(tema: str, luogo: str) -> str:
    return (
        f"Messi insieme, i sei frammenti raccontano di {luogo}: un luogo che ricorda chi parla, ascolta, ritorna, "
        "risparmia, combatte e sceglie insieme agli altri. Chi li ha raccolti tutti non è più un ospite: è parte della storia."
    )


def titolo_raro(tema: str) -> str:
    return f"Custode del tema «{tema}»"


ISTRUZIONI_FINALE = (
    "Scrivi una breve storia (max 120 parole) che unisce sei frammenti di lore: la voce, l'eco, il filo mai spezzato, "
    "il tesoro, il trofeo del mostro, la mappa del dungeon. Coerente con l'ambientazione. Non citare persone reali."
)
