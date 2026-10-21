"""
cogs/nsfw/ricerca.py
====================
Comandi dell'istanza NSFW: `/nsfw cerca` per i membri e `/nsfw-admin`
per lo staff (attiva, lista permessa, pubblicazione automatica, stato),
più il bottone «Segnala» sotto ogni contenuto. Si carica solo sul client
NSFW (core/nsfw_bot.py): sul bot principale `setup` non fa nulla.
Funzioni coperte: SPEC §16.10 (NF-23)
Dipende da: core/nsfw_servizio.py
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core import nsfw_servizio as servizio
from core.config import config
from core.nsfw_bot import e_istanza_nsfw
from core.nsfw_filter_logic import MAX_TAG_PERMESSI, canale_ammesso
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.nsfw")

ID_SEGNALA = "nsfw:segnala"
AVVISO_ATTIVA = (
    "Accendendo l'istanza confermi che questo server segue le regole di Discord sui contenuti per adulti: "
    "solo canali vietati ai minori, nessun minore tra i membri che li vedono. I contenuti arrivano solo da "
    "fonti che dichiarano età e consenso, e passano la lista vietata fissa e la lista permessa del server."
)


class VistaSegnala(BaseView):
    """Bottone persistente sotto ogni contenuto: lo toglie e lo blocca in tutti i server."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Segnala", style=discord.ButtonStyle.danger, custom_id=ID_SEGNALA)
    async def segnala(self, interaction: discord.Interaction, _bottone: discord.ui.Button) -> None:
        messaggio = interaction.message
        esito = await servizio.segnala(messaggio.id, interaction.user.id) if messaggio else None
        if esito is None:
            await interaction.response.send_message("Questo contenuto non è nel registro.", ephemeral=True)
            return
        try:
            await messaggio.delete()
        except discord.HTTPException:
            pass
        invio, ovunque = esito
        dove = "in tutti i server" if ovunque else "in questo server"
        await interaction.response.send_message(
            f"Contenuto tolto e bloccato {dove}. Se pensi che sia illegale, segnalalo anche a Discord: "
            "https://dis.gd/request",
            ephemeral=True,
        )
        if ovunque:  # oltre il tetto niente DM all'owner: il bottone non diventa un modo per riempirgli i DM
            await _avvisa_owner(
                interaction.client, f"Contenuto NSFW segnalato e bloccato: {invio.fonte}/{invio.id_fonte}."
            )


def vista_pubblicazione() -> discord.ui.View:
    return VistaSegnala()


async def _avvisa_owner(client: discord.Client, testo: str) -> None:
    try:
        owner = await client.fetch_user(config.OWNER_ID)
        await owner.send(testo[:2000])
    except discord.HTTPException:
        logger.info("Avviso all'owner non consegnato (nessun DM possibile dall'istanza NSFW).")


def _puo_gestire(interaction: discord.Interaction) -> bool:
    permessi = getattr(interaction.user, "guild_permissions", None)
    return bool(permessi and permessi.manage_guild)


