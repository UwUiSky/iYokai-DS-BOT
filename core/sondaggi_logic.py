"""
core/sondaggi_logic.py
======================
Regole del sondaggio a bottoni, senza Discord: opzioni, righe di bottoni, pesi dei ruoli, barre dei risultati.
Funzioni coperte: catalogo #128 UTL-088, 089, 091, 093, 094, 096 (D69, B22, B23)
"""

from __future__ import annotations

MAX_OPZIONI = 20
MAX_TESTO_OPZIONE = 80
MAX_DOMANDA = 256
MAX_PESI = 25
PESO_MASSIMO = 100
PER_RIGA = 5
ETICHETTA_BOTTONE = 45
MAX_COMPONENTI = 25
MAX_VOTANTI_CHIUSURA = 100_000
INIZIO_MINIMO = 60
INIZIO_MASSIMO = 30 * 86400

CONTROLLI = {"r": "risultati", "t": "togli", "g": "gestisci"}


def leggi_opzioni(testo: str) -> list[str] | str:
    """Opzioni separate da `|`. Torna la lista oppure il codice dell'errore: «poche», «troppe», «doppie»."""
    opzioni = [o.strip()[:MAX_TESTO_OPZIONE] for o in testo.split("|") if o.strip()]
    if len(opzioni) < 2:
        return "poche"
    if len(opzioni) > MAX_OPZIONI:
        return "troppe"
    if len({o.casefold() for o in opzioni}) != len(opzioni):
        return "doppie"
    return opzioni


def etichetta_bottone(n: int, testo: str) -> str:
    return f"{n + 1}. {testo}"[:ETICHETTA_BOTTONE]


def righe_bottoni(quante: int) -> list[list[tuple[str, int | str]]]:
    """Le righe del messaggio: ogni voce è («opzione», n) o («controllo», chiave). Mai più di 5 righe da 5."""
    righe: list[list[tuple[str, int | str]]] = []
    for inizio in range(0, quante, PER_RIGA):
        righe.append([("opzione", n) for n in range(inizio, min(inizio + PER_RIGA, quante))])
    righe.append([("controllo", c) for c in CONTROLLI])
    return righe


def custom_id(sondaggio_id: int, parte: int | str) -> str:
    return f"sb:{sondaggio_id}:{parte}"


def peso_votante(ruoli_membro: set[int], pesi: dict[int, int]) -> int:
    """Vale il peso più alto tra i ruoli del votante; senza ruoli con peso vale 1."""
    return max([pesi[r] for r in ruoli_membro if r in pesi], default=1)


def puo_votare(ruoli_membro: set[int], riservati: list[int]) -> bool:
    return not riservati or bool(ruoli_membro.intersection(riservati))


def scelte_dopo_voto(attuali: set[int], scelta: int, multipla: bool) -> set[int]:
    """Con una sola scelta il nuovo voto sostituisce il vecchio; con più scelte il tasto accende e spegne."""
    if multipla:
        return attuali ^ {scelta}
    return {scelta}


def barra(parte: int, totale: int, larghezza: int = 10) -> str:
    pieni = round(larghezza * parte / totale) if totale else 0
    return "█" * pieni + "░" * (larghezza - pieni)


def righe_risultati(opzioni: list[tuple[str, int]]) -> list[str]:
    totale = sum(v for _, v in opzioni)
    righe = []
    for n, (testo, voti) in enumerate(opzioni):
        pc = round(100 * voti / totale) if totale else 0
        righe.append(f"**{n + 1}.** {testo[:MAX_TESTO_OPZIONE]}\n{barra(voti, totale)} {voti} ({pc}%)")
    return righe


def conta_componenti(quante_opzioni: int) -> int:
    return sum(len(r) for r in righe_bottoni(quante_opzioni))


def inizio_valido(secondi: int) -> bool:
    """«inizia_tra»: da 1 minuto a 30 giorni."""
    return INIZIO_MINIMO <= secondi <= INIZIO_MASSIMO
