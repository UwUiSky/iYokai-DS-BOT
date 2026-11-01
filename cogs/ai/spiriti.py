"""
cogs/ai/spiriti.py
==================
`/utility ai spirito` (spirito Yokai che cresce con l'attività) e `/utility ai frammenti` (frammenti di lore da
collezionare, con la storia finale). Solo conteggi, nessun testo dei messaggi; parte solo su richiesta della persona.
Funzioni coperte: SPEC §25.71, §25.72 (AI-R-078, AI-R-079)
"""

from __future__ import annotations

from datetime import date, timedelta

import discord
from discord import app_commands
from discord.ext import commands

from cogs.ai._comune import NESSUNA_MENZIONE, SOTTO_AI, chiedi, registra_modulo_ai, taglia
from cogs.ai.dungeon import tema_del_server
from core import spiriti_logic as logica
from core.ai_servizio import RichiestaAI
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.repositories.activity_stats_repo import activity_stats_repo
from core.repositories.ai_gioco_repo import ai_gioco_repo
from core.repositories.ai_repo import ai_repo
from core.repositories.leveling_repo import leveling_repo

GIORNI = 30
TRAGUARDO_FINALE = "tutti_i_frammenti"


async def misure_di(guild_id: int, user_id: int, oggi: date | None = None) -> logica.Misure:
    """Messaggi, minuti in vocale, giorni attivi (ultimi 30 giorni) e saldo monete della persona."""
    dal = (oggi or date.today()) - timedelta(days=GIORNI)
    return logica.Misure(
        messaggi=await activity_stats_repo.member_total(guild_id, user_id, dal, "messages"),
        minuti_voce=await activity_stats_repo.member_total(guild_id, user_id, dal, "voice_minutes"),
        giorni_attivi=await ai_gioco_repo.giorni_attivi(guild_id, user_id, dal),
        monete=(await leveling_repo.get_totals(guild_id, user_id)).coins_total,
    )


def embed_spirito(nome_persona: str, tema: str, aff: dict[str, float], indice: int | None, scelto: bool) -> discord.Embed:
    spiriti = logica.spiriti_del_tema(tema)
    embed = discord.Embed(title=taglia(f"Lo spirito di {nome_persona}", 256), color=discord.Color.teal())
    if indice is None:
        embed.description = "Il tuo spirito non si è ancora svegliato. Scrivi, parla in vocale, torna ogni giorno: lo vedrai arrivare."
    else:
        nome, tratto = spiriti[indice]
        livello = logica.livello_legame(aff)
        embed.description = f"**{nome}**, {tratto}.\n{logica.titolo(nome, livello)}" + (" (scelto da te)" if scelto else "")
    for i, asse in enumerate(logica.ASSI):
        embed.add_field(name=f"{spiriti[i][0]} ({asse})", value=f"{logica.barra(aff[asse])} {round(aff[asse] * 100)}%", inline=False)
    embed.set_footer(text="Si conta l'attività degli ultimi 30 giorni. Solo numeri, mai i tuoi messaggi.")
    return embed


async def storia_finale(guild_id: int, user_id: int, tema: str, luogo: str) -> str:
    """I sei frammenti messi insieme: l'AI la scrive, altrimenti c'è il testo pronto."""
    risposta, _ = await chiedi(RichiestaAI(
        user_id=user_id, funzione="frammenti_finale", tipo="testo", guild_id=guild_id, fascia="bassa",
        testo=f"Luogo: {luogo}. Tema: {tema}", istruzioni=logica.ISTRUZIONI_FINALE, max_token=350,
    ))
    return taglia(risposta.testo, 1500) if risposta and risposta.testo.strip() else logica.storia_finale_pronta(tema, luogo)


class AiSpiritiCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo("utility", nome="spirito", descrizione="Il tuo spirito Yokai: cresce con la tua attività.", sottogruppo=SOTTO_AI)
    @app_commands.describe(scelta="Vuoi un altro spirito? Scegli cosa ti rappresenta (vuoto: lo decide la tua attività)")
    @app_commands.choices(scelta=[app_commands.Choice(name=a, value=a) for a in logica.ASSI] + [app_commands.Choice(name="automatico", value="auto")])
    async def spirito(self, interaction: discord.Interaction, scelta: str | None = None) -> None:
        await interaction.response.defer(ephemeral=True)
        g, u = interaction.guild_id, interaction.user.id
        if scelta is not None:
            await ai_gioco_repo.spirito_imposta(g, u, None if scelta == "auto" else scelta)
        aff = logica.affinita(await misure_di(g, u))
        scelto = await ai_gioco_repo.spirito_scelto(g, u)
        indice = logica.ASSI.index(scelto) if scelto in logica.ASSI else logica.spirito_dominante(aff)
        tema, _ = await tema_del_server(g)
        await interaction.followup.send(embed=embed_spirito(interaction.user.display_name, tema, aff, indice, scelto in logica.ASSI), ephemeral=True)

    @comando_di_gruppo("utility", nome="frammenti", descrizione="I frammenti di lore che hai raccolto.", sottogruppo=SOTTO_AI)
    async def frammenti(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        g, u = interaction.guild_id, interaction.user.id
        for f in logica.frammenti_da_sbloccare(await misure_di(g, u), set(await ai_gioco_repo.frammenti(g, u))):
            await ai_gioco_repo.frammento_sblocca(g, u, f.codice)
        avuti = set(await ai_gioco_repo.frammenti(g, u))
        tema, _ = await tema_del_server(g)
        luogo = interaction.guild.name
        righe = [
            (f"[x] {f.nome}: {logica.testo_frammento(f, luogo)}" if f.codice in avuti else f"[ ] {f.nome}: {f.come}")
            for f in logica.FRAMMENTI
        ]
        embed = discord.Embed(title=f"Frammenti: {len(avuti)} su {len(logica.FRAMMENTI)}", description=taglia("\n".join(righe), 3800), color=discord.Color.gold())
        if len(avuti) == len(logica.FRAMMENTI):
            await ai_repo.traguardo_assegna(u, TRAGUARDO_FINALE)
            embed.add_field(name=logica.titolo_raro(tema), value=await storia_finale(g, u, tema, luogo), inline=False)
        traguardi = await ai_repo.traguardi(u)
        if traguardi:
            embed.set_footer(text=taglia("Traguardi: " + ", ".join(traguardi), 200))
        await interaction.followup.send(embed=embed, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)


async def setup(bot: commands.Bot) -> None:
    registra_modulo_ai()
    await bot.add_cog(AiSpiritiCog(bot))
