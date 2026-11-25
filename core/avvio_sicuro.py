"""
core/avvio_sicuro.py
====================
Avvio che non toglie i comandi ai server. Se un cog non si carica, o se non si riesce a leggere
lo stato della sincronizzazione, il bot parte lo stesso ma NON sincronizza i comandi con Discord
(la sync è una sovrascrittura in blocco): avvisa l'owner in DM e riprova da solo, con pause
crescenti, finché tutto è a posto. A quel punto sincronizza e avvisa che è tutto a posto.
Funzioni coperte: consiglio 25/11/2026, critico 6 (blocco C)
Dipende da: core/cog_manager.py, core/command_sync.py, core/giro_periodico.py
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from core.avvisi_owner import avvisa_owner_chiave
from core.cog_manager import carica_cog
from core.command_sync import DA_RITENTARE
from core.giro_periodico import giro_periodico

logger = logging.getLogger(__name__)

# Funzione che sincronizza i comandi: riceve i cog ancora non caricati e restituisce {ambito: esito}.
Sincronizza = Callable[[list[str]], Awaitable[dict[str, str]]]

INTERVALLO_RIPROVA_SECONDI = 60


def avvio_incompleto(cog_falliti: list[str], esiti: dict[str, str]) -> bool:
    """True se manca qualcosa: un cog non caricato o una sync da rifare."""
    return bool(cog_falliti) or any(e in DA_RITENTARE for e in esiti.values())


def _testo_sync(esiti: dict[str, str]) -> str:
    da_rifare = sorted(a for a, e in esiti.items() if e in DA_RITENTARE)
    return ", ".join(da_rifare) or "-"


async def avvisa_avvio_incompleto(bot: Any, cog_falliti: list[str], esiti: dict[str, str]) -> bool:
    """DM all'owner: cosa non è partito e che si riprova da soli."""
    moduli = ", ".join(m.rsplit(".", 1)[-1] for m in cog_falliti[:15]) or "-"
    return await avvisa_owner_chiave(bot, "owner_avvio_incompleto", moduli=moduli, sync=_testo_sync(esiti))


def avvia_ripresa_avvio(bot: Any, cog_falliti: list[str], sincronizza: Sincronizza):
    """
    Un giro che ogni minuto (con pause crescenti se continua a fallire) ricarica i cog
    mancanti e rifà la sync. Si ferma da solo quando è tutto a posto, e avvisa l'owner.
    """
    mancanti = list(cog_falliti)

    @giro_periodico(seconds=INTERVALLO_RIPROVA_SECONDI, subito=True, silenzioso=True)
    async def _riprova_avvio() -> None:
        for modulo in list(mancanti):
            if await carica_cog(bot, modulo):
                mancanti.remove(modulo)
        esiti = await sincronizza(list(mancanti))
        if avvio_incompleto(mancanti, esiti):
            raise RuntimeError(f"avvio ancora incompleto: cog {mancanti}, sync {_testo_sync(esiti)}")
        _riprova_avvio.stop()
        await avvisa_owner_chiave(bot, "owner_avvio_completato")

    _riprova_avvio.start()
    return _riprova_avvio
