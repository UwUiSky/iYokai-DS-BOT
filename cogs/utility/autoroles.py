"""
cogs/utility/autoroles.py
=========================
Ruoli automatici all'ingresso, ruoli ridati a chi rientra entro 30 giorni,
ruoli dati dopo un ritardo (NF-07, SPEC §22.1-22.3). Comandi in
`/gestione ruoli auto-*`; la logica è in core/autorole_logic.py.
Funzioni coperte: SPEC §22 (NF-07)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.autorole_logic import (
    MAX_GIORNI_MEMORIA,
    MAX_REGOLE,
    MAX_RITARDO_SECONDI,
    membro_in_attesa,
    piano_ingresso,
    ruoli_da_ricordare,
    ruoli_da_ridare,
)
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.premium import PremiumModule, registry
from core.repositories.autorole_repo import autorole_repo
from core.repositories.verify_repo import verify_repo
from core.role_safety import check_role_assignable, motivo_ruolo_automatico_non_assegnabile
from core.scheduler import in_seconds, scheduler
from core.security_raid_state import DURATA_RAID_SECONDI, raid_in_corso

logger = logging.getLogger("iyokai.autoroles")

MODULE_AUTOROLES = "autoroles"
MODULE_VERIFY = "verify"
AUTOROLE_ACTION_TYPE = "autorole_give"

_SG_RUOLI = ("ruoli", "Ruoli: ruoli-premio per livello e menu di ruoli")


def _testo_ritardo(secondi: int) -> str:
    if secondi <= 0:
        return "subito"
    if secondi % 86400 == 0:
        return f"dopo {secondi // 86400} g"
    if secondi % 3600 == 0:
        return f"dopo {secondi // 3600} h"
    return f"dopo {max(secondi // 60, 1)} min"


class AutorolesCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ================================================================
    # Assegnazione
    # ================================================================
    async def _ruolo_verificato_atteso(self, guild: discord.Guild) -> int | None:
        """L'ID del ruolo "verificato" se la verifica del server è attiva, altrimenti None."""
        if not await db.is_module_active_for_guild(guild.id, MODULE_VERIFY):
            return None
        return (await verify_repo.get_config(guild.id)).verified_role_id

    async def _assegna(self, member: discord.Member, ruoli_id: list[int]) -> None:
        """Dà i ruoli che il bot può assegnare; salta gli altri con un avviso nel log."""
        da_dare: list[discord.Role] = []
        for rid in ruoli_id:
            motivo = motivo_ruolo_automatico_non_assegnabile(member.guild, rid)
            if motivo is not None:
                logger.warning("Ruolo automatico %s saltato nel server %s: %s", rid, member.guild.id, motivo)
                continue
            da_dare.append(member.guild.get_role(rid))
        if not da_dare:
            return
        try:
            await member.add_roles(*da_dare, reason="Ruolo automatico")
        except discord.HTTPException as errore:
            logger.warning("Ruoli automatici non dati a %s nel server %s: %s", member.id, member.guild.id, errore)

    async def _applica_regole(self, member: discord.Member) -> None:
        """Ruoli ricordati e regole: subito o in coda sullo scheduler."""
        guild = member.guild
        regole = await autorole_repo.list_rules(guild.id)
        posseduti = {r.id for r in member.roles}
        subito, dopo = piano_ingresso(regole, is_bot=member.bot, ruoli_posseduti=posseduti)
        if member.bot:
            return
        pausa = raid_in_corso(guild.id)
        if pausa:
            # Durante un raid i ruoli non si danno: si programmano a raid finito.
            dopo = dopo + [(rid, 0) for rid in subito]
            subito = []
        if subito:
            await self._assegna(member, subito)
        for rid, attesa in dopo:
            secondi = attesa + (DURATA_RAID_SECONDI if pausa else 0)
            await scheduler.schedule(
                guild.id, member.id, AUTOROLE_ACTION_TYPE, in_seconds(secondi), {"role_id": rid}
            )

    async def handle_autorole_give(self, guild_id: int, user_id: int, payload: dict) -> None:
        """Handler dello scheduler: dà un ruolo ritardato se la regola c'è ancora e il membro pure."""
        guild = self.bot.get_guild(guild_id)
        role_id = payload.get("role_id")
        if guild is None or role_id is None:
            return
        member = guild.get_member(user_id)
        if member is None or not await autorole_repo.has_rule(guild_id, role_id):
            return
        if role_id in {r.id for r in member.roles}:
            return
        await self._assegna(member, [role_id])

    # ================================================================
    # Eventi
    # ================================================================
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return
        if not await db.is_module_active_for_guild(member.guild.id, MODULE_AUTOROLES):
            return

        config = await autorole_repo.get_config(member.guild.id)
        if config.remember_enabled:
            ricordati = await autorole_repo.pop_memory(member.guild.id, member.id)
            if ricordati is not None:
                ruoli = ruoli_da_ridare(
                    ricordati.role_ids, ricordati.left_at, datetime.now(timezone.utc), config.remember_days
                )
                if ruoli:
                    await self._assegna(member, ruoli)

        verificato = await self._ruolo_verificato_atteso(member.guild)
        if membro_in_attesa(
            member.pending, verificato is not None, verificato in {r.id for r in member.roles}
        ):
            return  # i ruoli arrivano da on_member_update, a verifica o regole accettate
        await self._applica_regole(member)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if after.bot:
            return
        ruoli_prima = {r.id for r in before.roles}
        ruoli_dopo = {r.id for r in after.roles}
        ha_accettato = before.pending and not after.pending
        verificato_ora = False
        if not ha_accettato:
            # Solo il passaggio al ruolo "verificato" interessa: controllo economico prima.
            nuovi = ruoli_dopo - ruoli_prima
            if not nuovi:
                return
        if not await db.is_module_active_for_guild(after.guild.id, MODULE_AUTOROLES):
            return
        verificato = await self._ruolo_verificato_atteso(after.guild)
        if verificato is not None and verificato in (ruoli_dopo - ruoli_prima):
            verificato_ora = True
        if not (ha_accettato or verificato_ora):
            return
        if membro_in_attesa(after.pending, verificato is not None, verificato in ruoli_dopo):
            return
        await self._applica_regole(after)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if member.bot:
            return
        if not await db.is_module_active_for_guild(member.guild.id, MODULE_AUTOROLES):
            return
        config = await autorole_repo.get_config(member.guild.id)
        if not config.remember_enabled:
            return
        ruoli = ruoli_da_ricordare(member.roles)
        if not ruoli:
            return
        await autorole_repo.save_memory(member.guild.id, member.id, ruoli, datetime.now(timezone.utc))

    # ================================================================
    # Comandi
    # ================================================================
    async def _modulo_attivo(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_AUTOROLES):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /admin setup attiva.",
                ephemeral=True,
            )
            return False
        return True

    @comando_di_gruppo(
        "gestione",
        nome="auto-aggiungi",
        descrizione="Aggiungi un ruolo dato in automatico a chi entra.",
        sottogruppo=_SG_RUOLI,
    )
    @app_commands.describe(
        ruolo="Il ruolo da dare a chi entra",
        ritardo_minuti="Attesa prima di darlo (0 = subito, al massimo 7 giorni)",
    )
    async def auto_aggiungi(
        self,
        interaction: discord.Interaction,
        ruolo: discord.Role,
        ritardo_minuti: app_commands.Range[int, 0, MAX_RITARDO_SECONDI // 60] = 0,
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return
        motivo = check_role_assignable(interaction.guild, ruolo, interaction.user, self_service=True)
        if motivo is not None:
            await interaction.response.send_message(motivo, ephemeral=True)
            return
        ok = await autorole_repo.add_rule(
            interaction.guild.id, ruolo.id, ritardo_minuti * 60, created_by=interaction.user.id
        )
        if not ok:
            await interaction.response.send_message(
                f"Questo server ha già {MAX_REGOLE} ruoli automatici: togline uno prima.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"{ruolo.mention} sarà dato a chi entra {_testo_ritardo(ritardo_minuti * 60)}.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @comando_di_gruppo(
        "gestione",
        nome="auto-rimuovi",
        descrizione="Togli un ruolo dato in automatico a chi entra.",
        sottogruppo=_SG_RUOLI,
    )
    @app_commands.describe(ruolo="Il ruolo da non dare più")
    async def auto_rimuovi(self, interaction: discord.Interaction, ruolo: discord.Role) -> None:
        if not await self._modulo_attivo(interaction):
            return
        tolto = await autorole_repo.remove_rule(interaction.guild.id, ruolo.id)
        testo = (
            f"{ruolo.mention} non sarà più dato a chi entra."
            if tolto
            else f"{ruolo.mention} non era tra i ruoli automatici."
        )
        await interaction.response.send_message(
            testo, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )

    @comando_di_gruppo(
        "gestione",
        nome="auto-elenco",
        descrizione="Mostra i ruoli automatici del server.",
        sottogruppo=_SG_RUOLI,
    )
    async def auto_elenco(self, interaction: discord.Interaction) -> None:
        if not await self._modulo_attivo(interaction):
            return
        regole = await autorole_repo.list_rules(interaction.guild.id)
        config = await autorole_repo.get_config(interaction.guild.id)
        righe = [f"<@&{r.role_id}> — {_testo_ritardo(r.delay_seconds)}" for r in regole] or [
            "Nessun ruolo automatico."
        ]
        ricorda = (
            f"Ruoli ridati a chi rientra entro {config.remember_days} giorni: attivo."
            if config.remember_enabled
            else "Ruoli ridati a chi rientra: spento."
        )
        embed = discord.Embed(
            title="Ruoli automatici", description="\n".join(righe)[:4000] + f"\n\n{ricorda}"
        )
        await interaction.response.send_message(
            embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )

    @comando_di_gruppo(
        "gestione",
        nome="auto-ricorda",
        descrizione="Ridai i ruoli a chi esce e rientra entro un certo tempo.",
        sottogruppo=_SG_RUOLI,
    )
    @app_commands.describe(
        attivo="Ricordare i ruoli di chi esce?",
        giorni=f"Entro quanti giorni dal rientro (al massimo {MAX_GIORNI_MEMORIA})",
    )
    async def auto_ricorda(
        self,
        interaction: discord.Interaction,
        attivo: bool,
        giorni: app_commands.Range[int, 1, MAX_GIORNI_MEMORIA] = MAX_GIORNI_MEMORIA,
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return
        await autorole_repo.set_remember(interaction.guild.id, attivo, giorni)
        testo = (
            f"D'ora in poi chi esce e rientra entro {giorni} giorni riprende i suoi ruoli."
            if attivo
            else "Ruoli di chi esce non più ricordati; quelli già salvati sono stati cancellati."
        )
        await interaction.response.send_message(testo, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_AUTOROLES,
            display_name="Ruoli automatici",
            category="utility",
            description="Ruoli dati a chi entra (anche dopo un ritardo) e ridati a chi rientra.",
            premium_capable=False,
        )
    )
    cog = AutorolesCog(bot)
    await bot.add_cog(cog)
    scheduler.register_handler(AUTOROLE_ACTION_TYPE, cog.handle_autorole_give)
