"""
core/tavolo_logic.py
====================
Regole pure di tris (ECO-108) e forza 4 (ECO-107) tra due giocatori. Le griglie sono liste di righe;
0 = vuoto, 1 e 2 = i due giocatori.
Funzioni coperte: ECO-107, ECO-108
"""

from __future__ import annotations

RIGHE_F4 = 6
COLONNE_F4 = 7
SEGNI = {0: "⬜", 1: "🔴", 2: "🟡"}
SEGNI_TRIS = {0: "▫️", 1: "❌", 2: "⭕"}


def nuova_griglia(righe: int, colonne: int) -> list[list[int]]:
    return [[0] * colonne for _ in range(righe)]


def vincitore_tris(g: list[list[int]]) -> int:
    """1 o 2 se ha fatto tris, 0 altrimenti."""
    linee = [r for r in g] + [[g[r][c] for r in range(3)] for c in range(3)]
    linee += [[g[i][i] for i in range(3)], [g[i][2 - i] for i in range(3)]]
    for l in linee:
        if l[0] and l[0] == l[1] == l[2]:
            return l[0]
    return 0


def piena(g: list[list[int]]) -> bool:
    return all(c for riga in g for c in riga)


def metti_tris(g: list[list[int]], riga: int, colonna: int, giocatore: int) -> bool:
    if not (0 <= riga < 3 and 0 <= colonna < 3) or g[riga][colonna]:
        return False
    g[riga][colonna] = giocatore
    return True


def metti_f4(g: list[list[int]], colonna: int, giocatore: int) -> int | None:
    """Fa cadere un gettone nella colonna: restituisce la riga dove si ferma, o None se la colonna è piena."""
    if not 0 <= colonna < COLONNE_F4:
        return None
    for riga in range(RIGHE_F4 - 1, -1, -1):
        if g[riga][colonna] == 0:
            g[riga][colonna] = giocatore
            return riga
    return None


def vincitore_f4(g: list[list[int]]) -> int:
    """1 o 2 se ha quattro in fila (orizzontale, verticale, diagonale), 0 altrimenti."""
    for r in range(RIGHE_F4):
        for c in range(COLONNE_F4):
            v = g[r][c]
            if not v:
                continue
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                fine_r, fine_c = r + 3 * dr, c + 3 * dc
                if 0 <= fine_r < RIGHE_F4 and 0 <= fine_c < COLONNE_F4 and all(
                    g[r + k * dr][c + k * dc] == v for k in range(4)
                ):
                    return v
    return 0


def testo_griglia(g: list[list[int]], segni: dict[int, str]) -> str:
    return "\n".join("".join(segni[c] for c in riga) for riga in g)
