"""
cogs/moderation/nickname.py
===========================
/mod-sanzioni nick: cambia o azzera il soprannome di un membro. Servono «Gestire i soprannomi» a chi comanda
e al bot, e la gerarchia dei ruoli. Niente caso: è una correzione, non una sanzione; resta la riga nel log.
Dello stesso cog: lo storico dei nomi (`/mod-casi nomi`, MOD-103) e il soprannome e il mute vocale ridati a chi rientra
(MOD-104). Le due cose sono spente di base e si accendono con `/mod-sanzioni opzioni memoria`.
Funzioni coperte: SPEC §5.1 (MOD-101, MOD-103, MOD-104)
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from cogs.moderation._shared import MODULE_ACTIONS, audit_reason, check_can_moderate, ensure_module_enabled, post_to_mod_log
import logging

from core import moderation_nomi as nomi
from core import moderazione_canali_logic as logica
from core.database import db
from core.repositories.moderation_repo import moderation_repo
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import testo_per


logger = logging.getLogger("iyokai.moderation.nomi")


class ModerationNicknameCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @staticmethod
    async def _acceso(guild_id: int, chiave: str) -> bool:
        try:
            return bool(await db.get_guild_setting(guild_id, chiave))
        except Exception:
            return False

    # ---------------------------------------------------------- MOD-103: storico dei nomi
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if after.bot or before.nick == after.nick or not await self._acceso(after.guild.id, nomi.SETTING_STORICO_NOMI):
            return
        await moderation_repo.registra_nome(after.guild.id, after.id, "soprannome", before.nick, after.nick)

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User) -> None:
        if after.bot:
            return
        cambi = [
            (tipo, getattr(before, campo), getattr(after, campo))
            for tipo, campo in (("nome", "name"), ("visualizzato", "global_name"))
            if getattr(before, campo) != getattr(after, campo)
        ]
        if not cambi:
            return
        for guild in self.bot.guilds:
            if guild.get_member(after.id) is not None and await self._acceso(guild.id, nomi.SETTING_STORICO_NOMI):
                for tipo, prima, dopo in cambi:
                    await moderation_repo.registra_nome(guild.id, after.id, tipo, prima, dopo)

    @comando_di_gruppo("mod-casi", nome="nomi", descrizione="Mostra i nomi e i soprannomi che un membro ha avuto.")
    @app_commands.describe(utente="Di chi (anche fuori dal server)")
    async def nomi_cmd(self, interaction: discord.Interaction, utente: discord.User) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        if not await self._acceso(interaction.guild.id, nomi.SETTING_STORICO_NOMI):
            await interaction.response.send_message(await testo_per(interaction, "nomi_storico_spento"), ephemeral=True)
            return
        voci = await moderation_repo.elenco_nomi(interaction.guild.id, utente.id)
        if not voci:
            await interaction.response.send_message(await testo_per(interaction, "nomi_nessun_cambio"), ephemeral=True)
            return
        embed = discord.Embed(
            title=await testo_per(interaction, "nomi_titolo", nome=nomi.pulisci(utente.display_name)),
            description="\n".join(nomi.riga(v) for v in voci)[:4000], color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    # ---------------------------------------------------------- MOD-104: chi rientra
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if member.bot or not await self._acceso(member.guild.id, nomi.SETTING_PERSISTENZA):
            return
        voce = getattr(member, "voice", None)
        await moderation_repo.salva_persistenza(
            member.guild.id, member.id, member.nick, bool(voce and voce.mute), bool(voce and voce.deaf)
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot or not await self._acceso(member.guild.id, nomi.SETTING_PERSISTENZA):
            return
        salvato = await moderation_repo.leggi_persistenza(member.guild.id, member.id)
        if salvato is None:
            return
        guild = member.guild
        nick = nomi.nick_da_ridare(salvato["nick"], member.top_role >= guild.me.top_role)
        if nick and guild.me.guild_permissions.manage_nicknames:
            try:
                await member.edit(nick=nick, reason="Soprannome ridato a chi rientra")
            except discord.HTTPException:
                logger.warning("Soprannome non ridato a %s (server %s).", member.id, guild.id)
        if salvato["mute"] or salvato["deaf"]:  # il mute vocale vale solo in vocale: si dà alla prossima entrata
            await moderation_repo.salva_persistenza(guild.id, member.id, None, salvato["mute"], salvato["deaf"])
        else:
            await moderation_repo.togli_persistenza(guild.id, member.id)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before, after) -> None:
        if member.bot or after.channel is None or before.channel is not None:
            return
        if not await self._acceso(member.guild.id, nomi.SETTING_PERSISTENZA):
            return
        salvato = await moderation_repo.leggi_persistenza(member.guild.id, member.id)
        if salvato is None or not (salvato["mute"] or salvato["deaf"]):
            return
        permessi = member.guild.me.guild_permissions
        cosa = {}
        if salvato["mute"] and permessi.mute_members:
            cosa["mute"] = True
        if salvato["deaf"] and permessi.deafen_members:
            cosa["deafen"] = True
        try:
            if cosa:
                await member.edit(reason="Mute vocale ridato a chi rientra", **cosa)
        except discord.HTTPException:
            logger.warning("Mute vocale non ridato a %s (server %s).", member.id, member.guild.id)
        await moderation_repo.togli_persistenza(member.guild.id, member.id)

    @comando_di_gruppo("mod-sanzioni", nome="nick", descrizione="Cambia o azzera il soprannome di un membro.")
    @app_commands.describe(
        membro="Il membro",
        nuovo=f"Il nuovo soprannome (da 1 a {logica.MAX_NICK} caratteri). Vuoto: torna al nome normale",
    )
    async def nick(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        nuovo: app_commands.Range[str, 1, logica.MAX_NICK] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        if not interaction.user.guild_permissions.manage_nicknames:
            await interaction.response.send_message(await testo_per(interaction, "nickname_serve_permesso_tuo"), ephemeral=True)
            return
        if not interaction.guild.me.guild_permissions.manage_nicknames:
            await interaction.response.send_message(await testo_per(interaction, "nickname_serve_permesso_bot"), ephemeral=True)
            return
        if not await check_can_moderate(interaction, membro):
            return
        try:
            await membro.edit(nick=nuovo, reason=audit_reason(f"Soprannome cambiato da {interaction.user.id}"))
        except discord.HTTPException:
            await interaction.response.send_message(await testo_per(interaction, "nickname_non_riuscito"), ephemeral=True)
            return
        chiave = "nickname_cambiato" if nuovo else "nickname_azzerato"
        await interaction.response.send_message(await testo_per(interaction, chiave, membro=membro.mention, nuovo=nuovo or ""), ephemeral=True)
        embed = discord.Embed(title=await testo_per(interaction, "nickname_titolo", pubblica=True), color=discord.Color.blurple())
        embed.add_field(name=await testo_per(interaction, "voce_membro", pubblica=True), value=membro.mention, inline=True)
        embed.add_field(name=await testo_per(interaction, "channelcontr_moderatore", pubblica=True), value=interaction.user.mention, inline=True)
        embed.add_field(name=await testo_per(interaction, "nickname_nuovo", pubblica=True), value=(nuovo or "-")[:100], inline=True)
        await post_to_mod_log(interaction.guild, embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModerationNicknameCog(bot))
