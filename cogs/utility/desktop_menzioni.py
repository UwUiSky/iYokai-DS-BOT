"""
cogs/utility/desktop_menzioni.py
================================
Avvisi per iYokai Desktop (SPEC D.5, D.6): quando qualcuno menziona una persona, le risponde o scrive una sua
parola chiave, il bot mette l'avviso in coda per il programma. Solo per chi ha acceso gli avvisi (spenti di base)
e solo se la persona è nel server e vede il canale. Si salva un testo breve, per 90 giorni.
Funzioni coperte: SPEC D.5, D.6 (#108)
Dipende da: core/desktop_logic.py, core/repositories/desktop_repo.py
"""

from __future__ import annotations

import logging
import time

import discord
from discord.ext import commands

from core.desktop_logic import chi_avvisare, testo_breve
from core.repositories.desktop_repo import desktop_repo

logger = logging.getLogger("iyokai.desktop")

DURATA_ELENCO = 60.0  # secondi: la lista di chi ha acceso gli avvisi si rilegge una volta al minuto


class DesktopMenzioniCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._attivi: dict[int, list[str]] = {}
        self._letto_alle = float("-inf")

    async def _elenco(self) -> dict[int, list[str]]:
        if time.monotonic() - self._letto_alle > DURATA_ELENCO:
            self._attivi = await desktop_repo.utenti_con_avvisi()
            self._letto_alle = time.monotonic()
        return self._attivi

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        try:
            attivi = await self._elenco()
            if not attivi:
                return
            riferimento = message.reference.resolved if message.reference else None
            risposta_a = riferimento.author.id if isinstance(riferimento, discord.Message) else None

            def vede(utente_id: int) -> bool:
                membro = message.guild.get_member(utente_id)
                return membro is not None and message.channel.permissions_for(membro).view_channel

            avvisi = chi_avvisare(
                autore_id=message.author.id, contenuto=message.content,
                menzionati=[m.id for m in message.mentions], risposta_a=risposta_a, attivi=attivi, vede=vede,
            )
            for utente_id, tipo in avvisi.items():
                await desktop_repo.aggiungi_evento(
                    utente_id, tipo, guild_id=message.guild.id, channel_id=message.channel.id, message_id=message.id,
                    autore_id=message.author.id, autore_nome=message.author.display_name[:40],
                    canale_nome=str(getattr(message.channel, "name", ""))[:60], testo=testo_breve(message.content),
                )
        except Exception:  # noqa: BLE001 - un avviso perso non deve fermare gli altri ascoltatori
            logger.warning("Avviso per iYokai Desktop non registrato.", exc_info=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DesktopMenzioniCog(bot))
