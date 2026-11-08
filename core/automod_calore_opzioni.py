"""
core/automod_calore_opzioni.py
==============================
Impostazioni del calore AutoMod di un server: un solo punto di lettura e scrittura, usato dal comando
`/admin-automod calore` e dal futuro pannello web.
Funzioni coperte: SPEC §6 (AMD-068, 069, 072), D16
"""

from __future__ import annotations

from dataclasses import replace

from core.automod_advanced_logic import CaloreConfig
from core.repositories.automod_advanced_repo import automod_advanced_repo

CAMPI = ("attivo", "soglia", "calo_per_minuto", "fermo_minuti", "fermo_peso", "timeout_secondi", "warn")


async def leggi(guild_id: int) -> CaloreConfig:
    return (await automod_advanced_repo.get_settings(guild_id)).config.calore


async def imposta(guild_id: int, **cambi) -> CaloreConfig:
    """Cambia solo i campi dati (non None). Un nome che non esiste è un errore di chi chiama."""
    sconosciuti = set(cambi) - set(CAMPI)
    if sconosciuti:
        raise ValueError(f"campi del calore sconosciuti: {sorted(sconosciuti)}")
    settings = await automod_advanced_repo.get_settings(guild_id)
    nuovo = replace(settings.config.calore, **{k: v for k, v in cambi.items() if v is not None})
    await automod_advanced_repo.save_settings(replace(settings, config=replace(settings.config, calore=nuovo)))
    return nuovo
