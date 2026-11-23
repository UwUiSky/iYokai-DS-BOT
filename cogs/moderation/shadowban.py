"""
cogs/moderation/shadowban.py
============================
Shadowban (D127): `/mod-sanzioni shadowban dai|togli|canali`. Il membro perde i ruoli (salvati prima e scritti nel log
di moderazione) e vede solo un canale di testo e uno vocale dedicati, che vedono anche gli admin. A tempo con
scadenza dello scheduler (vale anche dopo un riavvio); chi esce e rientra resta in shadowban fino alla fine.
Funzioni coperte: D127 (shadowban), CFG-024 (azione «shadowban»)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from cogs.moderation._shared import (
    MODULE_ACTIONS,
    Reason,
    audit_reason,
    check_can_moderate,
    completa_motivo,
    ensure_module_enabled,
    parse_duration,
    post_to_mod_log,
    risolvi_motivo,
)
from cogs.moderation._tempban_modes import trova_membro
from core import moderation_shadowban as sb
from core.command_access import Livello
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import testo_per
from core.moderation_conferma import conferma_sanzione, invia_esito
from core.repositories.moderation_repo import moderation_repo
from core.scheduler import scheduler

logger = logging.getLogger("iyokai.moderation.shadowban")

SOTTOGRUPPO = ("shadowban", "Shadowban: il membro vede solo due canali dedicati.")
MAX_RUOLI_NEL_LOG = 40


def _embed(titolo: str, colore: discord.Color, member: discord.Member, moderatore, motivo: str, caso: int | None):
    embed = discord.Embed(title=titolo, color=colore)
    embed.add_field(name="Utente", value=f"{member.mention} ({member.id})", inline=False)
    embed.add_field(name="Moderatore", value=moderatore.mention, inline=True)
    if caso is not None:
        embed.add_field(name="Caso", value=f"#{caso}", inline=True)
    embed.add_field(name="Motivo", value=motivo[:1000], inline=False)
    return embed


def _ruoli_nel_log(ruoli_ids) -> str:
    """I ruoli tolti, per poterli ripristinare a mano se serve (anche se un ruolo sparisce dal server)."""
    righe = " ".join(f"<@&{i}>" for i in list(ruoli_ids)[:MAX_RUOLI_NEL_LOG])
    resto = len(ruoli_ids) - MAX_RUOLI_NEL_LOG
    return (righe + (f" … +{resto}" if resto > 0 else "") or "-")[:1000]


class ModerationShadowbanCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        """Un canale nato dopo non deve diventare una via d'uscita: riceve il blocco del ruolo shadowban."""
        cfg = await moderation_repo.get_shadowban_config(channel.guild.id)
        ruolo = channel.guild.get_role(cfg["ruolo_id"]) if cfg["ruolo_id"] else None
        if ruolo is None or channel.id in (cfg["canale_testo_id"], cfg["canale_vocale_id"]):
            return
        if not sb._ha_blocco(channel, ruolo):
            await sb._blocca_canale(channel, ruolo)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Chi esce e rientra durante lo shadowban resta in shadowban; se è scaduto lo stato si chiude."""
        stato = await moderation_repo.get_shadowban(member.guild.id, member.id)
        if stato is None:
            return
        fine = stato["finisce_il"]
        if fine is not None and fine <= datetime.now(timezone.utc):
            if stato["case_number"] is not None:
                await moderation_repo.revoke_case(member.guild.id, stato["case_number"], self.bot.user.id)
            await moderation_repo.elimina_shadowban(member.guild.id, member.id)
            return
        cfg = await moderation_repo.get_shadowban_config(member.guild.id)
        ruolo = member.guild.get_role(cfg["ruolo_id"]) if cfg["ruolo_id"] else None
        if ruolo is None:
            return
        try:
            await member.add_roles(ruolo, reason="Shadowban ancora in corso")
        except discord.HTTPException:
            logger.warning("Rientro: ruolo shadowban non rimesso a %s (server %s).", member.id, member.guild.id)

    async def handle_shadowban_fine(self, guild_id: int, user_id: int, payload: dict) -> None:
        """Lo scheduler: lo shadowban a tempo è finito."""
        stato = await moderation_repo.get_shadowban(guild_id, user_id)
        if stato is None or stato["case_number"] != payload.get("caso"):
            return  # tolto prima, oppure sostituito
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        member = await trova_membro(guild, user_id)
        if member is None:  # fuori dal server: si chiude lo stato e il caso
            await moderation_repo.revoke_case(guild_id, stato["case_number"], self.bot.user.id)
            await moderation_repo.elimina_shadowban(guild_id, user_id)
            return
        if await sb.togli(guild, member, "Shadowban scaduto", self.bot.user.id) is False:
            raise RuntimeError("ruoli dello shadowban non sistemati")  # lo scheduler riprova

    @comando_di_gruppo(
        "mod-sanzioni", nome="dai",
        descrizione="Toglie ai membri ogni canale tranne due dedicati (anche a tempo).", sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(
        member="Il membro da mettere in shadowban",
        reason="Motivo dello shadowban",
        durata="Per quanto tempo (es. 2h, 3d). Vuoto: finché non lo togli (max 1 anno)",
    )
    @app_commands.autocomplete(reason=completa_motivo)
    async def dai(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Reason | None = None,
        durata: app_commands.Range[str, 1, 20] | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        reason = await risolvi_motivo(interaction, reason)
        if reason is None:
            return
        if not await check_can_moderate(interaction, member):
            return
        guild = interaction.guild
        if sb.permessi_bot_mancanti(guild):
            await interaction.response.send_message(await testo_per(interaction, "shadowban_bot_senza_permesso"), ephemeral=True)
            return
        fine = None
        if durata is not None:
            try:
                secondi = parse_duration(durata)
            except ValueError as exc:
                await interaction.response.send_message(str(exc), ephemeral=True)
                return
            if not 60 <= secondi <= sb.MAX_DURATA_SECONDI:
                await interaction.response.send_message(await testo_per(interaction, "shadowban_durata_non_valida"), ephemeral=True)
                return
            fine = discord.utils.utcnow() + timedelta(seconds=secondi)
        interaction = await conferma_sanzione(interaction, member, "shadowban", reason, livello=Livello.MOD)
        if interaction is None:
            return
        await interaction.response.defer()
        esito = await sb.metti(member, audit_reason(f"Shadowban: {reason}"), interaction.user.id, fine)
        if esito.gia:
            await interaction.followup.send(await testo_per(interaction, "shadowban_gia", mention=member.mention), ephemeral=True)
            return
        if not esito.riuscita:
            await interaction.followup.send(await testo_per(interaction, "shadowban_non_riuscito"), ephemeral=True)
            return
        if fine is not None:
            await scheduler.schedule(guild.id, member.id, sb.SCHEDULED_SHADOWBAN_FINE, fine, payload={"caso": esito.caso})
        embed = _embed("👤 Shadowban", discord.Color.dark_grey(), member, interaction.user, reason, esito.caso)
        if fine is not None:
            embed.add_field(name=await testo_per(interaction, "softbanmute_fine", pubblica=True), value=discord.utils.format_dt(fine, "R"), inline=True)
        if esito.ruoli_non_tolti:
            embed.set_footer(text=await testo_per(interaction, "quarantena_ruoli_non_tolti", pubblica=True))
        await invia_esito(interaction, embed, seguito=True)
        log = embed.copy()
        log.add_field(name=await testo_per(interaction, "shadowban_ruoli_tolti", pubblica=True), value=_ruoli_nel_log(esito.ruoli_salvati), inline=False)
        await post_to_mod_log(guild, log)

    @comando_di_gruppo(
        "mod-sanzioni", nome="togli",
        descrizione="Toglie lo shadowban e ridà i ruoli di prima.", sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(member="Il membro da liberare", reason="Motivo")
    @app_commands.autocomplete(reason=completa_motivo)
    async def togli(
        self, interaction: discord.Interaction, member: discord.Member, reason: Reason | None = None
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        reason = await risolvi_motivo(interaction, reason)
        if reason is None:
            return
        if not await check_can_moderate(interaction, member):
            return
        await interaction.response.defer()
        await scheduler.cancel_for_user(interaction.guild.id, member.id, sb.SCHEDULED_SHADOWBAN_FINE)
        esito = await sb.togli(interaction.guild, member, audit_reason(f"Shadowban tolto: {reason}"), interaction.user.id)
        if esito is None:
            await interaction.followup.send(await testo_per(interaction, "shadowban_non_in_shadowban", mention=member.mention), ephemeral=True)
            return
        if esito is False:
            await interaction.followup.send(await testo_per(interaction, "softbanmute_non_sono_riuscito_sistemare_ruoli"), ephemeral=True)
            return
        embed = _embed("👁️ Shadowban tolto", discord.Color.green(), member, interaction.user, reason, None)
        await interaction.followup.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        await post_to_mod_log(interaction.guild, embed)

    @comando_di_gruppo(
        "mod-sanzioni", nome="canali",
        descrizione="Sceglie o crea i due canali dedicati dello shadowban.", sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(
        testo="Il canale di testo dedicato. Vuoto: quello già scelto, o ne creo uno",
        vocale="Il canale vocale dedicato. Vuoto: quello già scelto, o ne creo uno",
    )
    async def canali(
        self,
        interaction: discord.Interaction,
        testo: discord.TextChannel | None = None,
        vocale: discord.VoiceChannel | discord.StageChannel | None = None,
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        guild = interaction.guild
        if sb.permessi_bot_mancanti(guild):
            await interaction.response.send_message(await testo_per(interaction, "shadowban_bot_senza_permesso"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        prep = await sb.prepara(guild, testo, vocale)
        if prep is None:
            await interaction.followup.send(await testo_per(interaction, "shadowban_canali_non_preparati"), ephemeral=True)
            return
        _, falliti = await sb.blocca_canali(guild, prep)
        messaggio = await testo_per(
            interaction, "shadowban_canali_pronti", testo=prep.canale_testo.mention, vocale=prep.canale_vocale.mention,
        )
        if falliti:
            messaggio += "\n" + await testo_per(interaction, "shadowban_blocco_incompleto", falliti=falliti)
        await interaction.followup.send(messaggio[:2000], ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot) -> None:
    cog = ModerationShadowbanCog(bot)
    await bot.add_cog(cog)
    scheduler.register_handler(sb.SCHEDULED_SHADOWBAN_FINE, cog.handle_shadowban_fine)
