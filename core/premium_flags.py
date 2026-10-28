"""
core/premium_flags.py
=====================
Il punto unico che rende premium (o gratuito) un modulo: stato in memoria,
ultimo stato nel database e storico di ogni cambio. Usato da `/owner premium
toggle`, dal pannello interattivo dell'owner e dalla pagina dell'owner nel
pannello web (D16).
Funzioni coperte: SPEC §3.2, §17.10, C.4 (NF-20)
Dipende da: core/premium.py, core/database.py
"""

from __future__ import annotations

from core.database import db
from core.premium import registry


class ModuloNonCambiabile(ValueError):
    """Il modulo non esiste o è sempre gratuito. Il testo è pronto per l'owner."""


async def applica_cambio_premium(
    module_name: str, active: bool, changed_by: int, *, registro=None, database=None
) -> None:
    """Cambia la natura premium di un modulo con tutte e tre le conseguenze: memoria, stato salvato, storico."""
    registro = registro or registry
    database = database or db
    modulo = registro.get(module_name)
    if modulo is None:
        raise ModuloNonCambiabile(f"Modulo `{module_name}` non trovato.")
    if not modulo.premium_capable:
        raise ModuloNonCambiabile(f"`{module_name}` è marcato come sempre-gratuito e non può diventare premium.")
    registro.set_module_premium(module_name, active)
    await database.pool.execute(
        """
        INSERT INTO premium_module_flags (module_name, is_active, updated_by)
        VALUES ($1, $2, $3)
        ON CONFLICT (module_name) DO UPDATE
            SET is_active = EXCLUDED.is_active, updated_by = EXCLUDED.updated_by, updated_at = now()
        """,
        module_name, active, changed_by,
    )
    await database.pool.execute(
        "INSERT INTO premium_toggle_history (module_name, new_value, changed_by) VALUES ($1, $2, $3)",
        module_name, active, changed_by,
    )
