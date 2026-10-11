"""
cogs/moderation/tempban_modes.py
================================
Aiuti per il ban temporaneo con rientro e per il ban in isolamento
(/modban tempban, opzione `modo`): invito da mandare prima del ban,
ruolo e canale di isolamento, ruoli salvati e ridati.
Funzioni coperte: SPEC §5.11, §5.12 (issue #138)
Dipende da: core/tempban_logic.py
"""

from __future__ import annotations

import logging

import discord

from core.database import db
from core.tempban_logic import (
    INVITO_MAX_ETA,
    INVITO_MAX_USI,
    RuoloInfo,
    ruoli_da_ridare,
)

logger = logging.getLogger("iyokai.moderation.tempban_modes")

SETTING_ISOLAMENTO_RUOLO = "isolamento_role_id"
SETTING_ISOLAMENTO_CANALE = "isolamento_channel_id"


def info_ruolo(ruolo: discord.Role) -> RuoloInfo:
    return RuoloInfo(
        id=ruolo.id,
        position=ruolo.position,
        managed=ruolo.managed,
        is_default=ruolo.is_default(),
    )


def info_ruoli(ruoli) -> list[RuoloInfo]:
    return [info_ruolo(r) for r in ruoli]


async def crea_invito(guild: discord.Guild) -> discord.Invite | None:
    """
    Invito che non scade (così vale oltre la fine del ban) e si usa una
    volta sola. Prova il canale di sistema, quello delle regole e poi i
    primi canali di testo; None se nessuno lo permette.
    """
    candidati = [guild.system_channel, getattr(guild, "rules_channel", None)]
    candidati += list(guild.text_channels)[:5]
    visti = set()
    for canale in candidati:
        if canale is None or canale.id in visti:
            continue
        visti.add(canale.id)
        try:
            return await canale.create_invite(
                max_age=INVITO_MAX_ETA,
                max_uses=INVITO_MAX_USI,
                unique=True,
                reason="Invito di rientro dopo il ban temporaneo",
            )
        except discord.HTTPException:
            continue
    return None


async def cancella_invito(invito: discord.Invite | None) -> None:
    if invito is None:
        return
    try:
        await invito.delete(reason="Ban temporaneo non riuscito")
    except discord.HTTPException:
        pass


def _nega_vista(overwrite: discord.PermissionOverwrite) -> bool:
    """True se il permesso è stato cambiato (non era già negato)."""
    if overwrite.view_channel is False:
        return False
    overwrite.update(view_channel=False)
    return True


async def _nega_su_canale(canale: discord.abc.GuildChannel, ruolo: discord.Role) -> None:
    ow = canale.overwrites_for(ruolo)
    if not _nega_vista(ow):
        return
    try:
        await canale.set_permissions(ruolo, overwrite=ow, reason="Isolamento: canale nascosto")
    except discord.HTTPException:
        logger.warning("Isolamento: canale %s non nascosto (server %s).", canale.id, canale.guild.id)


async def prepara_isolamento(
    guild: discord.Guild,
) -> tuple[discord.Role, discord.TextChannel] | None:
    """
    Ruolo e canale di isolamento del server, creati al primo uso. Il ruolo
    non vede nessun canale tranne quello di isolamento (letto, non scritto).
    None se Discord rifiuta la creazione.
    """
    ruolo_id = await db.get_guild_setting(guild.id, SETTING_ISOLAMENTO_RUOLO)
    canale_id = await db.get_guild_setting(guild.id, SETTING_ISOLAMENTO_CANALE)
    ruolo = guild.get_role(ruolo_id) if ruolo_id else None
    canale = guild.get_channel(canale_id) if canale_id else None
    try:
        if ruolo is None:
            ruolo = await guild.create_role(
                name="Isolamento", reason="Ruolo del ban in isolamento"
            )
            await db.set_guild_setting(guild.id, SETTING_ISOLAMENTO_RUOLO, ruolo.id)
        if canale is None:
            canale = await guild.create_text_channel(
                "isolamento",
                overwrites={
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    ruolo: discord.PermissionOverwrite(
                        view_channel=True, send_messages=False, read_message_history=True
                    ),
                    guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                },
                reason="Canale del ban in isolamento",
            )
            await db.set_guild_setting(guild.id, SETTING_ISOLAMENTO_CANALE, canale.id)
    except discord.HTTPException:
        return None
    for altro in guild.channels:
        if altro.id != canale.id:
            await _nega_su_canale(altro, ruolo)
    return ruolo, canale


async def nega_canale_nuovo(canale: discord.abc.GuildChannel) -> None:
    """Un canale creato dopo riceve lo stesso divieto per chi è isolato."""
    ruolo_id = await db.get_guild_setting(canale.guild.id, SETTING_ISOLAMENTO_RUOLO)
    if ruolo_id is None:
        return
    canale_iso = await db.get_guild_setting(canale.guild.id, SETTING_ISOLAMENTO_CANALE)
    if canale.id == canale_iso:
        return
    ruolo = canale.guild.get_role(ruolo_id)
    if ruolo is not None:
        await _nega_su_canale(canale, ruolo)


def ruoli_da_riprendere(guild: discord.Guild, salvati: list[int]) -> list[discord.Role]:
    """I ruoli salvati che il bot può ridare oggi."""
    ammessi = set(
        ruoli_da_ridare(salvati, info_ruoli(guild.roles), guild.me.top_role.position)
    )
    ruoli = [guild.get_role(i) for i in salvati if i in ammessi]
    return [r for r in ruoli if r is not None]
