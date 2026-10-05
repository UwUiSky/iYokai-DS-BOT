"""
core/security_access.py
=======================
Controllo premium per i listener dei moduli di sicurezza (spam-trap,
anti-nuke, anti-raid, ban globale, heatmap). I comandi usano il
decorator `requires_module` di core/premium.py; un listener non ha
un'interazione, quindi chiede qui se il server può usare il modulo.
Funzioni coperte: SPEC §3.3
"""

from __future__ import annotations

from core.premium import guild_has_premium_access, registry


async def premium_sbloccato(guild_id: int, module_name: str, bot=None) -> bool:
    """
    True se il server può usare il modulo: sempre, finché il modulo
    non è premium (nessuna lettura dal database in quel caso);
    altrimenti solo se il server lo ha sbloccato.
    """
    if not registry.is_module_premium(module_name):
        return True
    return await guild_has_premium_access(guild_id, module_name, bot=bot)
