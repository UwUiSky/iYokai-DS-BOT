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

GIOCHI = ("monetina", "dadi", "slot")
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
