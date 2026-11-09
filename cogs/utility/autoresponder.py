"""
cogs/utility/autoresponder.py
=============================
Risposte automatiche (NF-10, SPEC §14.7): quando un messaggio contiene una
parola o frase scelta, il bot risponde da solo. Condizioni: canale, ruolo,
corrispondenza esatta o parziale. Comandi: `risposta-...` di `/admin-messaggi`.
Richiede l'intent `message_content` (D9).
Funzioni coperte: SPEC §14.7 (NF-10)
"""

from __future__ import annotations

import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

from core.admin_mentions_logic import menzioni_ammesse, utente_puo_pingare_ruoli
from core.autoresponder_logic import (
    regex_valida,
    resto_dopo,
    trigger_corrisponde,
    MAX_JOLLY,
    MAX_RISPOSTA,
    MAX_RISPOSTE,
    MAX_REGEX,
    MAX_TRIGGER,
    PAUSA_CANALE_SECONDI,
    jolly_validi,
    scegli_risposta,
)
from core.bounded_cache import BoundedCache
from core.command_access import Livello, puo_usare
from core.command_groups import CogConGruppi, SOTTOGRUPPI, comando_di_gruppo
from core.database import db
from core.i18n import testo_per
from core.lista_limiti_logic import righe_entro_limite
from core.premium import PremiumModule, registry
from core.repositories.autoresponder_repo import autoresponder_repo
from core.repositories.autorisposte_globali_repo import autorisposte_globali_repo
from core.ui_base import BaseView
from core.template_renderer import render_template

logger = logging.getLogger("iyokai.autoresponder")

MODULE_AUTORESPONDER = "autoresponder"

_SG_COMANDI = ("comandi", "Comandi personalizzati e risposte automatiche")
_TTL_REGOLE = 30  # secondi

# server -> (regole, scadenza); (regola, canale) -> istante dell'ultima risposta
_cache_regole: BoundedCache[int, tuple[list, float]] = BoundedCache(max_size=5_000)
_cache_globali: BoundedCache[int, tuple[list, float]] = BoundedCache(max_size=2)
_cache_spente: BoundedCache[int, tuple[bool, float]] = BoundedCache(max_size=5_000)
_ultima_risposta: BoundedCache[tuple[int, int], float] = BoundedCache(max_size=20_000)

_SCELTE_MODO = [
    app_commands.Choice(name="parola o frase intera nel messaggio", value="parziale"),
    app_commands.Choice(name="tutto il messaggio uguale", value="esatta"),
    app_commands.Choice(name="il messaggio inizia così (il resto è {resto})", value="inizia"),
    app_commands.Choice(name="espressione regolare (RE2)", value="regex"),
]
SECONDI_CONFERMA = 60


