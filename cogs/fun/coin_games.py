"""
cogs/fun/coin_games.py
======================
Giochi con le monete (/giochi gioca) e misuratore a tema libero (/fun misura). Le monete del bot
non si comprano con soldi veri. Il gioco del conteggio è in cogs/utility/conteggio.py.
Funzioni coperte: SPEC §23.16 (NF-40)
Dipende da: core/coin_games_logic.py
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.coin_games_logic import (
    ATTESA_TRA_PARTITE_SECONDI,
    LATI_MONETINA,
    PUNTATA_MASSIMA,
    PUNTATA_MINIMA,
    gioca_dadi,
    gioca_monetina,
    gioca_slot,
)
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.fun_logic import MAX_TEMA_MISURA, compute_misura, tema_ammesso
from core.i18n import testo_per
from core.moneta_server import aggiungi_moneta
from core.repositories.leveling_repo import leveling_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo

logger = logging.getLogger("iyokai.coin_games")

MODULE_FUN = "fun"
MODULE_LEVELING = "leveling"  # le monete stanno nel modulo livelli

_SCELTE_GIOCO = [
    app_commands.Choice(name="Monetina (testa o croce, vinci il doppio)", value="monetina"),
    app_commands.Choice(name="Dadi (tu contro il bot)", value="dadi"),
    app_commands.Choice(name="Slot (tre rulli)", value="slot"),
]
_SCELTE_LATO = [
    app_commands.Choice(name="Testa", value="testa"),
    app_commands.Choice(name="Croce", value="croce"),
]

_AVVISO = "Le coin del bot non si comprano con soldi veri."


def _barra(percentuale: int, lunghezza: int = 10) -> str:
    piene = round(percentuale / 100 * lunghezza)
    return "█" * piene + "░" * (lunghezza - piene)


class CoinGamesCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._rng = random.Random()

    async def _modulo_spento(self, interaction: discord.Interaction) -> bool:
        """Vero (dopo aver risposto) se il comando non può girare: fuori da un server o modulo spento."""
        if interaction.guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return True
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_FUN):
            await interaction.response.send_message(
                await testo_per(interaction, "ping_questo_modulo_non_attivo_su"),
                ephemeral=True,
            )
            return True
        return False

    # ================================================================
    # /giochi gioca
    # ================================================================
    @comando_di_gruppo(
        "giochi",
        nome="gioca",
        descrizione="Gioca le tue coin: monetina, dadi o slot.",
    )
    @app_commands.describe(
        gioco="A cosa giocare",
        puntata=f"Quante coin puntare ({PUNTATA_MINIMA}-{PUNTATA_MASSIMA})",
        scelta="Solo per la monetina: testa o croce",
    )
    @app_commands.choices(gioco=_SCELTE_GIOCO, scelta=_SCELTE_LATO)
    async def gioca(
        self,
        interaction: discord.Interaction,
        gioco: app_commands.Choice[str],
        puntata: app_commands.Range[int, PUNTATA_MINIMA, PUNTATA_MASSIMA],
        scelta: app_commands.Choice[str] | None = None,
    ) -> None:
        if await self._modulo_spento(interaction):
            return
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_LEVELING):
            await interaction.response.send_message(
                await testo_per(interaction, "coingames_le_coin_vivono_nel_modulo"),
                ephemeral=True,
            )
            return
        if gioco.value == "monetina" and (scelta is None or scelta.value not in LATI_MONETINA):
            await interaction.response.send_message(
                await testo_per(interaction, "coingames_per_la_monetina_scegli_testa"), ephemeral=True
            )
            return

        if gioco.value == "monetina":
            esito = gioca_monetina(scelta.value, puntata, self._rng)
        elif gioco.value == "dadi":
            esito = gioca_dadi(puntata, self._rng)
        else:
            esito = gioca_slot(puntata, self._rng)

        # Puntata tolta, vincita data e attesa controllata in una scrittura sola.
        saldo = await leveling_repo.gioca(
            interaction.guild.id,
            interaction.user.id,
            puntata,
            esito.restituzione,
            ATTESA_TRA_PARTITE_SECONDI,
        )
        if saldo is None:
            resto = await leveling_repo.attesa_partita_rimasta(
                interaction.guild.id, interaction.user.id, ATTESA_TRA_PARTITE_SECONDI
            )
            if resto > 0:
                await interaction.response.send_message(
                    await testo_per(interaction, "coingames_piano_aspetta_ancora_secondi_tra", resto=resto),
                    ephemeral=True,
                )
                return
            totali = await leveling_repo.get_totals(interaction.guild.id, interaction.user.id)
            await interaction.response.send_message(
                await testo_per(interaction, "coingames_non_hai_abbastanza_coin_ne", coins_total=totali.coins_total, puntata=puntata),
                ephemeral=True,
            )
            return
        if esito.vinto:
            verdetto, colore = f"🎉 Hai vinto **{esito.guadagno}** coin!", discord.Color.green()
        elif esito.pari:
            verdetto, colore = "🤝 Pari: riprendi la puntata.", discord.Color.light_grey()
        else:
            verdetto, colore = f"💸 Hai perso **{puntata}** coin.", discord.Color.red()
        embed = discord.Embed(
            title=f"{gioco.name.split(' (')[0]} — puntata {puntata}",
            description=f"{esito.descrizione}\n\n{verdetto}\nSaldo: **{saldo}** coin",
            color=colore,
        )
        embed.set_footer(text=_AVVISO)
        try:
            immagine = await leveling_settings_repo.get_immagine_moneta(interaction.guild.id)
        except Exception:
            immagine = None
        await interaction.response.send_message(embed=embed, file=aggiungi_moneta(embed, immagine))

    # ================================================================
    # /fun misura
    # ================================================================
    @comando_di_gruppo(
        "fun",
        nome="misura",
        descrizione="Misura da 0 a 100% quanto c'è di una cosa a tua scelta.",
    )
    @app_commands.describe(
        tema="Cosa misurare, per esempio: coraggio, fame, voglia di lunedì",
        membro="Chi misurare (di default tu)",
    )
    async def misura(
        self,
        interaction: discord.Interaction,
        tema: app_commands.Range[str, 1, MAX_TEMA_MISURA],
        membro: discord.Member | None = None,
    ) -> None:
        if await self._modulo_spento(interaction):
            return
        if not tema_ammesso(tema):
            await interaction.response.send_message(
                await testo_per(interaction, "coingames_su_questo_tema_non_misuro"),
                ephemeral=True,
            )
            return
        bersaglio = membro or interaction.user
        percentuale = compute_misura(bersaglio.id, tema, datetime.now(timezone.utc).date())
        embed = discord.Embed(
            title=await testo_per(interaction, "coingames_misura", pubblica=True),
            description=(
                await testo_per(interaction, "coingames_di_domani_potrebbe_cambiare", v1=tema.strip(), display_name=bersaglio.display_name, v3=_barra(percentuale), percentuale=percentuale, pubblica=True)
            ),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CoinGamesCog(bot))
