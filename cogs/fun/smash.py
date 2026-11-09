"""
cogs/fun/smash.py
=================
`/giochi smash`: «Smash or pass» con un personaggio adulto di AniList (solo canali con limite d'età). Il personaggio
è un link alla pagina di AniList (Discord mostra l'anteprima: nessuna immagine ospitata da noi); due bottoni, un voto
a testa; il conteggio è settimanale.
Funzioni coperte: SPEC §16 (FUN-021; B11 di #131)
Dipende da: core/smash_logic.py, core/repositories/smash_repo.py, core/repositories/cache_esterna_repo.py
"""

from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord.ext import commands

from cogs.fun.entertainment import MODULE_FUN
from core import smash_logic as sl
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.i18n import testo_per
from core.repositories.cache_esterna_repo import cache_esterna_repo
from core.repositories.smash_repo import smash_repo
from core.ui_base import BaseView

SCADENZA_SECONDI = 3600
NESSUNA_MENZIONE = discord.AllowedMentions.none()


class SmashView(BaseView):
    """Due bottoni; ogni persona vota una volta per personaggio e settimana, il conteggio si aggiorna sul messaggio."""

    def __init__(self, personaggio: sl.Personaggio, settimana: str, etichette: tuple[str, str]) -> None:
        super().__init__(timeout=SCADENZA_SECONDI)
        self._p, self._settimana = personaggio, settimana
        for scelta, etichetta, stile in (("smash", etichette[0], discord.ButtonStyle.danger), ("pass", etichette[1], discord.ButtonStyle.secondary)):
            bottone = discord.ui.Button(label=etichetta[:80], style=stile)
            bottone.callback = self._voto(scelta)
            self.add_item(bottone)

    def _voto(self, scelta: str):
        async def callback(interaction: discord.Interaction) -> None:
            guild_id = interaction.guild.id if interaction.guild else 0
            nuovo = await smash_repo.vota(guild_id, self._settimana, str(self._p.id), interaction.user.id, scelta)
            if not nuovo:
                await interaction.response.send_message(await testo_per(interaction, "smash_gia_votato"), ephemeral=True)
                return
            s, p = await smash_repo.conteggio(guild_id, self._settimana, str(self._p.id))
            testo = await testo_per(interaction, "smash_messaggio", pubblica=True, pagina=self._p.pagina, nome=self._p.nome, opera=self._p.opera or "-", smash=s, passa=p)
            await interaction.response.edit_message(content=testo[:2000], allowed_mentions=NESSUNA_MENZIONE)

        return callback


class SmashCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo("giochi", nome="smash", descrizione="Smash or pass: un personaggio adulto di AniList (solo canali con limite d'età).")
    async def smash(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_FUN):
            await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
            return
        if not bool(getattr(interaction.channel, "is_nsfw", lambda: False)()):
            await interaction.response.send_message(await testo_per(interaction, "smash_solo_limite_eta"), ephemeral=True)
            return
        await interaction.response.defer()
        personaggio = await sl.personaggio_a_caso(cache_esterna_repo)
        if personaggio is None:
            await interaction.delete_original_response()
            await interaction.followup.send(await testo_per(interaction, "smash_non_risponde"), ephemeral=True)
            return
        settimana = sl.settimana(datetime.now(timezone.utc))
        s, p = await smash_repo.conteggio(interaction.guild.id, settimana, str(personaggio.id))
        testo = await testo_per(interaction, "smash_messaggio", pubblica=True, pagina=personaggio.pagina, nome=personaggio.nome, opera=personaggio.opera or "-", smash=s, passa=p)
        etichette = (await testo_per(interaction, "smash_bottone_smash", pubblica=True), await testo_per(interaction, "smash_bottone_pass", pubblica=True))
        await interaction.followup.send(testo[:2000], view=SmashView(personaggio, settimana, etichette), allowed_mentions=NESSUNA_MENZIONE)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SmashCog(bot))
