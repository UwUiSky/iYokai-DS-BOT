"""
cogs/utility/premium_server.py
==============================
Premium di un server: `/admin premium stato|riscatta|sblocca` (NF-22, #93) e gli eventi degli abbonamenti Discord (app premium).
Funzioni coperte: SPEC §3, §3.1 (NF-22)
Dipende da: core/premium_entitlement_service.py, core/premium_modulo_service.py, core/premium.py
"""

from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from core.bot_ready import attendi_bot_pronto
from core.command_access import Livello, autocomplete_protetto
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.config import config
from core.i18n import testo_per
from discord import app_commands

from core.premium import get_guild_premium_breakdown, registry
from core.premium_modulo_service import EsitoSblocco, sblocca_modulo_con_cassa
from core.premium_pricing_logic import COSTO_MODULO_IN_COIN, GIORNI_MODULO_IN_COIN
from core.ui_base import BaseView
from core.premium_code_service import TroppiTentativi, riscatta_codice
from core.premium_entitlement_service import allinea_con_discord, registra_evento
from core.premium_status_logic import righe_stato_server
from core.repositories.module_subscription_repo import module_subscription_repo

logger = logging.getLogger("iyokai.premium")

SOTTOGRUPPO_PREMIUM = ("premium", "Premium del server: stato, codici e marchio")


def url_negozio(application_id: int | None) -> str | None:
    """Il negozio dell'app dentro Discord (dove si compra l'abbonamento)."""
    if not application_id:
        return None
    return "/".join(("https://discord.com/application-directory", str(application_id), "store"))


