"""
cogs/ai/ticket_ai.py
====================
`/ticket assistente` dentro un ticket. Per chi ha aperto il ticket: risposta
dell'assistente dalla base di conoscenza del server, visibile a tutti nel
ticket, segnata come automatica. Per lo staff: bozza di risposta e
smistamento (categoria, urgenza, ruolo da chiamare), visibili solo a lui:
la risposta ufficiale la manda una persona.
Funzioni coperte: SPEC §25.65–§25.68 (AI-R-071..074; catalogo AI-019)

Il bottone "Chiedi all'assistente" nel messaggio di apertura del ticket è dei
file dei ticket: qui c'è il comando, che fa la stessa cosa.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from cogs.ai._comune import MODULO_AI, NESSUNA_MENZIONE, chiedi, embed_risposta, registra_modulo_ai, richiesta_da, taglia, testo_canale
from cogs.ai.helpdesk import conoscenza_del_server
from core.ai_testi_logic import ISTRUZIONI, estrai_json, riconosci_lingua
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.premium import requires_module
from core.repositories.ticket_repo import ticket_repo

MESSAGGI_LETTI = 30


def testo_smistamento(dati: dict | None) -> str:
    if not dati:
        return "Smistamento non riuscito."
    return (
        f"Categoria: {taglia(str(dati.get('categoria') or '-'), 80)} · "
        f"urgenza {taglia(str(dati.get('urgenza') or '?'), 5)}/5 · "
        f"chiamare: {taglia(str(dati.get('ruolo') or 'staff'), 80)}"
    )


class AiTicketCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo("ticket", nome="assistente", descrizione="Risposta dell'assistente AI (per lo staff: bozza e smistamento).")
    @requires_module(MODULO_AI)
    async def assistente(self, interaction: discord.Interaction) -> None:
        ticket = await ticket_repo.get_ticket_by_channel(interaction.channel_id)
        if ticket is None or ticket.status != "open":
            await interaction.response.send_message("Questo comando si usa dentro un ticket aperto.", ephemeral=True)
            return
        staff = interaction.user.id != ticket.user_id
        await interaction.response.defer(ephemeral=staff)
        conversazione = await testo_canale(interaction.channel, MESSAGGI_LETTI, max_caratteri=6000)
        if not conversazione:
            await interaction.followup.send("Nel ticket non c'è ancora testo da leggere.", ephemeral=True)
            return
        conoscenza = await conoscenza_del_server(interaction.guild_id)
        base = f"\n\nBase di conoscenza:\n{conoscenza}" if conoscenza else "\n\nBase di conoscenza: vuota."
        lingua = riconosci_lingua(conversazione)
        if not staff:
            risposta, locale = await chiedi(richiesta_da(
                interaction, "ticket_utente", "testo", conversazione, fascia="media",
                istruzioni=ISTRUZIONI["ticket_utente"] + base, messaggi_utenti=True, lingua=lingua, riusa=False,
            ))
            testo = risposta.testo if risposta else f"{locale}\nLo staff ti risponderà a breve."
            embed = embed_risposta("Assistente", testo)
            embed.set_footer(text="Risposta automatica: lo staff la controllerà")
            await interaction.followup.send(embed=embed, allowed_mentions=NESSUNA_MENZIONE)
            return
        bozza, locale = await chiedi(richiesta_da(
            interaction, "ticket_bozza", "testo", conversazione, fascia="media",
            istruzioni=ISTRUZIONI["ticket_bozza"] + base, messaggi_utenti=True, lingua=lingua, riusa=False,
        ))
        if bozza is None:
            await interaction.followup.send(locale, ephemeral=True)
            return
        smista, _ = await chiedi(richiesta_da(
            interaction, "ticket_smista", "giudizio", conversazione, fascia="media",
            istruzioni=ISTRUZIONI["ticket_smista"], messaggi_utenti=True, riusa=False,
        ))
        embed = embed_risposta("Bozza di risposta", bozza.testo)
        embed.add_field(name="Smistamento", value=testo_smistamento(estrai_json(smista.testo) if smista else None), inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    registra_modulo_ai()
    await bot.add_cog(AiTicketCog(bot))
