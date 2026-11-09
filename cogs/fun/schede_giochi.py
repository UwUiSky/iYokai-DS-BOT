"""
cogs/fun/schede_giochi.py
=========================
`/web scheda tipo: nome:` (#131, D70, B9): scheda di un Pokémon (con il bottone «Debolezze»), un anime, un manga,
una carta di Magic o Hearthstone, un giocatore di osu! o di Fortnite. I dati arrivano da `core/schede_giochi_logic.py`
(cache comune, servizi spenti senza chiave). Contenuti per adulti solo nei canali con limite d'età.
Funzioni coperte: SPEC §16 (B9 di #131: FUN-066..070, 073)
Dipende da: core/schede_giochi_logic.py, core/repositories/cache_esterna_repo.py
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core import schede_giochi_logic as sl
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import lingua_interazione, t, testo_per
from core.repositories.cache_esterna_repo import cache_esterna_repo
from core.ui_base import BaseView

COLORI = {"pokemon": 0xEE1515, "anime": 0x02A9FF, "manga": 0x02A9FF, "magic": 0x8E5A2B, "hearthstone": 0xF0A030, "osu": 0xFF66AA, "fortnite": 0x6A5ACD}


def testo_debolezze(tipi: list[str], lingua: str) -> str:
    nomi = sl.TIPI_IT if lingua.startswith("it") else {k: k.title() for k in sl.TIPI_IT}
    righe = []
    for m, etichetta in ((4.0, "×4"), (2.0, "×2"), (0.5, "×½"), (0.25, "×¼"), (0.0, "×0")):
        elenco = sl.debolezze(tipi).get(m)
        if elenco:
            righe.append(f"**{etichetta}**: " + ", ".join(nomi[x] for x in elenco))
    return "\n".join(righe)[:1900]


class VistaPokemon(BaseView):
    """Il bottone «Debolezze»: calcola i moltiplicatori dai tipi, senza altre richieste di rete."""

    def __init__(self, autore_id: int, tipi: list[str], etichetta: str, lingua: str) -> None:
        super().__init__(timeout=300)
        self.autore_id, self.tipi, self.lingua = autore_id, tipi, lingua
        self.debolezze.label = etichetta[:45]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.autore_id:
            await interaction.response.send_message(await testo_per(interaction, "fun_solo_chi_gioca"), ephemeral=True)
            return False
        return True

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="🛡️")
    async def debolezze(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message(testo_debolezze(self.tipi, self.lingua) or "-", ephemeral=True)


def costruisci_embed(servizio: str, dati: dict, lingua: str) -> discord.Embed:
    embed = discord.Embed(title=dati["titolo"][:256], description=(dati.get("descrizione") or None), url=dati.get("url") or None, color=COLORI[servizio])
    for chiave, valore in dati.get("campi", [])[:10]:
        embed.add_field(name=t(chiave, lingua)[:256], value=str(valore)[:1024], inline=len(str(valore)) < 40)
    if dati.get("miniatura"):
        embed.set_thumbnail(url=dati["miniatura"])
    if dati.get("immagine"):
        embed.set_image(url=dati["immagine"])  # l'immagine delle carte resta intera (Scryfall)
    embed.set_footer(text=t(f"scheda_fonte_{servizio}", lingua)[:2048])
    return embed


class SchedeGiochiCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        await super().cog_load()

    async def cog_unload(self) -> None:
        await super().cog_unload()

    @comando_di_gruppo("web", nome="scheda", descrizione="La scheda di un Pokémon, anime, carta o giocatore.")
    @app_commands.describe(tipo="Che cosa cercare", nome="Il nome (massimo 100 caratteri)")
    @app_commands.choices(
        tipo=[
            app_commands.Choice(name="Pokémon", value="pokemon"), app_commands.Choice(name="Anime", value="anime"),
            app_commands.Choice(name="Manga", value="manga"), app_commands.Choice(name="Magic: carta", value="magic"),
            app_commands.Choice(name="Hearthstone: carta", value="hearthstone"), app_commands.Choice(name="osu!: giocatore", value="osu"),
            app_commands.Choice(name="Fortnite: giocatore", value="fortnite"),
        ]
    )
    async def scheda(self, interaction: discord.Interaction, tipo: app_commands.Choice[str], nome: app_commands.Range[str, 1, sl.MAX_NOME]) -> None:
        lingua = await lingua_interazione(interaction)
        if not sl.servizio_acceso(tipo.value):
            await interaction.response.send_message(t("scheda_spento", lingua), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        dati = await sl.cerca(tipo.value, nome, lingua, cache_esterna_repo)
        if not dati:
            await interaction.followup.send(t("scheda_non_trovata", lingua), ephemeral=True)
            return
        canale = interaction.channel
        if dati.get("adulti") and not bool(getattr(canale, "is_nsfw", lambda: False)()):
            await interaction.followup.send(t("scheda_adulti", lingua), ephemeral=True)
            return
        vista = VistaPokemon(interaction.user.id, dati.get("tipi") or [], t("scheda_debolezze", lingua), lingua) if tipo.value == "pokemon" and dati.get("tipi") else None
        await interaction.followup.send(embed=costruisci_embed(tipo.value, dati, lingua), ephemeral=True, **({"view": vista} if vista else {}))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SchedeGiochiCog(bot))