class ConfermaSblocco(BaseView):
    """Due passaggi: lo sblocco spende 1.000.000 di coin della cassa, non si fa con un clic solo."""

    def __init__(self, guild_id: int, user_id: int, modulo: str) -> None:
        super().__init__(timeout=60)
        self.guild_id, self.user_id, self.modulo = guild_id, user_id, modulo
        self._usata = False

    @discord.ui.button(label="Conferma e spendi", style=discord.ButtonStyle.success)
    async def conferma(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        # Due clic veloci arrivano entrambi qui (la vista prima attende il controllo della lista nera):
        # il segno si mette prima di ogni await, così si spende una volta sola.
        if self._usata:
            await interaction.response.defer()
            return
        self._usata = True
        self.stop()
        r = await sblocca_modulo_con_cassa(self.guild_id, self.modulo, self.user_id)
        if r.esito is EsitoSblocco.SBLOCCATO:
            testo = await testo_per(
                interaction, "prem_sblocca_ok", modulo=self.modulo, data=r.scade_il.date().isoformat()
            )
        else:
            testo = await testo_per(interaction, f"prem_sblocca_{r.esito.value}", costo=f"{r.costo:,}".replace(",", "."))
        await interaction.response.edit_message(content=testo, view=None)

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def annulla(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._usata:  # la conferma è già partita: «annullato» sarebbe falso
            await interaction.response.defer()
            return
        self._usata = True
        self.stop()
        await interaction.response.edit_message(content=await testo_per(interaction, "prem_sblocca_annullato"), view=None)


class PremiumServerCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._allineamento: asyncio.Task | None = None

    async def cog_load(self) -> None:
        await super().cog_load()
        self._allineamento = asyncio.create_task(self._allinea_all_avvio())

    async def cog_unload(self) -> None:
        if self._allineamento is not None:
            self._allineamento.cancel()
        await super().cog_unload()

    async def _allinea_all_avvio(self) -> None:
        """Dopo `attendi_bot_pronto`: rilegge gli abbonamenti Discord. Un errore non ferma il bot."""
        try:
            await attendi_bot_pronto(self.bot)
            registrati = await allinea_con_discord(self.bot)
            logger.info("Abbonamenti Discord allineati: %d.", registrati)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Allineamento degli abbonamenti Discord fallito.", exc_info=True)

    # ------------------------------------------------------------------
    # Eventi di Discord (discord.py 2.4+)
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_entitlement_create(self, entitlement: discord.Entitlement) -> None:
        await self._registra(entitlement, eliminato=False)

    @commands.Cog.listener()
    async def on_entitlement_update(self, entitlement: discord.Entitlement) -> None:
        await self._registra(entitlement, eliminato=False)

    @commands.Cog.listener()
    async def on_entitlement_delete(self, entitlement: discord.Entitlement) -> None:
        await self._registra(entitlement, eliminato=True)

    async def _registra(self, entitlement: discord.Entitlement, *, eliminato: bool) -> None:
        try:
            await registra_evento(entitlement, eliminato=eliminato)
        except Exception:
            logger.warning("Abbonamento Discord %s non registrato.", getattr(entitlement, "id", "?"), exc_info=True)

    # ------------------------------------------------------------------
    @comando_di_gruppo(
        "admin", nome="stato", descrizione="Mostra come è sbloccato il premium in questo server.",
        sottogruppo=SOTTOGRUPPO_PREMIUM,
    )
    async def stato(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        dettaglio = await get_guild_premium_breakdown(guild.id, bot=self.bot)
        scadenze = [
            f"`{s.module_name}` fino al {s.expires_at.date().isoformat()}"
            for s in await module_subscription_repo.list_for_guild(guild.id)
        ]
        righe = righe_stato_server(dettaglio, scadenze)
        if config.PREMIUM_ALPHA_UNLOCK_ALL:
            righe.append(await testo_per(interaction, "prem_stato_alpha"))
        corpo = "\n".join(f"- {r}" for r in righe) or await testo_per(interaction, "prem_stato_nessuno")
        negozio = url_negozio(self.bot.application_id)
        corpo += "\n\n" + (
            await testo_per(interaction, "prem_stato_acquista", url=negozio)
            if negozio
            else await testo_per(interaction, "prem_stato_acquista_senza_negozio")
        )
        embed = discord.Embed(
            title=await testo_per(interaction, "prem_stato_titolo"), description=corpo[:3900], color=discord.Color.gold()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @comando_di_gruppo(
        "admin", nome="riscatta", descrizione="Riscatta un codice premium per questo server.",
        sottogruppo=SOTTOGRUPPO_PREMIUM,
    )
    @app_commands.describe(codice="Il codice che hai ricevuto, es. YOKAI-ABCD-EFGH-JKMN")
    async def riscatta(self, interaction: discord.Interaction, codice: app_commands.Range[str, 1, 40]) -> None:
        try:
            esito = await riscatta_codice(codice, interaction.user.id, interaction.guild.id)
        except TroppiTentativi:
            await interaction.response.send_message(await testo_per(interaction, "prem_riscatta_attesa"), ephemeral=True)
            return
        if esito is None:
            await interaction.response.send_message(await testo_per(interaction, "prem_riscatta_non_valido"), ephemeral=True)
            return
        modulo, scadenza = esito
        data = scadenza.date().isoformat()
        chiave = "prem_riscatta_ok_modulo" if modulo else "prem_riscatta_ok_tutti"
        await interaction.response.send_message(
            await testo_per(interaction, chiave, modulo=modulo or "", data=data), ephemeral=True
        )

    @autocomplete_protetto(Livello.ADMIN)
    async def _moduli_premium(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        trovati = [
            m for m in registry.all_modules()
            if registry.is_module_premium(m.name) and current.lower() in f"{m.name} {m.display_name}".lower()
        ]
        return [app_commands.Choice(name=m.display_name[:100], value=m.name) for m in trovati[:25]]

    @comando_di_gruppo(
        "admin", nome="sblocca",
        descrizione="Sblocca un modulo premium per 30 giorni con le monete della cassa del server.",
        sottogruppo=SOTTOGRUPPO_PREMIUM,
    )
    @app_commands.describe(modulo="Il modulo premium da sbloccare (costa 1.000.000 coin dalla cassa)")
    @app_commands.autocomplete(modulo=_moduli_premium)
    async def sblocca(self, interaction: discord.Interaction, modulo: app_commands.Range[str, 1, 100]) -> None:
        costo = f"{COSTO_MODULO_IN_COIN:,}".replace(",", ".")
        vista = ConfermaSblocco(interaction.guild.id, interaction.user.id, modulo)
        await interaction.response.send_message(
            await testo_per(interaction, "prem_sblocca_chiedi", modulo=modulo, costo=costo, giorni=GIORNI_MODULO_IN_COIN),
            view=vista, ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PremiumServerCog(bot))
