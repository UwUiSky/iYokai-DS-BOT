"""
core/coin_games_logic.py
========================
Regole dei giochi con le monete del bot (monetina, dadi, slot). Funzioni
pure: il caso arriva da fuori (`rng`), così ogni esito si prova con un
seme fisso. Le monete del bot non si comprano con soldi veri: i giochi
non sono gioco d'azzardo a pagamento (regola di Discord sulla monetizzazione).
Funzioni coperte: SPEC §23.16 (NF-40)
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from itertools import product

LATI_MONETINA = ("testa", "croce")
SIMBOLI_SLOT = ("🍒", "🍋", "🔔", "⭐", "💎", "7️⃣")

PUNTATA_MINIMA = 1
PUNTATA_MASSIMA = 10_000
ATTESA_TRA_PARTITE_SECONDI = 5


@dataclass(frozen=True)
class Esito:
    """`restituzione`: le monete che tornano al giocatore (0 = persa, uguale alla puntata = pari)."""

    descrizione: str
    restituzione: int
    puntata: int

    @property
    def vinto(self) -> bool:
        return self.restituzione > self.puntata

    @property
    def pari(self) -> bool:
        return self.restituzione == self.puntata

    @property
    def guadagno(self) -> int:
        return self.restituzione - self.puntata


def gioca_monetina(scelta: str, puntata: int, rng: random.Random) -> Esito:
    """Testa o croce: se indovini vinci il doppio, se sbagli perdi la puntata."""
    if scelta not in LATI_MONETINA:
        raise ValueError(f"Lato sconosciuto: {scelta}")
    uscito = rng.choice(LATI_MONETINA)
    return Esito(
        descrizione=f"🪙 È uscita **{uscito}**.",
        restituzione=puntata * 2 if uscito == scelta else 0,
        puntata=puntata,
    )


def gioca_dadi(puntata: int, rng: random.Random) -> Esito:
    """Tu contro il bot, un dado a testa: il più alto vince il doppio, pari restituisce la puntata."""
    tuo, suo = rng.randint(1, 6), rng.randint(1, 6)
    if tuo > suo:
        restituzione = puntata * 2
    elif tuo == suo:
        restituzione = puntata
    else:
        restituzione = 0
    return Esito(
        descrizione=f"🎲 Tu **{tuo}**, il bot **{suo}**.", restituzione=restituzione, puntata=puntata
    )


def _restituzione_slot(rulli: tuple[str, ...], puntata: int) -> int:
    uguali = len(rulli) - len(set(rulli)) + 1  # quanti simboli uguali al massimo (1, 2 o 3)
    if uguali == 3:
        return puntata * 8
    if uguali == 2:
        return puntata * 3 // 2
    return 0


def gioca_slot(puntata: int, rng: random.Random) -> Esito:
    """Tre rulli: tre uguali pagano 8 volte, due uguali una volta e mezza (arrotondato per difetto)."""
    rulli = tuple(rng.choice(SIMBOLI_SLOT) for _ in range(3))
    return Esito(
        descrizione=" ".join(rulli),
        restituzione=_restituzione_slot(rulli, puntata),
        puntata=puntata,
    )


def ritorno_atteso_slot(puntata: int) -> float:
    """Quanto rende in media ogni coin puntata alla slot (sotto 1: il banco ha un vantaggio)."""
    combinazioni = list(product(SIMBOLI_SLOT, repeat=3))
    totale = sum(_restituzione_slot(c, puntata) for c in combinazioni)
    return totale / len(combinazioni) / puntata


def numero_del_messaggio(testo: str) -> int | None:
    """Il numero scritto da solo in un messaggio (solo cifre), altrimenti None: il resto è chiacchiera."""
    pulito = testo.strip()
    if not pulito.isascii() or not pulito.isdigit() or len(pulito) > 9:
        return None
    return int(pulito)


def valuta_conteggio(corrente: int, ultimo_utente: int | None, utente: int, numero: int) -> bool:
    """Giusto se è il numero dopo l'ultimo e non lo scrive chi ha contato per ultimo."""
    return numero == corrente + 1 and utente != ultimo_utente


# ----------------------------------------------------------------------
# Roulette, carta, scala (#125 B2). Il banco ha sempre un piccolo vantaggio.
# ----------------------------------------------------------------------
ROSSI = frozenset({1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36})
# scelta -> (quanti numeri la vincono, moltiplicatore pagato)
SCOMMESSE_ROULETTE = {
    "rosso": 2, "nero": 2, "pari": 2, "dispari": 2, "basso": 2, "alto": 2,
    "dozzina1": 3, "dozzina2": 3, "dozzina3": 3, "colonna1": 3, "colonna2": 3, "colonna3": 3,
    "numero": 36,
}


