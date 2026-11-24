"""
core/combattimento_logic.py
===========================
Regole pure del combattimento a più giocatori (da 2 a 6) con regole su misura (ECO-105): vite iniziali, numero di
giri, oggetti sì/no. A turno si attacca un altro giocatore (7 colpi su 10 vanno a segno) oppure, se gli oggetti
sono ammessi, si usa una volta la pozione (+1 vita) o lo scudo (para il prossimo colpo). Chi non muove in tempo
esce. Vince l'ultimo in piedi, o chi ha più vite quando i giri finiscono (i pari dividono il piatto).
Il caso arriva da fuori (`rng`).
Funzioni coperte: ECO-105
"""

from __future__ import annotations

import random

MIN_GIOCATORI = 2
MAX_GIOCATORI = 6
VITE_MIN, VITE_MAX, VITE_BASE = 1, 5, 3
GIRI_MIN, GIRI_MAX, GIRI_BASE = 3, 20, 10
CHANCE_COLPO = 0.7


def controlla_regole(vite: int, giri: int) -> str | None:
    """Un solo punto dei limiti (comando e, domani, pannello). None se vanno bene."""
    if not VITE_MIN <= vite <= VITE_MAX:
        return f"Le vite vanno da {VITE_MIN} a {VITE_MAX}."
    if not GIRI_MIN <= giri <= GIRI_MAX:
        return f"I giri vanno da {GIRI_MIN} a {GIRI_MAX}."
    return None


def ripartisci_piatto(giocatori: list[int], puntata: int, vincitori: list[int]) -> dict[int, int]:
    """Quanto riceve ciascuno alla chiusura. Senza vincitori ognuno riprende la puntata. La somma resta quella puntata."""
    if not vincitori:
        return {u: puntata for u in giocatori}
    if not set(vincitori) <= set(giocatori):
        raise ValueError("Vincitore fuori dalla partita.")
    piatto = puntata * len(giocatori)
    quota, resto = divmod(piatto, len(vincitori))
    risultato = {u: 0 for u in giocatori}
    for n, u in enumerate(vincitori):
        risultato[u] = quota + (1 if n < resto else 0)
    return risultato


class Combattimento:
    def __init__(self, giocatori: list[int], vite: int, giri: int, oggetti: bool, rng: random.Random) -> None:
        if not MIN_GIOCATORI <= len(giocatori) <= MAX_GIOCATORI or len(set(giocatori)) != len(giocatori):
            raise ValueError("Servono da 2 a 6 giocatori diversi.")
        if (errore := controlla_regole(vite, giri)) is not None:
            raise ValueError(errore)
        self.rng, self.oggetti, self.vite_iniziali = rng, oggetti, vite
        self.vivi = list(giocatori)
        self.vite = {u: vite for u in giocatori}
        self.scudo: set[int] = set()  # chi ha lo scudo alzato
        self.scudo_usato: set[int] = set()
        self.pozione_usata: set[int] = set()
        self.mosse = 0
        self.mosse_max = giri * len(giocatori)
        self.di_turno = giocatori[0]

    @property
    def vincitori(self) -> list[int] | None:
        if len(self.vivi) == 1:
            return list(self.vivi)
        if self.mosse >= self.mosse_max:
            migliore = max(self.vite[u] for u in self.vivi)
            return [u for u in self.vivi if self.vite[u] == migliore]
        return None

    def _prossimo(self) -> None:
        """Dopo una mossa: tocca al giocatore vivo che segue chi ha mosso."""
        self.mosse += 1
        posto = self.vivi.index(self.di_turno)
        self.di_turno = self.vivi[(posto + 1) % len(self.vivi)]

    def _puo_muovere(self, utente: int) -> bool:
        return self.vincitori is None and utente == self.di_turno

    def attacca(self, utente: int, bersaglio: int) -> str:
        """'non_turno' | 'bersaglio_no' | 'parato' | 'mancato' | 'colpito' | 'eliminato'."""
        if not self._puo_muovere(utente):
            return "non_turno"
        if bersaglio == utente or bersaglio not in self.vivi:
            return "bersaglio_no"
        if self.rng.random() >= CHANCE_COLPO:
            esito = "mancato"
        elif bersaglio in self.scudo:
            self.scudo.discard(bersaglio)
            esito = "parato"
        else:
            self.vite[bersaglio] -= 1
            esito = "colpito"
            if self.vite[bersaglio] <= 0:
                self.vivi.remove(bersaglio)
                esito = "eliminato"
        self._prossimo()
        return esito

    def usa_pozione(self, utente: int) -> str:
        """'non_turno' | 'no_oggetti' | 'gia_usata' | 'piena' | 'curato'. Con le vite piene non serve e non costa il turno."""
        if not self._puo_muovere(utente):
            return "non_turno"
        if not self.oggetti:
            return "no_oggetti"
        if utente in self.pozione_usata:
            return "gia_usata"
        if self.vite[utente] >= self.vite_iniziali:
            return "piena"
        self.pozione_usata.add(utente)
        self.vite[utente] += 1
        self._prossimo()
        return "curato"

    def usa_scudo(self, utente: int) -> str:
        """'non_turno' | 'no_oggetti' | 'gia_usato' | 'scudo'."""
        if not self._puo_muovere(utente):
            return "non_turno"
        if not self.oggetti:
            return "no_oggetti"
        if utente in self.scudo_usato:
            return "gia_usato"
        self.scudo_usato.add(utente)
        self.scudo.add(utente)
        self._prossimo()
        return "scudo"

    def esci(self, utente: int) -> None:
        """Chi non muove in tempo è fuori. L'ultimo rimasto non esce."""
        if utente not in self.vivi or len(self.vivi) <= 1:
            return
        posto = self.vivi.index(utente)
        self.vivi.remove(utente)
        self.scudo.discard(utente)
        if utente == self.di_turno:
            self.di_turno = self.vivi[posto % len(self.vivi)]
