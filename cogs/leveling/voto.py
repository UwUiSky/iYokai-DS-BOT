"""
cogs/leveling/voto.py
=====================
Voto al bot su un sito di elenchi (top.gg): il server web che riceve il voto (spento senza VOTO_SEGRETO nel .env),
/monete conto voto (riscatta il premio, scegli il riscatto automatico) e /admin-giochi voto (premio del server: XP,
monete, bonus XP a tempo, premium a tempo). Un premio per voto; le monete non si comprano con soldi veri.
Funzioni coperte: LIV-019, ECO-048, ECO-049, CFG-039
Dipende da: core/voto_server.py, core/repositories/voto_repo.py
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.leveling.leveling import _comando_rifiutato
from cogs.leveling.rischio import _SG_CONTO
from core import voto_server
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.config import config
from core.i18n import testo_per
from core.premium_code_service import applica_sblocco
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.voto_repo import voto_repo
from core.voto_logic import SITO_TOPGG, segreto_valido

logger = logging.getLogger("iyokai.voto")


def modulo_acceso() -> bool:
    """Il modulo lavora solo con la chiave nel .env: senza, tutto resta spento e nessuna porta si apre."""
    return segreto_valido(config.VOTO_SEGRETO)


class VotoCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._runner = None

    async def cog_load(self) -> None:
        await super().cog_load()
        if not modulo_acceso():
            logger.info("Voto al bot: VOTO_SEGRETO non impostato, modulo spento.")
            return
        try:
            app = voto_server.build_app(segreto=config.VOTO_SEGRETO, registra=voto_repo.registra, dopo_voto=self._dopo_voto)
            self._runner = await voto_server.start_server(app, config.WEB_BIND_HOST, config.VOTO_PORT)
        except OSError:
            logger.exception("Voto al bot: la porta %s non si apre, modulo spento.", config.VOTO_PORT)

    async def cog_unload(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
        togli_comandi_del_cog(self)

    # ---------------------------------------------------------------- premio
    async def premia(self, guild: discord.Guild, user_id: int):
        """Il voto in attesa diventa il premio di questo server; None se non c'è nulla da riscattare."""
        i = (await leveling_settings_repo.get_config(guild.id)).impostazioni
        premio = await voto_repo.riscatta(guild.id, user_id, tetto_livello=i.max_level, formula=i.formula)
        if premio is None:
            return None
        if premio.premium_giorni:
            try:
                await applica_sblocco(guild.id, None, premio.premium_giorni, None)
            except Exception:
                logger.exception("Premium a tempo del voto non dato (server %s).", guild.id)
        livelli = self.bot.get_cog("LevelingCog")
        membro = guild.get_member(user_id)
        if premio.xp and livelli is not None and membro is not None:
            await livelli.sincronizza_server(guild, [user_id])
        return premio

    async def _dopo_voto(self, user_id: int) -> None:
        """ECO-049: se la persona ha scelto un server per il riscatto automatico, il premio arriva subito."""
        guild_id = await voto_repo.auto_di(user_id)
        guild = self.bot.get_guild(guild_id) if guild_id else None
        if guild is None:
            return
        if await self.premia(guild, user_id) is None:
            return
        utente = self.bot.get_user(user_id)
        if utente is not None:
            try:
                await utente.send(f"🗳️ Grazie per il voto! Il premio di **{guild.name[:60]}** è già tuo.")
            except discord.HTTPException:
                pass

    # ---------------------------------------------------------------- comandi
    @comando_di_gruppo("monete", nome="voto", descrizione="Riscatta il premio per aver votato il bot, o scegli il riscatto automatico.", sottogruppo=_SG_CONTO)
    @app_commands.describe(automatico="Sì = il premio arriva da solo in questo server a ogni voto; No = lo spegni")
    async def voto(self, interaction: discord.Interaction, automatico: bool | None = None) -> None:
        if await _comando_rifiutato(interaction):
            return
        if not modulo_acceso():
            await interaction.response.send_message(await testo_per(interaction, "voto_spento"), ephemeral=True)
            return
        g, u = interaction.guild, interaction.user.id
        if automatico is not None:
            await voto_repo.imposta_auto(u, g.id if automatico else None)
            await interaction.response.send_message(await testo_per(interaction, "voto_auto_si" if automatico else "voto_auto_no"), ephemeral=True)
            return
        i = await voto_repo.impostazioni(g.id)
        if not i["attivo"]:
            await interaction.response.send_message(await testo_per(interaction, "voto_server_spento", n=await voto_repo.da_riscattare(u)), ephemeral=True)
            return
        premio = await self.premia(g, u)
        if premio is None:
            await interaction.response.send_message(await testo_per(interaction, "voto_niente", sito=SITO_TOPGG), ephemeral=True)
            return
        moneta = (await leveling_settings_repo.get_config(g.id)).impostazioni.currency_name
        await interaction.response.send_message(
            await testo_per(interaction, "voto_premio", monete=premio.monete, moneta=moneta, xp=premio.xp, pct=premio.bonus_pct, ore=premio.bonus_ore, giorni=premio.premium_giorni),
            ephemeral=True,
        )

    @comando_di_gruppo("admin-giochi", nome="voto", descrizione="Il premio che il server dà a chi vota il bot (senza valori: lo stato).")
    @app_commands.describe(
        attivo="Accendi o spegni il premio", monete="Monete per voto (0-100000)", xp="XP per voto (0-100000)",
        bonus_xp="Bonus XP in % dopo il voto (0-100, 0 = nessuno)", bonus_ore="Ore di durata del bonus XP (1-48)", premium_giorni="Giorni di premium per voto (0-30, 0 = nessuno)",
    )
    async def voto_admin(
        self, interaction: discord.Interaction, attivo: bool | None = None, monete: app_commands.Range[int, 0, 100_000] | None = None,
        xp: app_commands.Range[int, 0, 100_000] | None = None, bonus_xp: app_commands.Range[int, 0, 100] | None = None,
        bonus_ore: app_commands.Range[int, 1, 48] | None = None, premium_giorni: app_commands.Range[int, 0, 30] | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        campi = {k: v for k, v in {"attivo": attivo, "monete": monete, "xp": xp, "xp_bonus_pct": bonus_xp, "xp_bonus_ore": bonus_ore, "premium_giorni": premium_giorni}.items() if v is not None}
        if campi:
            await voto_repo.imposta(interaction.guild.id, **campi)
        i = await voto_repo.impostazioni(interaction.guild.id)
        await interaction.response.send_message(
            await testo_per(
                interaction, "voto_stato", chiave="✅" if modulo_acceso() else "❌", attivo="✅" if i["attivo"] else "❌", monete=i["monete"], xp=i["xp"],
                pct=i["xp_bonus_pct"], ore=i["xp_bonus_ore"], giorni=i["premium_giorni"],
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VotoCog(bot))
