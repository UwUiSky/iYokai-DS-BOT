"""
cogs/leveling/stipendi.py
=========================
Stipendi e tasse per ruolo (/admin-giochi stipendi ..., /monete riscuoti), pagamento automatico a un'ora
scelta (UTC) e monete per i messaggi nei canali scelti (/admin-giochi stipendi auto). Ogni pagamento è
una transazione sola (core/repositories/stipendi_repo.py).
Funzioni coperte: ECO-033, ECO-034, ECO-035, ECO-036, ECO-037, ECO-038
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.leveling.leveling import MODULE_LEVELING, _comando_rifiutato, _format_seconds
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.database import db
from core.i18n import testo_per
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.stipendi_repo import EsitoRiscossione, PAUSA_STIPENDIO, stipendi_repo

logger = logging.getLogger("iyokai.leveling.stipendi")
NESSUNA_MENZIONE = discord.AllowedMentions.none()
_SG = ("stipendi", "Stipendi per ruolo e monete per messaggio")
MAX_MEMBRI_GIRO = 5000
PAUSA_TRA_PERSONE = 0.02


class StipendiCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._ultimo: dict[tuple[int, int], float] = {}
        self._canali: dict[int, tuple[float, set[int]]] = {}
        self._giro.start()

    def cog_unload(self) -> None:
        self._giro.cancel()
        togli_comandi_del_cog(self)

    # ---------------------------------------------------------------- ECO-033: monete per messaggio
    async def _canali_del_server(self, guild_id: int) -> set[int]:
        voce = self._canali.get(guild_id)
        if voce is not None and time.monotonic() - voce[0] < 60:
            return voce[1]
        canali = await stipendi_repo.canali_monete(guild_id)
        self._canali[guild_id] = (time.monotonic(), canali)
        return canali

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot or message.type not in (discord.MessageType.default, discord.MessageType.reply):
            return
        try:
            if message.channel.id not in await self._canali_del_server(message.guild.id):
                return
            i = (await leveling_settings_repo.get_config(message.guild.id)).impostazioni
            if i.msg_coins <= 0:
                return
            chiave = (message.guild.id, message.author.id)
            adesso = time.monotonic()
            if adesso - self._ultimo.get(chiave, -1e9) < i.msg_coins_pausa:
                return
            if not await db.is_module_active_for_guild(message.guild.id, MODULE_LEVELING):
                return
            self._ultimo[chiave] = adesso
            await stipendi_repo.monete_messaggio(
                message.guild.id, message.author.id, datetime.now(timezone.utc).date(), i.msg_coins, i.msg_coins_tetto
            )
        except Exception:
            logger.warning("Monete per messaggio non date (server %s)", message.guild.id, exc_info=True)

    # ---------------------------------------------------------------- ECO-034: riscuoti
    @comando_di_gruppo("monete", nome="riscuoti", descrizione="Riscuoti lo stipendio dei tuoi ruoli (e paga le tasse).")
    async def riscuoti(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        ruoli = [r.id for r in getattr(interaction.user, "roles", [])]
        r = await stipendi_repo.riscuoti(interaction.guild.id, interaction.user.id, ruoli)
        if r.esito is EsitoRiscossione.NESSUNO:
            await interaction.response.send_message(await testo_per(interaction, "stp_nessuno"), ephemeral=True)
            return
        if r.esito is EsitoRiscossione.PAUSA:
            await interaction.response.send_message(await testo_per(interaction, "stp_pausa", tempo=_format_seconds(PAUSA_STIPENDIO)), ephemeral=True)
            return
        moneta = (await leveling_settings_repo.get_config(interaction.guild.id)).impostazioni.currency_name
        await interaction.response.send_message(
            await testo_per(interaction, "stp_fatto", contanti=r.contanti, banca=r.banca, tassa=r.tassa, moneta=moneta), ephemeral=True
        )

    # ---------------------------------------------------------------- ECO-035/037: giro automatico
    @tasks.loop(minutes=10)
    async def _giro(self) -> None:
        adesso = datetime.now(timezone.utc)
        for guild in list(self.bot.guilds):
            try:
                i = (await leveling_settings_repo.get_config(guild.id)).impostazioni
                if not i.stipendio_auto or adesso.hour != i.stipendio_ora:
                    continue
                if not await db.is_module_active_for_guild(guild.id, MODULE_LEVELING):
                    continue
                if not await stipendi_repo.giro_automatico(guild.id, adesso.date()):
                    continue
                await self._paga_server(guild)
            except Exception:
                logger.exception("Giro degli stipendi (server %s)", guild.id)

    @_giro.before_loop
    async def _prima(self) -> None:
        await self.bot.wait_until_ready()

    async def _paga_server(self, guild: discord.Guild) -> int:
        import asyncio

        voci = {v["role_id"] for v in await stipendi_repo.elenco(guild.id)}
        pagati = 0
        for membro in list(guild.members)[:MAX_MEMBRI_GIRO]:
            if membro.bot or not voci & {r.id for r in membro.roles}:
                continue
            r = await stipendi_repo.riscuoti(guild.id, membro.id, [x.id for x in membro.roles])
            pagati += r.esito is EsitoRiscossione.FATTO
            await asyncio.sleep(PAUSA_TRA_PERSONE)
        return pagati

    # ---------------------------------------------------------------- admin
    @comando_di_gruppo("admin-giochi", nome="imposta", descrizione="Stipendio (positivo) o tassa (negativo) per un ruolo.", sottogruppo=_SG)
    @app_commands.describe(ruolo="Il ruolo", importo="Monete a ogni riscossione (da -100000 a 100000, non zero)", in_banca="Sì = lo stipendio va in banca")
    async def imposta(
        self, interaction: discord.Interaction, ruolo: discord.Role,
        importo: app_commands.Range[int, -100_000, 100_000], in_banca: bool = False,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        if importo == 0 or ruolo.is_default():
            await interaction.response.send_message(await testo_per(interaction, "stp_valore"), ephemeral=True)
            return
        if not await stipendi_repo.imposta(interaction.guild.id, ruolo.id, importo, in_banca):
            await interaction.response.send_message(await testo_per(interaction, "stp_pieno"), ephemeral=True)
            return
        await interaction.response.send_message(await testo_per(interaction, "eco_salvato"), ephemeral=True)

    @comando_di_gruppo("admin-giochi", nome="toglie", descrizione="Toglie lo stipendio o la tassa di un ruolo.", sottogruppo=_SG)
    @app_commands.describe(ruolo="Il ruolo")
    async def toglie(self, interaction: discord.Interaction, ruolo: discord.Role) -> None:
        if await _comando_rifiutato(interaction):
            return
        fatto = await stipendi_repo.rimuovi(interaction.guild.id, ruolo.id)
        await interaction.response.send_message(await testo_per(interaction, "eco_salvato" if fatto else "stp_valore"), ephemeral=True)

    @comando_di_gruppo("admin-giochi", nome="elenco", descrizione="Gli stipendi e le tasse per ruolo, e le regole dei messaggi.", sottogruppo=_SG)
    async def elenco(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        voci = await stipendi_repo.elenco(interaction.guild.id)
        canali = await stipendi_repo.canali_monete(interaction.guild.id)
        i = (await leveling_settings_repo.get_config(interaction.guild.id)).impostazioni
        righe = [f"<@&{v['role_id']}> {v['importo']:+d} {'(banca)' if v['in_banca'] else ''}" for v in voci] or ["-"]
        righe.append(f"Auto: {'sì' if i.stipendio_auto else 'no'} alle {i.stipendio_ora}:00 UTC")
        righe.append(f"Messaggi: {i.msg_coins} ogni {i.msg_coins_pausa}s, tetto {i.msg_coins_tetto} al giorno; canali: " + (" ".join(f"<#{c}>" for c in sorted(canali)) or "-"))
        await interaction.response.send_message("\n".join(righe)[:3900], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("admin-giochi", nome="auto", descrizione="Paga gli stipendi da solo a un'ora (UTC) e scegli le monete per messaggio.", sottogruppo=_SG)
    @app_commands.describe(
        attivo="Sì = paga gli stipendi da solo ogni giorno", ora="Ora UTC del pagamento (0-23)",
        monete_messaggio="Monete per messaggio nei canali scelti (0 = spento)", pausa="Secondi tra due messaggi che pagano",
        tetto_giorno="Monete al giorno per persona", aggiungi_canale="Un canale dove i messaggi pagano", togli_canale="Un canale da togliere",
    )
    async def auto(
        self, interaction: discord.Interaction, attivo: bool | None = None,
        ora: app_commands.Range[int, 0, 23] | None = None,
        monete_messaggio: app_commands.Range[int, 0, 100] | None = None,
        pausa: app_commands.Range[int, 10, 3600] | None = None,
        tetto_giorno: app_commands.Range[int, 1, 10_000] | None = None,
        aggiungi_canale: discord.TextChannel | None = None, togli_canale: discord.TextChannel | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        campi = {"stipendio_auto": attivo, "stipendio_ora": ora, "msg_coins": monete_messaggio,
                 "msg_coins_pausa": pausa, "msg_coins_tetto": tetto_giorno}
        campi = {k: v for k, v in campi.items() if v is not None}
        if not campi and aggiungi_canale is None and togli_canale is None:
            await interaction.response.send_message(await testo_per(interaction, "eco_scegli_un_valore"), ephemeral=True)
            return
        try:
            if campi:
                await leveling_settings_repo.set_options(interaction.guild.id, **campi)
            if aggiungi_canale is not None and not await stipendi_repo.aggiungi_canale(interaction.guild.id, aggiungi_canale.id):
                await interaction.response.send_message(await testo_per(interaction, "stp_pieno"), ephemeral=True)
                return
            if togli_canale is not None:
                await stipendi_repo.togli_canale(interaction.guild.id, togli_canale.id)
        except ValueError as errore:
            await interaction.response.send_message(f"❌ {errore}", ephemeral=True)
            return
        self._canali.pop(interaction.guild.id, None)
        await interaction.response.send_message(await testo_per(interaction, "eco_salvato"), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StipendiCog(bot))
