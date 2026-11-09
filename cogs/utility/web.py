"""
cogs/utility/web.py
===================
Gruppo `/web`: Wikipedia, Wikizionario, numeri di emergenza (e, nei blocchi
seguenti, meteo, film, giochi, prezzi, accorciatore). Ogni richiesta esterna
passa da core/safe_http.py con defer() subito e cache.
Funzioni coperte: catalogo #128 UTL-215, 214, 220 (B1), 213, 217, 218, 219, 208 (B2, D69)
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core import strumenti_rapidi_logic as logica
from core import web_servizi_logic as servizi
from core.config import config
from core.repositories.web_repo import web_repo
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import lingua_interazione, t


def embed_wiki(r: dict[str, str], fonte: str, colore: discord.Color) -> discord.Embed:
    embed = discord.Embed(title=r["titolo"][:256], description=r["testo"][:4000], url=r["link"] or None, color=colore)
    if r.get("immagine"):
        embed.set_thumbnail(url=r["immagine"])
    embed.set_footer(text=fonte[:2048])
    return embed


async def _completa_moneta(interaction: discord.Interaction, corrente: str) -> list[app_commands.Choice[str]]:
    return [app_commands.Choice(name=m.upper(), value=m) for m in servizi.cerca_monete(corrente)]


async def _completa_paese(interaction: discord.Interaction, corrente: str) -> list[app_commands.Choice[str]]:
    paesi = logica.carica_emergenze()["paesi"]
    return [app_commands.Choice(name=p[:100], value=p[:60]) for p in logica.cerca_paesi(corrente, paesi)]


class WebCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo("web", nome="wiki", descrizione="Il riassunto di una voce di Wikipedia.")
    @app_commands.describe(cerca="Che cosa cercare (massimo 100 caratteri)")
    async def wiki(self, interaction: discord.Interaction, cerca: app_commands.Range[str, 1, logica.MAX_RICERCA]) -> None:
        lingua = await lingua_interazione(interaction)
        await interaction.response.defer(ephemeral=True)
        r = await logica.cerca_wikipedia(logica.lingua_wiki(lingua), cerca)
        if r is None:
            await interaction.followup.send(t("wiki_non_trovata", lingua), ephemeral=True)
            return
        await interaction.followup.send(
            embed=embed_wiki(r, t("wiki_fonte", lingua), discord.Color.light_grey()), ephemeral=True
        )

    @comando_di_gruppo("web", nome="dizionario", descrizione="Il significato di una parola, da Wikizionario.")
    @app_commands.describe(parola="La parola (massimo 50 caratteri)")
    async def dizionario(
        self, interaction: discord.Interaction, parola: app_commands.Range[str, 1, logica.MAX_PAROLA]
    ) -> None:
        lingua = await lingua_interazione(interaction)
        await interaction.response.defer(ephemeral=True)
        r = await logica.cerca_parola(logica.lingua_wiki(lingua), parola)
        if r is None:
            await interaction.followup.send(t("dizionario_non_trovata", lingua), ephemeral=True)
            return
        await interaction.followup.send(
            embed=embed_wiki(r, t("dizionario_fonte", lingua), discord.Color.dark_grey()), ephemeral=True
        )

    @comando_di_gruppo("web", nome="emergenza", descrizione="I numeri di emergenza di un paese.")
    @app_commands.describe(paese="Il paese (scrivi per cercare)")
    @app_commands.autocomplete(paese=_completa_paese)
    async def emergenza(self, interaction: discord.Interaction, paese: app_commands.Range[str, 1, 60]) -> None:
        lingua = await lingua_interazione(interaction)
        dati = logica.carica_emergenze()
        nome = next(
            (p for p in dati["paesi"] if p.casefold() == paese.strip().casefold()), None
        ) or next(iter(logica.cerca_paesi(paese, dati["paesi"], 1)), None)
        if nome is None:
            await interaction.response.send_message(t("emergenza_non_trovato", lingua), ephemeral=True)
            return
        embed = discord.Embed(title=t("emergenza_titolo", lingua, paese=nome)[:256], color=discord.Color.red())
        for chiave, numero in dati["paesi"][nome].items():
            embed.add_field(name=t("emergenza_" + chiave, lingua)[:256], value=str(numero)[:1024])
        embed.set_footer(text=t("emergenza_fonte", lingua, data=dati.get("data", ""))[:2048])
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @comando_di_gruppo("web", nome="meteo", descrizione="Il meteo di una città: adesso e i prossimi giorni.")
    @app_commands.describe(citta="La città (massimo 100 caratteri)")
    async def meteo(self, interaction: discord.Interaction, citta: app_commands.Range[str, 2, servizi.MAX_CITTA]) -> None:
        lingua = await lingua_interazione(interaction)
        await interaction.response.defer(ephemeral=True)
        esito = await servizi.meteo_di(web_repo, citta)
        if esito is None or esito == "luogo":
            chiave = "meteo_luogo_non_trovato" if esito == "luogo" else "meteo_non_risponde"
            await interaction.followup.send(t(chiave, lingua), ephemeral=True)
            return
        nome, m = esito
        embed = discord.Embed(title=t("meteo_titolo", lingua, luogo=nome.split(",")[0])[:256], color=discord.Color.blue())
        embed.description = t("meteo_adesso", lingua, cielo=t(servizi.chiave_cielo(m["codice"]), lingua), temp=round(m["temp"]),
                              vento=m["vento"] if m["vento"] is not None else "—",
                              umidita=round(m["umidita"]) if m["umidita"] is not None else "—")[:4000]
        for g in m["giorni"]:
            embed.add_field(name=g["data"], value=f"{round(g['temp'])} °C · {t(servizi.chiave_cielo(g['codice']), lingua)}"[:1024])
        embed.set_footer(text=t("meteo_fonte", lingua)[:2048])
        await interaction.followup.send(embed=embed, ephemeral=True)

    @comando_di_gruppo("web", nome="film", descrizione="Informazioni su un film o una serie TV.")
    @app_commands.describe(titolo="Il titolo (massimo 100 caratteri)", tipo="Film o serie (di base: serie)")
    @app_commands.choices(tipo=[app_commands.Choice(name="film", value="film"), app_commands.Choice(name="serie", value="serie")])
    async def film(self, interaction: discord.Interaction, titolo: app_commands.Range[str, 1, servizi.MAX_TITOLO],
                   tipo: str = "serie") -> None:
        lingua = await lingua_interazione(interaction)
        await interaction.response.defer(ephemeral=True)
        try:
            r = await (servizi.cerca_film(logica.lingua_wiki(lingua), titolo) if tipo == "film" else servizi.cerca_serie(titolo))
        except TimeoutError:
            r = None
        if r is None:
            await interaction.followup.send(t("film_non_trovato", lingua), ephemeral=True)
            return
        embed = embed_wiki(r, t("film_fonte_wiki" if tipo == "film" else "film_fonte_tvmaze", lingua), discord.Color.dark_purple())
        if r.get("dettagli"):
            embed.add_field(name=t("film_dettagli", lingua)[:256], value=r["dettagli"][:1024])
        await interaction.followup.send(embed=embed, ephemeral=True)

    @comando_di_gruppo("web", nome="gioco", descrizione="Un gioco di Steam: prezzo, data e generi.")
    @app_commands.describe(titolo="Il titolo (massimo 100 caratteri)")
    async def gioco(self, interaction: discord.Interaction, titolo: app_commands.Range[str, 1, servizi.MAX_TITOLO]) -> None:
        lingua = await lingua_interazione(interaction)
        await interaction.response.defer(ephemeral=True)
        try:
            r = await servizi.cerca_gioco(logica.lingua_wiki(lingua), titolo)
        except TimeoutError:
            r = None
        if r is None:
            await interaction.followup.send(t("gioco_non_trovato", lingua), ephemeral=True)
            return
        embed = embed_wiki(r, t("gioco_fonte", lingua), discord.Color.dark_blue())
        for chiave in ("prezzo", "uscita", "generi"):
            embed.add_field(name=t("gioco_" + chiave, lingua)[:256], value=r[chiave][:1024])
        await interaction.followup.send(embed=embed, ephemeral=True)

    @comando_di_gruppo("web", nome="prezzo", descrizione="Il prezzo di una criptovaluta.")
    @app_commands.describe(simbolo="Il simbolo, per esempio btc (scrivi per cercare)", valuta="Euro o dollari (di base: euro)")
    @app_commands.autocomplete(simbolo=_completa_moneta)
    @app_commands.choices(valuta=[app_commands.Choice(name="EUR", value="eur"), app_commands.Choice(name="USD", value="usd")])
    async def prezzo(self, interaction: discord.Interaction, simbolo: app_commands.Range[str, 1, 20], valuta: str = "eur") -> None:
        lingua = await lingua_interazione(interaction)
        if not config.COINGECKO_API_KEY:
            await interaction.response.send_message(t("prezzo_non_attivo", lingua), ephemeral=True)
            return
        if simbolo.strip().casefold() not in servizi.MONETE:
            await interaction.response.send_message(t("prezzo_sconosciuto", lingua), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        esito = await servizi.prezzo_di(config.COINGECKO_API_KEY, simbolo, valuta)
        if esito is None:
            await interaction.followup.send(t("prezzo_non_risponde", lingua), ephemeral=True)
            return
        valore, variazione = esito
        testo = t("prezzo_riga", lingua, simbolo=simbolo.upper(), valore=f"{valore:,.6g}", valuta=valuta.upper())
        if variazione is not None:
            testo += "\n" + t("prezzo_variazione", lingua, v=f"{variazione:+.2f}")
        await interaction.followup.send(f"{testo}\n-# {t('prezzo_fonte', lingua)}"[:2000], ephemeral=True)

    @comando_di_gruppo("web", nome="accorcia", descrizione="Accorcia un link (se il server ha acceso il comando).")
    @app_commands.describe(link="Il link da accorciare (massimo 2000 caratteri)")
    async def accorcia(self, interaction: discord.Interaction, link: app_commands.Range[str, 8, servizi.MAX_LINK]) -> None:
        lingua = await lingua_interazione(interaction)
        if interaction.guild is None or not await web_repo.accorcia_attivo(interaction.guild.id):
            await interaction.response.send_message(t("accorcia_spento", lingua), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        esito = await servizi.accorcia_link(link)
        chiave = {"non_valido": "accorcia_non_valido", "pericoloso": "accorcia_pericoloso", "gia_corto": "accorcia_gia_corto",
                  "errore": "accorcia_errore"}.get(esito)
        await interaction.followup.send(t(chiave, lingua) if chiave else esito, ephemeral=True,
                                        allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WebCog(bot))
