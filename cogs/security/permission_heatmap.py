"""
cogs/security/permission_heatmap.py
======================================
Permission Risk Heatmap (SPEC.md §7.4, estensione del Permission
Auditor — BACKLOG.md §11). Modulo CANDIDATO PREMIUM, coerente con
gli altri moduli avanzati di Security Suite (Spam Trap è
premium_capable=True).

Due parti:
- `/permission-heatmap`: comando su richiesta, elenca i ruoli con
  permessi critici e quanti membri li possiedono
- alert automatico: quando un membro riceve (via ruolo) un permesso
  critico che prima non aveva, un DM al proprietario del server —
  nessun comando di setup necessario, stesso principio di
  core/memory_guard.py (allarme diretto, non un canale da configurare
  prima che serva davvero)
"""

# DA FARE (issue #59, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §3 (Sicurezza (anti-raid,
#   anti-nuke, spam-trap, ban globale)).

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.permission_risk_logic import (
    critical_permissions_of,
    newly_gained_critical_permissions,
)
from core.premium import PremiumModule, registry, requires_module
from core.security_access import premium_sbloccato

logger = logging.getLogger("iyokai.permission_heatmap")

MODULE_PERMISSION_HEATMAP = "permission_heatmap"


# La descrizione di un embed tiene 4096 caratteri: l'elenco si ferma
# prima, per lasciare posto alla riga "…e altri N ruoli".
MAX_CARATTERI_ELENCO = 4000


def _permission_flags(permissions: discord.Permissions) -> dict[str, bool]:
    return dict(permissions)


def _elenco_entro_il_limite(righe: list[str]) -> str:
    """Unisce le righe finché ci stanno e dice quanti ruoli restano fuori."""
    mostrate: list[str] = []
    lunghezza = 0
    for riga in righe:
        lunghezza += len(riga) + 2  # 2 = la riga vuota che separa i ruoli
        if lunghezza > MAX_CARATTERI_ELENCO:
            break
        mostrate.append(riga)

    testo = "\n\n".join(mostrate)
    esclusi = len(righe) - len(mostrate)
    if esclusi:
        testo += f"\n\n…e altri {esclusi} ruoli con permessi critici."
    return testo


class PermissionHeatmapCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="permission-heatmap",
        description="[Admin] Mostra quali ruoli hanno permessi critici e chi li possiede.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @requires_module(MODULE_PERMISSION_HEATMAP)
    async def permission_heatmap(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        if not await db.is_module_active_for_guild(guild.id, MODULE_PERMISSION_HEATMAP):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /setup.",
                ephemeral=True,
            )
            return

        righe = []
        for role in guild.roles:
            if role.is_default():
                continue  # @everyone non è mai utile qui: tutti i membri lo hanno
            critici = critical_permissions_of(_permission_flags(role.permissions))
            if not critici:
                continue
            righe.append(
                f"**{role.name}** ({len(role.members)} membri): "
                f"{', '.join(critici)}"
            )

        if not righe:
            await interaction.response.send_message(
                "Nessun ruolo con permessi critici trovato — buon segno.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🛡️ Permission Risk Heatmap",
            description=_elenco_entro_il_limite(righe),
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        if not await db.is_module_active_for_guild(after.guild.id, MODULE_PERMISSION_HEATMAP):
            return
        if not await premium_sbloccato(after.guild.id, MODULE_PERMISSION_HEATMAP, self.bot):
            return

        before_role_ids = {r.id for r in before.roles}
        after_role_ids = {r.id for r in after.roles}
        if before_role_ids == after_role_ids:
            return  # niente cambi di ruolo in questo evento, non serve calcolare nulla

        # Mappa SOLO dei ruoli appena aggiunti — non serve calcolare i
        # permessi critici di ruoli che il membro aveva già o non ha.
        ruoli_aggiunti = after_role_ids - before_role_ids
        mappa_permessi_critici = {}
        for role_id in ruoli_aggiunti:
            role = after.guild.get_role(role_id)
            if role is not None:
                mappa_permessi_critici[role_id] = critical_permissions_of(
                    _permission_flags(role.permissions)
                )

        risultato = newly_gained_critical_permissions(
            before_role_ids, after_role_ids, mappa_permessi_critici
        )
        if not risultato:
            return

        owner = after.guild.owner
        if owner is None:
            return

        dettagli = []
        for role_id, permessi in risultato.items():
            role = after.guild.get_role(role_id)
            nome_ruolo = role.name if role else f"ruolo #{role_id}"
            dettagli.append(f"**{nome_ruolo}**: {', '.join(permessi)}")

        try:
            await owner.send(
                f"⚠️ **Permission Risk Alert** — {after.mention} ({after.id}) ha "
                f"appena ricevuto un ruolo con permessi critici in "
                f"**{after.guild.name}**:\n\n" + "\n".join(dettagli)
            )
        except discord.HTTPException:
            logger.warning(
                "Impossibile avvisare l'owner del server %s del permesso "
                "critico appena assegnato (DM chiusi?).",
                after.guild.id,
            )


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_PERMISSION_HEATMAP,
            display_name="Permission Risk Heatmap",
            category="security",
            description="Mappa dei ruoli con permessi critici + alert su nuove assegnazioni.",
            premium_capable=True,
        )
    )
    await bot.add_cog(PermissionHeatmapCog(bot))