def numero_vince(scelta: str, uscito: int, numero: int | None = None) -> bool:
    """ECO-090: vero se `uscito` (0-36) vince la scommessa. Lo zero perde tutto tranne il numero secco."""
    if scelta == "numero":
        return numero is not None and uscito == numero
    if uscito == 0:
        return False
    controlli = {
        "rosso": uscito in ROSSI, "nero": uscito not in ROSSI,
        "pari": uscito % 2 == 0, "dispari": uscito % 2 == 1,
        "basso": uscito <= 18, "alto": uscito >= 19,
        "dozzina1": uscito <= 12, "dozzina2": 13 <= uscito <= 24, "dozzina3": uscito >= 25,
        "colonna1": uscito % 3 == 1, "colonna2": uscito % 3 == 2, "colonna3": uscito % 3 == 0,
    }
    return controlli[scelta]


def gioca_roulette(scelta: str, puntata: int, rng: random.Random, numero: int | None = None) -> Esito:
    """ECO-090: roulette europea (0-36). `numero` serve solo per la scommessa «numero» (0-36)."""
    if scelta not in SCOMMESSE_ROULETTE:
        raise ValueError(f"Scommessa sconosciuta: {scelta}")
    if scelta == "numero" and (numero is None or not 0 <= numero <= 36):
        raise ValueError("Il numero deve stare tra 0 e 36.")
    uscito = rng.randint(0, 36)
    colore = "verde" if uscito == 0 else ("rosso" if uscito in ROSSI else "nero")
    vinto = numero_vince(scelta, uscito, numero)
    return Esito(
        descrizione=f"🎡 È uscito il **{uscito}** ({colore}).",
        restituzione=puntata * SCOMMESSE_ROULETTE[scelta] if vinto else 0,
        puntata=puntata,
    )


SEMI = ("cuori", "quadri", "fiori", "picche")
VALORI = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
# ECO-100: colore paga 1,9x, seme 3,8x, valore 12x (in decimi)
PAGAMENTI_CARTA = {"colore": 19, "seme": 38, "valore": 120}


def gioca_carta(tipo: str, scelta: str, puntata: int, rng: random.Random) -> Esito:
    """ECO-100: si estrae una carta da un mazzo da 52; si indovina colore (rosso/nero), seme o valore."""
    if tipo not in PAGAMENTI_CARTA:
        raise ValueError(f"Tipo di scommessa sconosciuto: {tipo}")
    ammessi = {"colore": ("rosso", "nero"), "seme": SEMI, "valore": VALORI}[tipo]
    if scelta not in ammessi:
        raise ValueError(f"Scelta non valida per {tipo}: {scelta}")
    seme, valore = rng.choice(SEMI), rng.choice(VALORI)
    colore = "rosso" if seme in ("cuori", "quadri") else "nero"
    uscito = {"colore": colore, "seme": seme, "valore": valore}[tipo]
    return Esito(
        descrizione=f"🃏 È uscito **{valore} di {seme}** ({colore}).",
        restituzione=puntata * PAGAMENTI_CARTA[tipo] // 10 if uscito == scelta else 0,
        puntata=puntata,
    )


# ECO-099: gradini della scala, (decimi della puntata che tornano, peso su 100). Resa media 0,96.
GRADINI_SCALA = ((0, 52), (5, 20), (15, 16), (30, 8), (60, 3), (200, 1))


def gioca_scala(puntata: int, rng: random.Random) -> Esito:
    """ECO-099: si estrae un gradino; più è in alto più rende. I primi gradini perdono tutto o parte."""
    punto = rng.randint(1, 100)
    totale = 0
    for indice, (decimi, peso) in enumerate(GRADINI_SCALA):
        totale += peso
        if punto <= totale:
            return Esito(
                descrizione=f"🪜 Gradino **{indice + 1}** su {len(GRADINI_SCALA)}.",
                restituzione=puntata * decimi // 10,
                puntata=puntata,
            )
    raise AssertionError("pesi della scala sbagliati")


def resa_media_scala() -> float:
    """Quante monete tornano in media per ogni moneta puntata alla scala."""
    return sum(decimi * peso for decimi, peso in GRADINI_SCALA) / 1000


BATTE = {"sasso": "forbici", "carta": "sasso", "forbici": "carta"}


def gioca_rps(scelta: str, puntata: int, rng: random.Random) -> Esito:
    """ECO-097: sasso-carta-forbici con puntata. Vittoria 1,9 volte, pareggio restituisce, sconfitta perde (resa media 0,97)."""
    if scelta not in BATTE:
        raise ValueError(f"Scelta sconosciuta: {scelta}")
    bot = rng.choice(tuple(BATTE))
    if bot == scelta:
        restituzione, testo = puntata, "pareggio"
    elif BATTE[scelta] == bot:
        restituzione, testo = puntata * 19 // 10, "vittoria"
    else:
        restituzione, testo = 0, "sconfitta"
    return Esito(descrizione=f"✊ Tu **{scelta}**, il bot **{bot}**: {testo}.", restituzione=restituzione, puntata=puntata)
