"""
cogs/ai/ticket_ai.py
====================
`/ticket assistente` dentro un ticket. Per chi ha aperto il ticket: risposta
dell'assistente dalla base di conoscenza del server, visibile a tutti nel
ticket, segnata come automatica. Per lo staff: bozza di risposta e
smistamento (categoria, urgenza, ruolo da chiamare), visibili solo a lui:
la risposta ufficiale la manda una persona.
Funzioni coperte: SPEC §25.65–§25.68 (AI-R-071..074; catalogo AI-019)

Il bottone "Chiedi all'assistente" sta nel messaggio di apertura (vista persistente
di questo file) e fa la stessa cosa del comando. Con la prima risposta automatica accesa per
il pannello (`/ai staff prima-risposta`), l'AI risponde da sola una volta sola per ticket.
Funzioni coperte anche: SPEC §25.66 (AI-R-072)
"""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.ai._comune import MODULO_AI, NESSUNA_MENZIONE, chiedi, embed_risposta, registra_modulo_ai, richiesta_da, taglia, testo_canale
from cogs.ai.helpdesk import conoscenza_del_server
from cogs.ai.staff import SOTTO_STAFF
from cogs.tickets.risposte import completa_pannelli
from core.ai_servizio import RichiestaAI
from core.ai_testi_logic import ISTRUZIONI, estrai_json, riconosci_lingua
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.premium import requires_module
from core.repositories.ai_ticket_repo import ai_ticket_repo
from core.repositories.ticket_form_repo import ticket_form_repo
from core.repositories.ticket_repo import ticket_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.ai_ticket")

MESSAGGI_LETTI = 30


def testo_smistamento(dati: dict | None) -> str:
    if not dati:
        return "Smistamento non riuscito."
    return (
        f"Categoria: {taglia(str(dati.get('categoria') or '-'), 80)} · "
        f"urgenza {taglia(str(dati.get('urgenza') or '?'), 5)}/5 · "
        f"chiamare: {taglia(str(dati.get('ruolo') or 'staff'), 80)}"
    )


async def rispondi_assistente(interaction: discord.Interaction) -> None:
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



class AssistenteTicketView(BaseView):
    """Bottone persistente «Chiedi all'assistente» nel messaggio di apertura del ticket (AI-R-071)."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Chiedi all'assistente", style=discord.ButtonStyle.secondary, custom_id="aitk:chiedi")
    async def chiedi_assistente(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await rispondi_assistente(interaction)


class AiTicketCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        await super().cog_load()
        self.bot.add_view(AssistenteTicketView())

    # ---------------------------------------------------------------- prima risposta automatica (AI-R-072)
    async def prima_risposta(self, channel, ticket, contenuto: str) -> bool:
        """Una sola risposta automatica per ticket, solo con il pannello acceso. Lo staff la vede nel ticket."""
        if ticket.panel_id is None or not await ai_ticket_repo.prima_risposta_attiva(ticket.guild_id, ticket.panel_id):
            return False
        if not contenuto.strip() or not await ai_ticket_repo.prenota_risposta(channel.id, ticket.guild_id):
            return False
        conoscenza = await conoscenza_del_server(ticket.guild_id)
        base = f"\n\nBase di conoscenza:\n{conoscenza}" if conoscenza else "\n\nBase di conoscenza: vuota."
        risposta, _ = await chiedi(RichiestaAI(
            user_id=ticket.user_id, funzione="ticket_prima_risposta", tipo="testo", testo=contenuto[:3000], guild_id=ticket.guild_id,
            channel_id=channel.id, fascia="media", istruzioni=ISTRUZIONI["ticket_utente"] + base, messaggi_utenti=True,
            lingua=riconosci_lingua(contenuto), riusa=False, conta_utente=False,
        ))
        if risposta is None or not risposta.testo.strip():
            await ai_ticket_repo.rilascia_risposta(channel.id)  # AI ferma: si riprova al prossimo messaggio
            return False
        embed = embed_risposta("Assistente", risposta.testo)
        embed.set_footer(text="Risposta automatica: lo staff la controllerà e ti risponderà di persona")
        try:
            await channel.send(embed=embed, allowed_mentions=NESSUNA_MENZIONE)
        except discord.HTTPException:
            await ai_ticket_repo.rilascia_risposta(channel.id)
            return False
        return True

    async def dopo_apertura(self, channel, ticket_user_id: int, guild_id: int, panel_id: int | None, contenuto: str) -> None:
        """Dall'apertura del ticket: se ci sono già parole della persona (motivo, risposte del modulo) si risponde subito."""
        ticket = await ticket_repo.get_ticket_by_channel(channel.id)
        if ticket is not None and contenuto.strip():
            await self.prima_risposta(channel, ticket, contenuto)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Il primo messaggio di chi ha aperto il ticket, se all'apertura non c'era niente da leggere."""
        if message.guild is None or message.author.bot or not message.content:
            return
        try:
            ticket = await ticket_repo.get_ticket_by_channel(message.channel.id)
            if ticket is None or ticket.status != "open" or message.author.id != ticket.user_id or ticket.panel_id is None:
                return
            if not await ai_ticket_repo.prima_risposta_attiva(ticket.guild_id, ticket.panel_id):
                return
            await asyncio.sleep(2)  # se la risposta standard dello staff scatta, l'AI non si aggiunge
            ticket = await ticket_repo.get_ticket_by_channel(message.channel.id)
            if ticket is None or ticket.standard_reply_id is not None or ticket.first_response_at is not None:
                return
            await self.prima_risposta(message.channel, ticket, message.content)
        except Exception:  # noqa: BLE001 - un errore dell'AI non ferma mai un ticket
            logger.warning("Prima risposta automatica non riuscita.", exc_info=True)

    @comando_di_gruppo("ai", nome="prima-risposta", descrizione="Accende o spegne la prima risposta automatica dell'AI in un pannello ticket.", sottogruppo=SOTTO_STAFF)
    @app_commands.describe(pannello="Il pannello dei ticket", attiva="Sì: l'AI risponde da sola una volta, lo staff la vede")
    @app_commands.autocomplete(pannello=completa_pannelli)
    async def prima_risposta_cmd(self, interaction: discord.Interaction, pannello: app_commands.Range[str, 1, 50], attiva: bool) -> None:
        panel = await ticket_form_repo.pannello_per_nome(interaction.guild_id, pannello.strip())
        if panel is None:
            await interaction.response.send_message(f"Nessun pannello chiamato **{pannello.strip()[:100]}**.", ephemeral=True)
            return
        await ai_ticket_repo.imposta_prima_risposta(interaction.guild_id, panel.id, attiva)
        await interaction.response.send_message(
            f"Prima risposta automatica {'accesa' if attiva else 'spenta'} per **{panel.name[:100]}**. Serve l'AI accesa nel server.", ephemeral=True,
        )

    @comando_di_gruppo("ticket", nome="assistente", descrizione="Risposta dell'assistente AI (per lo staff: bozza e smistamento).")
    @requires_module(MODULO_AI)
    async def assistente(self, interaction: discord.Interaction) -> None:
        await rispondi_assistente(interaction)


async def setup(bot: commands.Bot) -> None:
    registra_modulo_ai()
    await bot.add_cog(AiTicketCog(bot))
