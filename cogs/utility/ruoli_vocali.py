"""
cogs/utility/ruoli_vocali.py
============================
Ruoli vocali: chi entra in un canale vocale riceve un ruolo, chi esce lo perde (catalogo #123: RUO-044).
Comando `/admin-ruoli vocale`. Dopo un riavvio il bot rimette a posto i ruoli (pochi alla volta).
La logica è in core/ruoli_vocali_logic.py.
Funzioni coperte: SPEC §14 (RUO-044)
"""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import testo_per
from core.repositories.voice_role_repo import voice_role_repo
from core.role_safety import check_role_assignable
from core.ruoli_vocali_logic import (
    MAX_CORREZIONI_AVVIO,
    MAX_RUOLI_VOCALI,
    PAUSA_CORREZIONI_SECONDI,
    cambio_ruoli,
    correzioni,
)

logger = logging.getLogger("iyokai.ruoli_vocali")

NESSUNA_MENZIONE = discord.AllowedMentions.none()
SCELTE_AZIONE = [app_commands.Choice(name=n, value=n) for n in ("aggiungi", "togli", "elenco")]


class RuoliVocaliCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._regole: dict[int, dict[int, int]] = {}  # copia in memoria, si riempie solo dopo una lettura riuscita
        self._pulito = False
        self._compito: asyncio.Task | None = None

    async def cog_unload(self) -> None:
        if self._compito is not None:
            self._compito.cancel()
        await super().cog_unload()

    async def _regole_del_server(self, guild_id: int) -> dict[int, int]:
        if guild_id not in self._regole:
            self._regole[guild_id] = await voice_role_repo.rules(guild_id)
        return self._regole[guild_id]

    # ------------------------------------------------------------ eventi
    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, prima: discord.VoiceState, dopo: discord.VoiceState
    ) -> None:
        if member.bot or (prima.channel and prima.channel.id) == (dopo.channel and dopo.channel.id):
            return
        regole = await self._regole_del_server(member.guild.id)
        if not regole:
            return
        da_dare, da_togliere = cambio_ruoli(
            regole, prima.channel.id if prima.channel else None, dopo.channel.id if dopo.channel else None
        )
        await self._applica(member, da_dare, da_togliere)

    async def _applica(self, member: discord.Member, da_dare: set[int], da_togliere: set[int]) -> None:
        """Dà solo i ruoli che il bot può dare (controllo a ogni volta: il ruolo può essere cambiato); toglierli si può sempre."""
        guild = member.guild
        ruoli_dare = []
        for rid in da_dare:
            ruolo = guild.get_role(rid)
            if ruolo is None:
                continue
            if check_role_assignable(guild, ruolo, guild.me, self_service=True) is not None:
                logger.warning("Ruolo vocale %s non assegnabile nel server %s.", rid, guild.id)
                continue
            ruoli_dare.append(ruolo)
        ruoli_togliere = [r for r in (guild.get_role(rid) for rid in da_togliere) if r is not None]
        try:
            if ruoli_dare:
                await member.add_roles(*ruoli_dare, reason="Ruolo vocale")
            if ruoli_togliere:
                await member.remove_roles(*ruoli_togliere, reason="Ruolo vocale")
        except discord.HTTPException as errore:
            logger.warning("Ruolo vocale non aggiornato per %s nel server %s: %s", member.id, guild.id, errore)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Una volta sola dopo l'avvio: chi era già nei vocali o chi ha un ruolo di troppo si rimette a posto."""
        if self._pulito:
            return
        self._pulito = True
        self._compito = asyncio.create_task(self._pulisci_tutti())

    async def _pulisci_tutti(self) -> None:
        try:
            for guild_id in await voice_role_repo.guild_ids():
                guild = self.bot.get_guild(guild_id)
                if guild is not None:
                    await self.sincronizza(guild)
        except Exception:
            logger.exception("Pulizia dei ruoli vocali non riuscita.")

    async def sincronizza(self, guild: discord.Guild) -> int:
        """Rimette a posto i ruoli vocali di un server; torna quante correzioni ha fatto (al massimo MAX_CORREZIONI_AVVIO)."""
        regole = await self._regole_del_server(guild.id)
        nei_canali: dict[int, set[int]] = {}
        for canale_id in regole:
            canale = guild.get_channel(canale_id)
            if canale is not None and hasattr(canale, "members"):
                nei_canali[canale_id] = {m.id for m in canale.members if not m.bot}
        coi_ruoli: dict[int, set[int]] = {}
        for ruolo_id in set(regole.values()):
            ruolo = guild.get_role(ruolo_id)
            if ruolo is not None:
                coi_ruoli[ruolo_id] = {m.id for m in ruolo.members if not m.bot}
        dare, togliere = correzioni(regole, nei_canali, coi_ruoli)
        fatte = 0
        for membro_id, ruolo_id in (dare + togliere)[:MAX_CORREZIONI_AVVIO]:
            membro = guild.get_member(membro_id)
            if membro is None:
                continue
            await self._applica(
                membro, {ruolo_id} if (membro_id, ruolo_id) in dare else set(),
                {ruolo_id} if (membro_id, ruolo_id) in togliere else set(),
            )
            fatte += 1
            await asyncio.sleep(PAUSA_CORREZIONI_SECONDI)
        return fatte

    # ------------------------------------------------------------ comando
    @comando_di_gruppo("admin-ruoli", nome="vocale", descrizione="Un ruolo per chi è in un canale vocale.")
    @app_commands.describe(
        azione="Aggiungere, togliere o vedere i ruoli vocali",
        canale="Il canale vocale",
        ruolo="Il ruolo da dare a chi è nel canale (serve per aggiungere)",
    )
    @app_commands.choices(azione=SCELTE_AZIONE)
    async def vocale(
        self,
        interaction: discord.Interaction,
        azione: str,
        canale: discord.VoiceChannel | discord.StageChannel | None = None,
        ruolo: discord.Role | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        if azione == "elenco":
            regole = await voice_role_repo.rules(guild.id)
            righe = [f"<#{c}> → <@&{r}>" for c, r in regole.items()] or ["Nessun ruolo vocale."]
            await interaction.response.send_message(
                "\n".join(righe)[:1900], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE
            )
            return
        if canale is None:
            await interaction.response.send_message("Scegli il canale vocale.", ephemeral=True)
            return
        if azione == "togli":
            ruolo_tolto = await voice_role_repo.remove(guild.id, canale.id)
            self._regole.pop(guild.id, None)
            await interaction.response.send_message(
                "Canale scollegato." if ruolo_tolto else "Quel canale non aveva un ruolo.", ephemeral=True
            )
            return
        if ruolo is None:
            await interaction.response.send_message("Scegli il ruolo da dare.", ephemeral=True)
            return
        motivo = check_role_assignable(guild, ruolo, interaction.user, self_service=True)
        if motivo is not None:
            await interaction.response.send_message(motivo, ephemeral=True)
            return
        if not await voice_role_repo.set(guild.id, canale.id, ruolo.id, interaction.user.id):
            await interaction.response.send_message(
                f"Questo server ha già {MAX_RUOLI_VOCALI} ruoli vocali: toglierne uno.", ephemeral=True
            )
            return
        self._regole.pop(guild.id, None)
        await interaction.response.send_message(
            f"Chi entra in {canale.mention} riceve {ruolo.mention} e lo perde quando esce.",
            ephemeral=True, allowed_mentions=NESSUNA_MENZIONE,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RuoliVocaliCog(bot))
