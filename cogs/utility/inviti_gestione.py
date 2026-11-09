"""
cogs/utility/inviti_gestione.py
===============================
Gestione degli inviti per lo staff (D69 B13): riallinea i conteggi a Discord, azzera, esporta in CSV o JSON,
statistiche di chi resta e di chi è attivo. Comandi: `/admin-inviti riallinea|azzera|esporta|statistiche`.
Funzioni coperte: catalogo UTL-178, 179, 182, 183
"""

from __future__ import annotations

import io
import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.utility.invites import MODULE_INVITES
from cogs.utility.inviti_codici import inviti_del_server
from core.command_access import Livello, richiedi
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.i18n import testo_per
from core.invite_tracker import invite_tracker
from core.inviti_codici_logic import da_invito
from core.inviti_export_logic import FORMATI, costruisci
from core.repositories.invite_stats_repo import invite_stats_repo
from core.repositories.inviti_extra_repo import inviti_extra_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.inviti_gestione")

SECONDI_CONFERMA = 60
GIORNI_ATTIVITA = 7
COLONNE = {
    "ingressi": ["user_id", "inviter_id", "code", "kind", "finto", "usciti", "joined_at", "left_at"],
    "classifica": ["posizione", "user_id", "presenti", "totale", "finti", "bonus", "punti"],
    "codici": ["code", "creatore_id", "canale_id", "usi", "usi_massimi", "scade_il", "etichetta"],
}


class ConfermaAzzera(BaseView):
    def __init__(self, proprietario: int, guild_id: int) -> None:
        super().__init__(timeout=SECONDI_CONFERMA)
        self.proprietario = proprietario
        self.guild_id = guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.proprietario:
            await interaction.response.send_message(await testo_per(interaction, "invites_non_e_tuo"), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Azzera tutto", style=discord.ButtonStyle.danger)
    async def conferma(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        ingressi, bonus = await invite_stats_repo.azzera(self.guild_id)
        logger.info("Inviti azzerati nel server %s da %s: %s ingressi, %s bonus", self.guild_id, interaction.user.id, ingressi, bonus)
        await interaction.response.edit_message(
            content=await testo_per(interaction, "invites_azzerati", ingressi=ingressi, bonus=bonus), view=None
        )

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def annulla(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content=await testo_per(interaction, "invites_annullato"), view=None)


class InvitiGestioneCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _pronto(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_INVITES):
            await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
            return False
        return True

    # ---------------------------------------------------------------- riallinea
    @comando_di_gruppo("admin-inviti", nome="riallinea", descrizione="Rileggi gli inviti da Discord e confrontali con gli ingressi salvati.")
    @richiedi(Livello.ADMIN)
    async def riallinea(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        inviti = await inviti_del_server(interaction.guild)
        if inviti is None:
            await interaction.followup.send(await testo_per(interaction, "invites_serve_gestire_server"))
            return
        await invite_tracker.refresh_guild(interaction.guild)
        salvati = await invite_stats_repo.conteggio_per_codice(interaction.guild.id)
        mancanti = sorted(
            ((i.code, (i.uses or 0) - salvati.get(i.code, 0)) for i in inviti if (i.uses or 0) > salvati.get(i.code, 0)),
            key=lambda x: -x[1],
        )
        righe = [f"`{codice}`: {diff}" for codice, diff in mancanti[:10]]
        testo = await testo_per(interaction, "invites_riallineato", inviti=len(inviti), diversi=len(mancanti))
        if righe:
            testo += "\n" + await testo_per(interaction, "invites_riallineato_dettaglio") + "\n" + "\n".join(righe)
        await interaction.followup.send(testo)

    # ---------------------------------------------------------------- azzera
    @comando_di_gruppo("admin-inviti", nome="azzera", descrizione="Cancella lo storico degli inviti e i bonus del server.")
    @richiedi(Livello.ADMIN)
    async def azzera(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        await interaction.response.send_message(
            await testo_per(interaction, "invites_conferma_azzera"), view=ConfermaAzzera(interaction.user.id, interaction.guild.id),
            ephemeral=True,
        )

    # ---------------------------------------------------------------- esporta
    @comando_di_gruppo("admin-inviti", nome="esporta", descrizione="Esporta ingressi, classifica o codici in un file.")
    @app_commands.describe(cosa="Cosa esportare", formato="Il tipo di file")
    @app_commands.choices(
        cosa=[app_commands.Choice(name=n, value=n) for n in ("ingressi", "classifica", "codici")],
        formato=[app_commands.Choice(name=f, value=f) for f in FORMATI],
    )
    @richiedi(Livello.ADMIN)
    async def esporta(
        self, interaction: discord.Interaction, cosa: app_commands.Choice[str], formato: app_commands.Choice[str] | None = None,
    ) -> None:
        if not await self._pronto(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        tipo = formato.value if formato else "csv"
        if cosa.value == "ingressi":
            righe = await invite_stats_repo.righe_per_esportare(guild.id)
        elif cosa.value == "classifica":
            top = await invite_stats_repo.top(guild.id, 100, tetto=100)
            righe = [
                {"posizione": n, "user_id": uid, "presenti": s.presenti, "totale": s.totale, "finti": s.finti,
                 "bonus": s.bonus, "punti": s.punti}
                for n, (uid, s) in enumerate(top, 1)
            ]
        else:
            inviti = await inviti_del_server(guild)
            if inviti is None:
                await interaction.followup.send(await testo_per(interaction, "invites_serve_gestire_server"))
                return
            visti = [da_invito(i) for i in inviti]
            etichette = await inviti_extra_repo.etichette_di(guild.id, [v.codice for v in visti])
            righe = [
                {"code": v.codice, "creatore_id": v.creatore_id, "canale_id": v.canale_id, "usi": v.usi,
                 "usi_massimi": v.usi_massimi, "scade_il": v.scade_il, "etichetta": etichette.get(v.codice, (None,))[0]}
                for v in visti
            ]
        if not righe:
            await interaction.followup.send(await testo_per(interaction, "invites_niente_da_esportare"))
            return
        dati, messe = costruisci(righe, COLONNE[cosa.value], tipo)
        nota = "" if messe == len(righe) else " " + await testo_per(interaction, "invites_export_tagliato", messe=messe, totale=len(righe))
        await interaction.followup.send(
            await testo_per(interaction, "invites_export_pronto", n=messe) + nota,
            file=discord.File(io.BytesIO(dati), filename=f"inviti-{cosa.value}.{tipo}"),
        )

    # ---------------------------------------------------------------- statistiche
    @comando_di_gruppo("admin-inviti", nome="statistiche", descrizione="Quanti membri portati dagli inviti restano e sono attivi.")
    @richiedi(Livello.ADMIN)
    async def statistiche(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        s = await invite_stats_repo.statistiche_server(interaction.guild.id, GIORNI_ATTIVITA)
        await interaction.response.send_message(
            await testo_per(interaction, "invites_statistiche", giorni=GIORNI_ATTIVITA, **s), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InvitiGestioneCog(bot))
