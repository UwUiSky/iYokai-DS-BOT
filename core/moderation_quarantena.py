"""
core/moderation_quarantena.py
=============================
La quarantena a mano (`/mod-sanzioni quarantena` e `libera`): il membro perde i suoi ruoli, riceve il ruolo
«Quarantined» dell'anti-raid e li riprende al rilascio, a mano o alla scadenza. Lo stato si scrive prima di toccare
il membro. Un rilascio rimette solo ruoli che il bot può ridare oggi (non gestiti, sotto il bot, ancora esistenti).
Funzioni coperte: MOD-016
"""

from __future__ import annotations

import logging

import discord

from core import security_quarantine
from core.repositories.moderation_repo import moderation_repo

logger = logging.getLogger("iyokai.moderation.quarantena")

SCHEDULED_QUARANTENA_FINE = "moderation_quarantena_end"
CASO_QUARANTENA = "quarantena"
MAX_DURATA_SECONDI = 365 * 86400


def ruoli_da_salvare(member: discord.Member, ruolo_quarantena_id: int | None) -> list[int]:
    """I ruoli che la quarantena toglie: tutti tranne @everyone, quelli gestiti da Discord e la quarantena stessa."""
    return [r.id for r in member.roles if not r.is_default() and not r.managed and r.id != ruolo_quarantena_id]


async def metti(member: discord.Member, motivo: str, moderatore_id: int, fine) -> tuple[bool, int | None, bool]:
    """
    Mette in quarantena. Restituisce (riuscita, numero del caso, ruoli_non_tolti). Lo stato si scrive prima; se la
    quarantena non parte lo stato si cancella, senza caso né ruoli persi.
    """
    guild = member.guild
    ruolo = await security_quarantine.ruolo_quarantena(guild)
    if ruolo is None:
        return False, None, False
    salvati = ruoli_da_salvare(member, ruolo.id)
    precedente = await moderation_repo.get_quarantena(guild.id, member.id)
    if precedente is not None:  # già dentro: i ruoli veri sono quelli salvati la prima volta
        salvati = list(dict.fromkeys([*precedente["ruoli"], *salvati]))
    await moderation_repo.salva_quarantena(guild.id, member.id, salvati, None, fine, moderatore_id)
    esito = await security_quarantine.metti_in_quarantena(member, motivo[:512], togli_ruoli=True)
    if not esito.in_quarantena:
        if precedente is None:
            await moderation_repo.elimina_quarantena(guild.id, member.id)
        return False, None, False
    caso = await moderation_repo.create_case(
        guild.id, member.id, moderatore_id, CASO_QUARANTENA, motivo[:512],
        duration_seconds=None if fine is None else max(1, int((fine - discord.utils.utcnow()).total_seconds())),
    )
    await moderation_repo.salva_quarantena(guild.id, member.id, salvati, caso, fine, moderatore_id)
    return True, caso, esito.ruoli_non_tolti


async def libera(guild: discord.Guild, member: discord.Member, motivo: str, chi_id: int) -> bool | None:
    """
    Toglie la quarantena e ridà i ruoli salvati (solo quelli che il bot può ridare). True se fatto, False se Discord
    rifiuta (lo stato resta, si può riprovare), None se il membro non era in quarantena a mano.
    """
    from cogs.moderation._tempban_modes import ruoli_da_riprendere

    stato = await moderation_repo.get_quarantena(guild.id, member.id)
    if stato is None:
        return None
    ruolo = await security_quarantine.ruolo_quarantena(guild, allinea=False)
    ridati = ruoli_da_riprendere(guild, list(stato["ruoli"]))
    attuali = [r for r in member.roles if not r.is_default() and (ruolo is None or r.id != ruolo.id)]
    try:
        await member.edit(roles=attuali + [r for r in ridati if r not in attuali], reason=motivo[:512])
    except discord.HTTPException:
        logger.warning("Quarantena non tolta a %s (server %s).", member.id, guild.id)
        return False
    if stato["case_number"] is not None:
        await moderation_repo.revoke_case(guild.id, stato["case_number"], chi_id)
    await moderation_repo.elimina_quarantena(guild.id, member.id)
    return True
