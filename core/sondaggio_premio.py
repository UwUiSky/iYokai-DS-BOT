"""
core/sondaggio_premio.py
========================
Il premio di un sondaggio (ECO-051, D121): quando il sondaggio finisce, il bot estrae a sorte da 1 a 10 persone tra chi
ha votato (mai i bot, una persona una volta sola anche con più opzioni) e dà loro le monete scelte dallo staff (da 1 a
100.000 a testa), con un annuncio nel canale. Si dà una volta sola. Si legge al massimo 5.000 votanti.
Funzioni coperte: ECO-051
Dipende da: core/repositories/sondaggi_nativi_repo.py, core/repositories/leveling_repo.py
"""

from __future__ import annotations

import logging
import random

import discord

from core.repositories.leveling_repo import leveling_repo
from core.repositories.sondaggi_nativi_repo import sondaggi_nativi_repo

logger = logging.getLogger("iyokai.sondaggio_premio")

MAX_VOTANTI_LETTI = 5000


def scegli(votanti: list, quanti: int, rng: random.Random | None = None) -> list:
    """Fino a `quanti` persone diverse a sorte."""
    return (rng or random).sample(votanti, min(quanti, len(votanti))) if votanti else []


async def _votanti(messaggio) -> list:
    visti: dict[int, object] = {}
    sondaggio = getattr(messaggio, "poll", None)
    for risposta in getattr(sondaggio, "answers", None) or []:
        async for utente in risposta.voters():
            if not utente.bot:
                visti[utente.id] = utente
            if len(visti) >= MAX_VOTANTI_LETTI:
                return list(visti.values())
    return list(visti.values())


async def premia(guild_id: int, riga, messaggio, rng: random.Random | None = None) -> list:
    """Estrae e paga. Restituisce i vincitori ([] se non c'è premio, è già dato o nessuno ha votato). Mai solleva."""
    try:
        if riga is None or not riga["premio"] or not await sondaggi_nativi_repo.segna_premiato(riga["id"]):
            return []
        vincitori = scegli(await _votanti(messaggio), riga["vincitori"], rng)
        for u in vincitori:
            await leveling_repo.add_coins(guild_id, u.id, riga["premio"])
        if vincitori:
            elenco = ", ".join(u.mention for u in vincitori)
            await messaggio.channel.send(
                f"🎁 Premio del sondaggio: **{riga['premio']}** monete a testa a {elenco}. Grazie a tutti per aver votato!",
                allowed_mentions=discord.AllowedMentions(users=vincitori, everyone=False, roles=False),
            )
        return vincitori
    except Exception:
        logger.warning("Premio del sondaggio %s non dato.", getattr(riga, "get", lambda k: "?")("id"), exc_info=True)
        return []
