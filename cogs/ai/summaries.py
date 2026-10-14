"""
cogs/ai/summaries.py
====================
`/utility ai riassumi` (ultimi messaggi di un canale), `/utility ai spiega`
(un messaggio dato con il suo link), `/utility ai stile` (un messaggio nuovo
scritto come scrivi tu, dai TUOI messaggi del canale).
Funzioni coperte: SPEC §25.6, §25.36, §25.88 (AI-R-043, AI-R-038, AI-R-095; catalogo AI-024)

Senza AI: riassumi mostra i numeri del canale (messaggi, persone, le più attive).
"Nello stile di un utente" (AI-024) usa solo i messaggi di chi lo chiede: copiare
lo stile di un'altra persona senza il suo consenso non si fa (privacy, D19).
"""

from __future__ import annotations

import re
from collections import Counter

import discord
from discord import app_commands
from discord.ext import commands

from cogs.ai._comune import (
    MODULO_AI, NESSUNA_MENZIONE, SOTTO_AI, chiedi, embed_risposta, registra_modulo_ai, richiesta_da, testo_canale,
)
from core.ai_testi_logic import ISTRUZIONI, riconosci_lingua
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.premium import requires_module

_LINK = re.compile(r"discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)")


def numeri_del_canale(autori: list[str]) -> str:
    """Il riepilogo senza AI: quanti messaggi, quante persone, le 5 più attive."""
    if not autori:
        return "Nessun messaggio da riassumere."
    conta = Counter(autori)
    piu = ", ".join(f"{nome} ({n})" for nome, n in conta.most_common(5))
    return f"{len(autori)} messaggi da {len(conta)} persone. Più attive: {piu}."


class AiRiassuntiCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo("utility", nome="riassumi", descrizione="Riassunto degli ultimi messaggi di un canale.", sottogruppo=SOTTO_AI)
    @app_commands.describe(canale="Il canale (vuoto: questo)", messaggi="Quanti messaggi leggere")
    @requires_module(MODULO_AI)
    async def riassumi(
        self, interaction: discord.Interaction, canale: discord.TextChannel | None = None,
        messaggi: app_commands.Range[int, 10, 200] = 50,
    ) -> None:
        canale = canale or interaction.channel
        permessi = canale.permissions_for(interaction.user)
        if not (permessi.view_channel and permessi.read_message_history):
            await interaction.response.send_message("Non puoi leggere quel canale.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            testo = await testo_canale(canale, messaggi)
            autori = [m.author.display_name async for m in canale.history(limit=messaggi) if not m.author.bot]
        except discord.Forbidden:
            await interaction.followup.send("Non riesco a leggere quel canale.", ephemeral=True)
            return
        if not testo:
            await interaction.followup.send(numeri_del_canale(autori), ephemeral=True)
            return
        risposta, locale = await chiedi(richiesta_da(
            interaction, "riassumi", "testo", testo, fascia="media", istruzioni=ISTRUZIONI["riassumi"],
            messaggi_utenti=True, lingua=riconosci_lingua(testo),
        ))
        if risposta is None:
            await interaction.followup.send(f"{locale}\n\n{numeri_del_canale(autori)}", ephemeral=True)
            return
        await interaction.followup.send(
            embed=embed_risposta(f"Riassunto di #{canale.name}", risposta.testo, da_cache=risposta.da_cache),
            ephemeral=True,
        )

    @comando_di_gruppo("utility", nome="spiega", descrizione="Spiega in parole semplici un messaggio (dal suo link).", sottogruppo=SOTTO_AI)
    @app_commands.describe(link="Link del messaggio (tasto destro → Copia link)")
    @requires_module(MODULO_AI)
    async def spiega(self, interaction: discord.Interaction, link: app_commands.Range[str, 20, 200]) -> None:
        trovato = _LINK.search(link)
        if trovato is None or int(trovato.group(1)) != interaction.guild_id:
            await interaction.response.send_message("Serve il link di un messaggio di questo server.", ephemeral=True)
            return
        canale = interaction.guild.get_channel_or_thread(int(trovato.group(2)))
        if canale is None or not canale.permissions_for(interaction.user).read_message_history:
            await interaction.response.send_message("Non puoi leggere quel messaggio.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            messaggio = await canale.fetch_message(int(trovato.group(3)))
        except discord.HTTPException:
            await interaction.followup.send("Messaggio non trovato.", ephemeral=True)
            return
        if not messaggio.content:
            await interaction.followup.send("Il messaggio non ha testo da spiegare.", ephemeral=True)
            return
        risposta, locale = await chiedi(richiesta_da(
            interaction, "spiega", "testo", messaggio.content[:3000], istruzioni=ISTRUZIONI["spiega"],
            messaggi_utenti=True, lingua=riconosci_lingua(messaggio.content),
        ))
        if risposta is None:
            await interaction.followup.send(locale, ephemeral=True)
            return
        await interaction.followup.send(embed=embed_risposta("Spiegazione", risposta.testo, da_cache=risposta.da_cache), ephemeral=True)

    @comando_di_gruppo("utility", nome="stile", descrizione="Un messaggio nuovo scritto come scrivi tu.", sottogruppo=SOTTO_AI)
    @app_commands.describe(argomento="Di cosa deve parlare il messaggio")
    @requires_module(MODULO_AI)
    async def stile(self, interaction: discord.Interaction, argomento: app_commands.Range[str, 3, 200]) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            esempi = await testo_canale(interaction.channel, 200, autore_id=interaction.user.id, max_caratteri=3000)
        except discord.Forbidden:
            esempi = ""
        if not esempi:
            await interaction.followup.send("Non trovo tuoi messaggi recenti in questo canale da usare come esempio.", ephemeral=True)
            return
        risposta, locale = await chiedi(richiesta_da(
            interaction, "stile", "testo", f"Argomento: {argomento}\n\nEsempi:\n{esempi}",
            istruzioni=ISTRUZIONI["stile"], messaggi_utenti=True, riusa=False,
        ))
        await interaction.followup.send(
            risposta.testo[:2000] if risposta else locale, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE
        )


async def setup(bot: commands.Bot) -> None:
    registra_modulo_ai()
    await bot.add_cog(AiRiassuntiCog(bot))
