"""
core/music_jukebox_logic.py
===========================
Jukebox (MUS-065): mettere un brano in coda costa monete. `esegui_con_addebito` fa pagare, esegue
l'azione e, se il brano non entra in coda (esito negativo, errore o comando annullato), rimborsa.
Nessun Discord e nessun database qui dentro: addebito e rimborso sono funzioni passate da chi chiama.
Funzioni coperte: SPEC §9 (catalogo MUS-065)
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum

logger = logging.getLogger("iyokai.music.jukebox")

PREZZO_MAX = 100_000  # monete per richiesta; 0 = jukebox spento (di base)


class Esito(str, Enum):
    LIBERO = "libero"  # jukebox spento: nessun addebito
    PAGATO = "pagato"
    SENZA_MONETE = "senza_monete"
    NON_IN_CODA = "non_in_coda"  # pagato e poi rimborsato


def prezzo_valido(valore) -> int:
    """Il prezzo se e' un intero tra 1 e PREZZO_MAX, altrimenti 0 (spento)."""
    if isinstance(valore, bool) or not isinstance(valore, int) or not (0 < valore <= PREZZO_MAX):
        return 0
    return valore


async def _rimborsa_senza_perdere_l_errore(rimborsa) -> None:
    try:
        await asyncio.shield(rimborsa())
    except Exception:  # il guasto del rimborso va nel log, ma non copre l'errore vero
        logger.exception("Jukebox: rimborso non riuscito.")


async def esegui_con_addebito(prezzo: int, addebita, rimborsa, azione) -> tuple[Esito, bool]:
    """
    `addebita()` dice se il pagamento e' riuscito; `azione()` dice se il brano e' entrato in coda;
    `rimborsa()` rimette le monete. Restituisce (esito, brano_in_coda).
    """
    if prezzo <= 0:
        return Esito.LIBERO, bool(await azione())
    if not await addebita():
        return Esito.SENZA_MONETE, False
    try:
        in_coda = bool(await azione())
    except BaseException:  # errore o comando annullato: il brano non e' entrato
        await _rimborsa_senza_perdere_l_errore(rimborsa)
        raise
    if not in_coda:
        await _rimborsa_senza_perdere_l_errore(rimborsa)
        return Esito.NON_IN_CODA, False
    return Esito.PAGATO, True
