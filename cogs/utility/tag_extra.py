"""
cogs/utility/tag_extra.py
=========================
Scheda di un tag (autore, usi, nomi alternativi, testo grezzo), nomi alternativi (alias) e divieti per ruolo, canale o utente:
`/admin-messaggi-tag info|alias|divieti`.
Funzioni coperte: catalogo #128 UTL-007, 008, 009, 014 (r2utl)
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.command_access import Livello, autocomplete_protetto
from core.command_groups import CogConGruppi, SOTTOGRUPPI, comando_di_gruppo
from core.custom_command_logic import MAX_NOME
from core.database import db
from core.i18n import testo_per
from core.nome_logic import normalizza_nome
from core.repositories.custom_command_repo import MAX_ALIAS, MAX_VIETATI, custom_command_repo

MODULE_CUSTOM_COMMANDS = "custom_commands"
_NESSUNA = discord.AllowedMentions.none()
_SCELTE_ALIAS = [app_commands.Choice(name="aggiungi", value="aggiungi"), app_commands.Choice(name="togli", value="togli"),
                 app_commands.Choice(name="elenco", value="elenco")]


def testo_grezzo(testo: str, massimo: int = 1700) -> str:
    """Il testo di un tag dentro un blocco di codice: i backtick si spezzano per non chiudere il blocco, le menzioni non suonano."""
    pulito = discord.utils.escape_mentions(testo.replace("```", "`​``"))
    return pulito if len(pulito) <= massimo else pulito[: massimo - 1] + "…"


class TagExtraCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @autocomplete_protetto(Livello.ADMIN)
    async def _completa(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        nomi = await custom_command_repo.search_names(interaction.guild.id, current.lower(), 25)
        return [app_commands.Choice(name=n, value=n) for n in nomi]

    async def _pronto(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_CUSTOM_COMMANDS):
            await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
            return False
        return True

    async def _tag(self, interaction: discord.Interaction, nome: str):
        """Il tag chiamato `nome`; se non c'è risponde e ritorna None."""
        normalizzato = normalizza_nome(nome)
        tag = await custom_command_repo.get_tag(interaction.guild.id, normalizzato) if normalizzato else None
        if tag is None:
            await interaction.response.send_message(await testo_per(interaction, "tag_non_esiste"), ephemeral=True)
        return tag

    # ---------------------------------------------------------------- info (UTL-007, 008)
    @comando_di_gruppo("admin-messaggi-tag", nome="info", descrizione="Scheda di un tag: autore, usi, nomi alternativi e testo grezzo.")
    @app_commands.describe(nome="Il tag", grezzo="Mostra anche il testo così com'è, senza segnaposto risolti")
    @app_commands.autocomplete(nome=_completa)
    async def info(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, MAX_NOME], grezzo: bool = False) -> None:
        if not await self._pronto(interaction):
            return
        tag = await self._tag(interaction, nome)
        if tag is None:
            return
        alias = await custom_command_repo.alias_di(interaction.guild.id, tag.name)
        righe = [
            await testo_per(interaction, "tag_info_autore", autore=f"<@{tag.created_by}>" if tag.created_by else "?"),
            await testo_per(interaction, "tag_info_usi", usi=tag.uses),
            await testo_per(interaction, "tag_info_alias", alias=", ".join(f"`{a}`" for a in alias) or "-"),
        ]
        embed = discord.Embed(title=f"`{tag.name}`", description="\n".join(righe))
        if grezzo:
            embed.add_field(name=await testo_per(interaction, "tag_info_grezzo"), value=f"```\n{testo_grezzo(tag.response)}\n```", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True, allowed_mentions=_NESSUNA)

    # ---------------------------------------------------------------- alias (UTL-009)
    @comando_di_gruppo("admin-messaggi-tag", nome="alias", descrizione="Nomi alternativi di un tag (al massimo 3).")
    @app_commands.describe(nome="Il tag", azione="Cosa fare", alias="Il nome alternativo (serve per aggiungi e togli)")
    @app_commands.choices(azione=_SCELTE_ALIAS)
    @app_commands.autocomplete(nome=_completa)
    async def alias(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, MAX_NOME],
                    azione: app_commands.Choice[str], alias: app_commands.Range[str, 1, MAX_NOME] | None = None) -> None:
        if not await self._pronto(interaction):
            return
        tag = await self._tag(interaction, nome)
        if tag is None:
            return
        guild_id = interaction.guild.id
        if azione.value == "elenco":
            elenco = await custom_command_repo.alias_di(guild_id, tag.name)
            await interaction.response.send_message(
                await testo_per(interaction, "tag_alias_elenco", nome=tag.name, alias=", ".join(f"`{a}`" for a in elenco) or "-"), ephemeral=True)
            return
        pulito = normalizza_nome(alias) if alias else None
        if pulito is None:
            await interaction.response.send_message(await testo_per(interaction, "forms_il_nome_puo_avere_solo"), ephemeral=True)
            return
        if azione.value == "togli":
            esito = "tag_alias_tolto" if await custom_command_repo.togli_alias(guild_id, pulito) else "tag_alias_non_trovato"
        else:
            esito = {"ok": "tag_alias_aggiunto", "occupato": "tag_alias_occupato", "pieno": "tag_alias_pieno", "tag_manca": "tag_non_esiste"}[
                await custom_command_repo.aggiungi_alias(guild_id, tag.name, pulito)]
        await interaction.response.send_message(
            await testo_per(interaction, esito, nome=tag.name, alias=pulito, massimo=MAX_ALIAS), ephemeral=True)

    # ---------------------------------------------------------------- divieti (UTL-014)
    @comando_di_gruppo("admin-messaggi-tag", nome="divieti", descrizione="Vieta un tag a un ruolo, un canale o un utente (al massimo 10 per elenco).")
    @app_commands.describe(nome="Il tag", ruolo="Ruolo a cui è vietato", canale="Canale dove è vietato", utente="Utente a cui è vietato",
                           togli="Toglie il divieto invece di metterlo (senza scelte: mostra gli elenchi)")
    @app_commands.autocomplete(nome=_completa)
    async def divieti(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, MAX_NOME],
                      ruolo: discord.Role | None = None, canale: discord.abc.GuildChannel | None = None,
                      utente: discord.User | None = None, togli: bool = False) -> None:
        if not await self._pronto(interaction):
            return
        tag = await self._tag(interaction, nome)
        if tag is None:
            return
        scelte = [(t, o) for t, o in (("ruolo", ruolo), ("canale", canale), ("utente", utente)) if o is not None]
        if not scelte:
            await interaction.response.send_message(
                await testo_per(interaction, "tag_divieti_elenco", nome=tag.name,
                                ruoli=" ".join(f"<@&{i}>" for i in tag.ruoli_vietati) or "-",
                                canali=" ".join(f"<#{i}>" for i in tag.canali_vietati) or "-",
                                utenti=" ".join(f"<@{i}>" for i in tag.utenti_vietati) or "-"),
                ephemeral=True, allowed_mentions=_NESSUNA)
            return
        pieno = False
        for tipo, oggetto in scelte:
            nuovo = await custom_command_repo.cambia_divieto(interaction.guild.id, tag.name, tipo, oggetto.id, not togli)
            if nuovo is not None and not togli and oggetto.id not in nuovo:
                pieno = True
        await interaction.response.send_message(
            await testo_per(interaction, "tag_divieti_pieno" if pieno else "tag_divieti_salvati", nome=tag.name, massimo=MAX_VIETATI), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TagExtraCog(bot))
