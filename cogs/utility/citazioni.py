"""
cogs/utility/citazioni.py
=========================
Citazioni del server (fino a 500) e registro dei comandi: `/fun citazioni caso|aggiungi|cerca|elimina`, menu del
tasto destro «Salva citazione», `/admin-moduli citazioni azione` (esporta, importa, elimina in JSON). Conta i comandi usati per
server e giorno (metrica «comandi» di `/utility serverstats`) e scrive nel log lo staff che usa un comando di gestione.
Funzioni coperte: catalogo #128 UTL-206, 207, 222, 229 (D69, B16)
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core import channel_router as router
from core.citazioni_logic import (
    MAX_BYTE_IMPORT, MAX_PER_SERVER, MAX_TESTO, ImportCitazioniErrato, e_comando_staff, leggi_importazione, pulisci_testo,
    righe_in_json, riga_citazione,
)
from core.command_access import Livello, puo_usare, richiedi
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.i18n import lingua_risposta, t, testo_per
from core.repositories.citazioni_repo import TroppeCitazioni, citazioni_repo, comandi_uso_repo
from core.repositories.log_eventi_repo import log_eventi_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.citazioni")

MODULE_FUN = "fun"
NOME_MENU = "Salva citazione"
_NESSUNA_MENZIONE = discord.AllowedMentions.none()
_SG = ("citazioni", "Citazioni del server")
_SG_ADMIN = ("citazioni", "Citazioni del server: esporta, importa, elimina")
SECONDI_CONFERMA = 60
_AZIONI = [
    app_commands.Choice(name="esporta", value="esporta"),
    app_commands.Choice(name="importa", value="importa"),
    app_commands.Choice(name="elimina tutte", value="elimina"),
]


class ConfermaEliminaCitazioni(BaseView):
    """Eliminare tutte le citazioni non si può disfare: serve una conferma di chi ha dato il comando."""

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
        if not await puo_usare(interaction, Livello.ADMIN):  # il livello si ricontrolla al tasto
            await interaction.response.edit_message(content=await testo_per(interaction, "conteggio_non_e_tuo"), view=None)
            return
        quante = await citazioni_repo.elimina_tutte(self.guild_id)
        await interaction.response.edit_message(content=await testo_per(interaction, "citazioni_eliminate", quante=quante), view=None)

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def annulla(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content=await testo_per(interaction, "conteggio_togli_annullato"), view=None)


class CitazioniCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._menu = app_commands.ContextMenu(name=NOME_MENU, callback=self.menu_salva)

    async def cog_load(self) -> None:
        await super().cog_load()
        self.bot.tree.add_command(self._menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(NOME_MENU, type=discord.AppCommandType.message)
        await super().cog_unload()

    async def _pronto(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_FUN):
            await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
            return False
        return True

    async def _salva(self, interaction: discord.Interaction, testo: str, autore_id: int | None, link: str | None) -> None:
        testo = pulisci_testo(testo)
        if not testo:
            await interaction.response.send_message(await testo_per(interaction, "citazioni_vuota"), ephemeral=True)
            return
        try:
            numero = await citazioni_repo.aggiungi(interaction.guild.id, testo, autore_id, interaction.user.id, link)
        except TroppeCitazioni:
            await interaction.response.send_message(
                await testo_per(interaction, "citazioni_troppe", massimo=MAX_PER_SERVER), ephemeral=True)
            return
        await interaction.response.send_message(await testo_per(interaction, "citazioni_salvata", numero=numero), ephemeral=True)

    # ------------------------------------------------------------ menu e comandi per tutti
    async def menu_salva(self, interaction: discord.Interaction, messaggio: discord.Message) -> None:
        if not await self._pronto(interaction):
            return
        autore = None if messaggio.author.bot else messaggio.author.id
        await self._salva(interaction, messaggio.content or "", autore, messaggio.jump_url)

    @comando_di_gruppo("fun", nome="aggiungi", descrizione="Salva una citazione del server.", sottogruppo=_SG)
    @app_commands.describe(testo="Cosa è stato detto", autore="Chi l'ha detto")
    async def aggiungi(
        self, interaction: discord.Interaction, testo: app_commands.Range[str, 1, MAX_TESTO], autore: discord.Member | None = None
    ) -> None:
        if await self._pronto(interaction):
            await self._salva(interaction, testo, autore.id if autore and not autore.bot else None, None)

    @comando_di_gruppo("fun", nome="caso", descrizione="Mostra una citazione a caso del server.", sottogruppo=_SG)
    async def caso(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        riga = await citazioni_repo.a_caso(interaction.guild.id)
        if riga is None:
            await interaction.response.send_message(await testo_per(interaction, "citazioni_nessuna"), ephemeral=True)
            return
        await interaction.response.send_message(riga_citazione(riga)[:2000], allowed_mentions=_NESSUNA_MENZIONE)

    @comando_di_gruppo("fun", nome="cerca", descrizione="Cerca una parola tra le citazioni del server.", sottogruppo=_SG)
    @app_commands.describe(testo="La parola o la frase da cercare")
    async def cerca(self, interaction: discord.Interaction, testo: app_commands.Range[str, 1, 100]) -> None:
        if not await self._pronto(interaction):
            return
        righe = await citazioni_repo.cerca(interaction.guild.id, testo)
        if not righe:
            await interaction.response.send_message(await testo_per(interaction, "citazioni_nessuna"), ephemeral=True)
            return
        await interaction.response.send_message(
            "\n".join(riga_citazione(r) for r in righe)[:1900], ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE)

    @comando_di_gruppo("fun", nome="elimina", descrizione="Elimina una citazione che hai salvato tu.", sottogruppo=_SG)
    @app_commands.describe(numero="Il numero della citazione (lo vedi tra parentesi)")
    async def elimina(self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 9_000_000_000_000_000]) -> None:
        if not await self._pronto(interaction):
            return
        tolta = await citazioni_repo.elimina(interaction.guild.id, numero, interaction.user.id)
        await interaction.response.send_message(
            await testo_per(interaction, "citazioni_tolta" if tolta else "citazioni_non_tua"), ephemeral=True)

    # ------------------------------------------------------------ staff
    @comando_di_gruppo("admin-moduli", nome="azione", descrizione="Esporta, importa o elimina le citazioni (JSON).", sottogruppo=_SG_ADMIN)
    @app_commands.describe(azione="Cosa fare", file="Il file JSON da importare (solo per «importa»)")
    @app_commands.choices(azione=_AZIONI)
    @richiedi(Livello.ADMIN)
    async def azione(self, interaction: discord.Interaction, azione: app_commands.Choice[str], file: discord.Attachment | None = None) -> None:
        if not await self._pronto(interaction):
            return
        guild_id = interaction.guild.id
        if azione.value == "esporta":
            await interaction.response.defer(ephemeral=True)
            dati = righe_in_json(await citazioni_repo.tutte(guild_id))
            await interaction.followup.send(
                await testo_per(interaction, "citazioni_esportate"), ephemeral=True,
                file=discord.File(io.BytesIO(dati), filename="citazioni.json"))
            return
        if azione.value == "importa":
            if file is None or file.size > MAX_BYTE_IMPORT:
                await interaction.response.send_message(await testo_per(interaction, "citazioni_serve_file"), ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            posti = MAX_PER_SERVER - await citazioni_repo.conta(guild_id)
            try:
                righe = leggi_importazione(await file.read(), max(posti, 0))
            except ImportCitazioniErrato as errore:
                await interaction.followup.send(await testo_per(interaction, f"citazioni_{errore}"), ephemeral=True)
                return
            aggiunte = await citazioni_repo.importa(guild_id, righe, interaction.user.id)
            await interaction.followup.send(await testo_per(interaction, "citazioni_importate", quante=aggiunte), ephemeral=True)
            return
        etichette = (await testo_per(interaction, "conteggio_togli_bottone"), await testo_per(interaction, "conteggio_togli_annulla"))
        await interaction.response.send_message(
            await testo_per(interaction, "citazioni_elimina_chiedi", quante=await citazioni_repo.conta(guild_id)), ephemeral=True,
            view=ConfermaEliminaCitazioni(interaction.user.id, guild_id, etichette))

    # ------------------------------------------------------------ uso dei comandi e registro dello staff
    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command) -> None:
        if not isinstance(command, app_commands.Command) or interaction.guild is None or not interaction.is_guild_integration():
            return
        percorso = command.qualified_name
        try:
            await comandi_uso_repo.registra(interaction.guild.id, percorso, datetime.now(timezone.utc).date())
            if e_comando_staff(percorso):
                await self._registro_staff(interaction, percorso)
        except Exception:
            logger.warning("Uso del comando non registrato.", exc_info=True)

    async def _registro_staff(self, interaction: discord.Interaction, percorso: str) -> None:
        guild = interaction.guild
        if not await log_eventi_repo.evento_acceso(guild.id, "staff_command"):
            return
        dest = await router.destinazione(guild, router.TIPO_MODERAZIONE, None)
        if dest is None:
            return
        lingua = await lingua_risposta(guild.id, pubblica=True)
        embed = discord.Embed(
            title=t("citazioni_log_titolo", lingua), color=discord.Color.dark_grey(),
            description=t("citazioni_log_riga", lingua, utente=interaction.user.mention, comando=percorso[:200],
                          canale=f"<#{interaction.channel_id}>" if interaction.channel_id else "-"),
        )
        await router.invia_a(dest, guild, router.TIPO_MODERAZIONE, embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CitazioniCog(bot))
