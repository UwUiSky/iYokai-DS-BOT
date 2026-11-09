"""
cogs/utility/tag_opzioni.py
===========================
Opzioni di comportamento dei tag e risposte con peso: `/admin-tag tag opzioni` (permesso richiesto, bersaglio, cancella
l'innesco, dove rispondere, solo NSFW) e `/admin-tag tag risposte` (fino a 5 risposte con peso, in una finestra).
Funzioni coperte: catalogo #128 UTL-011, 015, 017, 019, 020, 021, 037 (D69, B19-B20)
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.channel_access import PERMESSI_DI_SCRITTURA, permessi_mancanti
from core.command_access import Livello, autocomplete_protetto
from core.command_groups import CogConGruppi, SOTTOGRUPPI, comando_di_gruppo
from core.custom_command_logic import (
    INVII, MAX_NOME, MAX_RISPOSTE_TAG, MAX_TESTO, MIN_CANCELLA_DOPO, PERMESSI_TAG, leggi_reazioni, leggi_risposta,
)
from core.database import db
from core.i18n import testo_per
from core.nome_logic import normalizza_nome
from core.repositories.custom_command_repo import custom_command_repo
from core.tag_pacchetti_logic import nome_gruppo_valido
from core.ui_base import BaseModal

MODULE_CUSTOM_COMMANDS = "custom_commands"
_SCELTE_PERMESSO = [app_commands.Choice(name="nessuno", value="nessuno")] + [
    app_commands.Choice(name=f"serve: {nome}", value=chiave) for chiave, nome in PERMESSI_TAG.items()
]
_SCELTE_INVIO = [
    app_commands.Choice(name="nel canale dove si usa", value="canale"),
    app_commands.Choice(name="in privato a chi lo usa", value="privato"),
    app_commands.Choice(name="in un altro canale", value="altro"),
]


class RisposteModal(BaseModal):
    """Fino a 5 risposte; ognuna può cominciare con un peso: `3| ciao`. Chi usa il tag ne riceve una a caso."""

    def __init__(self, titolo: str, guild_id: int, nome: str, attuali: list[tuple[int, str]], etichetta: str) -> None:
        super().__init__(title=titolo[:45], timeout=600)
        self.guild_id, self.nome = guild_id, nome
        self.campi: list[discord.ui.TextInput] = []
        for i in range(MAX_RISPOSTE_TAG):
            iniziale = f"{attuali[i][0]}| {attuali[i][1]}" if i < len(attuali) else ""
            campo = discord.ui.TextInput(
                label=f"{etichetta} {i + 1}"[:45], style=discord.TextStyle.paragraph, required=False,
                max_length=MAX_TESTO, default=iniziale[:MAX_TESTO])
            self.campi.append(campo)
            self.add_item(campo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        lette = [r for r in (leggi_risposta(c.value) for c in self.campi) if r is not None]
        if not await custom_command_repo.set_risposte(self.guild_id, self.nome, lette):
            await interaction.response.send_message(await testo_per(interaction, "tag_non_esiste"), ephemeral=True)
            return
        await interaction.response.send_message(
            await testo_per(interaction, "tag_risposte_salvate", quante=len(lette)), ephemeral=True)


class TagOpzioniCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @autocomplete_protetto(Livello.ADMIN)
    async def _completa(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        nomi = await custom_command_repo.search_names(interaction.guild.id, current.lower(), 25)
        return [app_commands.Choice(name=n, value=n) for n in nomi]

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        await custom_command_repo.canale_cancellato(channel.guild.id, channel.id)

    async def _pronto(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_CUSTOM_COMMANDS):
            await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
            return False
        return True

    @comando_di_gruppo("admin-tag", nome="opzioni", descrizione="Come si comporta un tag: permesso, bersaglio, dove risponde.",
                       sottogruppo=SOTTOGRUPPI["admin-tag tag"])
    @app_commands.describe(
        nome="Il tag da cambiare", permesso="Il permesso Discord che serve per usarlo",
        bersaglio="Il tag chiede un membro (segnaposto {bersaglio})", cancella_innesco="Col prefisso, cancella il messaggio che lo ha chiamato",
        invio="Dove va la risposta", canale="Il canale, se la risposta va in un altro canale", solo_nsfw="Si usa solo nei canali per adulti",
        reazioni="Fino a 5 emoji che il bot mette alla risposta (vuoto: nessuna)",
        si_cancella_dopo="La risposta sparisce dopo tanti secondi (da 5 a 3600; 0: resta)",
        cancella_messaggi="Prima di rispondere cancella gli ultimi N messaggi (0: nessuno; non oltre 14 giorni)",
        anche_modificati="Scatta anche se il messaggio viene modificato in un comando",
        gruppo="Il gruppo del tag, con le sue regole di canale e ruolo (vuoto: nessuno)",
    )
    @app_commands.choices(permesso=_SCELTE_PERMESSO, invio=_SCELTE_INVIO)
    @app_commands.autocomplete(nome=_completa)
    async def opzioni(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, MAX_NOME], permesso: str | None = None,
        bersaglio: bool | None = None, cancella_innesco: bool | None = None, invio: str | None = None,
        canale: discord.TextChannel | None = None, solo_nsfw: bool | None = None,
        reazioni: app_commands.Range[str, 0, 200] | None = None,
        si_cancella_dopo: app_commands.Range[int, 0, 3600] | None = None,
        cancella_messaggi: app_commands.Range[int, 0, 100] | None = None, anche_modificati: bool | None = None,
        gruppo: app_commands.Range[str, 0, 32] | None = None,
    ) -> None:
        if not await self._pronto(interaction):
            return
        normalizzato = normalizza_nome(nome)
        tag = await custom_command_repo.get_tag(interaction.guild.id, normalizzato) if normalizzato else None
        if tag is None:
            await interaction.response.send_message(await testo_per(interaction, "tag_non_esiste"), ephemeral=True)
            return
        campi: dict = {}
        if permesso is not None:
            campi["permesso"] = None if permesso == "nessuno" else permesso
        if reazioni is not None:
            lette = leggi_reazioni(reazioni)
            if lette is None:
                await interaction.response.send_message(await testo_per(interaction, "tag_reazioni_non_valide"), ephemeral=True)
                return
            campi["reazioni"] = lette
        if si_cancella_dopo is not None:
            if 0 < si_cancella_dopo < MIN_CANCELLA_DOPO:
                await interaction.response.send_message(
                    await testo_per(interaction, "tag_cancella_dopo_minimo", minimo=MIN_CANCELLA_DOPO), ephemeral=True)
                return
            campi["si_cancella_dopo"] = si_cancella_dopo or None
        if gruppo is not None:
            nome_g = nome_gruppo_valido(gruppo) if gruppo.strip() else None
            if gruppo.strip() and nome_g is None:
                await interaction.response.send_message(await testo_per(interaction, "tag_gruppo_nome"), ephemeral=True)
                return
            if nome_g and await custom_command_repo.gruppo(interaction.guild.id, nome_g) is None:
                await custom_command_repo.imposta_gruppo(interaction.guild.id, nome_g, None, None)  # nasce senza regole
            campi["gruppo"] = nome_g
        if cancella_messaggi is not None:
            campi["cancella_messaggi"] = cancella_messaggi or None
        for chiave, valore in (("bersaglio", bersaglio), ("cancella_innesco", cancella_innesco), ("solo_nsfw", solo_nsfw),
                               ("anche_modificati", anche_modificati)):
            if valore is not None:
                campi[chiave] = valore
        if invio is not None:
            if invio not in INVII:
                return
            campi["invio"] = invio
        finale_invio = campi.get("invio", tag.invio)
        if canale is not None:
            campi["canale_id"] = canale.id
        finale_canale = canale.id if canale is not None else tag.canale_id
        if finale_invio == "altro":
            scelto = canale or (interaction.guild.get_channel(finale_canale) if finale_canale else None)
            if scelto is None:
                await interaction.response.send_message(await testo_per(interaction, "tag_serve_canale"), ephemeral=True)
                return
            if permessi_mancanti(scelto, interaction.guild.me, PERMESSI_DI_SCRITTURA) or not scelto.permissions_for(interaction.user).send_messages:
                await interaction.response.send_message(await testo_per(interaction, "tag_canale_non_scrivibile"), ephemeral=True)
                return
        if not campi:
            await interaction.response.send_message(await testo_per(interaction, "tag_nessuna_opzione"), ephemeral=True)
            return
        await custom_command_repo.update_tag(interaction.guild.id, normalizzato, **campi)
        await interaction.response.send_message(await testo_per(interaction, "tag_opzioni_salvate", nome=normalizzato), ephemeral=True)

    @comando_di_gruppo("admin-tag", nome="risposte", descrizione="Dai a un tag fino a 5 risposte, ognuna con il suo peso.",
                       sottogruppo=SOTTOGRUPPI["admin-tag tag"])
    @app_commands.describe(nome="Il tag da cambiare")
    @app_commands.autocomplete(nome=_completa)
    async def risposte(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, MAX_NOME]) -> None:
        if not await self._pronto(interaction):
            return
        normalizzato = normalizza_nome(nome)
        tag = await custom_command_repo.get_tag(interaction.guild.id, normalizzato) if normalizzato else None
        if tag is None:
            await interaction.response.send_message(await testo_per(interaction, "tag_non_esiste"), ephemeral=True)
            return
        attuali = await custom_command_repo.get_risposte(interaction.guild.id, normalizzato)
        titolo = await testo_per(interaction, "tag_risposte_titolo")
        await interaction.response.send_modal(
            RisposteModal(titolo, interaction.guild.id, normalizzato, attuali, await testo_per(interaction, "tag_risposta_etichetta")))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TagOpzioniCog(bot))
