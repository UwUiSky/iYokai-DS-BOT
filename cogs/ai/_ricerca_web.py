"""
cogs/ai/_ricerca_web.py
=======================
Risposta con ricerca sul web (opzione `cerca` di `-chiedi`): cerca, l'AI riassume con le fonti; con l'AI ferma restano
i risultati con i link. Spenta finché l'owner non configura il servizio di ricerca.
Funzioni coperte: SPEC §25.45 (AI-R-048)
"""

from __future__ import annotations

import discord

from cogs.ai._comune import NESSUNA_MENZIONE, chiedi, taglia
from core import ricerca_web_logic as logica
from core.ai_servizio import AINonDisponibile, RichiestaAI, servizio_ai
from core.ricerca_web import ricerca_web

NON_ATTIVA = "La ricerca sul web non è attiva su questo bot: la deve configurare il proprietario."
NIENTE = "Non ho trovato risultati sicuri, oppure la ricerca ha finito la quota di oggi. Riprova più tardi."


async def risposta_con_ricerca(interaction: discord.Interaction, domanda: str, guild_id: int | None) -> None:
    """Risponde alla persona (ephemeral). Presuppone che l'interazione non abbia ancora risposto."""
    servizio = ricerca_web()
    if not servizio.attiva:
        await interaction.response.send_message(NON_ATTIVA, ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    risultati = await servizio.cerca(domanda)
    if not risultati:
        await interaction.followup.send(NIENTE, ephemeral=True)
        return
    testo = None
    try:
        await servizio_ai().controlla_accesso(guild_id, interaction.channel_id)
        risposta, _ = await chiedi(RichiestaAI(
            user_id=interaction.user.id, funzione="ricerca_web", tipo="chat", guild_id=guild_id, channel_id=interaction.channel_id,
            testo=f"Domanda: {domanda}\n\nRisultati:\n{logica.testo_per_ai(risultati)}",
            fascia="bassa", istruzioni=logica.ISTRUZIONI, messaggi_utenti=True, riusa=False, max_token=500,
        ))
        testo = risposta.testo.strip() if risposta else None
    except AINonDisponibile:
        testo = None
    embed = discord.Embed(
        title="Ricerca sul web", color=discord.Color.blurple(),
        description=taglia(testo or "L'AI è ferma: ecco i risultati trovati.", 3500),
    )
    embed.add_field(name="Fonti", value=taglia(logica.elenco_fonti(risultati), 1000), inline=False)
    embed.set_footer(text="Riassunto dell'AI su pagine trovate sul web: controlla le fonti." if testo else "Risultati della ricerca, senza riassunto.")
    await interaction.followup.send(embed=embed, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)
