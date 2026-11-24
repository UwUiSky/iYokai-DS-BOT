"""
core/moderation_mute_azione.py
==============================
Il mute con il ruolo «muto» dato da un gradino della scala delle sanzioni: ruolo, stato con la fine, caso e
scadenza nello scheduler (la fine resta valida anche dopo un riavvio, la riprende il database).
Funzioni coperte: D127 (mute a ruolo a tempo come gradino della scala), MOD-014
"""

from __future__ import annotations

import discord

from core import bot_roles
from core.repositories.moderation_repo import moderation_repo
from core.scheduler import in_seconds, scheduler


async def applica_mute_a_tempo(
    member: discord.Member, secondi: int, motivo: str, moderatore_id: int, origine: str = "automod"
) -> int | None:
    """
    Mette il ruolo muto per `secondi` secondi. Restituisce il numero del caso, o None se il ruolo non c'è e non si
    può creare. Un errore di Discord nel dare il ruolo sale a chi chiama (nessuno stato resta scritto).
    Un hardmute già in corso tiene i suoi ruoli salvati.
    """
    from cogs.moderation.softban_mute import (
        MUTE_ROLE_ACTION_TYPE,
        SCHEDULED_MUTE_EXPIRE,
        _get_or_create_mute_role,
    )

    guild = member.guild
    ruolo = await _get_or_create_mute_role(guild)
    if ruolo is None:
        return None
    await bot_roles.aggiungi_ruolo(member, ruolo, reason=motivo[:512])
    precedente = await moderation_repo.get_mute_state(guild.id, member.id)
    hard = bool(precedente and precedente["hard"])
    ruoli = list(precedente["ruoli"]) if hard else []
    fine = in_seconds(secondi)
    await scheduler.cancel_for_user(guild.id, member.id, SCHEDULED_MUTE_EXPIRE)
    await moderation_repo.revoke_active_cases_for_user(guild.id, member.id, MUTE_ROLE_ACTION_TYPE, moderatore_id)
    caso = await moderation_repo.create_case(
        guild_id=guild.id, user_id=member.id, moderator_id=moderatore_id, action_type=MUTE_ROLE_ACTION_TYPE,
        reason=motivo[:512], duration_seconds=secondi, origine=origine,
    )
    await moderation_repo.save_mute_state(guild.id, member.id, hard, ruoli, caso, fine)
    await scheduler.schedule(guild.id, member.id, SCHEDULED_MUTE_EXPIRE, fine, {"caso": caso})
    return caso
