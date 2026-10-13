"""
cogs/utility/counters.py
========================
Canali contatore (NF-16, SPEC §23.2): canali vocali il cui nome mostra un numero (membri,
online, boost, obiettivo). Comandi in `/moduli contatori`; il giro che aggiorna i nomi
sta in core/counter_worker.py ed è ospitato da questo cog (parte con lui, si ferma con lui).
Funzioni coperte: SPEC §23 (NF-16)
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.counter_logic import (
    ETICHETTE_DI_BASE,
    INTERVALLO_SECONDI,
    MAX_CONTATORI,
    MAX_ETICHETTA,
    NOMI_TIPI,
    TIPI,
    nome_canale,
    valida_etichetta,
)
from core.counter_worker import CounterWorker
from core.database import db
from core.premium import PremiumModule, registry
from core.repositories.counter_repo import counter_repo

logger = logging.getLogger("iyokai.counters")

MODULE_COUNTERS = "counters"

_SG_CONTATORI = ("contatori", "Canali che mostrano un numero")
_NESSUNA_MENZIONE = discord.AllowedMentions.none()


class CountersCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._worker = CounterWorker(counter_repo)

        @tasks.loop(seconds=INTERVALLO_SECONDI)
        async def _giro() -> None:
            try:
                await self._worker.tick(self.bot)
            except Exception:
                logger.exception("Errore nel giro dei contatori")

        @_giro.before_loop
        async def _prima() -> None:
            await self.bot.wait_until_ready()

        self._giro = _giro

    async def cog_load(self) -> None:
        await super().cog_load()
        if not self._giro.is_running():
            self._giro.start()

    async def cog_unload(self) -> None:
        self._giro.cancel()
        await super().cog_unload()

    async def _pronto(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_COUNTERS):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /admin setup attiva.",
                ephemeral=True,
            )
            return False
        return True

    @comando_di_gruppo("moduli", nome="crea", descrizione="Crea un canale che mostra un numero.", sottogruppo=_SG_CONTATORI)
    @app_commands.describe(
        tipo="Cosa contare",
        canale="Un canale vocale tuo; se non lo scegli ne creo uno chiuso a tutti",
        etichetta="Il nome del canale, con {n} al posto del numero (e {target} per l'obiettivo)",
        obiettivo="Il numero da raggiungere (solo per il tipo obiettivo)",
    )
    @app_commands.choices(tipo=[app_commands.Choice(name=NOMI_TIPI[t], value=t) for t in TIPI])
    async def crea(
        self,
        interaction: discord.Interaction,
        tipo: str,
        canale: discord.VoiceChannel | None = None,
        etichetta: app_commands.Range[str, 1, MAX_ETICHETTA] | None = None,
        obiettivo: app_commands.Range[int, 1, 10_000_000] | None = None,
    ) -> None:
        if not await self._pronto(interaction):
            return
        guild = interaction.guild
        if tipo == "goal" and obiettivo is None:
            await interaction.response.send_message("Per l'obiettivo indica il numero da raggiungere.", ephemeral=True)
            return
        testo = etichetta or ETICHETTE_DI_BASE[tipo]
        errore = valida_etichetta(testo, tipo)
        if errore is not None:
            await interaction.response.send_message(errore, ephemeral=True)
            return
        if canale is not None:
            permessi = canale.permissions_for(guild.me)
            if not (permessi.manage_channels and permessi.view_channel):
                await interaction.response.send_message(
                    f"Per rinominare {canale.mention} al bot serve il permesso «Gestire i canali» su quel canale.",
                    ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
                )
                return
        await interaction.response.defer(ephemeral=True)
        creato = False
        if canale is None:
            try:
                canale = await guild.create_voice_channel(
                    nome_canale(testo, guild.member_count or 0, obiettivo),
                    overwrites={guild.default_role: discord.PermissionOverwrite(connect=False)},
                    reason="Contatore",
                )
                creato = True
            except discord.HTTPException:
                await interaction.followup.send(
                    "Non riesco a creare il canale: al bot serve il permesso «Gestire i canali».", ephemeral=True
                )
                return
        esito = await counter_repo.create(guild.id, canale.id, tipo, testo, obiettivo, interaction.user.id)
        if esito != "ok":
            if creato:
                try:
                    await canale.delete(reason="Contatore non creato")
                except discord.HTTPException:
                    pass
            messaggi = {
                "esiste": "Quel canale è già un contatore.",
                "pieno": f"Questo server ha già {MAX_CONTATORI} contatori: eliminane uno.",
            }
            await interaction.followup.send(messaggi[esito], ephemeral=True)
            return
        await interaction.followup.send(
            f"Contatore creato su {canale.mention}: si aggiorna al massimo ogni 10 minuti (limite di Discord).",
            ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
        )

    @comando_di_gruppo("moduli", nome="elenco", descrizione="Mostra i contatori del server.", sottogruppo=_SG_CONTATORI)
    async def elenco(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        contatori = await counter_repo.list_for_guild(interaction.guild.id)
        righe = [
            f"`{c.id}` · {NOMI_TIPI.get(c.kind, c.kind)} · <#{c.channel_id}> · ultimo valore {c.last_value if c.last_value is not None else '—'}"
            for c in contatori
        ] or ["Nessun contatore."]
        await interaction.response.send_message(
            embed=discord.Embed(title=f"Contatori ({len(contatori)}/{MAX_CONTATORI})", description="\n".join(righe)),
            ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
        )

    @comando_di_gruppo("moduli", nome="elimina", descrizione="Smetti di aggiornare un contatore (il canale resta).", sottogruppo=_SG_CONTATORI)
    @app_commands.describe(numero="Il numero mostrato da /moduli contatori elenco")
    async def elimina(self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 2_000_000_000]) -> None:
        if not await self._pronto(interaction):
            return
        fatto = await counter_repo.delete(interaction.guild.id, numero)
        await interaction.response.send_message(
            "Contatore tolto: il canale resta com'è, lo puoi cancellare a mano." if fatto
            else "Non c'è un contatore con quel numero.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_COUNTERS,
            display_name="Contatori",
            category="utility",
            description="Canali il cui nome mostra membri, online, boost o un obiettivo.",
            premium_capable=False,
        )
    )
    await bot.add_cog(CountersCog(bot))
