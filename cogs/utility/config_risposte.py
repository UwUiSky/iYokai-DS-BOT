"""
cogs/utility/config_risposte.py
===============================
`/admin-bot config risposte` (CFG-013, CFG-014, CFG-033, CFG-011, #122): il server decide se le risposte del bot sono sempre
private, dopo quanti secondi si cancellano e (premium) i colori di successo ed errore degli embed.
La logica e il controllo del premium sono in `core/risposte_server.py` (un solo punto, D16).
Funzioni coperte: SPEC §20 (NF-05), catalogo #122
Dipende da: core/risposte_server.py, core/premium.py
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core import risposte_server as rs
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import testo_per
from core.premium import guild_has_premium_access

SOTTOGRUPPO_CONFIG = ("config", "Configurazione: canali, storico, ripristino ed esportazione")
PAROLA_BASE = "base"


def _colore_o_manca(testo: str | None):
    """None dall'utente = non si tocca; «base» = si toglie il colore scelto."""
    if testo is None:
        return rs.MANCA
    return None if testo.strip().lower() == PAROLA_BASE else testo


def _scrivi_colore(valore: int | None) -> str:
    return "—" if valore is None else f"#{valore:06X}"


class ConfigRisposteCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "admin-bot", nome="risposte", descrizione="Risposte del bot: private, cancellate dopo un po', colori.",
        sottogruppo=SOTTOGRUPPO_CONFIG,
    )
    @app_commands.describe(
        solo_private="Sì = tutte le risposte del bot in questo server sono private",
        cancella_dopo="Cancella le risposte pubbliche dopo questi secondi (0 = mai, massimo 600)",
        colore_successo="Colore dei messaggi di successo, es. #2ECC71 («base» = torna normale; premium)",
        colore_errore="Colore dei messaggi di errore, es. #E74C3C («base» = torna normale; premium)",
        canale_bot="Fuori da questo canale le risposte dei comandi diventano private",
        senza_canale_bot="Sì = togli il canale dei bot (le risposte tornano come prima)",
        comandi_canale_bot="Solo questi comandi: «fun, giochi» (non scritto = tutti, «tutti» = toglie l'elenco)",
    )
    async def risposte(
        self,
        interaction: discord.Interaction,
        solo_private: bool | None = None,
        cancella_dopo: app_commands.Range[int, 0, rs.MAX_CANCELLA_SECONDI] | None = None,
        colore_successo: app_commands.Range[str, 1, 7] | None = None,
        colore_errore: app_commands.Range[str, 1, 7] | None = None,
        canale_bot: discord.TextChannel | None = None,
        senza_canale_bot: bool | None = None,
        comandi_canale_bot: app_commands.Range[str, 1, 600] | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            return
        if canale_bot is not None and senza_canale_bot:
            await interaction.response.send_message(await testo_per(interaction, "risp_canale_non_valido"), ephemeral=True)
            return
        try:
            elenco = rs.MANCA if comandi_canale_bot is None else (
                [] if comandi_canale_bot.strip().lower() == "tutti" else rs.comandi_da_testo(comandi_canale_bot)
            )
        except rs.RispostaNonValida as exc:
            await interaction.response.send_message(await testo_per(interaction, str(exc)), ephemeral=True)
            return
        fornite = {
            "canale_bot": canale_bot.id if canale_bot is not None else (None if senza_canale_bot else rs.MANCA),
            "comandi_canale_bot": elenco,
            "effimere": rs.MANCA if solo_private is None else solo_private,
            "cancella_secondi": rs.MANCA if cancella_dopo is None else cancella_dopo,
            "colore_successo": _colore_o_manca(colore_successo),
            "colore_errore": _colore_o_manca(colore_errore),
        }
        if all(v is rs.MANCA for v in fornite.values()):
            attuali = await rs.leggi_risposte(guild.id)
            await interaction.response.send_message(
                await testo_per(
                    interaction, "risp_stato",
                    private=await testo_per(interaction, "risp_si" if attuali.effimere else "risp_no"),
                    secondi=attuali.cancella_secondi,
                    ok=_scrivi_colore(attuali.colore_successo), err=_scrivi_colore(attuali.colore_errore),
                ) + (
                    await testo_per(
                        interaction, "risp_stato_canale_bot", canale=f"<#{attuali.canale_bot}>",
                        comandi=", ".join(attuali.comandi_canale_bot) or "tutti",
                    ) if attuali.canale_bot is not None else ""
                ),
                ephemeral=True,
            )
            return
        premium = False
        if fornite["colore_successo"] is not rs.MANCA or fornite["colore_errore"] is not rs.MANCA:
            premium = await guild_has_premium_access(guild.id, rs.MODULO_COLORI, bot=self.bot)
        try:
            cambiati = await rs.imposta_risposte(guild.id, changed_by=interaction.user.id, premium=premium, **fornite)
        except rs.RispostaNonValida as exc:
            await interaction.response.send_message(await testo_per(interaction, str(exc)), ephemeral=True)
            return
        chiave = "risp_ok" if cambiati else "risp_niente"
        await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ConfigRisposteCog(bot))
