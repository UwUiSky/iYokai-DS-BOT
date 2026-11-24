"""
cogs/utility/cerca_ai.py
========================
`/utility-web cerca`: «cerca qualsiasi cosa» (risposte rapide, web, video) con i servizi AI che sanno cercare sul web,
scelti dallo snodo AI con il lavoro «ricerca». Link controllati, testo troncato, menzioni spente, pausa e tetto
al giorno per persona. Rispetta consenso, privacy e interruttori AI del server; senza un servizio adatto lo dice.
Funzioni coperte: SPEC §25 (UTL-216; D124, D19, D55)
Dipende da: core/cerca_ai_logic.py, core/ai_servizio.py, core/controllo_link.py
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core import cerca_ai_logic as logica
from core.ai_servizio import AINonDisponibile, RichiestaAI, servizio_ai
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import lingua_interazione, t

NESSUNA_MENZIONE = discord.AllowedMentions.none()
FUNZIONE = "ricerca_web"  # stesso interruttore della ricerca dell'assistente (AI-017)


class CercaAICog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.limite = logica.LimitePersona()

    @comando_di_gruppo("utility-web", nome="cerca", descrizione="Cerca qualsiasi cosa: una risposta rapida, il web o dei video.")
    @app_commands.describe(domanda="Cosa cercare", tipo="Che tipo di risultato vuoi")
    @app_commands.choices(
        tipo=[
            app_commands.Choice(name="Risposta rapida", value="rapida"),
            app_commands.Choice(name="Web", value="web"),
            app_commands.Choice(name="Video", value="video"),
        ]
    )
    async def cerca(
        self, interaction: discord.Interaction, domanda: app_commands.Range[str, 2, logica.MAX_DOMANDA],
        tipo: app_commands.Choice[str] | None = None,
    ) -> None:
        lingua = await lingua_interazione(interaction)
        if interaction.guild is None:
            await interaction.response.send_message(t("cerca_ai_solo_server", lingua), ephemeral=True)
            return
        testo_domanda = logica.pulisci_domanda(domanda)
        if len(testo_domanda) < 2:
            await interaction.response.send_message(t("cerca_ai_domanda_vuota", lingua), ephemeral=True)
            return
        ammessa, attesa = self.limite.prova(interaction.user.id)
        if not ammessa:
            await interaction.response.send_message(t("cerca_ai_pausa", lingua, secondi=attesa), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            risposta = await servizio_ai().richiedi(RichiestaAI(
                user_id=interaction.user.id, funzione=FUNZIONE, tipo="ricerca", testo=testo_domanda,
                guild_id=interaction.guild.id, channel_id=interaction.channel_id, fascia="bassa",
                istruzioni=logica.istruzioni(tipo.value if tipo else "rapida"), messaggi_utenti=True,
                riusa=False, max_token=700,
            ))
        except AINonDisponibile as e:
            self.limite.restituisci(interaction.user.id)
            testo = t("cerca_ai_nessun_servizio", lingua) if e.motivo == "non_configurata" else e.testo
            await interaction.followup.send(testo[:2000], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)
            return
        pulito, tolti = await logica.pulisci_risposta(risposta.testo)
        if not pulito:
            await interaction.followup.send(t("cerca_ai_niente", lingua), ephemeral=True)
            return
        embed = discord.Embed(title=t("cerca_ai_titolo", lingua), description=pulito, color=discord.Color.blurple())
        embed.set_footer(text=t("cerca_ai_avviso_tolti" if tolti else "cerca_ai_avviso", lingua, n=tolti)[:2000])
        await interaction.followup.send(embed=embed, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CercaAICog(bot))
