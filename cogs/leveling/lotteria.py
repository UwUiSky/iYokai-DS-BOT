"""
cogs/leveling/lotteria.py
=========================
Lotteria giornaliera (/monete conto lotteria), rimborso di parte delle perdite (/monete conto rimborso) e
le loro regole (/admin-giochi stipendi lotteria). Un lavoro ogni 10 minuti estrae i giorni passati: il vincitore
prende il 90% di quanto speso, il resto va alla cassa del server. Le monete non si comprano con soldi veri.
Funzioni coperte: ECO-117, ECO-118, ECO-121
Dipende da: core/repositories/lotteria_repo.py
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.leveling.leveling import _comando_rifiutato
from cogs.leveling.rischio import _SG_CONTO
from cogs.leveling.stipendi import _SG as _SG_ADMIN
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.i18n import testo_per
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.lotteria_repo import MAX_BIGLIETTI_AL_GIORNO, lotteria_repo

logger = logging.getLogger("iyokai.lotteria")
NESSUNA_MENZIONE = discord.AllowedMentions.none()


def _oggi():
    return datetime.now(timezone.utc).date()


class LotteriaCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._giro.start()

    def cog_unload(self) -> None:
        self._giro.cancel()
        togli_comandi_del_cog(self)

    @tasks.loop(minutes=10)
    async def _giro(self) -> None:
        oggi = _oggi()
        try:
            server = await lotteria_repo.guild_con_biglietti(oggi)
        except Exception:
            logger.exception("Lotteria: elenco dei server")
            return
        for guild_id in server:
            try:
                for e in await lotteria_repo.estrai(guild_id, oggi):
                    guild = self.bot.get_guild(guild_id)
                    utente = guild.get_member(e.vincitore) if guild else None
                    if utente is not None:
                        try:
                            await utente.send(f"🎟️ Hai vinto la lotteria di **{guild.name[:60]}**: {e.premio} monete!")
                        except discord.HTTPException:
                            pass
            except Exception:
                logger.exception("Lotteria: estrazione del server %s", guild_id)

    @_giro.before_loop
    async def _prima(self) -> None:
        await self.bot.wait_until_ready()

    @comando_di_gruppo("monete", nome="lotteria", descrizione="Compra biglietti della lotteria di oggi o guarda le ultime estrazioni.", sottogruppo=_SG_CONTO)
    @app_commands.describe(quanti=f"Quanti biglietti comprare (1-{MAX_BIGLIETTI_AL_GIORNO}); senza numero vedi lo stato")
    async def lotteria(self, interaction: discord.Interaction, quanti: app_commands.Range[int, 1, MAX_BIGLIETTI_AL_GIORNO] | None = None) -> None:
        if await _comando_rifiutato(interaction):
            return
        g, u = interaction.guild.id, interaction.user.id
        i = (await leveling_settings_repo.get_config(g)).impostazioni
        if i.lotteria_prezzo <= 0:
            await interaction.response.send_message(await testo_per(interaction, "lot_spenta"), ephemeral=True)
            return
        if quanti is not None:
            posseduti = await lotteria_repo.compra(g, u, _oggi(), i.lotteria_prezzo, quanti)
            if posseduti is None:
                await interaction.response.send_message(
                    await testo_per(interaction, "lot_no", massimo=MAX_BIGLIETTI_AL_GIORNO, prezzo=i.lotteria_prezzo, moneta=i.currency_name), ephemeral=True
                )
                return
        miei, tutti = await lotteria_repo.miei(g, u, _oggi())
        registro = await lotteria_repo.registro(g, 5)
        righe = [await testo_per(interaction, "lot_stato", miei=miei, tutti=tutti, prezzo=i.lotteria_prezzo, moneta=i.currency_name)]
        righe += [f"{r['giorno']}: <@{r['vincitore']}> **{r['premio']}** ({r['partecipanti']})" for r in registro]
        await interaction.response.send_message("\n".join(righe)[:3900], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("monete", nome="rimborso", descrizione="Riscuoti una parte delle tue perdite nei giochi, se il server la rimborsa.", sottogruppo=_SG_CONTO)
    async def rimborso(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        i = (await leveling_settings_repo.get_config(interaction.guild.id)).impostazioni
        if i.rimborso_pct <= 0:
            await interaction.response.send_message(await testo_per(interaction, "lot_rimborso_spento"), ephemeral=True)
            return
        dato = await lotteria_repo.rimborso(interaction.guild.id, interaction.user.id, i.rimborso_pct)
        if dato is None:
            await interaction.response.send_message(await testo_per(interaction, "lot_rimborso_niente"), ephemeral=True)
            return
        await interaction.response.send_message(
            await testo_per(interaction, "lot_rimborso_ok", dato=dato, moneta=i.currency_name, pct=i.rimborso_pct, pubblica=True)
        )

    @comando_di_gruppo("admin-giochi", nome="lotteria", descrizione="Prezzo della lotteria e quota di perdite rimborsata.", sottogruppo=_SG_ADMIN)
    @app_commands.describe(prezzo="Prezzo di un biglietto (0 = lotteria spenta)", rimborso="Quota delle perdite nette che torna indietro, in % (0-20)")
    async def regole(
        self, interaction: discord.Interaction,
        prezzo: app_commands.Range[int, 0, 10_000] | None = None, rimborso: app_commands.Range[int, 0, 20] | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        campi = {k: v for k, v in {"lotteria_prezzo": prezzo, "rimborso_pct": rimborso}.items() if v is not None}
        if not campi:
            await interaction.response.send_message(await testo_per(interaction, "eco_scegli_un_valore"), ephemeral=True)
            return
        await leveling_settings_repo.set_options(interaction.guild.id, **campi)
        await interaction.response.send_message(await testo_per(interaction, "eco_salvato"), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LotteriaCog(bot))
