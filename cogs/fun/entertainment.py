"""
cogs/fun/entertainment.py
============================
Mini-giochi (SPEC.md §16.1), altri comandi di intrattenimento
classici (§16.8): testa/croce, dado, carta/forbici/sasso, palla
magica 8, barzelletta, citazione, curiosità — e image manipulation
(§16.2)/fun meme (§16.3): scala di grigi, inverti, sfoca, pixela,
generatore di meme testo-sopra/testo-sotto. Tutti operano
sull'allegato passato al comando o, se assente, sull'avatar
dell'utente (o dell'utente menzionato) — così ogni comando funziona
anche senza dover allegare un'immagine ogni volta. I comandi immagine
passano tutti da `_rispondi_con_immagine` (SEC-20): allegato
controllato prima di scaricarlo, `defer()`, risposta con followup.

Funzioni coperte: SPEC §16.1-16.4, §16.8-16.9; M 15.1, M 15.2.
Tutti i comandi stanno nel gruppo condiviso `/fun` (core/command_groups.py);
`/fun ship` e `/fun rate` sono in cogs/fun/ship_rate.py.

Terzo lotto (§16.4 Comandi animal, §16.9 Ricerca immagini SFW):
`/fun animal` usa tre API pubbliche gratuite senza chiave
(dog.ceo, thecatapi.com, randomfox.ca — core/animal_fetcher.py);
`/fun search-image` usa Pixabay, che invece richiede una chiave
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

import io
import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from core.animal_fetcher import animal_fetcher
from core.classic_entertainment_logic import random_fact, random_joke, random_quote
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.config import config
from core.database import db
from core.image_manipulation import apply_blur, apply_grayscale, apply_invert, apply_pixelate
from core.image_search_fetcher import image_search_fetcher
from core.meme_logic import render_meme
from core.minigames_logic import answer_8ball, flip_coin, play_rps, roll_dice
from core.premium import PremiumModule, registry
from core.safe_image import MAX_IMAGE_BYTES, run_image_task

MODULE_FUN = "fun"
PAUSA_RICERCA_IMMAGINI_SECONDI = 10
MAX_UTENTI_NELLA_PAUSA = 1000

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
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return False

        if not await db.is_module_active_for_guild(guild.id, MODULE_FUN):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /admin setup attiva.",
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
                "L'allegato non è un'immagine.", ephemeral=True
            )
            return False
        if image.size > MAX_IMAGE_BYTES:
            limite_mb = MAX_IMAGE_BYTES // (1024 * 1024)
            await interaction.response.send_message(
                f"L'immagine è troppo grande (massimo {limite_mb} MB).", ephemeral=True
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
            await interaction.followup.send("Non sono riuscito a scaricare l'immagine.")
            return

        risultato = await run_image_task(elabora, dati, *argomenti)
        if risultato is None:
            await interaction.followup.send("Non sono riuscito a elaborare questa immagine.")
            return

        await interaction.followup.send(
            file=discord.File(io.BytesIO(risultato), filename=nome_file)
        )

    @comando_di_gruppo("fun", nome="coinflip", descrizione="Lancia una moneta: testa o croce.")
    async def coinflip(self, interaction: discord.Interaction) -> None:
        if not await self._modulo_attivo(interaction):
            return

        risultato = flip_coin(self._rng)
        await interaction.response.send_message(f"🪙 **{risultato.upper()}**!")

    @comando_di_gruppo("fun", nome="dice", descrizione="Tira un dado.")
    @app_commands.describe(sides="Numero di facce del dado (default 6, minimo 2, massimo 1000)")
    async def dice(self, interaction: discord.Interaction, sides: int = 6) -> None:
        if not await self._modulo_attivo(interaction):
            return

        if sides < 2 or sides > 1000:
            await interaction.response.send_message(
                "Il dado deve avere tra 2 e 1000 facce.", ephemeral=True
            )
            return

        risultato = roll_dice(self._rng, sides=sides)
        await interaction.response.send_message(f"🎲 Hai tirato un **{risultato}** (d{sides}).")

    @comando_di_gruppo("fun", nome="rps", descrizione="Carta, forbici, sasso contro il bot.")
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
    @app_commands.describe(domanda="La tua domanda")
    async def eight_ball(self, interaction: discord.Interaction, domanda: str) -> None:
        if not await self._modulo_attivo(interaction):
            return

        risposta = answer_8ball(self._rng)
        embed = discord.Embed(
            title="🎱 Palla magica 8",
            description=f"**Domanda:** {domanda}\n**Risposta:** {risposta}",
            color=discord.Color.dark_purple(),
        )
        await interaction.response.send_message(embed=embed)

    @comando_di_gruppo("fun", nome="joke", descrizione="Racconta una barzelletta a caso.")
    async def joke(self, interaction: discord.Interaction) -> None:
        if not await self._modulo_attivo(interaction):
            return
        await interaction.response.send_message(f"😄 {random_joke(self._rng)}")

    @comando_di_gruppo("fun", nome="quote", descrizione="Mostra una citazione a caso.")
    async def quote(self, interaction: discord.Interaction) -> None:
        if not await self._modulo_attivo(interaction):
            return
        await interaction.response.send_message(f"💬 {random_quote(self._rng)}")

    @comando_di_gruppo("fun", nome="fact", descrizione="Mostra una curiosità a caso.")
    async def fact(self, interaction: discord.Interaction) -> None:
        if not await self._modulo_attivo(interaction):
            return
        await interaction.response.send_message(f"🧠 {random_fact(self._rng)}")

    @comando_di_gruppo("fun", nome="grayscale", descrizione="Trasforma un'immagine in scala di grigi.")
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

    @comando_di_gruppo("fun", nome="invert", descrizione="Inverte i colori di un'immagine.")
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

    @comando_di_gruppo("fun", nome="blur", descrizione="Applica una sfocatura a un'immagine.")
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

    @comando_di_gruppo("fun", nome="pixelate", descrizione="Pixela un'immagine.")
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

    @comando_di_gruppo("fun", nome="meme", descrizione="Genera un meme con testo sopra/sotto.")
    @app_commands.describe(
        top_text="Testo in alto (facoltativo)",
        bottom_text="Testo in basso (facoltativo)",
        image="Immagine da usare (facoltativa: senza, usa l'avatar)",
        utente="Usa l'avatar di questo utente invece dell'allegato/del tuo",
    )
    async def meme(
        self,
        interaction: discord.Interaction,
        top_text: str = "",
        bottom_text: str = "",
        image: discord.Attachment | None = None,
        utente: discord.Member | None = None,
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return

        if not top_text and not bottom_text:
            await interaction.response.send_message(
                "Serve almeno un testo (sopra o sotto).", ephemeral=True
            )
            return

        await self._rispondi_con_immagine(
            interaction, image, utente, "meme.png", render_meme, top_text, bottom_text
        )

    @comando_di_gruppo("fun", nome="animal", descrizione="Mostra un'immagine casuale di un animale.")
    @app_commands.describe(specie="Che animale vuoi vedere?")
    @app_commands.choices(
        specie=[
            app_commands.Choice(name="Cane", value="dog"),
            app_commands.Choice(name="Gatto", value="cat"),
            app_commands.Choice(name="Volpe", value="fox"),
        ]
    )
    async def animal(self, interaction: discord.Interaction, specie: app_commands.Choice[str]) -> None:
        if not await self._modulo_attivo(interaction):
            return

        await interaction.response.defer()

        url = await animal_fetcher.fetch_image_url(specie.value)
        if url is None:
            await interaction.followup.send(
                "Non sono riuscito a recuperare un'immagine in questo momento. Riprova più tardi.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(title=f"{specie.name} casuale", color=discord.Color.orange())
        embed.set_image(url=url)
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

    @comando_di_gruppo("fun", nome="search-image", descrizione="Cerca un'immagine SFW su Pixabay.")
    @app_commands.describe(query="Cosa vuoi cercare? (massimo 100 caratteri)")
    async def search_image(
        self, interaction: discord.Interaction, query: app_commands.Range[str, 1, 100]
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return

        if not config.PIXABAY_API_KEY:
            await interaction.response.send_message(
                "La ricerca immagini non è configurata su questo bot: serve una chiave "
                "gratuita di Pixabay (PIXABAY_API_KEY) — vedi .env.example.",
                ephemeral=True,
            )
            return

        attesa = self._secondi_di_pausa(interaction.user.id)
        if attesa:
            await interaction.response.send_message(
                f"Aspetta {attesa} secondi prima di una nuova ricerca.", ephemeral=True
            )
            return
        self._segna_ricerca(interaction.user.id)

        await interaction.response.defer()

        risultato = await image_search_fetcher.fetch_image(
            config.PIXABAY_API_KEY, query, self._rng
        )
        if risultato is None:
            await interaction.followup.send(
                "Nessun risultato per questa ricerca (o Pixabay non risponde).", ephemeral=True
            )
            return

        nome_file = f"pixabay.{risultato.estensione}"
        embed = discord.Embed(
            title="Risultato della ricerca",
            description=f"Immagine da [Pixabay]({risultato.pagina})",
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
