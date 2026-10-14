"""
cogs/ai/helpdesk.py
===================
Assistente: risposta di `-chiedi` con l'AI (al massimo 3 comandi veri,
cliccabili, anche quando la richiesta è un'azione da fare), base di
conoscenza del server, risposta quando il bot viene menzionato con la
memoria corta della conversazione.
Funzioni coperte: SPEC §25.5, §25.24–§25.28, §25.31–§25.34 (AI-R-024..029, AI-R-032..036; catalogo AI-009, AI-011, AI-013)

Chiedere a parole di ESEGUIRE un comando (AI-013): un bot non può far partire
un comando slash al posto dell'utente né precompilarlo. Alternativa più vicina:
l'AI indica il comando cliccabile e i valori da inserire; la persona lo lancia
(e così restano i controlli di permesso di Discord).
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from cogs.ai._comune import NESSUNA_MENZIONE, chiedi, registra_modulo_ai, taglia
from core.ai_servizio import RichiestaAI, servizio_ai
from core.ai_testi_logic import ISTRUZIONI, comandi_citati, elenco_comandi_per_ai, riconosci_lingua
from core.repositories.ai_repo import ai_repo

logger = logging.getLogger("iyokai.ai_helpdesk")

MAX_CONOSCENZA_CARATTERI = 4000


async def conoscenza_del_server(guild_id: int | None) -> str:
    """Le voci della base di conoscenza, come testo per le istruzioni (entro un tetto)."""
    if guild_id is None:
        return ""
    voci = await ai_repo.conoscenza_elenco(guild_id)
    testo = "\n".join(f"- {v['titolo']}: {v['testo']}" for v in voci)
    return testo[:MAX_CONOSCENZA_CARATTERI]


async def risposta_ai_chiedi(interaction: discord.Interaction, domanda: str, comandi: list) -> tuple[str | None, list, str | None]:
    """
    (testo, comandi citati, None) se l'AI ha risposto; (None, [], testo locale) se no.
    `comandi`: i comandi che la persona può usare (oggetti con `percorso` e `descrizione`).
    """
    conoscenza = await conoscenza_del_server(interaction.guild_id)
    istruzioni = ISTRUZIONI["chiedi"] + "\n\nComandi:\n" + elenco_comandi_per_ai(comandi)
    if conoscenza:
        istruzioni += "\n\nInformazioni sul server:\n" + conoscenza
    risposta, locale = await chiedi(
        RichiestaAI(
            user_id=interaction.user.id, funzione="chiedi", tipo="chat", testo=domanda,
            guild_id=interaction.guild_id, channel_id=interaction.channel_id,
            istruzioni=istruzioni, lingua=riconosci_lingua(domanda),
        )
    )
    if risposta is None:
        return None, [], locale
    return risposta.testo, comandi_citati(risposta.testo, comandi), None


class AiHelpdeskCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot or self.bot.user is None:
            return
        if self.bot.user not in message.mentions or not message.content:
            return
        servizio = servizio_ai()
        if not servizio.configurato:
            return
        cfg = await ai_repo.get_config(message.guild.id)
        if not (cfg.attivo and cfg.menzione):
            return
        domanda = message.content.replace(f"<@{self.bot.user.id}>", "").replace(f"<@!{self.bot.user.id}>", "").strip()
        if not domanda:
            return
        async with message.channel.typing():
            risposta, locale = await chiedi(
                RichiestaAI(
                    user_id=message.author.id, funzione="menzione", tipo="chat", testo=domanda[:1500],
                    guild_id=message.guild.id, channel_id=message.channel.id, istruzioni=ISTRUZIONI["menzione"],
                    messaggi_utenti=True, lingua=riconosci_lingua(domanda),
                    conversazione=(message.guild.id, message.channel.id, message.author.id),
                )
            )
        testo = risposta.testo if risposta else locale
        try:
            await message.reply(taglia(testo, 2000), allowed_mentions=NESSUNA_MENZIONE, mention_author=False)
        except discord.HTTPException:
            logger.info("Risposta alla menzione non inviata nel canale %s.", message.channel.id)


async def setup(bot: commands.Bot) -> None:
    registra_modulo_ai()
    await bot.add_cog(AiHelpdeskCog(bot))
