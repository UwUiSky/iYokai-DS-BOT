"""
cogs/utility/alert_gestione.py
==============================
Gestione degli avvisi social (feed, Twitch, YouTube, Kick, Picarto) con /admin-alert: messaggio per ogni
tipo, formato ed embed, sposta, ferma tutti, controllo a mano di una diretta. Le opzioni già esistenti
restano in /admin-moduli alert; qui stanno le funzioni nate dal catalogo (#129).
Funzioni coperte: SPEC §10.9, §10.13 (#129 ALR-009, 014, 020, 021, 024, 029, 037, 038, 040)
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core import diretta_controllo_logic as controllo
from core.alert_messaggio_logic import MAX_MODELLO, segnaposto_sconosciuti
from core.alert_options_logic import leggi_id_avviso
from core.command_access import Livello, autocomplete_protetto
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.feed_alert_gate import MODULE_FEED_ALERTS
from core.i18n import testo_per
from core.repositories.alert_gestione_repo import alert_gestione_repo
from core.repositories.alert_options_repo import alert_options_repo
from core.repositories.saved_embed_repo import saved_embed_repo
from core.ui_base import BaseView

GRUPPO = "admin-alert"
MAX_NOME_EMBED = 32
PERMESSI_CANALE = ("view_channel", "send_messages", "embed_links")


class _Conferma(BaseView):
    """Due bottoni: solo chi ha lanciato il comando può confermare (38)."""

    def __init__(self, autore_id: int) -> None:
        super().__init__(timeout=60)
        self.autore_id = autore_id
        self.scelta: bool | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.autore_id:
            await interaction.response.send_message(await testo_per(interaction, "alertgest_solo_chi_ha_lanciato"), ephemeral=True)
            return False
        return await super().interaction_check(interaction)

    @discord.ui.button(label="Conferma", style=discord.ButtonStyle.danger)
    async def conferma(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.scelta = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def annulla(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.scelta = False
        await interaction.response.defer()
        self.stop()


class AlertGestioneCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _modulo_attivo(self, interaction: discord.Interaction) -> bool:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return False
        if not await db.is_module_active_for_guild(guild.id, MODULE_FEED_ALERTS):
            await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
            return False
        return True

    async def _avviso(self, interaction: discord.Interaction, id_avviso: str) -> tuple[str, int] | None:
        """Sigla e numero di un avviso del server, oppure None dopo aver risposto con l'errore."""
        if not await self._modulo_attivo(interaction):
            return None
        letto = leggi_id_avviso(id_avviso)
        if letto is None:
            await interaction.response.send_message(await testo_per(interaction, "feedalerts_formato_id_non_valido_usa_2"), ephemeral=True)
            return None
        # Il proprietario dell'avviso è il server: l'id da solo non basta (guild_id nella query).
        if not await alert_gestione_repo.esiste(letto[0], letto[1], interaction.guild.id):
            await interaction.response.send_message(await testo_per(interaction, "feedalerts_nessuna_sottoscrizione_trovata_con_quest"), ephemeral=True)
            return None
        return letto

    @staticmethod
    def _canale_ok(canale: discord.TextChannel, guild: discord.Guild) -> bool:
        me = guild.me
        if me is None or canale.guild.id != guild.id:
            return False
        permessi = canale.permissions_for(me)
        return all(getattr(permessi, p) for p in PERMESSI_CANALE)

    # ------------------------------------------------------------ messaggio (ALR-020, 021, 029)
    @comando_di_gruppo(GRUPPO, nome="messaggio", descrizione="Cambia il testo di un avviso (anche Twitch, YouTube, Kick).")
    @app_commands.describe(
        id_avviso="ID dell'avviso, es. TW-2 o RSS-1",
        testo="Testo con {label} {title} {link} {login} {gioco} {ruolo}…",
        quale="Quando si usa: all'inizio della diretta (o per ogni voce) o alla fine",
    )
    @app_commands.choices(quale=[app_commands.Choice(name="inizio", value="inizio"), app_commands.Choice(name="fine", value="fine")])
    async def messaggio(
        self,
        interaction: discord.Interaction,
        id_avviso: app_commands.Range[str, 1, 20],
        testo: app_commands.Range[str, 1, MAX_MODELLO],
        quale: app_commands.Choice[str] | None = None,
    ) -> None:
        letto = await self._avviso(interaction, id_avviso)
        if letto is None:
            return
        sigla, numero = letto
        scelta = quale.value if quale else "inizio"
        if not await alert_gestione_repo.imposta_modello(sigla, numero, interaction.guild.id, scelta, testo):
            await interaction.response.send_message(await testo_per(interaction, "alertgest_nessun_modello_di_fine"), ephemeral=True)
            return
        avvisi = ""
        sconosciuti = segnaposto_sconosciuti(testo, sigla)
        if sconosciuti:
            avvisi += "\n" + await testo_per(interaction, "alertgest_segnaposto_sconosciuti", v1=", ".join("{" + n + "}" for n in sconosciuti)[:200])
        if "{ruolo}" in testo and not (await alert_options_repo.get(sigla, numero)).mention_role_id:
            avvisi += "\n" + await testo_per(interaction, "alertgest_ruolo_non_scelto", v1=id_avviso[:20])
        await interaction.response.send_message(await testo_per(interaction, "alertgest_testo_aggiornato", v1=id_avviso[:20]) + avvisi, ephemeral=True)

    # ------------------------------------------------------------ formato (ALR-009, 014, 024)
    @autocomplete_protetto(Livello.ADMIN)
    async def _completa_embed(self, interaction: discord.Interaction, corrente: str) -> list[app_commands.Choice[str]]:
        if interaction.guild is None:
            return []
        nomi = [e.name for e in await saved_embed_repo.list(interaction.guild.id)]
        trovati = [n for n in nomi if corrente.lower() in n.lower()][:25]
        return [app_commands.Choice(name=n[:100], value=n) for n in trovati]

    @comando_di_gruppo(GRUPPO, nome="formato", descrizione="Testo o embed, embed salvato come modello, Short di YouTube.")
    @app_commands.describe(
        id_avviso="ID dell'avviso, es. RSS-1 o TW-2",
        formato="Pubblica come testo o come embed",
        embed="Nome di un embed salvato da usare come modello («-» per toglierlo)",
        shorts="Solo per i feed di YouTube: tutti i video, senza Short o solo Short",
    )
    @app_commands.autocomplete(embed=_completa_embed)
    @app_commands.choices(
        formato=[app_commands.Choice(name="testo", value="testo"), app_commands.Choice(name="embed", value="embed")],
        shorts=[app_commands.Choice(name="tutti", value="tutti"), app_commands.Choice(name="senza Short", value="no"),
                app_commands.Choice(name="solo Short", value="solo")],
    )
    async def formato(
        self,
        interaction: discord.Interaction,
        id_avviso: app_commands.Range[str, 1, 20],
        formato: app_commands.Choice[str] | None = None,
        embed: app_commands.Range[str, 1, MAX_NOME_EMBED] | None = None,
        shorts: app_commands.Choice[str] | None = None,
    ) -> None:
        letto = await self._avviso(interaction, id_avviso)
        if letto is None:
            return
        sigla, numero = letto
        campi: dict = {}
        if formato is not None:
            campi["formato"] = formato.value
        if shorts is not None:
            if sigla != "RSS":
                await interaction.response.send_message(await testo_per(interaction, "alertgest_shorts_solo_feed"), ephemeral=True)
                return
            campi["shorts"] = shorts.value
        if embed is not None:
            if embed.strip() == "-":
                campi["embed_nome"] = ""
            else:
                if await saved_embed_repo.get(interaction.guild.id, embed.strip().lower()) is None:
                    await interaction.response.send_message(await testo_per(interaction, "alertgest_embed_non_trovato"), ephemeral=True)
                    return
                campi["embed_nome"] = embed.strip().lower()
        if not campi:
            opz = await alert_options_repo.get(sigla, numero)
            await interaction.response.send_message(
                await testo_per(interaction, "alertgest_formato_attuale", v1=id_avviso[:20], v2=opz.formato, v3=opz.embed_nome or "-", v4=opz.shorts),
                ephemeral=True,
            )
            return
        await alert_options_repo.set_fields(sigla, numero, interaction.guild.id, **campi)
        await interaction.response.send_message(await testo_per(interaction, "alertgest_formato_aggiornato", v1=id_avviso[:20]), ephemeral=True)

    # ------------------------------------------------------------ sposta (ALR-037)
    @comando_di_gruppo(GRUPPO, nome="sposta", descrizione="Sposta un avviso in un altro canale.")
    @app_commands.describe(id_avviso="ID dell'avviso, es. TW-2", canale="Il nuovo canale")
    async def sposta(
        self, interaction: discord.Interaction, id_avviso: app_commands.Range[str, 1, 20], canale: discord.TextChannel
    ) -> None:
        letto = await self._avviso(interaction, id_avviso)
        if letto is None:
            return
        if not self._canale_ok(canale, interaction.guild):
            await interaction.response.send_message(await testo_per(interaction, "alertgest_canale_senza_permessi", v1=canale.mention), ephemeral=True)
            return
        await alert_gestione_repo.sposta(letto[0], letto[1], interaction.guild.id, canale.id)
        await interaction.response.send_message(await testo_per(interaction, "alertgest_spostato", v1=id_avviso[:20], v2=canale.mention), ephemeral=True)

    # ------------------------------------------------------------ ferma tutti (ALR-038)
    @comando_di_gruppo(GRUPPO, nome="ferma-tutti", descrizione="Cancella tutti gli avvisi del server o di un canale (con conferma).")
    @app_commands.describe(canale="Solo gli avvisi di questo canale (vuoto: tutto il server)")
    async def ferma_tutti(self, interaction: discord.Interaction, canale: discord.TextChannel | None = None) -> None:
        if not await self._modulo_attivo(interaction):
            return
        guild = interaction.guild
        quanti = len(await alert_gestione_repo.elenco(guild.id, canale.id if canale else None))
        if quanti == 0:
            await interaction.response.send_message(await testo_per(interaction, "feedalerts_nessuna_sottoscrizione_attiva_su_questo"), ephemeral=True)
            return
        vista = _Conferma(interaction.user.id)
        dove = canale.mention if canale else await testo_per(interaction, "alertgest_tutto_il_server")
        await interaction.response.send_message(await testo_per(interaction, "alertgest_confermi_ferma", v1=quanti, v2=dove), view=vista, ephemeral=True)
        await vista.wait()
        if vista.scelta is not True:
            await interaction.edit_original_response(content=await testo_per(interaction, "alertgest_annullato"), view=None)
            return
        tolti = await alert_gestione_repo.rimuovi_tutti(guild.id, canale.id if canale else None)
        await interaction.edit_original_response(content=await testo_per(interaction, "alertgest_fermati", v1=tolti), view=None)

    # ------------------------------------------------------------ controllo a mano (ALR-040)
    @comando_di_gruppo(GRUPPO, nome="diretta", descrizione="Controlla ora se un canale Twitch, Kick o YouTube è in diretta.")
    @app_commands.describe(servizio="Dove controllare", nome="Nome utente (Twitch), nome del canale (Kick) o ID del canale (YouTube, UC…)")
    @app_commands.choices(servizio=[app_commands.Choice(name=n.capitalize(), value=n) for n in controllo.SERVIZI])
    async def diretta(
        self, interaction: discord.Interaction, servizio: app_commands.Choice[str], nome: app_commands.Range[str, 1, 100]
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return
        pulito = controllo.nome_valido(servizio.value, nome)
        if pulito is None:
            await interaction.response.send_message(await testo_per(interaction, "alertgest_nome_non_valido"), ephemeral=True)
            return
        attesa = controllo.pausa_server(interaction.guild.id)
        if attesa > 0:
            await interaction.response.send_message(await testo_per(interaction, "alertgest_aspetta", v1=int(attesa) + 1), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        stato = await controllo.controlla(servizio.value, pulito)
        if stato.in_diretta is None:
            testo = await testo_per(interaction, "alertgest_servizio_non_risponde", v1=servizio.name)
        elif stato.in_diretta:
            testo = await testo_per(interaction, "alertgest_in_diretta", v1=pulito[:100], v2=stato.titolo or "-", v3=stato.gioco or "-")
        else:
            testo = await testo_per(interaction, "alertgest_non_in_diretta", v1=pulito[:100])
        await interaction.followup.send(testo, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AlertGestioneCog(bot))
