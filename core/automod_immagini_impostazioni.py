"""
core/automod_immagini_impostazioni.py
=====================================
Legge e scrive le impostazioni `immagini_*` del filtro immagini attraverso il punto unico delle impostazioni
(SETTINGS_SCHEMA e storico). Le chiavi le crea il filone delle immagini trappola: finché non ci sono, il comando
risponde «non disponibile». Non contiene la logica del filtro.
Funzioni coperte: D62, D63
"""

from __future__ import annotations

import importlib
from typing import Any

from core.database import db

CHIAVI = {
    "filtro": "immagini_filtro_attivo",  # bool
    "azione": "immagini_azione",  # cancella | avvisa | timeout
    "timeout": "immagini_timeout_minuti",  # int
    "canale": "immagini_canale_log_id",  # canale
}
AZIONI = ("cancella", "avvisa", "timeout")


class ImmaginiNonDisponibili(Exception):
    """Le chiavi immagini_* non sono ancora nello schema delle impostazioni."""


class ValoreNonValido(ValueError):
    pass


def _storia():
    return importlib.import_module("cogs.utility.config_history")


def disponibili() -> bool:
    return all(c in _storia().SETTINGS_SCHEMA for c in CHIAVI.values())


async def leggi(guild_id: int) -> dict[str, Any]:
    if not disponibili():
        raise ImmaginiNonDisponibili
    return {nome: await db.get_guild_setting(guild_id, chiave) for nome, chiave in CHIAVI.items()}


async def imposta(guild_id: int, nome: str, valore: Any, autore_id: int | None) -> None:
    """Scrive una delle quattro impostazioni con gli stessi controlli dello schema."""
    if not disponibili():
        raise ImmaginiNonDisponibili
    if nome == "azione" and valore not in AZIONI:
        raise ValoreNonValido(f"ammessi: {', '.join(AZIONI)}")
    chiave = CHIAVI[nome]
    storia = _storia()
    controllo, descrizione = storia.CONTROLLI_PER_TIPO[storia.SETTINGS_SCHEMA[chiave]]
    if not controllo(valore):
        raise ValoreNonValido(f"deve essere {descrizione}")
    await db.set_guild_setting(guild_id, chiave, valore, changed_by=autore_id)
