"""
core/bounded_cache.py
========================
Cache LRU (Least Recently Used) con dimensione massima —
SPEC.md §1.5, e il pezzo che sblocca "Limitazione dimensione cache"
sotto §1.3 Memory Guard.

Perché serve: alcune strutture del progetto tengono stato in memoria
per tutta la durata del processo — l'esempio reale è
core/invite_tracker.py, che tiene un dizionario per ogni server in
cui il bot si trova (`{guild_id: {invite_code: uses}}`). Con un
bot che punta a 10.000 server, quel dizionario cresce con il numero
di server e NON si riduce mai da solo — un server che il bot lascia
non viene mai rimosso dalla cache. `BoundedCache` risolve questo:
una dimensione massima oltre la quale l'elemento usato meno di
recente viene scartato automaticamente, senza bisogno che nessuno se
ne ricordi esplicitamente.

Implementazione: un `OrderedDict` di libreria standard, che già
garantisce l'ordine di inserimento/accesso in tempo costante — non
serve reinventare una struttura dati, solo incapsularne l'uso con la
politica LRU.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class BoundedCache(Generic[K, V]):
    """
    Dizionario con una dimensione massima. Quando si supera il
    limite inserendo un nuovo elemento, quello acceduto meno di
    recente (in lettura O in scrittura: entrambe contano come
    "uso") viene rimosso automaticamente — non serve chiamare nulla
    esplicitamente per liberare spazio.
    """

    def __init__(self, max_size: int) -> None:
        if max_size <= 0:
            raise ValueError("max_size deve essere un intero positivo.")
        self._max_size = max_size
        self._data: OrderedDict[K, V] = OrderedDict()

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: K) -> bool:
        return key in self._data

    def get(self, key: K, default: V | None = None) -> V | None:
        if key not in self._data:
            return default
        # Un GET conta come "uso recente": lo spostiamo in fondo
        # (move_to_end) così non è il primo candidato all'espulsione.
        self._data.move_to_end(key)
        return self._data[key]

    def set(self, key: K, value: V) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        if len(self._data) > self._max_size:
            # popitem(last=False) rimuove il PRIMO elemento
            # dell'OrderedDict, cioè quello usato meno di recente
            # (l'ultimo spostato in fondo è sempre il più recente).
            self._data.popitem(last=False)

    def delete(self, key: K) -> None:
        self._data.pop(key, None)

    def keys(self) -> list[K]:
        return list(self._data.keys())

    def clear(self) -> None:
        self._data.clear()

    @property
    def max_size(self) -> int:
        return self._max_size
