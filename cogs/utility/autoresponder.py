"""
cogs/utility/autoresponder.py
=============================
Risposte automatiche (NF-10, SPEC §14.7): quando un messaggio contiene una
parola o frase scelta, il bot risponde da solo. Condizioni: canale, ruolo,
corrispondenza esatta o parziale. Comandi in `/moduli comandi risposta-*`.
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
    MAX_RISPOSTA,
    MAX_RISPOSTE,
    MAX_TRIGGER,
    PAUSA_CANALE_SECONDI,
    scegli_risposta,
)
from core.bounded_cache import BoundedCache
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.lista_limiti_logic import righe_entro_limite
from core.premium import PremiumModule, registry
from core.repositories.autoresponder_repo import autoresponder_repo
from core.template_renderer import render_template

logger = logging.getLogger("iyokai.autoresponder")

MODULE_AUTORESPONDER = "autoresponder"

_SG_COMANDI = ("comandi", "Comandi personalizzati e risposte automatiche")
_TTL_REGOLE = 30  # secondi

# server -> (regole, scadenza); (regola, canale) -> istante dell'ultima risposta
_cache_regole: BoundedCache[int, tuple[list, float]] = BoundedCache(max_size=5_000)
_ultima_risposta: BoundedCache[tuple[int, int], float] = BoundedCache(max_size=20_000)

_SCELTE_MODO = [
    app_commands.Choice(name="parola o frase intera nel messaggio", value="parziale"),
    app_commands.Choice(name="tutto il messaggio uguale", value="esatta"),
]


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
        if regola is None:
            return
        chiave = (regola.id, message.channel.id)
        ora = time.monotonic()
        ultima = _ultima_risposta.get(chiave)
        if ultima is not None and ora - ultima < PAUSA_CANALE_SECONDI:
            return
        _ultima_risposta.set(chiave, ora)
        testo = render_template(
            regola.response,
            {
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
                allowed_mentions=menzioni_ammesse(regola.ping_ruoli),
            )
        except discord.HTTPException:
            logger.warning("Risposta automatica %s: invio fallito nel canale %s", regola.id, message.channel.id)

    # ================================================================
    # Comandi
    # ================================================================
    async def _pronto(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_AUTORESPONDER):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /admin setup attiva.",
                ephemeral=True,
            )
            return False
        return True

    @comando_di_gruppo("moduli", nome="risposta-crea", descrizione="Crea una risposta automatica.", sottogruppo=_SG_COMANDI)
    @app_commands.describe(
        parola="La parola o frase che fa scattare la risposta",
        risposta="Cosa risponde il bot. Segnaposto: {user} {username} {server} {channel}",
        modalita="Come cercare la parola nel messaggio",
        canale="Solo in questo canale (vuoto = ovunque)",
        ruolo="Solo per chi ha questo ruolo (vuoto = tutti)",
    )
    @app_commands.choices(modalita=_SCELTE_MODO)
    async def risposta_crea(
        self,
        interaction: discord.Interaction,
        parola: app_commands.Range[str, 1, MAX_TRIGGER],
        risposta: app_commands.Range[str, 1, MAX_RISPOSTA],
        modalita: str = "parziale",
        canale: discord.TextChannel | None = None,
        ruolo: discord.Role | None = None,
    ) -> None:
        if not await self._pronto(interaction):
            return
        esito, nuovo_id = await autoresponder_repo.create(
            interaction.guild.id,
            parola.strip(),
            match_mode=modalita,
            response=risposta,
            channel_id=canale.id if canale else None,
            role_id=ruolo.id if ruolo else None,
            ping_ruoli=utente_puo_pingare_ruoli(interaction.user),
            created_by=interaction.user.id,
        )
        _cache_regole._data.pop(interaction.guild.id, None)
        messaggi = {
            "ok": f"Risposta automatica n. {nuovo_id} creata.",
            "esiste": "Esiste già una risposta con quella parola: eliminala prima con `/moduli comandi risposta-elimina`.",
            "pieno": f"Questo server ha già {MAX_RISPOSTE} risposte automatiche: eliminane una.",
        }
        await interaction.response.send_message(messaggi[esito], ephemeral=True)

    @comando_di_gruppo("moduli", nome="risposta-elimina", descrizione="Elimina una risposta automatica.", sottogruppo=_SG_COMANDI)
    @app_commands.describe(numero="Il numero mostrato da /moduli comandi risposte")
    async def risposta_elimina(self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 2_000_000_000]) -> None:
        if not await self._pronto(interaction):
            return
        fatta = await autoresponder_repo.delete(interaction.guild.id, numero)
        _cache_regole._data.pop(interaction.guild.id, None)
        await interaction.response.send_message(
            "Risposta eliminata." if fatta else "Non esiste una risposta con quel numero.", ephemeral=True
        )

    @comando_di_gruppo("moduli", nome="risposte", descrizione="Mostra le risposte automatiche del server.", sottogruppo=_SG_COMANDI)
    async def risposte(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        regole = await autoresponder_repo.list(interaction.guild.id)
        righe = [
            f"**{r.id}** · `{r.trigger[:60]}` ({'esatta' if r.match_mode == 'esatta' else 'parziale'})"
            + (f" · <#{r.channel_id}>" if r.channel_id else "")
            + (f" · <@&{r.role_id}>" if r.role_id else "")
            for r in regole
        ] or ["Nessuna risposta automatica."]
        testo, _ = righe_entro_limite(righe, 3900)
        await interaction.response.send_message(
            embed=discord.Embed(title=f"Risposte automatiche ({len(regole)}/{MAX_RISPOSTE})", description=testo),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


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
