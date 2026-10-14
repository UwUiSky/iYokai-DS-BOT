"""
core/live_role_logic.py
=======================
Dà e toglie il ruolo «in diretta» a chi è collegato a un avviso Twitch o Kick
(NF-32). Il collegamento è scelto dall'admin con /moduli alert ruolo-live;
non serve l'intent delle presenze. Funzioni coperte: SPEC §10.13 (NF-32)
"""

from __future__ import annotations

import logging

import discord

logger = logging.getLogger("iyokai.live_role")


async def aggiorna_ruolo_live(guild, member_id: int | None, role_id: int | None, in_diretta: bool) -> bool:
    """True se il ruolo è stato cambiato. Mai un'eccezione: un ruolo che non si può dare non ferma l'avviso."""
    if not member_id or not role_id or guild is None:
        return False
    membro = guild.get_member(member_id)
    ruolo = guild.get_role(role_id)
    me = guild.me
    if membro is None or ruolo is None or me is None or membro.bot:
        return False
    if not me.guild_permissions.manage_roles or ruolo >= me.top_role or ruolo.managed:
        return False
    ce_l_ha = ruolo in membro.roles
    try:
        if in_diretta and not ce_l_ha:
            await membro.add_roles(ruolo, reason="In diretta")
            return True
        if not in_diretta and ce_l_ha:
            await membro.remove_roles(ruolo, reason="Diretta finita")
            return True
    except discord.HTTPException:
        logger.warning("Ruolo in diretta non aggiornato (server %s, membro %s)", guild.id, member_id)
    return False
