"""
cogs/fun/coin_games.py
======================
Giochi con le monete (/fun gioca), misuratore a tema libero (/fun misura) e
gioco del conteggio in un canale (/fun conteggio). Le monete del bot non si
comprano con soldi veri.
Funzioni coperte: SPEC §23.16 (NF-40)
Dipende da: core/coin_games_logic.py, core/repositories/counting_game_repo.py
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
    numero_del_messaggio,
)
from core.channel_access import PERMESSI_DI_REAZIONE, motivo_se_il_bot_non_puo
from core.command_access import Livello, richiedi
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.fun_logic import MAX_TEMA_MISURA, compute_misura, tema_ammesso
from core.repositories.counting_game_repo import counting_game_repo
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
_SCELTE_CONTEGGIO = [
    app_commands.Choice(name="Scegli il canale", value="imposta"),
    app_commands.Choice(name="Spegni", value="spegni"),
    app_commands.Choice(name="Stato", value="stato"),
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
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return True
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_FUN):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /admin setup attiva.",
                ephemeral=True,
            )
            return True
        return False

    # ================================================================
    # /fun gioca
    # ================================================================
    @comando_di_gruppo(
        "fun",
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
                "Le coin vivono nel modulo Livelli, che qui non è attivo: "
                "un amministratore può attivarlo con /admin setup attiva.",
                ephemeral=True,
            )
            return
        if gioco.value == "monetina" and (scelta is None or scelta.value not in LATI_MONETINA):
            await interaction.response.send_message(
                "Per la monetina scegli testa o croce.", ephemeral=True
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
                    f"Piano! Aspetta ancora {resto} secondi tra una partita e l'altra.",
                    ephemeral=True,
                )
                return
            totali = await leveling_repo.get_totals(interaction.guild.id, interaction.user.id)
            await interaction.response.send_message(
                f"Non hai abbastanza coin: ne hai **{totali.coins_total}**, ne servono **{puntata}**.",
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
                "Su questo tema non misuro: scegline un altro (niente caratteristiche "
                "personali come origine, religione, salute o orientamento).",
                ephemeral=True,
            )
            return
        bersaglio = membro or interaction.user
        percentuale = compute_misura(bersaglio.id, tema, datetime.now(timezone.utc).date())
        embed = discord.Embed(
            title="📏 Misura",
            description=(
                f"**{tema.strip()}** di **{bersaglio.display_name}**\n\n"
                f"{_barra(percentuale)} **{percentuale}%**\n\nDomani potrebbe cambiare."
            ),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed)

    # ================================================================
    # /fun conteggio e il gioco in sé
    # ================================================================
    @comando_di_gruppo(
        "fun",
        nome="conteggio",
        descrizione="Gioco del conteggio: scegli il canale dove contare a turno 1, 2, 3...",
    )
    @app_commands.describe(azione="Cosa fare", canale="Il canale (solo per «Scegli il canale»)")
    @app_commands.choices(azione=_SCELTE_CONTEGGIO)
    @richiedi(Livello.ADMIN)
    async def conteggio(
        self,
        interaction: discord.Interaction,
        azione: app_commands.Choice[str],
        canale: discord.TextChannel | None = None,
    ) -> None:
        if await self._modulo_spento(interaction):
            return
        guild_id = interaction.guild.id
        if azione.value == "imposta":
            if canale is None:
                await interaction.response.send_message("Indica il canale.", ephemeral=True)
                return
            motivo = motivo_se_il_bot_non_puo(
                canale, interaction.guild.me, PERMESSI_DI_REAZIONE
            )
            if motivo is not None:
                await interaction.response.send_message(
                    f"Non posso far giocare in {canale.mention}: {motivo}.", ephemeral=True
                )
                return
            await counting_game_repo.set_channel(guild_id, canale.id)
            await interaction.response.send_message(
                f"✅ Si conta in {canale.mention}: scrivete **1**, poi **2**, e così via, "
                "a turno (nessuno due volte di fila). Chi sbaglia riporta tutto a zero.",
                ephemeral=True,
            )
        elif azione.value == "spegni":
            spento = await counting_game_repo.disable(guild_id)
            await interaction.response.send_message(
                "✅ Gioco del conteggio spento." if spento else "Il gioco non era attivo.",
                ephemeral=True,
            )
        else:
            stato = await counting_game_repo.get(guild_id)
            if stato is None:
                await interaction.response.send_message("Il gioco non è attivo.", ephemeral=True)
                return
            await interaction.response.send_message(
                f"Canale: <#{stato.channel_id}> · Ultimo numero: **{stato.current}** · "
                f"Record: **{stato.best}**",
                ephemeral=True,
            )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        numero = numero_del_messaggio(message.content or "")
        if numero is None:
            return
        try:
            if await counting_game_repo.channel_id(message.guild.id) != message.channel.id:
                return
            if not await db.is_module_active_for_guild(message.guild.id, MODULE_FUN):
                return
            esito = await counting_game_repo.register(
                message.guild.id, message.channel.id, message.author.id, numero
            )
        except Exception:
            logger.warning("Conteggio non registrato nel server %s.", message.guild.id)
            return
        if esito is None:
            return
        try:
            if esito.corretto:
                await message.add_reaction("✅")
            else:
                await message.add_reaction("❌")
                await message.channel.send(
                    f"{message.author.mention} ha rovinato tutto a **{esito.numero}**! "
                    f"Si riparte da **1**. Record: **{esito.record}**.",
                    allowed_mentions=discord.AllowedMentions(users=[message.author]),
                )
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CoinGamesCog(bot))
