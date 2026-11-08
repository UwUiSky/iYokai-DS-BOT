"""
cogs/automod/eventi.py
======================
Ascolta gli eventi che non sono messaggi e li passa alle regole personali AutoMod (core/automod_eventi.py):
spostamenti tra vocali (AMD-009), thread creati (010), nome e soprannome (017), stato personalizzato (018, solo
con l'interruttore acceso e l'intent Presenze), ingresso, uscita, ruolo dato o tolto e caso di moderazione (075).
Funzioni coperte: SPEC §6 (AMD-009, 010, 017, 018, 075), D63
Dipende da: core/automod_eventi.py, core/caso_eventi.py
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from core import automod_eventi as eventi
from core import caso_eventi
from core.automod_eventi_logic import DatiEvento

logger = logging.getLogger("iyokai.automod.eventi")


def testo_dello_stato(attivita) -> str:
    """Il testo dello stato personalizzato (e dei nomi delle attività), unito in una riga."""
    parti = []
    for a in attivita or ():
        if isinstance(a, discord.CustomActivity):
            parti.append(str(a.name or ""))
        else:
            parti.append(str(getattr(a, "name", "") or ""))
    return " ".join(p for p in parti if p)[:300]


class EventiAutomodCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        caso_eventi.registra(self._caso)

    async def cog_unload(self) -> None:
        caso_eventi.rimuovi(self._caso)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if before.channel is not None and after.channel is not None and before.channel.id != after.channel.id:
            await eventi.elabora(self.bot, member.guild, member, "vocale", canale=after.channel)

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        autore = thread.guild.get_member(thread.owner_id) if thread.owner_id else None
        if autore is not None:
            await eventi.elabora(self.bot, thread.guild, autore, "thread", canale=thread.parent)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await eventi.elabora(self.bot, member.guild, member, "ingresso")
        await eventi.elabora(self.bot, member.guild, member, "nome", DatiEvento(testo=_nomi(member)))

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        await eventi.elabora(self.bot, member.guild, member, "uscita")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.nick != after.nick and after.nick:
            await eventi.elabora(self.bot, after.guild, after, "nome", DatiEvento(testo=_nomi(after)))
        prima, dopo = {r.id for r in before.roles}, {r.id for r in after.roles}
        for ruolo_id in sorted(dopo - prima):
            await eventi.elabora(self.bot, after.guild, after, "ruolo_dato", DatiEvento(ruolo_id=ruolo_id))
        for ruolo_id in sorted(prima - dopo):
            await eventi.elabora(self.bot, after.guild, after, "ruolo_tolto", DatiEvento(ruolo_id=ruolo_id))

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User) -> None:
        if before.name == after.name and before.global_name == after.global_name:
            return
        for guild in self.bot.guilds:
            membro = guild.get_member(after.id)
            if membro is not None:
                await eventi.elabora(self.bot, guild, membro, "nome", DatiEvento(testo=_nomi(membro)))

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member) -> None:
        if not eventi.stato_attivo():  # AMD-018: spento di base, e senza l'intent Presenze Discord non manda nulla
            return
        testo = testo_dello_stato(after.activities)
        if testo and testo != testo_dello_stato(before.activities):
            await eventi.elabora(self.bot, after.guild, after, "stato", DatiEvento(testo=testo))

    async def _caso(self, guild_id: int, case_number: int, user_id: int, moderator_id: int, action_type: str, origine: str,
                    motivo: str | None) -> None:
        if origine == "automod":
            return  # un caso nato da una regola non fa scattare un'altra regola: niente giri a vuoto
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        await eventi.elabora(self.bot, guild, guild.get_member(user_id), "caso",
                             DatiEvento(testo=(motivo or "")[:200], tipo_caso=(action_type or "").lower()), user_id=user_id)


def _nomi(membro: discord.Member) -> str:
    """Tutti i nomi che si vedono: soprannome nel server, nome visualizzato e nome utente."""
    parti = [getattr(membro, "nick", None), getattr(membro, "global_name", None), getattr(membro, "name", None)]
    return " ".join(dict.fromkeys(p for p in parti if p))[:300]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EventiAutomodCog(bot))
