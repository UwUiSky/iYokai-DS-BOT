"""
cogs/fun/giochi_monete.py
=========================
Giochi con le monete oltre a monetina, dadi e slot: roulette, carta, scala (/giochi roulette, carta,
scala), statistiche personali e vincite più grosse (/giochi statistiche, record). Puntate e pausa
sono quelle scelte dal server; la puntata si toglie e la vincita si dà in una scrittura sola.
Le monete del bot non si comprano con soldi veri.
Funzioni coperte: ECO-021, ECO-022, ECO-090, ECO-099, ECO-100, ECO-115, ECO-116
Dipende da: core/coin_games_logic.py, core/repositories/economia_repo.py
"""

from __future__ import annotations

import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

from core.coin_games_logic import Esito, gioca_carta, gioca_roulette, gioca_scala, SEMI, VALORI
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.database import db
from core.i18n import testo_per
from core.leveling_logic import controlla_puntata
from core.moneta_server import aggiungi_moneta
from core.repositories.economia_repo import economia_repo
from core.repositories.leveling_repo import leveling_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo

logger = logging.getLogger("iyokai.giochi_monete")
MODULE_FUN = "fun"
MODULE_LEVELING = "leveling"
NESSUNA_MENZIONE = discord.AllowedMentions.none()
PUNTATA_TETTO_ASSOLUTO = 1_000_000  # ECO-021: oltre questo il server non può andare
RNG = random.SystemRandom()  # casualità del sistema operativo, non prevedibile


async def esegui_partita(interaction: discord.Interaction, gioco: str, titolo: str, puntata: int, calcola) -> None:
    """
    Una partita intera: controlla modulo e puntata, estrae l'esito (`calcola(puntata)`), poi toglie la
    puntata e dà la vincita in UNA scrittura che controlla anche saldo e pausa (ECO-021, ECO-022).
    """
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
        return
    if not await db.is_module_active_for_guild(guild.id, MODULE_FUN) or not await db.is_module_active_for_guild(
        guild.id, MODULE_LEVELING
    ):
        await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
        return
    impostazioni = (await leveling_settings_repo.get_config(guild.id)).impostazioni
    motivo = controlla_puntata(puntata, impostazioni)
    if motivo is not None:
        await interaction.response.send_message(f"❌ {motivo}", ephemeral=True)
        return
    esito: Esito = calcola(puntata)
    saldo = await leveling_repo.gioca(guild.id, interaction.user.id, puntata, esito.restituzione, impostazioni.attesa_gioco)
    if saldo is None:
        resto = await leveling_repo.attesa_partita_rimasta(guild.id, interaction.user.id, impostazioni.attesa_gioco)
        if resto > 0:
            await interaction.response.send_message(
                await testo_per(interaction, "coingames_piano_aspetta_ancora_secondi_tra", resto=resto), ephemeral=True
            )
            return
        totali = await leveling_repo.get_totals(guild.id, interaction.user.id)
        await interaction.response.send_message(
            await testo_per(interaction, "coingames_non_hai_abbastanza_coin_ne", coins_total=totali.coins_total, puntata=puntata),
            ephemeral=True,
        )
        return
    try:
        await economia_repo.registra_partita(guild.id, interaction.user.id, gioco, puntata, esito.restituzione)
    except Exception:
        logger.warning("Statistiche della partita non scritte (server %s)", guild.id, exc_info=True)
    moneta = impostazioni.currency_name
    if esito.vinto:
        verdetto, colore = f"🎉 +**{esito.guadagno}** {moneta}", discord.Color.green()
    elif esito.pari:
        verdetto, colore = "🤝 =", discord.Color.light_grey()
    else:
        verdetto, colore = f"💸 -**{puntata}** {moneta}", discord.Color.red()
    embed = discord.Embed(
        title=f"{titolo} — {puntata}",
        description=f"{esito.descrizione}\n\n{verdetto}\nSaldo: **{saldo}** {moneta}",
        color=colore,
    )
    embed.set_footer(text=await testo_per(interaction, "gm_avviso", pubblica=True))
    try:
        immagine = await leveling_settings_repo.get_immagine_moneta(guild.id)
    except Exception:
        immagine = None
    await interaction.response.send_message(embed=embed, file=aggiungi_moneta(embed, immagine), allowed_mentions=NESSUNA_MENZIONE)


