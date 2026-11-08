"""
core/automod_pulizia.py
=======================
Un giro di pulizia su un canale (AMD-073, 074): legge fino a 500 messaggi, sceglie quelli del tipo voluto (i
fissati restano, salvo scelta del server), cancella in blocco i recenti e uno per uno i vecchi (al massimo 100),
con una pausa fra una cancellazione e l'altra. Dopo tre rifiuti 403 si ferma. Non ripete mai la stessa
cancellazione e non esce dai limiti di Discord.
Funzioni coperte: SPEC §6 (AMD-073, 074)
Dipende da: core/automod_pulizia_logic.py
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import discord

from core import automod_pulizia_logic as lg
from core.i18n import testo_guild
from core.repositories.automod_pulizie_repo import Pulizia

logger = logging.getLogger("iyokai.automod.pulizia")

PAUSA_S = 1.0  # fra una cancellazione singola e l'altra
_PERMESSI = ("view_channel", "read_message_history", "manage_messages")


class EsitoGiro(lg.Esito):
    def __init__(self) -> None:
        super().__init__()
        self.senza_permessi = False


def _eta_giorni(messaggio_id: int, adesso: datetime) -> float:
    return (adesso - discord.utils.snowflake_time(messaggio_id)).total_seconds() / 86400


async def _scegli(canale, p: Pulizia, adesso: datetime) -> list[tuple[discord.Message, float]]:
    scelti = []
    async for m in canale.history(limit=lg.MAX_ESAMINATI):
        if m.is_system() or not lg.da_cancellare(fissato=bool(m.pinned), incluso_fissati=p.fissati):
            continue
        if lg.corrisponde(p.tipo, e_bot=bool(m.author.bot), testo=m.content or "", allegati=len(m.attachments)):
            scelti.append((m, _eta_giorni(m.id, adesso)))
    return scelti


async def pulisci(canale, p: Pulizia, adesso: datetime | None = None) -> EsitoGiro:
    """Un giro. Restituisce quanti messaggi ha cancellato e se si è fermato (403 o permessi mancanti)."""
    adesso = adesso or datetime.now(timezone.utc)
    esito = EsitoGiro()
    perms = canale.permissions_for(canale.guild.me)
    if not all(getattr(perms, nome) for nome in _PERMESSI):
        esito.senza_permessi = True
        return esito
    scelti = await _scegli(canale, p, adesso)
    per_id = {m.id: m for m, _ in scelti}
    blocchi, singoli = lg.dividi([(m.id, eta) for m, eta in scelti])
    motivo = await testo_guild(canale.guild, "ampulizia_motivo")
    for blocco in blocchi:
        if esito.fermo:
            return esito
        try:
            await canale.delete_messages([per_id[i] for i in blocco], reason=motivo)
            esito.cancellati += len(blocco)
        except discord.Forbidden:
            esito.vieta()
        except discord.HTTPException:
            logger.warning("Pulizia %s/%s: blocco non cancellato.", p.guild_id, p.canale_id, exc_info=False)
    for messaggio_id in singoli:
        if esito.fermo:
            return esito
        try:
            await per_id[messaggio_id].delete()
            esito.cancellati += 1
        except discord.Forbidden:
            esito.vieta()
        except discord.NotFound:
            pass  # già sparito
        except discord.HTTPException:
            logger.warning("Pulizia %s/%s: messaggio non cancellato.", p.guild_id, p.canale_id)
        await asyncio.sleep(PAUSA_S)
    return esito