class NsfwCog(commands.Cog):
    nsfw = app_commands.Group(
        name="nsfw", description="Contenuti per adulti, solo nei canali vietati ai minori.", guild_only=True, nsfw=True
    )
    admin = app_commands.Group(
        name="nsfw-admin",
        description="Impostazioni dell'istanza NSFW di questo server.",
        guild_only=True,
        nsfw=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _tag_permessi(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if interaction.guild is None:
            return []
        config_server = await servizio.leggi(interaction.guild.id)
        cerca = current.lower().strip()
        return [app_commands.Choice(name=t, value=t) for t in config_server.tag_permessi if cerca in t][:25]

    # ---------------------------------------------------------------- membri
    @nsfw.command(name="cerca", description="Pubblica qui un contenuto con un tag permesso dal server.")
    @app_commands.describe(tag="Un tag della lista permessa del server")
    @app_commands.checks.cooldown(1, 15, key=lambda i: i.user.id)
    async def cerca(self, interaction: discord.Interaction, tag: app_commands.Range[str, 2, 32]) -> None:
        if not canale_ammesso(interaction.channel):
            await interaction.response.send_message(servizio.CANALE_NON_AMMESSO, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        scelta = await servizio.scegli(interaction.guild.id, tag)
        if isinstance(scelta, str):
            await interaction.followup.send(scelta, ephemeral=True)
            return
        esito = await servizio.pubblica(interaction.channel, scelta, vista_pubblicazione())
        await interaction.followup.send("Pubblicato." if not isinstance(esito, str) else esito, ephemeral=True)

    cerca.autocomplete("tag")(_tag_permessi)

    # ---------------------------------------------------------------- staff
    async def _solo_staff(self, interaction: discord.Interaction) -> bool:
        if _puo_gestire(interaction):
            return True
        await interaction.response.send_message("Serve il permesso «Gestisci server».", ephemeral=True)
        return False

    @admin.command(name="attiva", description="Accende o spegne l'istanza NSFW in questo server.")
    @app_commands.describe(accesa="Accesa o spenta", conferma="Confermo le regole sui contenuti per adulti")
    async def attiva(self, interaction: discord.Interaction, accesa: bool, conferma: bool = False) -> None:
        if not await self._solo_staff(interaction):
            return
        if accesa and not conferma:
            await interaction.response.send_message(AVVISO_ATTIVA + "\nRipeti il comando con `conferma: True`.", ephemeral=True)
            return
        await servizio.imposta_attivo(interaction.guild.id, accesa, interaction.user.id)
        testo = "Istanza NSFW accesa." if accesa else "Istanza NSFW spenta: anche le pubblicazioni automatiche sono ferme."
        await interaction.response.send_message(testo, ephemeral=True)

    @admin.command(name="tag-aggiungi", description="Aggiunge un tag alla lista permessa del server.")
    @app_commands.describe(tag="Il tag da permettere (2-32 caratteri)")
    async def tag_aggiungi(self, interaction: discord.Interaction, tag: app_commands.Range[str, 2, 32]) -> None:
        if not await self._solo_staff(interaction):
            return
        _ok, testo = await servizio.aggiungi_tag(interaction.guild.id, tag)
        await interaction.response.send_message(testo, ephemeral=True)

    @admin.command(name="tag-togli", description="Toglie un tag dalla lista permessa del server.")
    @app_commands.describe(tag="Il tag da togliere")
    async def tag_togli(self, interaction: discord.Interaction, tag: app_commands.Range[str, 2, 32]) -> None:
        if not await self._solo_staff(interaction):
            return
        _ok, testo = await servizio.togli_tag(interaction.guild.id, tag)
        await interaction.response.send_message(testo, ephemeral=True)

    tag_togli.autocomplete("tag")(_tag_permessi)

    @admin.command(name="autopost", description="Pubblica da solo in un canale vietato ai minori.")
    @app_commands.describe(
        canale="Canale vietato ai minori", tag="Tag della lista permessa (vuoto: uno a caso)", minuti="Ogni quanti minuti"
    )
    async def autopost(
        self,
        interaction: discord.Interaction,
        canale: discord.TextChannel,
        tag: app_commands.Range[str, 2, 32] | None = None,
        minuti: app_commands.Range[int, 30, 1440] = 120,
    ) -> None:
        if not await self._solo_staff(interaction):
            return
        _ok, testo = await servizio.imposta_autopost(interaction.guild.id, canale, tag, minuti, interaction.user.id)
        await interaction.response.send_message(testo, ephemeral=True)

    autopost.autocomplete("tag")(_tag_permessi)

    @admin.command(name="autopost-ferma", description="Ferma la pubblicazione automatica (vuoto: tutte).")
    @app_commands.describe(canale="Il canale da fermare; vuoto per fermarle tutte")
    async def autopost_ferma(self, interaction: discord.Interaction, canale: discord.TextChannel | None = None) -> None:
        if not await self._solo_staff(interaction):
            return
        tolte = await servizio.ferma_autopost(interaction.guild.id, canale.id if canale else None)
        await interaction.response.send_message(f"Pubblicazioni automatiche fermate: {tolte}.", ephemeral=True)

    @admin.command(name="stato", description="Mostra le impostazioni NSFW del server.")
    async def stato(self, interaction: discord.Interaction) -> None:
        if not await self._solo_staff(interaction):
            return
        config_server = await servizio.leggi(interaction.guild.id)
        autopost = await servizio.elenco_autopost(interaction.guild.id)
        embed = discord.Embed(title="Istanza NSFW", color=discord.Color.dark_red())
        embed.add_field(name="Stato", value="accesa" if config_server.attivo else "spenta", inline=False)
        tag = ", ".join(f"`{t}`" for t in config_server.tag_permessi) or "nessuno"
        embed.add_field(
            name=f"Lista permessa ({len(config_server.tag_permessi)}/{MAX_TAG_PERMESSI})", value=tag[:1024], inline=False
        )
        righe = [f"<#{a.channel_id}>: `{a.tag or 'a caso'}` ogni {a.intervallo_minuti} min" for a in autopost]
        embed.add_field(name="Pubblicazione automatica", value="\n".join(righe)[:1024] or "nessuna", inline=False)
        embed.set_footer(text="La lista vietata è fissa nel codice e vale sempre.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Solo sul client NSFW: il bot principale non riceve questi comandi."""
    if not e_istanza_nsfw(bot):
        return
    await bot.add_cog(NsfwCog(bot))
    bot.add_view(VistaSegnala())
