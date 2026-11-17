"""
core/ruoli_vocali_logic.py
==========================
Ruoli dati a chi sta in un canale vocale (catalogo #123: RUO-044). Decide quali ruoli dare e togliere
quando un membro cambia canale. Funzioni semplici, provabili senza Discord.
Funzioni coperte: SPEC §14 (RUO-044)
"""

from __future__ import annotations

# I ruoli vocali per server (nel catalogo: 1 gratis, 10 con il premium; qui tetto unico).
MAX_RUOLI_VOCALI = 10
# Dopo un riavvio si rimette a posto il server: al massimo tante correzioni, con una pausa tra l'una e l'altra.
MAX_CORREZIONI_AVVIO = 200
PAUSA_CORREZIONI_SECONDI = 0.6


def cambio_ruoli(regole: dict[int, int], prima: int | None, dopo: int | None) -> tuple[set[int], set[int]]:
    """
    (ruoli da dare, ruoli da togliere) per un membro che passa dal canale `prima` al canale `dopo`
    (None = non era in un vocale / esce). Se i due canali danno lo stesso ruolo non cambia nulla.
    """
    prima_ruoli = {regole[prima]} if prima in regole else set()
    dopo_ruoli = {regole[dopo]} if dopo in regole else set()
    return dopo_ruoli - prima_ruoli, prima_ruoli - dopo_ruoli


def correzioni(
    regole: dict[int, int], nei_canali: dict[int, set[int]], coi_ruoli: dict[int, set[int]]
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """
    Per rimettere a posto dopo un riavvio. `nei_canali`: canale -> membri che ci sono; `coi_ruoli`:
    ruolo -> membri che lo hanno. Torna ([(membro, ruolo) da dare], [(membro, ruolo) da togliere]).
    Un ruolo dato da due canali resta a chi è in uno dei due.
    """
    attesi: dict[int, set[int]] = {}
    for canale, ruolo in regole.items():
        attesi.setdefault(ruolo, set()).update(nei_canali.get(canale, set()))
    dare, togliere = [], []
    for ruolo, dovrebbero in attesi.items():
        ce_l_hanno = coi_ruoli.get(ruolo, set())
        dare += [(m, ruolo) for m in sorted(dovrebbero - ce_l_hanno)]
        togliere += [(m, ruolo) for m in sorted(ce_l_hanno - dovrebbero)]
    return dare, togliere
