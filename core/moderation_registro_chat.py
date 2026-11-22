"""
core/moderation_registro_chat.py
================================
Il registro degli ultimi messaggi del canale, salvato insieme al caso (MOD-051): spento di base, 100 messaggi, tenuto
30 giorni, letto con `/mod-casi caso chat`. Serve il permesso di leggere i messaggi e il Message Content Intent.
Degli allegati restano nome pulito, tipo e peso (D74), come per `/mod-canali esporta-chat`.
Funzioni coperte: MOD-051
"""

from __future__ import annotations

import logging

import discord

from core import moderation_esporta_chat as esporta
from core.database import db

logger = logging.getLogger("iyokai.moderation.registro_chat")

SETTING_REGISTRO_CHAT = "mod_registro_chat"
MESSAGGI = 100
MAX_BYTE = 1_000_000  # ben sotto il tetto del file: 100 messaggi stanno largamente


async def salva(interaction: discord.Interaction, case_number: int) -> bool:
    """Salva il registro del canale del comando per questo caso. Mai solleva: il caso c'è già, il registro è un'aggiunta."""
    guild, canale = interaction.guild, interaction.channel
    try:
        if guild is None or not await db.get_guild_setting(guild.id, SETTING_REGISTRO_CHAT):
            return False
        if not isinstance(canale, (discord.TextChannel, discord.Thread)):
            return False
        permessi = canale.permissions_for(guild.me)
        if not (permessi.view_channel and permessi.read_message_history):
            return False
        messaggi = [m async for m in canale.history(limit=MESSAGGI)]
        messaggi.reverse()
        contenuto, scritti, _ = esporta.costruisci_file(messaggi, canale.name)
        await db.pool.execute(
            "INSERT INTO moderation_chat_log (guild_id, case_number, channel_id, messaggi, contenuto) "
            "VALUES ($1, $2, $3, $4, $5) ON CONFLICT (guild_id, case_number) DO NOTHING",
            guild.id, case_number, canale.id, scritti, contenuto[:MAX_BYTE],
        )
        return True
    except Exception:
        logger.warning("Registro della chat non salvato (caso %s).", case_number, exc_info=True)
        return False


async def leggi(guild_id: int, case_number: int) -> tuple[bytes, int, int] | None:
    """(contenuto, messaggi, canale) oppure None."""
    r = await db.pool.fetchrow(
        "SELECT contenuto, messaggi, channel_id FROM moderation_chat_log WHERE guild_id = $1 AND case_number = $2",
        guild_id, case_number,
    )
    return (bytes(r["contenuto"]), r["messaggi"], r["channel_id"]) if r else None
