"""
cogs/fun/entertainment.py
============================
Mini-giochi (SPEC.md §16.1), altri comandi di intrattenimento
classici (§16.8): testa/croce, dado, carta/forbici/sasso, palla
magica 8, barzelletta, citazione, curiosità — e image manipulation
(§16.2)/immagini meme (§16.3): scala di grigi, inverti, sfoca, pixela,
generatore di meme testo-sopra/testo-sotto. Tutti operano
sull'allegato passato al comando o, se assente, sull'avatar
dell'utente (o dell'utente menzionato) — così ogni comando funziona
anche senza dover allegare un'immagine ogni volta. I comandi immagine
passano tutti da `_rispondi_con_immagine` (SEC-20): allegato
controllato prima di scaricarlo, `defer()`, risposta con followup.

Funzioni coperte: SPEC §16.1-16.4, §16.8-16.9; M 15.1, M 15.2; FUN-035, 049-052, 054 (#131).
Tutti i comandi stanno nel gruppo condiviso `/fun` (core/command_groups.py);
`/fun ship` e `/fun rate` sono in cogs/fun/ship_rate.py.

Terzo lotto (§16.4 Comandi animal, §16.9 Ricerca immagini SFW):
`/immagini animal` (fino a 5 immagini) usa tre API pubbliche gratuite senza chiave
(dog.ceo, thecatapi.com, randomfox.ca — core/animal_fetcher.py) e Pixabay per l'uccello;
`/immagini foto` (cibo, buonumore) usa Pixabay; `/immagini xkcd` core/xkcd_fetcher.py;
`/immagini search-image` usa Pixabay, che invece richiede una chiave
gratuita (PIXABAY_API_KEY in core/config.py, stesso principio di
sblocco opzionale già usato per Twitch/YouTube) — a differenza delle
altre integrazioni opzionali di questo bot, senza quella chiave il
comando non può funzionare affatto, quindi risponde con un messaggio
che spiega come attivarla invece di restare silenziosamente
inutilizzabile. Entrambi i fetcher sono iniettabili nel costruttore
del cog (default ai singleton di modulo) per essere sostituiti nei
test con un server aiohttp finto, stesso schema già usato per
core/twitch_watcher.py/core/youtube_watcher.py.
"""

from __future__ import annotations

import asyncio
import io
import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from core.animal_fetcher import animal_fetcher
from core.classic_entertainment_logic import (
    FACTS_ANIMALI,
    JOKES_TEMATICHE,
    random_fact,
    random_joke,
)
from core.fun_extra_logic import tira_formula
from core.fun_piccoli_logic import MAX_MONETE, striscia_monete, tira_monete
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.config import config
from core.database import db
from core.i18n import testo_per
from core.image_manipulation import apply_blur, apply_grayscale, apply_invert, apply_pixelate
from core.image_search_fetcher import image_search_fetcher
from core.meme_logic import render_meme
from core.minigames_logic import answer_8ball, flip_coin, play_rps, roll_dice
from core.premium import PremiumModule, registry
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.safe_image import MAX_IMAGE_BYTES, run_image_task
from core.xkcd_fetcher import xkcd_service

MODULE_FUN = "fun"
PAUSA_RICERCA_IMMAGINI_SECONDI = 10
MAX_UTENTI_NELLA_PAUSA = 1000
MAX_ANIMALI = 5
SPECIE_SORPRESA = ("dog", "cat", "fox", "bird")
# Ricerche curate per /immagini foto: sempre con safesearch (lo imposta image_search_fetcher).
QUERY_FOTO = {
    "cibo": ("food", "pizza", "pasta", "dessert", "fruit", "salad", "bread", "sushi"),
    "buonumore": ("happy", "smile", "sunshine", "rainbow", "puppy", "flowers", "kitten", "friends laughing"),
}

_RPS_CHOICE_DISPLAY = {"sasso": "🪨 Sasso", "carta": "📄 Carta", "forbici": "✂️ Forbici"}


class EntertainmentCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._rng = random.Random()
        self._ultima_ricerca_immagini: dict[int, float] = {}

    async def _modulo_attivo(self, interaction: discord.Interaction) -> bool:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return False

        if not await db.is_module_active_for_guild(guild.id, MODULE_FUN):
            await interaction.response.send_message(
                await testo_per(interaction, "ping_questo_modulo_non_attivo_su"),
                ephemeral=True,
            )
            return False
        return True

    async def _allegato_accettabile(
        self, interaction: discord.Interaction, image: discord.Attachment | None
    ) -> bool:
        """
        Controlla tipo e dimensione dichiarati dell'allegato SENZA
        scaricarlo (SEC-20). Se non va bene risponde da sola e
        restituisce False.
        """
        if image is None:
            return True
        if not (image.content_type or "").startswith("image/"):
            await interaction.response.send_message(
                await testo_per(interaction, "app_fun_non_immagine"), ephemeral=True
            )
            return False
        if image.size > MAX_IMAGE_BYTES:
            limite_mb = MAX_IMAGE_BYTES // (1024 * 1024)
            await interaction.response.send_message(
                await testo_per(interaction, "entertainmen_immagine_troppo_grande_massimo_mb", limite_mb=limite_mb), ephemeral=True
            )
            return False
        return True

    async def _scarica_immagine(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment | None,
        utente: discord.Member | None,
    ) -> bytes | None:
        """
        Priorità: allegato esplicito > utente menzionato > l'autore
        del comando stesso. None se il download fallisce.
        """
        try:
            if image is not None:
                return await image.read()
            soggetto = utente or interaction.user
            return await soggetto.display_avatar.read()
        except discord.HTTPException:
            return None

    async def _rispondi_con_immagine(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment | None,
        utente: discord.Member | None,
        nome_file: str,
        elabora,
        *argomenti,
    ) -> None:
        """
        Percorso comune dei comandi immagine (SEC-20): controlli che non
        richiedono download, poi `defer()` — scaricare ed elaborare può
        superare i 3 secondi concessi da Discord — e risposta con followup.
        """
        if not await self._allegato_accettabile(interaction, image):
            return

        await interaction.response.defer()

        dati = await self._scarica_immagine(interaction, image, utente)
        if dati is None:
            await interaction.followup.send(await testo_per(interaction, "app_immagine_non_scaricata", pubblica=True))
            return

        risultato = await run_image_task(elabora, dati, *argomenti)
        if risultato is None:
            await interaction.followup.send(await testo_per(interaction, "app_immagine_non_elaborata", pubblica=True))
            return

        await interaction.followup.send(
            file=discord.File(io.BytesIO(risultato), filename=nome_file)
        )

    @comando_di_gruppo("fun", nome="coinflip", descrizione="Lancia una moneta: testa o croce.")
    @app_commands.describe(quante="Quante monete lanciare, da 1 a 10 (facoltativo)")
    async def coinflip(
        self, interaction: discord.Interaction, quante: app_commands.Range[int, 1, MAX_MONETE] = 1
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return

        esiti = tira_monete(quante, self._rng)
        if quante == 1:
            await interaction.response.send_message(f"🪙 **{esiti[0].upper()}**!")
            return

        await interaction.response.defer()
        moneta = await leveling_settings_repo.get_immagine_moneta(interaction.guild.id)
        png = await run_image_task(striscia_monete, esiti, moneta)
        teste = esiti.count("testa")
        riga = await testo_per(interaction, "fun_monete_riepilogo", pubblica=True, teste=teste, croci=quante - teste)
        await interaction.followup.send(
            f"🪙 {riga}", file=discord.File(io.BytesIO(png), filename="monete.png")
        )

    @comando_di_gruppo("fun", nome="dice", descrizione="Tira un dado.")
    @app_commands.describe(
        sides="Numero di facce del dado (default 6, minimo 2, massimo 1000)",
        formula="Formula da gioco di ruolo, per esempio 3d6+2 (al posto delle facce)",
    )
    async def dice(
        self,
        interaction: discord.Interaction,
        sides: int = 6,
        formula: app_commands.Range[str, 2, 20] | None = None,
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return

        if formula:
            esito = tira_formula(formula, self._rng)
            if esito.errore:
                await interaction.response.send_message(esito.errore, ephemeral=True)
                return
            dettaglio = " + ".join(str(t) for t in esito.tiri)
            if esito.modificatore:
                dettaglio += f" {'+' if esito.modificatore > 0 else '-'} {abs(esito.modificatore)}"
            await interaction.response.send_message(
                f"🎲 `{formula.strip()}`: {dettaglio} = **{esito.totale}**"
            )
            return

        if sides < 2 or sides > 1000:
            await interaction.response.send_message(
                await testo_per(interaction, "entertainmen_il_dado_deve_avere_tra"), ephemeral=True
            )
            return

        risultato = roll_dice(self._rng, sides=sides)
        await interaction.response.send_message(await testo_per(interaction, "entertainmen_hai_tirato_un", pubblica=True, risultato=risultato, sides=sides))

    @comando_di_gruppo("giochi", nome="rps", descrizione="Carta, forbici, sasso contro il bot.")
    @app_commands.describe(scelta="Sasso, carta o forbici")
    @app_commands.choices(
        scelta=[
            app_commands.Choice(name="Sasso", value="sasso"),
            app_commands.Choice(name="Carta", value="carta"),
            app_commands.Choice(name="Forbici", value="forbici"),
        ]
    )
    async def rps(self, interaction: discord.Interaction, scelta: app_commands.Choice[str]) -> None:
        if not await self._modulo_attivo(interaction):
            return

        scelta_bot, esito = play_rps(scelta.value, self._rng)

        if esito == "vittoria":
            titolo = "🎉 Hai vinto!"
        elif esito == "sconfitta":
            titolo = "😔 Hai perso."
        else:
            titolo = "🤝 Pareggio!"

        await interaction.response.send_message(
            f"{titolo}\nTu: {_RPS_CHOICE_DISPLAY[scelta.value]} — "
            f"Bot: {_RPS_CHOICE_DISPLAY[scelta_bot]}"
        )

    @comando_di_gruppo("fun", nome="8ball", descrizione="Fai una domanda alla palla magica 8.")
    @app_commands.describe(domanda="La tua domanda (massimo 300 caratteri)")
    async def eight_ball(
        self, interaction: discord.Interaction, domanda: app_commands.Range[str, 1, 300]
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return

        risposta = answer_8ball(self._rng)
        embed = discord.Embed(
            title=await testo_per(interaction, "entertainmen_palla_magica", pubblica=True),
            description=f"**Domanda:** {domanda}\n**Risposta:** {risposta}",
            color=discord.Color.dark_purple(),
        )
        await interaction.response.send_message(
            embed=embed, allowed_mentions=discord.AllowedMentions.none()
        )

    @comando_di_gruppo("fun", nome="joke", descrizione="Racconta una barzelletta a caso.")
    @app_commands.describe(tema="Un tema (facoltativo)")
    @app_commands.choices(
        tema=[app_commands.Choice(name=n.capitalize(), value=n) for n in JOKES_TEMATICHE]
    )
    async def joke(
        self, interaction: discord.Interaction, tema: app_commands.Choice[str] | None = None
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return
        if tema is not None:
            await interaction.response.send_message(f"😄 {self._rng.choice(JOKES_TEMATICHE[tema.value])}")
            return
        await interaction.response.send_message(f"😄 {random_joke(self._rng)}")

    @comando_di_gruppo("fun", nome="fact", descrizione="Mostra una curiosità a caso.")
    @app_commands.describe(animale="Curiosità su gatti o cani (facoltativo)")
    @app_commands.choices(
        animale=[app_commands.Choice(name=n.capitalize(), value=n) for n in FACTS_ANIMALI]
    )
    async def fact(
        self, interaction: discord.Interaction, animale: app_commands.Choice[str] | None = None
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return
        if animale is not None:
            await interaction.response.send_message(f"🧠 {self._rng.choice(FACTS_ANIMALI[animale.value])}")
            return
        await interaction.response.send_message(f"🧠 {random_fact(self._rng)}")

    @comando_di_gruppo("immagini", nome="grayscale", descrizione="Trasforma un'immagine in scala di grigi.")
    @app_commands.describe(
        image="Immagine da elaborare (facoltativa: senza, usa l'avatar)",
        utente="Usa l'avatar di questo utente invece dell'allegato/del tuo",
    )
    async def grayscale(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment | None = None,
        utente: discord.Member | None = None,
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return

        await self._rispondi_con_immagine(
            interaction, image, utente, "grayscale.png", apply_grayscale
        )

    @comando_di_gruppo("immagini", nome="invert", descrizione="Inverte i colori di un'immagine.")
    @app_commands.describe(
        image="Immagine da elaborare (facoltativa: senza, usa l'avatar)",
        utente="Usa l'avatar di questo utente invece dell'allegato/del tuo",
    )
    async def invert(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment | None = None,
        utente: discord.Member | None = None,
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return

        await self._rispondi_con_immagine(
            interaction, image, utente, "invert.png", apply_invert
        )

    @comando_di_gruppo("immagini", nome="blur", descrizione="Applica una sfocatura a un'immagine.")
    @app_commands.describe(
        image="Immagine da elaborare (facoltativa: senza, usa l'avatar)",
        utente="Usa l'avatar di questo utente invece dell'allegato/del tuo",
        raggio="Intensità della sfocatura (1-50, default 8)",
    )
    async def blur(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment | None = None,
        utente: discord.Member | None = None,
        raggio: int = 8,
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return

        await self._rispondi_con_immagine(
            interaction, image, utente, "blur.png", apply_blur, raggio
        )

    @comando_di_gruppo("immagini", nome="pixelate", descrizione="Pixela un'immagine.")
    @app_commands.describe(
        image="Immagine da elaborare (facoltativa: senza, usa l'avatar)",
        utente="Usa l'avatar di questo utente invece dell'allegato/del tuo",
        dimensione_blocco="Dimensione dei blocchi (2-100, default 16, più alto = più pixelato)",
    )
    async def pixelate(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment | None = None,
        utente: discord.Member | None = None,
        dimensione_blocco: int = 16,
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return

        await self._rispondi_con_immagine(
            interaction, image, utente, "pixelate.png", apply_pixelate, dimensione_blocco
        )

    @comando_di_gruppo("immagini", nome="meme", descrizione="Genera un meme con testo sopra/sotto.")
    @app_commands.describe(
        top_text="Testo in alto (facoltativo)",
        bottom_text="Testo in basso (facoltativo)",
        image="Immagine da usare (facoltativa: senza, usa l'avatar)",
        utente="Usa l'avatar di questo utente invece dell'allegato/del tuo",
    )
    async def meme(
        self,
        interaction: discord.Interaction,
        top_text: app_commands.Range[str, 0, 100] = "",
        bottom_text: app_commands.Range[str, 0, 100] = "",
        image: discord.Attachment | None = None,
        utente: discord.Member | None = None,
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return

        if not top_text and not bottom_text:
            await interaction.response.send_message(
                await testo_per(interaction, "entertainmen_serve_almeno_un_testo_sopra"), ephemeral=True
            )
            return

        await self._rispondi_con_immagine(
            interaction, image, utente, "meme.png", render_meme, top_text, bottom_text
        )

    @comando_di_gruppo("immagini", nome="animal", descrizione="Mostra immagini casuali di animali (fino a 5).")
    @app_commands.describe(specie="Che animale vuoi vedere?", quante="Quante immagini, da 1 a 5 (facoltativo)")
    @app_commands.choices(
        specie=[
            app_commands.Choice(name="Cane", value="dog"),
            app_commands.Choice(name="Gatto", value="cat"),
            app_commands.Choice(name="Volpe", value="fox"),
            app_commands.Choice(name="Uccello", value="bird"),
            app_commands.Choice(name="Sorpresa", value="surprise"),
        ]
    )
    async def animal(
        self,
        interaction: discord.Interaction,
        specie: app_commands.Choice[str],
        quante: app_commands.Range[int, 1, MAX_ANIMALI] = 1,
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return

        scelte = [
            self._rng.choice(SPECIE_SORPRESA) if specie.value == "surprise" else specie.value for _ in range(quante)
        ]
        servono_uccelli = scelte.count("bird")
        if servono_uccelli and not config.PIXABAY_API_KEY:
            await interaction.response.send_message(
                await testo_per(interaction, "entertainmen_la_ricerca_immagini_non_configurata"), ephemeral=True
            )
            return
        if servono_uccelli:
            attesa = self._secondi_di_pausa(interaction.user.id)
            if attesa:
                await interaction.response.send_message(
                    await testo_per(interaction, "entertainmen_aspetta_secondi_prima_di_una", attesa=attesa),
                    ephemeral=True,
                )
                return
            self._segna_ricerca(interaction.user.id)

        await interaction.response.defer()

        indirizzi = await asyncio.gather(*(animal_fetcher.fetch_image_url(c) for c in scelte if c != "bird"))
        uccelli = (
            await image_search_fetcher.fetch_immagini(config.PIXABAY_API_KEY, "bird", self._rng, servono_uccelli)
            if servono_uccelli
            else []
        )
        embeds, file = [], []
        titolo = f"{specie.name} casuale"
        for url in indirizzi:
            if url is not None:
                embed = discord.Embed(title=titolo if not embeds else None, color=discord.Color.orange())
                embed.set_image(url=url)
                embeds.append(embed)
        for i, foto in enumerate(uccelli):
            nome_file = f"uccello{i}.{foto.estensione}"
            embed = discord.Embed(title=titolo if not embeds else None, url=foto.pagina, color=discord.Color.orange())
            embed.set_image(url=f"attachment://{nome_file}")
            embed.set_footer(text="Pixabay")
            embeds.append(embed)
            file.append(discord.File(io.BytesIO(foto.dati), filename=nome_file))
        if not embeds:
            await interaction.followup.send(
                await testo_per(interaction, "entertainmen_non_sono_riuscito_recuperare_un"),
                ephemeral=True,
            )
            return
        invio: dict = {"embed": embeds[0]} if len(embeds) == 1 else {"embeds": embeds}
        if len(file) == 1:
            invio["file"] = file[0]
        elif file:
            invio["files"] = file
        await interaction.followup.send(**invio)

    @comando_di_gruppo("immagini", nome="foto", descrizione="Una foto bella da vedere: cibo o buonumore.")
    @app_commands.describe(tema="Di cosa vuoi una foto")
    @app_commands.choices(
        tema=[
            app_commands.Choice(name="Cibo", value="cibo"),
            app_commands.Choice(name="Buonumore", value="buonumore"),
        ]
    )
    async def foto(self, interaction: discord.Interaction, tema: app_commands.Choice[str]) -> None:
        if not await self._modulo_attivo(interaction):
            return
        await self._foto_pixabay(interaction, self._rng.choice(QUERY_FOTO[tema.value]))

    @comando_di_gruppo("immagini", nome="xkcd", descrizione="Una vignetta di xkcd: l'ultima o quella col numero che scegli.")
    @app_commands.describe(numero="Il numero della vignetta (facoltativo: senza, l'ultima)")
    async def xkcd(
        self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 100000] | None = None
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return
        await interaction.response.defer()
        vignetta = await xkcd_service.vignetta(numero)
        if vignetta is None:
            await interaction.followup.send(await testo_per(interaction, "fun_xkcd_non_trovata"), ephemeral=True)
            return
        embed = discord.Embed(
            title=f"#{vignetta.numero} · {vignetta.titolo}"[:256],
            url=vignetta.pagina,
            description=vignetta.alt[:4096] or None,
            color=discord.Color.light_grey(),
        )
        embed.set_image(url=vignetta.immagine)
        embed.set_footer(text=await testo_per(interaction, "fun_xkcd_credito", pubblica=True))
        await interaction.followup.send(embed=embed)

    def _secondi_di_pausa(self, utente_id: int) -> int:
        """Secondi da aspettare prima di una nuova ricerca (0 = via libera)."""
        ultima = self._ultima_ricerca_immagini.get(utente_id)
        if ultima is None:
            return 0
        restano = PAUSA_RICERCA_IMMAGINI_SECONDI - (time.monotonic() - ultima)
        return max(0, int(restano) + 1) if restano > 0 else 0

    def _segna_ricerca(self, utente_id: int) -> None:
        ora = time.monotonic()
        if len(self._ultima_ricerca_immagini) >= MAX_UTENTI_NELLA_PAUSA:
            self._ultima_ricerca_immagini = {
                u: t
                for u, t in self._ultima_ricerca_immagini.items()
                if ora - t < PAUSA_RICERCA_IMMAGINI_SECONDI
            }
        self._ultima_ricerca_immagini[utente_id] = ora

    @comando_di_gruppo("immagini", nome="search-image", descrizione="Cerca un'immagine SFW su Pixabay.")
    @app_commands.describe(query="Cosa vuoi cercare? (massimo 100 caratteri)")
    async def search_image(
        self, interaction: discord.Interaction, query: app_commands.Range[str, 1, 100]
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return

        await self._foto_pixabay(interaction, query)

    async def _foto_pixabay(self, interaction: discord.Interaction, query: str) -> None:
        """Chiave, pausa per utente, defer, ricerca su Pixabay (safesearch), foto allegata con il credito."""
        if not config.PIXABAY_API_KEY:
            await interaction.response.send_message(
                await testo_per(interaction, "entertainmen_la_ricerca_immagini_non_configurata"),
                ephemeral=True,
            )
            return
        attesa = self._secondi_di_pausa(interaction.user.id)
        if attesa:
            await interaction.response.send_message(
                await testo_per(interaction, "entertainmen_aspetta_secondi_prima_di_una", attesa=attesa), ephemeral=True
            )
            return
        self._segna_ricerca(interaction.user.id)

        await interaction.response.defer()

        risultato = await image_search_fetcher.fetch_image(
            config.PIXABAY_API_KEY, query, self._rng
        )
        if risultato is None:
            await interaction.followup.send(
                await testo_per(interaction, "app_fun_nessun_risultato"), ephemeral=True
            )
            return

        nome_file = f"pixabay.{risultato.estensione}"
        embed = discord.Embed(
            title=await testo_per(interaction, "entertainmen_risultato_della_ricerca", pubblica=True),
            description=await testo_per(interaction, "entertainmen_immagine_da_pixabay", pagina=risultato.pagina, pubblica=True),
            color=discord.Color.blue(),
        )
        embed.set_image(url=f"attachment://{nome_file}")
        await interaction.followup.send(
            embed=embed, file=discord.File(io.BytesIO(risultato.dati), filename=nome_file)
        )


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_FUN,
            display_name="Fun",
            category="fun",
            description="Comandi di intrattenimento (Ship, Rate).",
            premium_capable=False,
        )
    )
    await bot.add_cog(EntertainmentCog(bot))
