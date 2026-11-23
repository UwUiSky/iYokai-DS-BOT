"""
core/tela_logic.py
==================
Regole pure della tela di pixel del server (FUN-013, FUN-014): misure, palette fissa di 16 colori, finestra di
zoom e costo per accorciare la pausa. Senza Discord e senza database.
Funzioni coperte: FUN-013, FUN-014
"""

from __future__ import annotations

LATO = 100
NUMERO_COLORI = 16
PAUSA_BASE = 300  # secondi tra un pixel e l'altro
PAUSA_MIN, PAUSA_MAX = 30, 3600
COSTO_MINUTO_BASE = 10  # monete per ogni minuto di pausa che si salta (0 = non si può)
COSTO_MINUTO_MAX = 10_000
LATO_IMMAGINE = 800  # pixel dell'immagine (senza i margini)

# Palette fissa (nome, esadecimale). Il colore 0 è il fondo vuoto della tela.
PALETTE: tuple[tuple[str, str], ...] = (
    ("vuoto", "#07070b"), ("cenere", "#2a2928"), ("nebbia", "#8a8680"), ("inchiostro", "#c8c4bc"),
    ("cinabro", "#c24a3a"), ("rubino", "#7a2e27"), ("arancio", "#d9843b"), ("ocra", "#d8b54a"),
    ("muschio", "#5e7f4b"), ("pino", "#2f5a4a"), ("acqua", "#4b9a9a"), ("notte", "#2b3f6b"),
    ("cielo", "#6c93c9"), ("orchidea", "#9b4d7a"), ("prugna", "#5a2d55"), ("terra", "#7a5436"),
)
ZOOM = {1: 100, 2: 50, 3: 25, 4: 10}  # livello -> lato della zona mostrata (in caselle)


def rgb(indice: int) -> tuple[int, int, int]:
    esa = PALETTE[indice][1].lstrip("#")
    return int(esa[0:2], 16), int(esa[2:4], 16), int(esa[4:6], 16)


def coordinate_valide(x: int, y: int) -> bool:
    return 0 <= x < LATO and 0 <= y < LATO


def colore_valido(colore: int) -> bool:
    return 0 <= colore < NUMERO_COLORI


def finestra(centro_x: int, centro_y: int, zoom: int) -> tuple[int, int, int]:
    """(x0, y0, lato) della zona da mostrare, centrata su (x, y) e tenuta dentro la tela."""
    lato = ZOOM.get(zoom)
    if lato is None:
        raise ValueError(zoom)
    x0 = min(max(centro_x - lato // 2, 0), LATO - lato)
    y0 = min(max(centro_y - lato // 2, 0), LATO - lato)
    return x0, y0, lato


def scala(lato: int) -> int:
    """Pixel dell'immagine per ogni casella."""
    return max(1, LATO_IMMAGINE // lato)


def costo_accorciare(resta_secondi: float, costo_minuto: int) -> int:
    """Monete per saltare `resta_secondi` di pausa: `costo_minuto` per ogni minuto cominciato."""
    if resta_secondi <= 0 or costo_minuto <= 0:
        return 0
    return -(-int(resta_secondi + 0.999) // 60) * costo_minuto


def formatta_attesa(secondi: float) -> str:
    s = max(0, int(secondi + 0.999))
    return f"{s // 60}:{s % 60:02d}"
