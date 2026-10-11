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

import discord

from core.premium import guild_has_premium_access, registry
from core.security_logic import AntiNukeConfig, is_extra_owner


# Ruoli staff esentati dalla Spam Trap (impostazione per server in
# guild_config.settings); contano anche come esenti dal ban globale.
SETTING_STAFF_ROLES = "spam_trap_staff_role_ids"


async def premium_sbloccato(guild_id: int, module_name: str, bot=None) -> bool:
    """
    True se il server può usare il modulo: sempre, finché il modulo
    non è premium (nessuna lettura dal database in quel caso);
    altrimenti solo se il server lo ha sbloccato.
    """
    if not registry.is_module_premium(module_name):
        return True
    return await guild_has_premium_access(guild_id, module_name, bot=bot)


def puo_gestire_antinuke(owner_id: int, user_id: int, config: AntiNukeConfig) -> bool:
    """
    SIC-018: chi puo' cambiare la lista dei fidati e le protezioni piu'
    delicate dell'anti-nuke: il proprietario del server e gli "extra
    owner". Un amministratore qualsiasi (o un "fidato") no: altrimenti
    il primo admin che decide di fare danni si metterebbe da solo nella
    lista degli esenti.
    """
    return user_id == owner_id or is_extra_owner(user_id, config)


async def solo_chi_gestisce(interaction: discord.Interaction, config: AntiNukeConfig) -> bool:
    """
    Le impostazioni che decidono chi e' esente o quanto e' forte la
    difesa (fiducia, soglie, punizione, recovery, blocco della quarantena,
    rilascio) le cambiano solo il proprietario e gli extra owner. Nessuna
    scorciatoia per un amministratore qualsiasi: il primo che decide di
    fare danni se le abbasserebbe da solo. Risponde da solo, con un
    rifiuto, se chi chiama non e' tra questi.
    """
    if puo_gestire_antinuke(interaction.guild.owner_id, interaction.user.id, config):
        return True
    await interaction.response.send_message(
        "Solo il proprietario del server e gli extra owner possono cambiare questa impostazione "
        "della sicurezza: un amministratore qualsiasi non può esentarsi da solo.",
        ephemeral=True,
    )
    return False


def is_staff_exempt(
    member: discord.Member, guild: discord.Guild, staff_role_ids: set[int] | frozenset[int] = frozenset()
) -> bool:
    """
    Chi non va mai punito da un automatismo di sicurezza: un bot, chi ha
    "Gestisci messaggi", "Bannare" o "Amministratore", chi ha uno dei ruoli
    staff configurati, o chi ha un ruolo sopra a quello del bot (il bot non
    potrebbe comunque agire su di lui).
    """
    if member.bot:
        return True
    permessi = member.guild_permissions
    if permessi.manage_messages or permessi.administrator or permessi.ban_members:
        return True
    if any(ruolo.id in staff_role_ids for ruolo in member.roles):
        return True
    return member.top_role > guild.me.top_role
