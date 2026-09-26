"""
core/guild_clan_role_service.py
====================================
Sincronizzazione dei ruoli Discord "Capo Clan"/"Admin Clan" con lo
stato in database (SPEC.md §15.14). I due ruoli sono CONDIVISI a
livello di server — un solo ruolo "Capo Clan" e un solo ruolo
"Admin Clan" per TUTTA la gilda Discord, riusati da ogni clan,
perché Discord non permette a due ruoli di stare alla stessa
posizione nella hierarchy. L'isolamento fra clan diversi non passa
quindi dal ruolo condiviso (che di per sé non dà nessun permesso su
nessun canale) ma dagli OVERWRITE PER-UTENTE sulla categoria del
proprio clan, applicati qui esattamente come già faceva `clan_crea`
per il fondatore.

Ogni funzione qui è "best effort" verso Discord: se una chiamata
Discord fallisce (permessi, rate limit, risorsa già sparita) viene
solo loggata — il database resta la fonte di verità su appartenenza
e ruolo, questa sincronizzazione è un livello aggiuntivo che non
deve mai bloccare un comando già confermato lato dati.
"""

from __future__ import annotations

import logging

import discord

logger = logging.getLogger(__name__)

CAPO_CLAN_ROLE_NAME = "Capo Clan"
ADMIN_CLAN_ROLE_NAME = "Admin Clan"

# Overwrite base: un membro comune deve solo poter vedere/usare i
# canali della propria gilda.
MEMBER_OVERWRITE = discord.PermissionOverwrite(
    view_channel=True, send_messages=True, connect=True,
)
# Overwrite da ufficiale: in più, gestione dei canali/vocali della
# categoria — MAI manage_permissions/manage_roles (eviterebbe che un
# Admin Clan possa alterare gli overwrite altrui o auto-promuoversi).
OFFICER_OVERWRITE = discord.PermissionOverwrite(
    view_channel=True, send_messages=True, connect=True,
    manage_channels=True, move_members=True,
)


async def get_or_create_shared_role(guild: discord.Guild, name: str) -> discord.Role | None:
    """Il ruolo condiviso `name` nella gilda Discord, creandolo se
    non esiste ancora — riusato da TUTTI i clan del server (mai uno
    per clan: due ruoli non possono stare alla stessa posizione)."""
    ruolo = discord.utils.get(guild.roles, name=name)
    if ruolo is not None:
        return ruolo
    try:
        return await guild.create_role(
            name=name, mentionable=False, reason="Ruolo condiviso Sistema Gilde/Clan"
        )
    except (discord.Forbidden, discord.HTTPException):
        logger.warning("Impossibile creare il ruolo condiviso '%s' nella gilda %s.", name, guild.id)
        return None


async def grant_member_access(category, member) -> None:
    """Overwrite base sulla categoria del clan per un membro appena
    entrato — senza questo non vedrebbe affatto i canali (la
    categoria nega la vista a @everyone fin dalla creazione)."""
    if category is None:
        return
    try:
        await category.set_permissions(member, overwrite=MEMBER_OVERWRITE)
    except (discord.Forbidden, discord.HTTPException):
        logger.warning(
            "Impossibile impostare gli overwrite base per %s sulla categoria %s.", member, category.id
        )


async def grant_officer_access(category, member) -> None:
    """Overwrite estesi (+ gestione canali/vocali) per Capo/Admin
    Clan — SOLO sulla categoria del proprio clan: è questo, non il
    ruolo condiviso, a garantire l'isolamento fra clan diversi."""
    if category is None:
        return
    try:
        await category.set_permissions(member, overwrite=OFFICER_OVERWRITE)
    except (discord.Forbidden, discord.HTTPException):
        logger.warning(
            "Impossibile impostare gli overwrite da ufficiale per %s sulla categoria %s.", member, category.id
        )


async def revoke_access(category, member) -> None:
    """Rimuove qualunque overwrite per-utente sulla categoria del
    clan — usato quando un membro viene espulso o il clan sciolto."""
    if category is None:
        return
    try:
        await category.set_permissions(member, overwrite=None)
    except (discord.Forbidden, discord.HTTPException):
        logger.warning(
            "Impossibile rimuovere gli overwrite per %s sulla categoria %s.", member, category.id
        )


async def sync_shared_role(guild, member, role_name: str, should_have: bool) -> None:
    """Aggiunge o rimuove il ruolo condiviso `role_name` sul membro —
    è solo un'etichetta visuale/di menzione: l'isolamento reale è
    dato dagli overwrite per-categoria sopra, non da questo ruolo."""
    ruolo = await get_or_create_shared_role(guild, role_name)
    if ruolo is None:
        return
    try:
        if should_have and ruolo not in member.roles:
            await member.add_roles(ruolo, reason=f"Sincronizzazione ruolo '{role_name}'")
        elif not should_have and ruolo in member.roles:
            await member.remove_roles(ruolo, reason=f"Sincronizzazione ruolo '{role_name}'")
    except (discord.Forbidden, discord.HTTPException):
        logger.warning("Impossibile sincronizzare il ruolo '%s' per %s.", role_name, member)


async def sync_member_clan_role(guild, category, member, role: str) -> None:
    """Punto d'ingresso unico usato da tutti i comandi che cambiano
    il ruolo di un membro in un clan (creazione, invita, promuovi):
    applica ruolo condiviso + overwrite di categoria coerenti col
    ruolo passato."""
    è_capo = role == "owner"
    è_admin = role == "admin"
    await sync_shared_role(guild, member, CAPO_CLAN_ROLE_NAME, è_capo)
    await sync_shared_role(guild, member, ADMIN_CLAN_ROLE_NAME, è_admin)
    if è_capo or è_admin:
        await grant_officer_access(category, member)
    else:
        await grant_member_access(category, member)


async def clear_member_clan_presence(guild, category, member) -> None:
    """Rimuove ogni traccia Discord dell'appartenenza di `member` al
    clan — usato quando viene espulso, lascia, o il clan viene
    sciolto."""
    await sync_shared_role(guild, member, CAPO_CLAN_ROLE_NAME, False)
    await sync_shared_role(guild, member, ADMIN_CLAN_ROLE_NAME, False)
    await revoke_access(category, member)
