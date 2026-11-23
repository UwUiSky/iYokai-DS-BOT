"""
core/auto_logic.py
==================
Regole pure delle auto da collezione (FUN-017): catalogo, potenziamenti e gara in tre prove (rettilineo,
partenza, curve). Senza Discord e senza database; il caso entra da fuori (`rng`). I nomi sono di fantasia.
Funzioni coperte: FUN-017
"""

from __future__ import annotations

import random
from dataclasses import dataclass

LIVELLO_MASSIMO = 5
BONUS_PER_LIVELLO = 4
MAX_TIRO = 30  # il caso aggiunge da 0 a 30 a ogni prova
PARTI = ("motore", "assetto", "gomme")  # motore -> velocità, assetto -> tenuta, gomme -> accelerazione
PROVE = ("rettilineo", "partenza", "curve")
RARITA = (1, 2, 3, 4)  # 1 comune, 2 rara, 3 epica, 4 leggendaria
COSTO_POTENZIAMENTO = {1: 60, 2: 120, 3: 250, 4: 500}  # per il livello successivo: costo × (livello + 1)
DIMENSIONE_FOTO_MASSIMA = 8 * 1024 * 1024  # byte dell'allegato che il bot accetta di leggere
LATO_FOTO = 640  # la copia che si conserva


@dataclass(frozen=True)
class Modello:
    chiave: str
    nome: str
    rarita: int
    prezzo: int
    velocita: int
    accelerazione: int
    tenuta: int


CATALOGO: tuple[Modello, ...] = (
    Modello("risaia", "Risaia 600", 1, 150, 38, 40, 42),
    Modello("sakura", "Sakura Touring", 1, 220, 44, 42, 46),
    Modello("kappa", "Kappa Urban", 1, 300, 48, 50, 44),
    Modello("tanuki", "Tanuki Rally", 2, 600, 56, 58, 60),
    Modello("yuki", "Yuki Quattro", 2, 800, 58, 56, 66),
    Modello("kitsune", "Kitsune GT", 2, 1000, 66, 62, 62),
    Modello("tengu", "Tengu Corsa", 3, 2000, 74, 70, 72),
    Modello("oni", "Oni V8", 3, 2800, 82, 72, 68),
    Modello("nue", "Nue Spider", 3, 3600, 78, 80, 76),
    Modello("ryu", "Ryu Hyper", 4, 6000, 88, 84, 82),
    Modello("kirin", "Kirin Zero", 4, 8500, 86, 90, 88),
    Modello("yokai", "Yokai One", 4, 12000, 94, 92, 90),
)
PER_CHIAVE = {m.chiave: m for m in CATALOGO}
MAX_AUTO = len(CATALOGO)


def trova(chiave: str) -> Modello | None:
    return PER_CHIAVE.get(chiave)


def costo_potenziamento(rarita: int, livello: int) -> int:
    """Costo per portare una parte da `livello` a `livello + 1`."""
    if livello < 0 or livello >= LIVELLO_MASSIMO:
        raise ValueError(livello)
    return COSTO_POTENZIAMENTO[rarita] * (livello + 1)


def statistiche(m: Modello, motore: int, assetto: int, gomme: int) -> tuple[int, int, int]:
    """(velocità, accelerazione, tenuta) con i potenziamenti."""
    return (m.velocita + BONUS_PER_LIVELLO * motore, m.accelerazione + BONUS_PER_LIVELLO * gomme, m.tenuta + BONUS_PER_LIVELLO * assetto)


def valutazione(m: Modello, motore: int, assetto: int, gomme: int) -> int:
    return sum(statistiche(m, motore, assetto, gomme))


@dataclass(frozen=True)
class Esito:
    vincitore: int  # 1 o 2
    prove: tuple[tuple[str, int, int, int], ...]  # (prova, punti 1, punti 2, chi la vince)


def gara(a: tuple[int, int, int], b: tuple[int, int, int], rng: random.Random | None = None) -> Esito:
    """Corsa tra due auto date come (velocità, accelerazione, tenuta). Vince chi vince più prove; a pari prove il totale."""
    rng = rng or random.SystemRandom()
    prove, vinte = [], [0, 0]
    totali = [0, 0]
    for nome, pa, pb in zip(PROVE, a, b):
        x, y = pa + rng.randint(0, MAX_TIRO), pb + rng.randint(0, MAX_TIRO)
        chi = 1 if x > y else 2 if y > x else rng.choice((1, 2))
        vinte[chi - 1] += 1
        totali[0] += x
        totali[1] += y
        prove.append((nome, x, y, chi))
    if vinte[0] != vinte[1]:
        vincitore = 1 if vinte[0] > vinte[1] else 2
    else:  # con tre prove non succede, ma la regola resta completa
        vincitore = 1 if totali[0] > totali[1] else 2 if totali[1] > totali[0] else rng.choice((1, 2))
    return Esito(vincitore, tuple(prove))


def avversario_del_banco(rarita: int, rng: random.Random | None = None) -> tuple[Modello, int, int, int]:
    """Auto del bot: un modello della stessa rarità (o della più vicina sotto) con potenziamenti a caso fino a 3."""
    rng = rng or random.SystemRandom()
    for r in range(rarita, 0, -1):
        scelte = [m for m in CATALOGO if m.rarita == r]
        if scelte:
            return rng.choice(scelte), rng.randint(0, 3), rng.randint(0, 3), rng.randint(0, 3)
    raise ValueError(rarita)