class ConfermaSvuota(BaseView):
    """Svuotare cancella tutte le risposte del server: conferma di chi ha dato il comando, livello ricontrollato al tasto."""

    def __init__(self, proprietario: int, guild_id: int, etichette: tuple[str, str]) -> None:
        super().__init__(timeout=SECONDI_CONFERMA)
        self.proprietario, self.guild_id = proprietario, guild_id
        self.conferma.label, self.annulla.label = etichette[0][:80], etichette[1][:80]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.proprietario:
            await interaction.response.send_message(await testo_per(interaction, "conteggio_non_e_tuo"), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Conferma", style=discord.ButtonStyle.danger)
    async def conferma(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()  # anti-doppio-clic prima di ogni await
        if not await puo_usare(interaction, Livello.ADMIN):
            await interaction.response.edit_message(content=await testo_per(interaction, "conteggio_non_e_tuo"), view=None)
            return
        quante = await autoresponder_repo.svuota(self.guild_id)
        _cache_regole.delete(self.guild_id)
        await interaction.response.edit_message(content=await testo_per(interaction, "risposte_svuotate", quante=quante), view=None)

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def annulla(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content=await testo_per(interaction, "conteggio_togli_annullato"), view=None)


class AutoresponderCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _regole(self, guild_id: int) -> list:
        voce = _cache_regole.get(guild_id)
        ora = time.monotonic()
        if voce is not None and voce[1] > ora:
            return voce[0]
        regole = await autoresponder_repo.list(guild_id)
        _cache_regole.set(guild_id, (regole, ora + _TTL_REGOLE))
        return regole

    async def _globale(self, guild_id: int, testo: str):
        voce = _cache_globali.get(0)
        ora = time.monotonic()
        if voce is None or voce[1] <= ora:
            voce = (await autorisposte_globali_repo.elenco(), ora + _TTL_REGOLE)
            _cache_globali.set(0, voce)
        trovate = [g for g in voce[0] if trigger_corrisponde(g.innesco, "parziale", testo)]
        if not trovate:
            return None
        spente = _cache_spente.get(guild_id)
        if spente is None or spente[1] <= ora:
            spente = (await autorisposte_globali_repo.spente_nel_server(guild_id), ora + _TTL_REGOLE)
            _cache_spente.set(guild_id, spente)
        return None if spente[0] else sorted(trovate, key=lambda g: (-len(g.innesco), g.id))[0]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None or not message.content:
            return
        if not await db.is_module_active_for_guild(message.guild.id, MODULE_AUTORESPONDER):
            return
        regola = scegli_risposta(
            await self._regole(message.guild.id),
            message.content,
            message.channel.id,
            {r.id for r in getattr(message.author, "roles", [])},
        )
        resto = ""
        if regola is not None and regola.match_mode == "inizia":
            resto = resto_dopo(regola.trigger, message.content)
        risposta = regola.response if regola else None
        ping_ruoli = regola.ping_ruoli if regola else False
        if regola is None:  # nessuna risposta del server: provano quelle globali dell'owner (se il server non le ha spente)
            globale = await self._globale(message.guild.id, message.content)
            if globale is None:
                return
            regola = globale
            risposta, ping_ruoli = globale.risposta, False
        chiave = (regola.id if hasattr(regola, "trigger") else -regola.id, message.channel.id)
        ora = time.monotonic()
        ultima = _ultima_risposta.get(chiave)
        if ultima is not None and ora - ultima < PAUSA_CANALE_SECONDI:
            return
        _ultima_risposta.set(chiave, ora)
        testo = render_template(
            risposta,
            {
                "resto": discord.utils.escape_mentions(resto),
                "user": message.author.mention,
                "username": discord.utils.escape_mentions(message.author.display_name),
                "server": message.guild.name,
                "channel": getattr(message.channel, "mention", ""),
            },
        )
        try:
            await message.channel.send(
                testo,
                reference=message,
                mention_author=False,
                allowed_mentions=menzioni_ammesse(ping_ruoli),
            )
        except discord.HTTPException:
            logger.warning("Risposta automatica %s: invio fallito nel canale %s", regola.id, message.channel.id)

    # ================================================================
    # Comandi
    # ================================================================
    async def _pronto(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_AUTORESPONDER):
            await interaction.response.send_message(
                await testo_per(interaction, "ping_questo_modulo_non_attivo_su"),
                ephemeral=True,
            )
            return False
        return True

    @comando_di_gruppo("admin-tag", nome="crea", descrizione="Crea una risposta automatica.", sottogruppo=SOTTOGRUPPI["admin-tag risposte"])
    @app_commands.describe(
        parola="La parola o frase che fa scattare la risposta (* = pezzo di parola)",
        risposta="Cosa risponde il bot. Segnaposto: {user} {username} {server} {channel} {resto}",
        modalita="Come cercare la parola nel messaggio",
        canale="Solo in questo canale (vuoto = ovunque)",
        ruolo="Solo per chi ha questo ruolo (vuoto = tutti)",
    )
    @app_commands.choices(modalita=_SCELTE_MODO)
    async def risposta_crea(
        self,
        interaction: discord.Interaction,
        parola: app_commands.Range[str, 1, MAX_REGEX],
        risposta: app_commands.Range[str, 1, MAX_RISPOSTA],
        modalita: str = "parziale",
        canale: discord.TextChannel | None = None,
        ruolo: discord.Role | None = None,
    ) -> None:
        if not await self._pronto(interaction):
            return
        parola = parola.strip()
        if not parola or not risposta.strip():
            await interaction.response.send_message(
                await testo_per(interaction, "autoresponde_la_parola_la_risposta_non"), ephemeral=True
            )
            return
        if modalita == "regex":
            if (problema := regex_valida(parola)) is not None:
                await interaction.response.send_message(
                    await testo_per(interaction, f"risposte_regex_{problema}", massimo=MAX_REGEX), ephemeral=True)
                return
        elif len(parola) > MAX_TRIGGER:
            await interaction.response.send_message(await testo_per(interaction, "risposte_parola_lunga", massimo=MAX_TRIGGER), ephemeral=True)
            return
        if "{resto}" in risposta and modalita != "inizia":
            await interaction.response.send_message(await testo_per(interaction, "risposte_resto_solo_inizia"), ephemeral=True)
            return
        if modalita != "regex" and not jolly_validi(parola):
            await interaction.response.send_message(
                await testo_per(interaction, "autoresponde_con_il_jolly_servono_lettere", v1=MAX_JOLLY), ephemeral=True
            )
            return
        esito, nuovo_id = await autoresponder_repo.create(
            interaction.guild.id,
            parola,
            match_mode=modalita,
            response=risposta,
            channel_id=canale.id if canale else None,
            role_id=ruolo.id if ruolo else None,
            ping_ruoli=utente_puo_pingare_ruoli(interaction.user),
            created_by=interaction.user.id,
        )
        _cache_regole.delete(interaction.guild.id)
        messaggi = {
            "ok": f"Risposta automatica n. {nuovo_id} creata.",
            "esiste": "Esiste già una risposta con quella parola: eliminala prima con `/admin-tag risposte elimina`.",
            "pieno": f"Questo server ha già {MAX_RISPOSTE} risposte automatiche: eliminane una.",
        }
        await interaction.response.send_message(messaggi[esito], ephemeral=True)

    @comando_di_gruppo("admin-tag", nome="elimina", descrizione="Elimina una risposta automatica.", sottogruppo=SOTTOGRUPPI["admin-tag risposte"])
    @app_commands.describe(numero="Il numero mostrato da /admin-tag risposte elenco")
    async def risposta_elimina(self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 2_000_000_000]) -> None:
        if not await self._pronto(interaction):
            return
        fatta = await autoresponder_repo.delete(interaction.guild.id, numero)
        _cache_regole.delete(interaction.guild.id)
        await interaction.response.send_message(
            await testo_per(interaction, "autoresponde_risposta_eliminata") if fatta else await testo_per(interaction, "autoresponde_non_esiste_una_risposta_con"), ephemeral=True
        )

    @comando_di_gruppo("admin-tag", nome="elenco", descrizione="Mostra le risposte automatiche del server.", sottogruppo=SOTTOGRUPPI["admin-tag risposte"])
    async def risposte(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        regole = await autoresponder_repo.list(interaction.guild.id)
        righe = [
            f"**{r.id}** · `{r.trigger[:60]}` ({r.match_mode})"
            + (f" · <#{r.channel_id}>" if r.channel_id else "")
            + (f" · <@&{r.role_id}>" if r.role_id else "")
            for r in regole
        ] or ["Nessuna risposta automatica."]
        testo, _ = righe_entro_limite(righe, 3900)
        await interaction.response.send_message(
            embed=discord.Embed(title=await testo_per(interaction, "autoresponde_risposte_automatiche", v1=len(regole), v2=MAX_RISPOSTE), description=testo),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @comando_di_gruppo("admin-tag", nome="svuota", descrizione="Elimina tutte le risposte automatiche del server.", sottogruppo=SOTTOGRUPPI["admin-tag risposte"])
    async def risposte_svuota(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        etichette = (await testo_per(interaction, "conteggio_togli_bottone"), await testo_per(interaction, "conteggio_togli_annulla"))
        await interaction.response.send_message(
            await testo_per(interaction, "risposte_svuota_chiedi", quante=await autoresponder_repo.conta(interaction.guild.id)),
            ephemeral=True, view=ConfermaSvuota(interaction.user.id, interaction.guild.id, etichette))

    @comando_di_gruppo("admin-tag", nome="globali", descrizione="Accendi o spegni le risposte automatiche dell'owner in questo server.", sottogruppo=SOTTOGRUPPI["admin-tag risposte"])
    @app_commands.describe(accese="Sì: il bot usa anche le risposte comuni a tutti i server. No: solo le tue")
    async def risposte_globali(self, interaction: discord.Interaction, accese: bool) -> None:
        if not await self._pronto(interaction):
            return
        await autorisposte_globali_repo.imposta_spente(interaction.guild.id, not accese)
        _cache_spente.delete(interaction.guild.id)
        await interaction.response.send_message(
            await testo_per(interaction, "risposte_globali_accese" if accese else "risposte_globali_spente"), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_AUTORESPONDER,
            display_name="Risposte automatiche",
            category="utility",
            description="Il bot risponde da solo a parole o frasi scelte, con condizioni di canale e ruolo.",
            premium_capable=False,
        )
    )
    await bot.add_cog(AutoresponderCog(bot))