_SCELTE_ROULETTE = [
    app_commands.Choice(name=n, value=v)
    for n, v in (
        ("Rosso (x2)", "rosso"), ("Nero (x2)", "nero"), ("Pari (x2)", "pari"), ("Dispari (x2)", "dispari"),
        ("1-18 (x2)", "basso"), ("19-36 (x2)", "alto"), ("Prima dozzina 1-12 (x3)", "dozzina1"),
        ("Seconda dozzina 13-24 (x3)", "dozzina2"), ("Terza dozzina 25-36 (x3)", "dozzina3"),
        ("Colonna 1 (x3)", "colonna1"), ("Colonna 2 (x3)", "colonna2"), ("Colonna 3 (x3)", "colonna3"),
        ("Un numero (x36)", "numero"),
    )
]
_SCELTE_TIPO_CARTA = [
    app_commands.Choice(name="Colore (x1,9)", value="colore"),
    app_commands.Choice(name="Seme (x3,8)", value="seme"),
    app_commands.Choice(name="Valore (x12)", value="valore"),
]


class GiochiMoneteCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def cog_unload(self) -> None:
        togli_comandi_del_cog(self)

    @comando_di_gruppo("giochi", nome="roulette", descrizione="Roulette: colore, pari, dozzina, colonna o numero.")
    @app_commands.describe(
        puntata="Quante monete puntare", scommessa="Su cosa punti", numero="Solo per «Un numero»: da 0 a 36"
    )
    @app_commands.choices(scommessa=_SCELTE_ROULETTE)
    async def roulette(
        self,
        interaction: discord.Interaction,
        puntata: app_commands.Range[int, 1, PUNTATA_TETTO_ASSOLUTO],
        scommessa: app_commands.Choice[str],
        numero: app_commands.Range[int, 0, 36] | None = None,
    ) -> None:
        if scommessa.value == "numero" and numero is None:
            await interaction.response.send_message(await testo_per(interaction, "gm_serve_numero"), ephemeral=True)
            return
        await esegui_partita(
            interaction, "roulette", "Roulette", puntata,
            lambda p: gioca_roulette(scommessa.value, p, RNG, numero),
        )

    @comando_di_gruppo("giochi", nome="carta", descrizione="Indovina la carta estratta: colore, seme o valore.")
    @app_commands.describe(
        puntata="Quante monete puntare", tipo="Cosa indovinare",
        scelta="rosso o nero; cuori, quadri, fiori o picche; A, 2-10, J, Q, K",
    )
    @app_commands.choices(tipo=_SCELTE_TIPO_CARTA)
    async def carta(
        self,
        interaction: discord.Interaction,
        puntata: app_commands.Range[int, 1, PUNTATA_TETTO_ASSOLUTO],
        tipo: app_commands.Choice[str],
        scelta: app_commands.Range[str, 1, 10],
    ) -> None:
        scelta = scelta.strip().lower() if tipo.value != "valore" else scelta.strip().upper()
        ammessi = {"colore": ("rosso", "nero"), "seme": SEMI, "valore": VALORI}[tipo.value]
        if scelta not in ammessi:
            await interaction.response.send_message(
                await testo_per(interaction, "gm_scelta_non_valida", ammessi=", ".join(ammessi)), ephemeral=True
            )
            return
        await esegui_partita(
            interaction, "carta", "Carta", puntata, lambda p: gioca_carta(tipo.value, scelta, p, RNG)
        )

    @comando_di_gruppo("giochi", nome="scala", descrizione="Scala fortunata: più sali, più rende.")
    @app_commands.describe(puntata="Quante monete puntare")
    async def scala(
        self, interaction: discord.Interaction, puntata: app_commands.Range[int, 1, PUNTATA_TETTO_ASSOLUTO]
    ) -> None:
        await esegui_partita(interaction, "scala", "Scala", puntata, lambda p: gioca_scala(p, RNG))

    @comando_di_gruppo("giochi", nome="statistiche", descrizione="Le tue partite, vincite e perdite per gioco.")
    async def statistiche(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        righe = await economia_repo.statistiche_giocatore(interaction.guild.id, interaction.user.id)
        if not righe:
            await interaction.response.send_message(await testo_per(interaction, "gm_nessuna_partita"), ephemeral=True)
            return
        testo = "\n".join(
            f"**{r['gioco']}**: {r['partite']} (✅{r['vinte']} ❌{r['perse']} 🤝{r['pari']}) · netto {r['netto']:+d} · record {r['max_vincita']}"
            for r in righe
        )
        await interaction.response.send_message(testo[:4000], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("giochi", nome="record", descrizione="Le 10 vincite più grosse del server.")
    async def record(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        righe = await economia_repo.vincite_piu_grosse(interaction.guild.id)
        if not righe:
            await interaction.response.send_message(await testo_per(interaction, "gm_nessuna_partita"), ephemeral=True)
            return
        testo = "\n".join(f"{n}. <@{r['user_id']}> — **{r['vincita']}** ({r['gioco']})" for n, r in enumerate(righe, 1))
        await interaction.response.send_message(testo, allowed_mentions=NESSUNA_MENZIONE)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GiochiMoneteCog(bot))
