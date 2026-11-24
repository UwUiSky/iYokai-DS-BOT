"""
cogs/utility/premium_server.py
==============================
Premium di un server: `/admin-bot premium stato|riscatta|sblocca` (NF-22, #93) e gli eventi degli abbonamenti Discord (app premium).
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
from core.ui_base import BaseModal, BaseView
from core.premium_code_service import TroppiTentativi, riscatta_codice
from core.premium_entitlement_service import allinea_con_discord, registra_evento
from core.premium_posti_service import Esito, assegna, posto_del_server, stato_utente, togli
from core.piani_comandi import esegui_chiave
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
        "admin-bot", nome="stato", descrizione="Mostra come è sbloccato il premium in questo server.",
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
        proprietario_posto = await posto_del_server(guild.id)
        if proprietario_posto is not None:  # CFG-034/035: il posto di una persona su questo server
            righe.append(await testo_per(interaction, "posti_stato_server", utente=f"<@{proprietario_posto}>"))
        suoi = await stato_utente(interaction.user.id)
        if suoi is not None:
            righe.append(await testo_per(interaction, "posti_stato_tuoi", usati=suoi.usati, posti=suoi.posti))
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
        "admin-bot", nome="assegna", descrizione="Metti uno dei tuoi posti premium su questo server.",
        sottogruppo=SOTTOGRUPPO_PREMIUM,
    )
    async def assegna_posto(self, interaction: discord.Interaction) -> None:
        esito = await assegna(interaction.user.id, interaction.guild.id)
        await interaction.response.send_message(
            await testo_per(interaction, f"posti_{esito.value}"), ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @comando_di_gruppo(
        "admin-bot", nome="togli-posto", descrizione="Togli il tuo posto premium da questo server.",
        sottogruppo=SOTTOGRUPPO_PREMIUM,
    )
    async def togli_posto(self, interaction: discord.Interaction) -> None:
        esito = await togli(interaction.user.id, interaction.guild.id)
        await interaction.response.send_message(
            await testo_per(interaction, "posti_tolto" if esito is Esito.FATTO else "posti_non_suo"), ephemeral=True
        )

    @comando_di_gruppo(
        "admin-bot", nome="riscatta", descrizione="Riscatta un codice premium per questo server.",
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
        "admin-bot", nome="sblocca",
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


    @comando_di_gruppo(
        "admin-bot", nome="chiave", descrizione="Usa la tua chiave API per i servizi AI: dà il livello VIP.",
        sottogruppo=SOTTOGRUPPO_PREMIUM,
    )
    @app_commands.describe(
        azione="Metti, togli o elenca le chiavi",
        ambito="Per questo server o solo per te",
        servizio="Il servizio (es. gemini); vuoto = tutti, solo per «togli»",
    )
    @app_commands.choices(
        azione=[app_commands.Choice(name=n, value=v) for n, v in (("Metti una chiave", "imposta"), ("Togli", "togli"), ("Elenca", "elenco"))],
        ambito=[app_commands.Choice(name=n, value=v) for n, v in (("Questo server", "server"), ("Solo io", "utente"))],
    )
    async def chiave(
        self, interaction: discord.Interaction, azione: app_commands.Choice[str], ambito: app_commands.Choice[str],
        servizio: app_commands.Range[str, 1, 40] | None = None,
    ) -> None:
        ambito_id = interaction.guild.id if ambito.value == "server" else interaction.user.id
        if azione.value == "imposta":
            await interaction.response.send_modal(ModaleChiave(ambito.value, ambito_id, (servizio or "").strip().lower()))
            return
        testo = await esegui_chiave(
            azione.value, ambito=ambito.value, ambito_id=ambito_id,
            servizio=(servizio or "").strip().lower() or None, chiave=None, utente_id=interaction.user.id,
            t=lambda k, **kw: testo_per(interaction, k, **kw),
        )
        await interaction.response.send_message(testo, ephemeral=True)


class ModaleChiave(BaseModal, title="Chiave API del servizio AI"):
    """La chiave si scrive qui e non nel comando: non resta nei suggerimenti né nella cronologia dei comandi."""

    servizio = discord.ui.TextInput(label="Servizio (es. gemini)", min_length=1, max_length=40)
    chiave = discord.ui.TextInput(label="Chiave API", min_length=8, max_length=400)

    def __init__(self, ambito: str, ambito_id: int, servizio: str) -> None:
        super().__init__()
        self.ambito, self.ambito_id = ambito, ambito_id
        self.servizio.default = servizio or None

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.ambito == "server" and not (
            interaction.guild is not None and interaction.guild.id == self.ambito_id
            and interaction.permissions.manage_guild
        ):  # il permesso si rilegge ora, non alla scrittura del comando
            await interaction.response.send_message(await testo_per(interaction, "accesso_admin"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)  # la prova in rete può superare i 3 secondi
        testo = await esegui_chiave(
            "imposta", ambito=self.ambito, ambito_id=self.ambito_id, servizio=str(self.servizio).strip().lower(),
            chiave=str(self.chiave).strip(), utente_id=interaction.user.id,
            t=lambda k, **kw: testo_per(interaction, k, **kw),
        )
        await interaction.followup.send(testo, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PremiumServerCog(bot))
