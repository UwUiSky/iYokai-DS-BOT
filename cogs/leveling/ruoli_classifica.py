"""
cogs/leveling/ruoli_classifica.py
=================================
/admin-livelli classifica-ruoli: un ruolo al primo della classifica XP, uno ai primi 3, uno ai primi 10.
Un lavoro all'ora li aggiorna: chi sale lo riceve, chi scende perde quello vecchio.
Funzioni coperte: SPEC §15 (LIV-044, 045; catalogo #124)
Dipende da: core/leveling_ruoli_classifica_logic.py, core/repositories/leveling_ruoli_classifica_repo.py
"""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.leveling.azzeramenti import _puo_gestire
from cogs.leveling.leveling import MODULE_LEVELING, _comando_rifiutato
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.database import db
from core.i18n import testo_per
from core.leveling_ruoli_classifica_logic import FASCE, differenze, fasce_degli_utenti
from core.repositories.leveling_repo import leveling_repo
from core.repositories.leveling_ruoli_classifica_repo import leveling_ruoli_classifica_repo
from core.role_safety import check_role_assignable

logger = logging.getLogger("iyokai.leveling.ruoli_classifica")

CANDIDATI = 25  # si guardano più persone di 10: chi è uscito dal server si salta
PAUSA_TRA_MODIFICHE = 0.5  # niente raffiche verso Discord
_SCELTE_FASCIA = [
    app_commands.Choice(name="Primo della classifica", value=1),
    app_commands.Choice(name="Primi 3", value=3),
    app_commands.Choice(name="Primi 10", value=10),
]


class RuoliClassificaCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._giro.start()

    def cog_unload(self) -> None:
        self._giro.cancel()
        togli_comandi_del_cog(self)

    @comando_di_gruppo(
        "admin-livelli",
        nome="classifica-ruoli",
        descrizione="Un ruolo al primo della classifica XP, ai primi 3 o ai primi 10 (aggiornato ogni ora).",
    )
    @app_commands.describe(
        fascia="A chi va il ruolo",
        ruolo="Il ruolo (vuoto = togli quello di questa fascia)",
    )
    @app_commands.choices(fascia=_SCELTE_FASCIA)
    async def classifica_ruoli(
        self, interaction: discord.Interaction, fascia: app_commands.Choice[int], ruolo: discord.Role | None = None
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        if not await _puo_gestire(interaction):
            return
        guild = interaction.guild
        if ruolo is None:
            togliuto = await leveling_ruoli_classifica_repo.togli(guild.id, fascia.value)
            chiave = "rcl_tolto" if togliuto else "rcl_niente_da_togliere"
            await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)
            return
        # Chi imposta non può dare un ruolo alto quanto il suo o più (il proprietario sì), e il bot deve poterlo dare.
        if interaction.user.id != guild.owner_id and ruolo.position >= interaction.user.top_role.position:
            await interaction.response.send_message(await testo_per(interaction, "rcl_sopra_di_te"), ephemeral=True)
            return
        motivo = check_role_assignable(guild, ruolo, guild.me, self_service=True)
        if motivo is not None:
            await interaction.response.send_message(
                await testo_per(interaction, "rcl_non_assegnabile", motivo=motivo), ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        await leveling_ruoli_classifica_repo.imposta(guild.id, fascia.value, ruolo.id)
        logger.info("Ruolo di classifica: server %s, staff %s, fascia %s, ruolo %s.", guild.id, interaction.user.id, fascia.value, ruolo.id)
        await interaction.response.send_message(
            await testo_per(interaction, "rcl_impostato", fascia=fascia.name, ruolo=ruolo.mention),
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
        )

    @tasks.loop(hours=1)
    async def _giro(self) -> None:
        try:
            for guild_id in await leveling_ruoli_classifica_repo.server_con_ruoli():
                guild = self.bot.get_guild(guild_id)
                if guild is None or not await db.is_module_active_for_guild(guild_id, MODULE_LEVELING):
                    continue
                try:
                    await self.aggiorna_server(guild)
                except Exception:
                    logger.exception("Ruoli di classifica non aggiornati nel server %s.", guild_id)
        except Exception:
            logger.exception("Giro dei ruoli di classifica fallito.")

    @_giro.before_loop
    async def _prima(self) -> None:
        await self.bot.wait_until_ready()

    async def aggiorna_server(self, guild: discord.Guild) -> int:
        """Dà e toglie i ruoli di classifica. Restituisce quante modifiche ha fatto."""
        ruoli_per_fascia = await leveling_ruoli_classifica_repo.elenco(guild.id)
        if not ruoli_per_fascia or not guild.me.guild_permissions.manage_roles:
            return 0
        voci = await leveling_repo.top_xp_alltime(guild.id, CANDIDATI)
        presenti = [v.user_id for v in voci if guild.get_member(v.user_id) is not None]
        if not presenti:
            return 0  # una classifica vuota (errore o server senza XP) non fa togliere niente a nessuno
        desiderate = fasce_degli_utenti(presenti, set(ruoli_per_fascia))
        ruoli: dict[int, discord.Role] = {}
        for fascia, role_id in ruoli_per_fascia.items():
            ruolo = guild.get_role(role_id)
            if ruolo is not None and check_role_assignable(guild, ruolo, guild.me, self_service=True) is None:
                ruoli[fascia] = ruolo
        possessori = {f: {m.id for m in r.members} for f, r in ruoli.items()}
        da_dare, da_togliere = differenze({u: f for u, f in desiderate.items() if f in ruoli}, possessori)
        fatte = 0
        for utente, fascia in da_togliere + da_dare:
            membro = guild.get_member(utente)
            if membro is None:
                continue
            try:
                if (utente, fascia) in da_dare:
                    await membro.add_roles(ruoli[fascia], reason="Ruolo di classifica")
                else:
                    await membro.remove_roles(ruoli[fascia], reason="Ruolo di classifica")
                fatte += 1
            except discord.HTTPException:
                logger.warning("Ruolo di classifica non aggiornato per %s nel server %s.", utente, guild.id)
            await asyncio.sleep(PAUSA_TRA_MODIFICHE)
        return fatte


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RuoliClassificaCog(bot))
