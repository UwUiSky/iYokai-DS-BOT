"""
cogs/security/alt_detection.py
==============================
Account doppi trovati dalla verifica web (NF-21): l'avviso allo staff nel
canale del log della verifica e `/security alt elenco`. Nessun ban
automatico: decide lo staff. La verifica dalla pagina e il confronto delle
impronte stanno in `core/panel_bridge.py` e `core/alt_detection_logic.py`.
Funzioni coperte: SPEC §4.2, §4.3 (NF-21)
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from cogs.moderation._shared import ensure_module_enabled
from core.alt_detection_logic import GIORNI_DOPPI, Doppio, testo_avviso
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.repositories.fingerprint_repo import MAX_ELENCO, fingerprint_repo
from core.repositories.verify_repo import verify_repo

logger = logging.getLogger("iyokai.alt_detection")

MODULO_VERIFY = "verify"
SOTTOGRUPPO = ("alt", "Account doppi trovati dalla verifica web.")


async def avvisa_staff(guild: discord.Guild, membro: discord.Member, doppi: list[Doppio]) -> bool:
    """Manda l'avviso nel canale del log della verifica. False se non c'è o non si può scrivere."""
    config = await verify_repo.get_config(guild.id)
    canale = guild.get_channel(config.log_channel_id) if config.log_channel_id else None
    if not isinstance(canale, discord.TextChannel):
        return False
    embed = discord.Embed(
        title="Possibile account doppio",
        description=testo_avviso(membro.mention, membro.id, doppi)[:4096],
        color=discord.Color.orange(),
    )
    try:
        await canale.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        logger.warning("Avviso dei doppi non inviato nel server %s.", guild.id)
        return False
    return True


def embed_elenco(righe) -> discord.Embed:
    embed = discord.Embed(title="Account doppi (verifica web)", color=discord.Color.orange())
    if not righe:
        embed.description = (
            "Nessun doppio trovato. Le coppie si vedono qui solo se il server usa la "
            "verifica dalla pagina web (`/security verify setup`, modalità Pagina web)."
        )
        return embed
    embed.description = "\n".join(
        f"<t:{int(r['trovato_il'].timestamp())}:d> <@{r['user_id']}> ↔ <@{r['altro_user_id']}> "
        f"(`{r['user_id']}` · `{r['altro_user_id']}`): **{r['livello']}**"
        for r in righe
    )[:4096]
    embed.set_footer(text=f"Ultimi {MAX_ELENCO} al massimo. Restano {GIORNI_DOPPI} giorni.")
    return embed


class AltDetectionCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "security", nome="elenco", descrizione="Gli account doppi trovati dalla verifica web.", sottogruppo=SOTTOGRUPPO
    )
    async def elenco_cmd(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULO_VERIFY):
            return
        righe = await fingerprint_repo.elenco_doppi(interaction.guild.id)
        await interaction.response.send_message(
            embed=embed_elenco(righe), ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AltDetectionCog(bot))
