"""
core/blocchi_deboli.py
======================
Un `asyncio.Lock` per chiave (un server, una persona) che non sparisce mentre qualcuno lo usa.
In una `BoundedCache` un blocco può essere sfrattato quando la cache è piena: chi lo tiene continua
a usarlo, ma il prossimo che chiede la stessa chiave ne riceve uno nuovo e due lavori che dovevano
andare uno alla volta girano insieme (per esempio due punizioni per lo stesso attacco). Qui i blocchi
sono riferimenti deboli: restano finché c'è chi li tiene o li aspetta, poi spariscono da soli.
Funzioni coperte: consiglio 25/11/2026, seri di stabilità (blocco C)
"""

from __future__ import annotations

import asyncio
import weakref
from collections.abc import Hashable


class BlocchiDeboli:
    def __init__(self) -> None:
        self._blocchi: weakref.WeakValueDictionary[Hashable, asyncio.Lock] = weakref.WeakValueDictionary()

    def prendi(self, chiave: Hashable) -> asyncio.Lock:
        """Il blocco di questa chiave; lo crea se nessuno lo sta usando."""
        blocco = self._blocchi.get(chiave)
        if blocco is None:
            blocco = asyncio.Lock()
            self._blocchi[chiave] = blocco
        return blocco

    def clear(self) -> None:
        """Dimentica tutti i blocchi (i test: un blocco resta legato al ciclo di eventi che lo ha usato)."""
        self._blocchi.clear()

    def __len__(self) -> int:
        return len(self._blocchi)
