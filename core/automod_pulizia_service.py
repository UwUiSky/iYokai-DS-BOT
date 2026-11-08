"""
core/automod_pulizia_service.py
===============================
Impostazioni della pulizia dei canali: l'unico punto che le scrive, usato dal comando `/admin-automod pulizia` e
dal futuro pannello web (D16). Controlla intervallo, tipo e tetto per server; una pulizia nuova o cambiata fa il
primo giro dopo un intero intervallo.
Funzioni coperte: SPEC §6 (AMD-073, 074), D16
"""

from __future__ import annotations

from core import automod_pulizia_logic as lg
from core.repositories.automod_pulizie_repo import Pulizia, automod_pulizie_repo as repo


class TroppePulizie(Exception):
    """Il server ha già il massimo di canali con la pulizia."""


async def imposta(
    guild_id: int, canale_id: int, *, ogni: str | None = None, tipo: str | None = None, fissati: bool | None = None,
    attiva: bool | None = None, autore_id: int | None = None,
) -> Pulizia:
    """Crea o cambia la pulizia di un canale; i campi non dati restano come sono."""
    attuale = await repo.leggi(guild_id, canale_id)
    if attuale is None:
        if ogni is None:
            raise lg.PuliziaNonValida("intervallo")
        if await repo.conta(guild_id) >= lg.MAX_RIGHE_PER_SERVER:
            raise TroppePulizie()
    if tipo is not None and tipo not in lg.TIPI:
        raise lg.PuliziaNonValida("tipo")
    nuova = Pulizia(
        guild_id, canale_id,
        lg.leggi_ogni(ogni) if ogni is not None else attuale.ogni_secondi,
        tipo if tipo is not None else (attuale.tipo if attuale else "tutti"),
        fissati if fissati is not None else (attuale.fissati if attuale else False),
        attiva if attiva is not None else (attuale.attiva if attuale else True),
    )
    await repo.salva(nuova, autore_id)
    return nuova


async def rimuovi(guild_id: int, canale_id: int) -> bool:
    return await repo.elimina(guild_id, canale_id)


async def canale_cancellato(guild_id: int, canale_id: int) -> None:
    """Un canale cancellato esce dalla pulizia."""
    await repo.elimina(guild_id, canale_id)
