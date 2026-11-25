"""
cogs/utility/counters.py
========================
Canali contatore (NF-16, SPEC §23.2): canali vocali il cui nome mostra un numero (membri, ticket, ruoli, canali, emoji,
online, boost, obiettivo). Comandi in `/admin-moduli contatori`; il giro che aggiorna i nomi
sta in core/counter_worker.py ed è ospitato da questo cog (parte con lui, si ferma con lui).
Funzioni coperte: SPEC §23 (NF-16); STA-033..052
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.counter_logic import (
    ETICHETTE_DI_BASE,
    INTERVALLO_SECONDI,
    MAX_CONTATORI,
    MAX_ETICHETTA,
    MAX_OBIETTIVO,
    NOMI_TIPI,
    TIPI,
    TIPI_CON_PARAMETRO,
    leggi_traguardi,
    nome_canale,
    valida_etichetta,
    valida_parametro,
)
from core.counter_worker import CounterWorker
from core.database import db
from core.i18n import testo_per
from core.premium import PremiumModule, registry
from core.ui_base import BaseView
from core.repositories.counter_repo import counter_repo
from core.giro_periodico import giro_periodico

logger = logging.getLogger("iyokai.counters")

MODULE_COUNTERS = "counters"

_SG_CONTATORI = ("contatori", "Canali che mostrano un numero")
_NESSUNA_MENZIONE = discord.AllowedMentions.none()


class CountersCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._worker = CounterWorker(counter_repo)

        @giro_periodico(seconds=INTERVALLO_SECONDI)
        async def _giro() -> None:
            await self._worker.tick(self.bot)

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
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_COUNTERS):
            await interaction.response.send_message(
                await testo_per(interaction, "ping_questo_modulo_non_attivo_su"),
                ephemeral=True,
            )
            return False
        return True

    async def _tipo_autocompleta(self, interaction: discord.Interaction, corrente: str) -> list[app_commands.Choice[str]]:
        corrente = corrente.lower()
        trovati = [t for t in TIPI if corrente in t or corrente in NOMI_TIPI[t]]
        return [app_commands.Choice(name=f"{NOMI_TIPI[t]} ({t})"[:100], value=t) for t in trovati[:25]]

    @comando_di_gruppo("admin-moduli", nome="crea", descrizione="Crea un canale che mostra un numero.", sottogruppo=_SG_CONTATORI)
    @app_commands.describe(
        tipo="Cosa mostrare (scrivi per cercare)",
        canale="Un canale vocale tuo; se non lo scegli ne creo uno chiuso a tutti",
        etichetta="Nome del canale: {n} numero, {breve} come 1,2K; {membri} {bot} {online}... per più numeri",
        obiettivo="Il numero da raggiungere (solo per il tipo obiettivo)",
        ruolo="Il ruolo (per i tipi «con» e «senza» ruolo)",
        parametro="Fuso o data (orologio, conto alla rovescia), canale YouTube o Twitch, indirizzo del gioco",
        traguardi="Obiettivi uno dopo l'altro, separati da virgola: 1000,2000,5000",
    )
    @app_commands.autocomplete(tipo=_tipo_autocompleta)
    async def crea(
        self,
        interaction: discord.Interaction,
        tipo: app_commands.Range[str, 1, 20],
        canale: discord.VoiceChannel | None = None,
        etichetta: app_commands.Range[str, 1, MAX_ETICHETTA] | None = None,
        obiettivo: app_commands.Range[int, 1, MAX_OBIETTIVO] | None = None,
        ruolo: discord.Role | None = None,
        parametro: app_commands.Range[str, 1, 200] | None = None,
        traguardi: app_commands.Range[str, 1, 100] | None = None,
    ) -> None:
        if not await self._pronto(interaction):
            return
        guild = interaction.guild
        if tipo not in TIPI:
            await interaction.response.send_message(await testo_per(interaction, "counters_tipo_sconosciuto"), ephemeral=True)
            return
        if tipo == "goal" and obiettivo is None and not traguardi:
            await interaction.response.send_message(await testo_per(interaction, "counters_per_obiettivo_indica_il_numero"), ephemeral=True)
            return
        grezzo = str(ruolo.id) if ruolo is not None else parametro
        pulito, chiave_errore = valida_parametro(tipo, grezzo)
        if chiave_errore is not None:
            await interaction.response.send_message(await testo_per(interaction, chiave_errore), ephemeral=True)
            return
        elenco = None
        if traguardi:  # STA-040
            elenco = leggi_traguardi(traguardi)
            if not elenco or tipo != "goal":
                await interaction.response.send_message(await testo_per(interaction, "counters_traguardi_non_validi"), ephemeral=True)
                return
            obiettivo = obiettivo or elenco[0]
        testo = etichetta or ETICHETTE_DI_BASE[tipo]
        errore = valida_etichetta(testo, tipo)
        if errore is not None:
            await interaction.response.send_message(errore, ephemeral=True)
            return
        if canale is not None:
            permessi = canale.permissions_for(guild.me)
            if not (permessi.manage_channels and permessi.view_channel):
                await interaction.response.send_message(
                    await testo_per(interaction, "counters_per_rinominare_al_bot_serve", mention=canale.mention),
                    ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
                )
                return
            if not canale.permissions_for(interaction.user).manage_channels:
                await interaction.response.send_message(
                    await testo_per(interaction, "counters_per_collegare_un_contatore_serve", mention=canale.mention),
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
                    await testo_per(interaction, "counters_non_riesco_creare_il_canale"), ephemeral=True
                )
                return
        esito = await counter_repo.create(
            guild.id, canale.id, tipo, testo, obiettivo, interaction.user.id,
            param=pulito, targets=",".join(map(str, elenco)) if elenco else None,
        )
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
            await testo_per(interaction, "counters_contatore_creato_su_si_aggiorna", mention=canale.mention),
            ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
        )

    @comando_di_gruppo("admin-moduli", nome="modifica", descrizione="Cambia l'etichetta o l'obiettivo di un contatore.", sottogruppo=_SG_CONTATORI)
    @app_commands.describe(
        numero="Il numero mostrato da /admin-moduli contatori elenco",
        etichetta="Il nuovo nome del canale (con il posto del numero)",
        obiettivo="Il nuovo obiettivo",
        traguardi="Nuovi traguardi uno dopo l'altro: 1000,2000,5000",
        parametro="Il nuovo fuso, data, canale o indirizzo",
    )
    async def modifica(
        self,
        interaction: discord.Interaction,
        numero: app_commands.Range[int, 1, 2_000_000_000],
        etichetta: app_commands.Range[str, 1, MAX_ETICHETTA] | None = None,
        obiettivo: app_commands.Range[int, 1, MAX_OBIETTIVO] | None = None,
        traguardi: app_commands.Range[str, 1, 100] | None = None,
        parametro: app_commands.Range[str, 1, 200] | None = None,
    ) -> None:
        # STA-050: modifica di un contatore già creato
        if not await self._pronto(interaction):
            return
        guild_id = interaction.guild.id
        attuale = await counter_repo.get(guild_id, numero)
        if attuale is None:
            await interaction.response.send_message(await testo_per(interaction, "counters_non_un_contatore_con_quel"), ephemeral=True)
            return
        campi: dict = {}
        if etichetta is not None:
            errore = valida_etichetta(etichetta, attuale.kind)
            if errore is not None:
                await interaction.response.send_message(errore, ephemeral=True)
                return
            campi["label"] = etichetta
        if obiettivo is not None:
            campi["target"] = obiettivo
        if traguardi is not None:
            elenco = leggi_traguardi(traguardi)
            if not elenco or attuale.kind != "goal":
                await interaction.response.send_message(await testo_per(interaction, "counters_traguardi_non_validi"), ephemeral=True)
                return
            campi["targets"] = ",".join(map(str, elenco))
        if parametro is not None:
            pulito, chiave_errore = valida_parametro(attuale.kind, parametro)
            if attuale.kind not in TIPI_CON_PARAMETRO or chiave_errore is not None:
                await interaction.response.send_message(await testo_per(interaction, chiave_errore or "counters_nessun_parametro"), ephemeral=True)
                return
            campi["param"] = pulito
        if not campi:
            await interaction.response.send_message(await testo_per(interaction, "counters_niente_da_cambiare"), ephemeral=True)
            return
        await counter_repo.update(guild_id, numero, **campi)
        await interaction.response.send_message(await testo_per(interaction, "counters_modificato"), ephemeral=True)

    @comando_di_gruppo("admin-moduli", nome="azzera", descrizione="Smetti di aggiornare tutti i contatori (i canali restano).", sottogruppo=_SG_CONTATORI)
    async def azzera(self, interaction: discord.Interaction) -> None:
        # STA-051: con la conferma, perché tocca tutti i contatori del server
        if not await self._pronto(interaction):
            return
        totale = len(await counter_repo.list_for_guild(interaction.guild.id))
        if totale == 0:
            await interaction.response.send_message(await testo_per(interaction, "counters_nessun_contatore"), ephemeral=True)
            return
        vista = _ConfermaAzzera(interaction.user.id, interaction.guild.id)
        await interaction.response.send_message(
            await testo_per(interaction, "counters_conferma_azzera", n=totale), view=vista, ephemeral=True
        )

    @comando_di_gruppo("admin-moduli", nome="categoria", descrizione="Crea una categoria con i contatori più usati.", sottogruppo=_SG_CONTATORI)
    @app_commands.describe(
        modello="Quali contatori creare",
        nome="Il nome della categoria",
    )
    @app_commands.choices(modello=[
        app_commands.Choice(name="Base: membri, bot, online, boost", value="base"),
        app_commands.Choice(name="Completo: base più ruoli, canali, emoji", value="completo"),
    ])
    async def categoria(
        self,
        interaction: discord.Interaction,
        modello: app_commands.Choice[str],
        nome: app_commands.Range[str, 1, 60] = "📊 Statistiche",
    ) -> None:
        # STA-049: la categoria e i canali li crea il bot, chiusi a tutti (nessuno può entrare in vocale)
        if not await self._pronto(interaction):
            return
        guild = interaction.guild
        if not (interaction.user.guild_permissions.manage_channels and guild.me.guild_permissions.manage_channels):
            await interaction.response.send_message(await testo_per(interaction, "counters_serve_gestire_canali"), ephemeral=True)
            return
        tipi = MODELLI_CATEGORIA[modello.value]
        presenti = len(await counter_repo.list_for_guild(guild.id))
        if presenti + len(tipi) > MAX_CONTATORI:
            await interaction.response.send_message(
                await testo_per(interaction, "counters_non_basta_il_posto", n=len(tipi), massimo=MAX_CONTATORI), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        chiuso = {guild.default_role: discord.PermissionOverwrite(connect=False)}
        creati: list = []
        try:
            cat = await guild.create_category(nome, overwrites=chiuso, reason="Contatori")
            creati.append(cat)
            for tipo in tipi:
                canale = await guild.create_voice_channel(
                    nome_canale(ETICHETTE_DI_BASE[tipo], guild.member_count or 0, None), category=cat, overwrites=chiuso, reason="Contatori"
                )
                creati.append(canale)
                esito = await counter_repo.create(guild.id, canale.id, tipo, ETICHETTE_DI_BASE[tipo], None, interaction.user.id)
                if esito != "ok":
                    raise _NonRiuscito()
        except (discord.HTTPException, _NonRiuscito):
            for c in reversed(creati):  # niente avanzi: si toglie ciò che si è creato
                await counter_repo.delete_by_channel(c.id)
                try:
                    await c.delete(reason="Contatori non creati")
                except discord.HTTPException:
                    pass
            await interaction.followup.send(await testo_per(interaction, "counters_non_riesco_creare_il_canale"), ephemeral=True)
            return
        await interaction.followup.send(
            await testo_per(interaction, "counters_categoria_creata", mention=creati[0].mention, n=len(tipi)),
            ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
        )

    @comando_di_gruppo("admin-moduli", nome="elenco", descrizione="Mostra i contatori del server.", sottogruppo=_SG_CONTATORI)
    async def elenco(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        contatori = await counter_repo.list_for_guild(interaction.guild.id)
        righe = [
            f"`{c.id}` · {NOMI_TIPI.get(c.kind, c.kind)} · <#{c.channel_id}> · ultimo valore {c.last_value if c.last_value is not None else '—'}"
            for c in contatori
        ] or ["Nessun contatore."]
        await interaction.response.send_message(
            embed=discord.Embed(title=await testo_per(interaction, "counters_contatori", v1=len(contatori), v2=MAX_CONTATORI), description="\n".join(righe)[:4000]),
            ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
        )

    @comando_di_gruppo("admin-moduli", nome="elimina", descrizione="Smetti di aggiornare un contatore (il canale resta).", sottogruppo=_SG_CONTATORI)
    @app_commands.describe(numero="Il numero mostrato da /admin-moduli contatori elenco")
    async def elimina(self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 2_000_000_000]) -> None:
        if not await self._pronto(interaction):
            return
        fatto = await counter_repo.delete(interaction.guild.id, numero)
        await interaction.response.send_message(
            await testo_per(interaction, "counters_contatore_tolto_il_canale_resta") if fatto
            else await testo_per(interaction, "counters_non_un_contatore_con_quel"),
            ephemeral=True,
        )


MODELLI_CATEGORIA = {
    "base": ("members", "bots", "online", "boosts"),
    "completo": ("members", "bots", "online", "boosts", "roles", "channels", "emojis"),
}


class _NonRiuscito(Exception):
    """Un contatore della categoria non si è potuto registrare (tetto raggiunto nel frattempo)."""


class _ConfermaAzzera(BaseView):
    def __init__(self, autore_id: int, guild_id: int) -> None:
        super().__init__(timeout=60)
        self._autore_id = autore_id
        self._guild_id = guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self._autore_id:
            await interaction.response.send_message(await testo_per(interaction, "counters_non_e_tuo"), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Sì, azzera", style=discord.ButtonStyle.danger)
    async def conferma(self, interaction: discord.Interaction, _bottone: discord.ui.Button) -> None:
        n = await counter_repo.delete_all(self._guild_id)
        self.stop()
        await interaction.response.edit_message(content=await testo_per(interaction, "counters_azzerati", n=n), view=None)

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def annulla(self, interaction: discord.Interaction, _bottone: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content=await testo_per(interaction, "counters_annullato"), view=None)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_COUNTERS,
            display_name="Contatori",
            category="community",
            description="Canali il cui nome mostra membri, online, boost o un obiettivo.",
            premium_capable=False,
        )
    )
    await bot.add_cog(CountersCog(bot))
