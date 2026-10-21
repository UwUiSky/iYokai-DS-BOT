"""
cogs/utility/config_strumenti.py
================================
Strumenti di configurazione del server e informazioni sul bot (#122): `/admin config pulizia` (CFG-019),
`/admin config sincronizza` (CFG-020), `/admin config nickname-bot` (CFG-021) e `/utility info` (CFG-046).
Funzioni coperte: SPEC §20 (NF-05), catalogo #122, parte E (D15)
Dipende da: core/bot_aspetto.py, core/config_cleanup_logic.py, core/command_permissions.py, core/bot_info.py, core/bot_roles.py
"""

from __future__ import annotations

import platform
import time

import discord
from discord import app_commands
from discord.ext import commands

from core import bot_info, bot_roles
from core.bot_aspetto import applica_aspetto
from core.command_permissions import (
    STATO_DA_RIPROVARE,
    STATO_SENZA_AUTORIZZAZIONE,
    STATO_TOKEN_NON_VALIDO,
    risincronizza_server,
)
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.config import config
from core.config_cleanup_logic import pulisci_configurazione
from core.i18n import lingua_interazione, t, testo_per

SOTTOGRUPPO_CONFIG = ("config", "Configurazione: canali, storico, ripristino ed esportazione")
ATTESA_SYNC_SECONDI = 300
MAX_VOCI_ANTEPRIMA = 15


def elenco_anteprima(voci) -> str:
    """Una riga per chiave: quanti ID morti e di che tipo. Tagliato per stare nel messaggio."""
    righe = [f"- `{v.chiave}` ({v.tipo}): {', '.join(str(i) for i in v.morti[:5])}" for v in voci[:MAX_VOCI_ANTEPRIMA]]
    if len(voci) > MAX_VOCI_ANTEPRIMA:
        righe.append(f"... +{len(voci) - MAX_VOCI_ANTEPRIMA}")
    return "\n".join(righe)


def riassumi_esiti(esiti: dict) -> tuple[str, dict]:
    """Da {tipo di ruolo: esito} alla chiave del messaggio e ai suoi valori."""
    presenti = [e for e in esiti.values() if e is not None]
    if not esiti:
        return "cfg_sync_nessun_ruolo", {}
    if not presenti or any(e.stato == STATO_SENZA_AUTORIZZAZIONE for e in presenti):
        return "cfg_sync_non_autorizzato", {}
    if any(e.stato == STATO_TOKEN_NON_VALIDO for e in presenti):
        return "cfg_sync_token_non_valido", {}
    if any(e.errori or e.stato == STATO_DA_RIPROVARE for e in presenti):
        gruppi = sorted({g for e in presenti for g in e.errori}) or ["-"]
        return "cfg_sync_parziale", {"gruppi": ", ".join(gruppi)}
    return "cfg_sync_ok", {"tipi": ", ".join(esiti)}


class ConfigStrumentiCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._ultima_sync: dict[int, float] = {}
        self._sync_in_corso: set[int] = set()

    # ------------------------------------------------------------------
    @comando_di_gruppo(
        "admin", nome="pulizia", descrizione="Toglie dalla configurazione canali e ruoli che non esistono più.",
        sottogruppo=SOTTOGRUPPO_CONFIG,
    )
    @app_commands.describe(applica="Sì = toglie davvero; No = mostra solo cosa toglierebbe")
    async def pulizia(self, interaction: discord.Interaction, applica: bool = False) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None or not guild.roles:
            await interaction.followup.send(await testo_per(interaction, "cfg_pulizia_non_pronto"), ephemeral=True)
            return
        esito = await pulisci_configurazione(guild, applica=applica, changed_by=interaction.user.id)
        if not esito.voci:
            testo = await testo_per(interaction, "cfg_pulizia_niente")
        elif applica:
            testo = await testo_per(interaction, "cfg_pulizia_fatta", n=esito.totale)
        else:
            testo = await testo_per(
                interaction, "cfg_pulizia_anteprima", n=esito.totale, elenco=elenco_anteprima(esito.voci)
            )
        await interaction.followup.send(testo[:1900], ephemeral=True)

    # ------------------------------------------------------------------
    @comando_di_gruppo(
        "admin", nome="sincronizza", descrizione="Riscrive i permessi dei comandi di questo server.",
        sottogruppo=SOTTOGRUPPO_CONFIG,
    )
    async def sincronizza(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        adesso = time.monotonic()
        trascorso = adesso - self._ultima_sync.get(guild.id, -ATTESA_SYNC_SECONDI)
        if trascorso < ATTESA_SYNC_SECONDI:
            await interaction.response.send_message(
                await testo_per(interaction, "cfg_sync_attesa", secondi=int(ATTESA_SYNC_SECONDI - trascorso) + 1),
                ephemeral=True,
            )
            return
        if guild.id in self._sync_in_corso:
            await interaction.response.send_message(await testo_per(interaction, "cfg_sync_in_corso"), ephemeral=True)
            return
        self._sync_in_corso.add(guild.id)
        try:
            await interaction.response.defer(ephemeral=True)
            esiti = await risincronizza_server(self.bot, guild)
        finally:
            self._sync_in_corso.discard(guild.id)
        chiave, valori = riassumi_esiti(esiti)
        if chiave == "cfg_sync_ok":  # l'attesa scatta solo se è riuscita: chi ha sbagliato può riprovare subito
            self._ultima_sync[guild.id] = time.monotonic()
        await interaction.followup.send(await testo_per(interaction, chiave, **valori), ephemeral=True)

    # ------------------------------------------------------------------
    @comando_di_gruppo(
        "admin", nome="nickname-bot", descrizione="Cambia il nome del bot in questo server.",
        sottogruppo=SOTTOGRUPPO_CONFIG,
    )
    @app_commands.describe(nome="Il nuovo nome (massimo 32 caratteri); vuoto = torna al nome normale")
    async def nickname_bot(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, 32] | None = None
    ) -> None:
        nuovo = nome.strip() if nome else None
        chiave = await applica_aspetto(self.bot, interaction.guild, interaction.user.id, nick=nuovo)
        if chiave != "asp_ok":
            chiave = "cfg_nick_errore" if chiave == "asp_errore" else chiave
            await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)
            return
        testo = await testo_per(interaction, "cfg_nick_ok", nome=nuovo) if nuovo else await testo_per(interaction, "cfg_nick_azzerato")
        await interaction.response.send_message(testo, ephemeral=True)

    # ------------------------------------------------------------------
    @comando_di_gruppo("utility", nome="info", descrizione="Informazioni sul bot: versione, invito e supporto.")
    async def info(self, interaction: discord.Interaction) -> None:
        lingua = await lingua_interazione(interaction)
        nome = self.bot.user.name if self.bot.user else "iYokai"
        embed = discord.Embed(title=t("info_titolo", lingua, nome=nome), color=discord.Color.blurple())
        embed.add_field(name=t("info_server", lingua), value=str(len(self.bot.guilds)))
        embed.add_field(name=t("info_latenza", lingua), value=f"{self.bot.latency * 1000:.0f} ms")
        embed.add_field(name=t("info_codice", lingua), value=f"`{bot_info.versione_codice()}`")
        embed.add_field(
            name=t("info_librerie", lingua),
            value=f"Python {platform.python_version()} · discord.py {discord.__version__}",
            inline=False,
        )
        collegamenti = []
        invito = bot_info.url_invito(self.bot.application_id)
        if invito:
            collegamenti.append(f"[{t('info_invito', lingua)}]({invito})")
        if config.SUPPORT_SERVER_URL.startswith(("https://", "http://")):
            collegamenti.append(f"[{t('info_supporto', lingua)}]({config.SUPPORT_SERVER_URL})")
        if collegamenti:
            embed.add_field(name="​", value=" · ".join(collegamenti), inline=False)
        embed.add_field(name=t("info_mod", lingua), value=_stato_mod(interaction.guild_id, lingua), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


def _stato_mod(guild_id: int | None, lingua: str) -> str:
    """Se iYokai Mod lavora in questo server; se manca, il link per invitarlo (D15)."""
    mod = bot_roles.client_mod()
    if mod is None or mod.application_id is None:
        return t("info_mod_spento", lingua)
    if guild_id is not None and bot_roles.server_mod(guild_id) is not None:
        return t("info_mod_attivo", lingua)
    return t("info_mod_assente", lingua, url=bot_info.url_invito_mod(mod.application_id, guild_id))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ConfigStrumentiCog(bot))
