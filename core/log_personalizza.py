"""
core/log_personalizza.py
========================
Il punto unico dove un evento di log prende la sua rotta (LOG-016: un canale per quell'evento al posto di quello
del gruppo) e il suo formato (LOG-026: il testo scritto dal server). Lo chiamano i tre punti da cui escono i log:
basic_logs, advanced_logs e message_logs. Mai solleva: con un errore il log esce come sempre.
Un server non vede mai il canale di un altro: la rotta si risolve con `guild.get_channel` del server dell'evento.
Funzioni coperte: SPEC §8.20 (LOG-016, LOG-026)
Dipende da: core/channel_router.py, core/repositories/log_personalizza_repo.py
"""

from __future__ import annotations

import logging

import discord

from core import channel_router as router
from core.log_eventi_logic import interruttore_di
from core.log_personalizza_logic import RIFERIMENTO_ROTTA, applica_formato
from core.repositories.log_personalizza_repo import log_personalizza_repo

logger = logging.getLogger("iyokai.log_personalizza")


async def personalizza(guild: discord.Guild, tipo: str, evento: str, dest, embed: discord.Embed | None = None):
    """
    Restituisce `(destinazione, tipo)` da usare per scrivere l'evento. Il formato del server cambia `embed` sul posto.
    Il «tipo» di una rotta è `rotta_<interruttore>`: serve solo per l'avviso al proprietario, una volta per rotta.
    """
    chiave = interruttore_di(evento)
    if chiave is None:
        return dest, tipo
    try:
        scelte = await log_personalizza_repo.carica(guild.id)
        formato = scelte.formati.get(chiave)
        if formato is not None and embed is not None:
            applica_formato(embed, formato[0], formato[1])
        canale_id = scelte.rotte.get(chiave)
        if canale_id is not None:
            nuova = await router.destinazione_rotta(guild, canale_id)
            if nuova is not None:
                return nuova, RIFERIMENTO_ROTTA + chiave
    except Exception:  # noqa: BLE001 - il log esce comunque, dal canale del gruppo
        logger.warning("Rotta o formato dei log non letti (server %s).", guild.id, exc_info=True)
    return dest, tipo
