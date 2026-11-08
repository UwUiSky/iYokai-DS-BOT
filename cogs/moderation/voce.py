"""
cogs/moderation/voce.py
=======================
Moderazione della voce: /mod-canali vocale muta | sordina | scollega | sposta | sposta-tutti | dove.
Il permesso si controlla nel codice, per lo staff e per il bot (il gruppo resta di moderate_members, D60).
`dove` può chiedere un avviso quando l'utente entra in un vocale: sorveglianza di 24 ore, un solo avviso.
Funzioni coperte: SPEC §5.1 (MOD-022, 023, 024, 025, 112)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

from cogs.moderation._shared import MODULE_ACTIONS, check_can_moderate, ensure_module_enabled, post_to_mod_log
from core import moderazione_vocale_logic as logica
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import testo_guild, testo_per
from core.repositories.moderation_repo import moderation_repo

logger = logging.getLogger(__name__)

PAUSA_SPOSTA = 0.4  # secondi fra due spostamenti (limite di frequenza di Discord)
MAX_403_DI_FILA = 3
SOTTOGRUPPO = ("vocale", "Moderazione delle chiamate vocali.")
Vocale = discord.VoiceChannel | discord.StageChannel


async def rifiuta(interaction: discord.Interaction, chiave: str, **valori) -> None:
    await interaction.response.send_message(await testo_per(interaction, chiave, **valori), ephemeral=True)


async def _staff_ha_permesso(interaction: discord.Interaction, azione: str) -> bool:
    permesso = logica.permesso_per(azione)
    utente = interaction.user
    if getattr(utente.guild_permissions, permesso, False):
        return True
    await rifiuta(interaction, "voce_staff_senza_permesso", permesso=permesso)
    return False


async def _bot_ha_permesso(interaction: discord.Interaction, azione: str, canale: Vocale) -> bool:
    permesso = logica.permesso_per(azione)
    if getattr(canale.permissions_for(interaction.guild.me), permesso, False):
        return True
    await rifiuta(interaction, "voce_bot_senza_permesso", permesso=permesso, canale=canale.mention)
    return False


async def _log(interaction: discord.Interaction, titolo_chiave: str, membro, dettaglio: str) -> None:
    embed = discord.Embed(title=await testo_per(interaction, titolo_chiave, pubblica=True), color=discord.Color.blurple())
    embed.add_field(name=await testo_per(interaction, "voce_membro", pubblica=True), value=membro.mention, inline=True)
    embed.add_field(name=await testo_per(interaction, "channelcontr_moderatore", pubblica=True), value=interaction.user.mention, inline=True)
    if dettaglio:
        embed.add_field(name=await testo_per(interaction, "voce_dettaglio", pubblica=True), value=dettaglio[:1000], inline=False)
    await post_to_mod_log(interaction.guild, embed)


class ModerationVoceCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # (server, utente) con una sorveglianza attiva; evita una query a ogni cambio di stato della voce
        self._sorvegliati: set[tuple[int, int]] = set()
        self._caricato = False

    async def _prepara_membro(self, interaction: discord.Interaction, azione: str, membro: discord.Member):
        """Controlli comuni su un membro: modulo, permesso dello staff, gerarchia, è in vocale, permesso del bot."""
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return None
        if not await _staff_ha_permesso(interaction, azione):
            return None
        if not await check_can_moderate(interaction, membro):
            return None
        voce = getattr(membro, "voice", None)
        canale = getattr(voce, "channel", None)
        if canale is None:
            await rifiuta(interaction, "voce_non_in_vocale", membro=membro.mention)
            return None
        if not await _bot_ha_permesso(interaction, azione, canale):
            return None
        return canale

    async def _cambia_stato(self, interaction, membro, azione: str, campo: str, attivo: bool) -> None:
        canale = await self._prepara_membro(interaction, azione, membro)
        if canale is None:
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await membro.edit(**{campo: attivo}, reason=f"{azione} vocale da {interaction.user.id}")
        except discord.HTTPException:
            await interaction.followup.send(await testo_per(interaction, "voce_azione_fallita"), ephemeral=True)
            return
        chiave = f"voce_{azione}_{'on' if attivo else 'off'}"
        await interaction.followup.send(await testo_per(interaction, chiave, membro=membro.mention), ephemeral=True)
        await _log(interaction, chiave + "_titolo", membro, canale.mention)

    @comando_di_gruppo("mod-canali", nome="muta", descrizione="Silenzia o riattiva il microfono di un membro in vocale.", sottogruppo=SOTTOGRUPPO)
    async def vocale_muta(self, interaction: discord.Interaction, membro: discord.Member, attivo: bool = True) -> None:
        await self._cambia_stato(interaction, membro, "muta", "mute", attivo)

    @comando_di_gruppo("mod-canali", nome="sordina", descrizione="Sordina o riattiva l'audio di un membro in vocale.", sottogruppo=SOTTOGRUPPO)
    async def vocale_sordina(self, interaction: discord.Interaction, membro: discord.Member, attivo: bool = True) -> None:
        await self._cambia_stato(interaction, membro, "sordina", "deafen", attivo)

    @comando_di_gruppo("mod-canali", nome="scollega", descrizione="Scollega un membro dal vocale.", sottogruppo=SOTTOGRUPPO)
    async def vocale_scollega(self, interaction: discord.Interaction, membro: discord.Member) -> None:
        canale = await self._prepara_membro(interaction, "scollega", membro)
        if canale is None:
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await membro.move_to(None, reason=f"scollegato da {interaction.user.id}")
        except discord.HTTPException:
            await interaction.followup.send(await testo_per(interaction, "voce_azione_fallita"), ephemeral=True)
            return
        await interaction.followup.send(await testo_per(interaction, "voce_scollegato", membro=membro.mention), ephemeral=True)
        await _log(interaction, "voce_scollega_titolo", membro, canale.mention)

    @comando_di_gruppo("mod-canali", nome="sposta", descrizione="Sposta un membro in un altro vocale.", sottogruppo=SOTTOGRUPPO)
    async def vocale_sposta(self, interaction: discord.Interaction, membro: discord.Member, canale: Vocale) -> None:
        origine = await self._prepara_membro(interaction, "sposta", membro)
        if origine is None:
            return
        if logica.stesso_canale(origine.id, canale.id):
            await rifiuta(interaction, "voce_stesso_canale")
            return
        if not canale.permissions_for(interaction.guild.me).connect:
            await rifiuta(interaction, "voce_bot_senza_permesso", permesso="connect", canale=canale.mention)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await membro.move_to(canale, reason=f"spostato da {interaction.user.id}")
        except discord.HTTPException:
            await interaction.followup.send(await testo_per(interaction, "voce_azione_fallita"), ephemeral=True)
            return
        await interaction.followup.send(
            await testo_per(interaction, "voce_spostato", membro=membro.mention, canale=canale.mention), ephemeral=True
        )
        await _log(interaction, "voce_sposta_titolo", membro, f"{origine.mention} -> {canale.mention}")

    @comando_di_gruppo("mod-canali", nome="sposta-tutti", descrizione="Sposta tutti i membri di un vocale in un altro.", sottogruppo=SOTTOGRUPPO)
    async def vocale_sposta_tutti(self, interaction: discord.Interaction, da: Vocale, a: Vocale) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        if not await _staff_ha_permesso(interaction, "sposta"):
            return
        if logica.stesso_canale(da.id, a.id):
            await rifiuta(interaction, "voce_stesso_canale")
            return
        if not await _bot_ha_permesso(interaction, "sposta", da):
            return
        if not a.permissions_for(interaction.guild.me).connect:
            await rifiuta(interaction, "voce_bot_senza_permesso", permesso="connect", canale=a.mention)
            return
        membri, restano = logica.da_spostare(list(da.members))
        if not membri:
            await rifiuta(interaction, "voce_canale_vuoto", canale=da.mention)
            return
        await interaction.response.defer(ephemeral=True)
        mossi = 0
        di_fila = 0
        for membro in membri:
            try:
                await membro.move_to(a, reason=f"spostamento di massa di {interaction.user.id}")
                mossi += 1
                di_fila = 0
            except discord.Forbidden:
                di_fila += 1
                if di_fila >= MAX_403_DI_FILA:  # tre 403 di fila: ci si ferma (rischio blocco IP)
                    break
            except discord.HTTPException:
                break
            await asyncio.sleep(PAUSA_SPOSTA)
        testo = await testo_per(interaction, "voce_spostati", v1=mossi, da=da.mention, a=a.mention)
        if restano:
            testo += " " + await testo_per(interaction, "voce_spostati_restano", v1=restano)
        await interaction.followup.send(testo, ephemeral=True)
        embed = discord.Embed(title=await testo_per(interaction, "voce_sposta_tutti_titolo", pubblica=True), color=discord.Color.blurple())
        embed.add_field(name=await testo_per(interaction, "channelcontr_moderatore", pubblica=True), value=interaction.user.mention, inline=True)
        embed.add_field(name=await testo_per(interaction, "voce_dettaglio", pubblica=True), value=f"{da.mention} -> {a.mention} ({mossi})", inline=True)
        await post_to_mod_log(interaction.guild, embed)

    @comando_di_gruppo("mod-canali", nome="dove", descrizione="Mostra in quale vocale è un membro, e chiedi un avviso quando entra.", sottogruppo=SOTTOGRUPPO)
    async def vocale_dove(self, interaction: discord.Interaction, membro: discord.Member, avvisa: bool = False) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        canale = getattr(getattr(membro, "voice", None), "channel", None)
        if canale is not None:
            await rifiuta(interaction, "voce_dove_in_vocale", membro=membro.mention, canale=canale.mention)
            return
        if not avvisa:
            await rifiuta(interaction, "voce_dove_non_in_vocale", membro=membro.mention)
            return
        guild = interaction.guild
        if await moderation_repo.count_vocale_sorveglia(guild.id) >= logica.MAX_SORVEGLIANZE_SERVER:
            await rifiuta(interaction, "voce_troppe_sorveglianze", v1=logica.MAX_SORVEGLIANZE_SERVER)
            return
        scade = logica.scadenza_sorveglianza(datetime.now(timezone.utc))
        await moderation_repo.add_vocale_sorveglia(guild.id, membro.id, interaction.user.id, scade)
        self._sorvegliati.add((guild.id, membro.id))
        await rifiuta(interaction, "voce_dove_avviso_creato", membro=membro.mention, ore=logica.SORVEGLIANZA_ORE)

    async def _carica(self) -> None:
        if self._caricato:
            return
        self._caricato = True
        try:
            self._sorvegliati |= set(await moderation_repo.utenti_sorvegliati())
        except Exception:  # noqa: BLE001 - senza tabella o senza database non si blocca la voce
            logger.warning("Sorveglianze della voce non lette.", exc_info=False)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, prima, dopo) -> None:
        """Un utente sorvegliato entra in vocale: avviso allo staff (DM, altrimenti log), poi la sorveglianza finisce."""
        if getattr(prima, "channel", None) is not None or getattr(dopo, "channel", None) is None:
            return
        await self._carica()
        chiave = (member.guild.id, member.id)
        if chiave not in self._sorvegliati:
            return
        self._sorvegliati.discard(chiave)
        staff_ids = await moderation_repo.vocale_sorveglianti(member.guild.id, member.id)
        await moderation_repo.delete_vocale_sorveglia(member.guild.id, member.id)
        testo = await testo_guild(member.guild, "voce_avviso_ingresso", membro=member.mention, canale=dopo.channel.mention, server=member.guild.name)
        mandato = False
        for staff_id in staff_ids:
            staff = member.guild.get_member(staff_id)
            if staff is None:
                continue
            try:
                await staff.send(testo)
                mandato = True
            except discord.HTTPException:
                continue
        if staff_ids and not mandato:
            await post_to_mod_log(member.guild, discord.Embed(description=testo))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModerationVoceCog(bot))
