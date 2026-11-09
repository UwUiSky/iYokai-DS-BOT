"""
cogs/utility/automazioni.py
===========================
Script dei tag: `/tag prova` (finestra, nulla si salva) e `/admin-automazioni script errori`. Gli inneschi e i comandi
del server stanno nei blocchi B27 e B28 (stesso gruppo `/admin-automazioni`).
Funzioni coperte: catalogo #128 UTL-043, UTL-044 (D69, B26)
Dipende da: core/tag_script_logic.py
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

from core import tag_script_logic as tag_script
from core.command_access import Livello, autocomplete_protetto
from core.command_groups import CogConGruppi, SOTTOGRUPPI, comando_di_gruppo
from core.custom_command_logic import MAX_NOME, dividi_testo
from core.database import db
from core.i18n import testo_per
from core.repositories.custom_command_repo import custom_command_repo
from core.repositories.tag_script_repo import massimo_chiavi, tag_script_repo
from core.ui_base import BaseModal

logger = logging.getLogger("iyokai.automazioni")

MODULE_CUSTOM_COMMANDS = "custom_commands"
SETTING_RUOLO_CREATORI = "tag_ruolo_creatori"
_NESSUNA = discord.AllowedMentions.none()
ROMA = ZoneInfo("Europe/Rome")


async def spiega_errore(interaction, errore: tag_script.ErroreScript) -> str:
    base = await testo_per(interaction, errore.chiave)
    return f"{base} ({errore.dettaglio})" if errore.dettaglio else base


class ProvaScriptModal(BaseModal):
    def __init__(self, cog: "AutomazioniCog", titolo: str, etichetta_script: str, etichetta_args: str) -> None:
        super().__init__(title=titolo[:45], timeout=900)
        self.cog = cog
        self.script = discord.ui.TextInput(label=etichetta_script[:45], style=discord.TextStyle.paragraph,
                                           max_length=tag_script.MAX_SCRIPT)
        self.argomenti = discord.ui.TextInput(label=etichetta_args[:45], required=False, max_length=200)
        self.add_item(self.script)
        self.add_item(self.argomenti)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await self.cog.esegui_prova(interaction, self.script.value, self.argomenti.value or "")


class AutomazioniCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _pronto(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_CUSTOM_COMMANDS):
            await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
            return False
        return True

    async def _puo_provare(self, interaction: discord.Interaction) -> bool:
        """Lo staff e chi può creare tag propri."""
        if interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator:
            return True
        ruolo_id = await db.get_guild_setting(interaction.guild.id, SETTING_RUOLO_CREATORI)
        return bool(ruolo_id) and any(r.id == ruolo_id for r in interaction.user.roles)

    # ------------------------------------------------------------ /tag prova
    @comando_di_gruppo("tag", nome="prova", descrizione="Prova uno script di tag: non salva niente e non scrive i dati veri.")
    async def prova(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        if not await self._puo_provare(interaction):
            await interaction.response.send_message(await testo_per(interaction, "tag_prova_non_puoi"), ephemeral=True)
            return
        await interaction.response.send_modal(ProvaScriptModal(
            self, await testo_per(interaction, "tag_prova_titolo"), await testo_per(interaction, "tag_prova_script"),
            await testo_per(interaction, "tag_prova_args")))

    async def esegui_prova(self, interaction: discord.Interaction, script: str, argomenti: str) -> None:
        guild, membro = interaction.guild, interaction.user
        archivio = tag_script.ArchivioProva(tag_script_repo.archivio(guild.id, lambda: massimo_chiavi(guild.id, self.bot)))
        valori = {"user": membro.mention, "username": membro.display_name, "server": guild.name,
                  "channel": getattr(interaction.channel, "mention", ""), "args": argomenti, "bersaglio": ""}
        esito = await tag_script.esegui(script, tag_script.Contesto(valori=valori, adesso=datetime.now(ROMA), archivio=archivio))
        if esito.errore is not None:
            testo = await testo_per(interaction, "tag_prova_errore", errore=await spiega_errore(interaction, esito.errore),
                                    operazioni=esito.operazioni)
            await interaction.followup.send(testo[:2000], ephemeral=True, allowed_mentions=_NESSUNA)
            return
        piede = await testo_per(interaction, "tag_prova_piede", operazioni=esito.operazioni, massimo=tag_script.MAX_OPERAZIONI)
        pezzi = dividi_testo(esito.testo.strip() or await testo_per(interaction, "tag_prova_vuoto"), 1900)
        pezzi[-1] += "\n\n" + piede
        for pezzo in pezzi:
            await interaction.followup.send(pezzo, ephemeral=True, allowed_mentions=_NESSUNA)

    # ------------------------------------------------------------ /admin-automazioni script errori
    @autocomplete_protetto(Livello.ADMIN)
    async def _completa_tag(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        nomi = await custom_command_repo.search_names(interaction.guild.id, current.lower(), 25)
        return [app_commands.Choice(name=n, value=n) for n in nomi]

    @comando_di_gruppo("admin-automazioni", nome="errori", descrizione="Gli ultimi 10 errori dello script di un tag.",
                       sottogruppo=SOTTOGRUPPI["admin-automazioni script"])
    @app_commands.describe(nome="Il tag")
    @app_commands.autocomplete(nome=_completa_tag)
    async def errori(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, MAX_NOME]) -> None:
        if not await self._pronto(interaction):
            return
        righe = await tag_script_repo.ultimi_errori(interaction.guild.id, nome.strip().lower())
        if not righe:
            await interaction.response.send_message(await testo_per(interaction, "tag_errori_vuoti", nome=nome[:MAX_NOME]),
                                                    ephemeral=True, allowed_mentions=_NESSUNA)
            return
        elenco = []
        for r in righe:
            motivo = await testo_per(interaction, r["chiave"])
            elenco.append(f"{discord.utils.format_dt(r['creato_il'], 'R')} · {motivo}" + (f" ({r['dettaglio']})" if r["dettaglio"] else ""))
        testo = await testo_per(interaction, "tag_errori_titolo", nome=nome[:MAX_NOME]) + "\n" + "\n".join(elenco)
        await interaction.response.send_message(testo[:2000], ephemeral=True, allowed_mentions=_NESSUNA)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutomazioniCog(bot))
