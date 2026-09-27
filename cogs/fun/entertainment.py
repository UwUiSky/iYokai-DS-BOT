"""
cogs/fun/entertainment.py
============================
Mini-giochi (SPEC.md §16.1), altri comandi di intrattenimento
classici (§16.8): testa/croce, dado, carta/forbici/sasso, palla
magica 8, barzelletta, citazione, curiosità — e image manipulation
(§16.2)/meme (§16.3): scala di grigi, inverti, sfoca, pixela,
generatore di meme testo-sopra/testo-sotto. Tutti operano
sull'allegato passato al comando o, se assente, sull'avatar
dell'utente (o dell'utente menzionato) — così ogni comando funziona
anche senza dover allegare un'immagine ogni volta.

Decisione tecnica IMPORTANTE, presa scrivendo questo file: il bot è
già a 96 comandi slash TOP-LEVEL su un limite GLOBALE di Discord di
100 (verificato con una prova reale — caricare tutti i cog insieme e
contare `bot.tree.get_commands()` — non solo letto sulla
documentazione). 7 nuovi comandi separati (coinflip/dice/rps/8ball/
joke/quote/fact) avrebbero sfondato il limite e fatto fallire in
silenzio la registrazione di un cog successivo in ordine di
caricamento (esattamente il bug già documentato in
tests/test_cog_manager_load_all.py per un nome duplicato — qui la
causa sarebbe stata il limite, non un doppione, ma l'effetto
identico: un cog che smette di funzionare senza errore visibile).
Per questo tutti i comandi di questo file vivono sotto UN SOLO
gruppo (`/fun ...`), che consuma un solo slot top-level indipendente
da quanti sotto-comandi contiene — lo stesso principio già seguito
altrove nel progetto per raggruppare comandi correlati (`/config`,
`/ticket-category`, ecc.), qui applicato per la prima volta come
misura di risparmio slot deliberata. Ship e Rate (§16.5/§16.7,
cogs/fun/ship_rate.py) restano comandi top-level a sé: sono già in
produzione, cambiarli in sotto-comandi ora sarebbe una rottura per
chi li usa già senza un guadagno di slot che serva adesso (restano
solo 2 di headroom). Qualunque comando FUTURO di §16 (image
manipulation, meme, animal, ricerca immagini) andrà sotto questo
stesso gruppo o un gruppo analogo, non come nuovo comando top-level.
"""

from __future__ import annotations

import asyncio
import io
import random

import discord
from discord import app_commands
from discord.ext import commands

from core.classic_entertainment_logic import random_fact, random_joke, random_quote
from core.database import db
from core.image_manipulation import apply_blur, apply_grayscale, apply_invert, apply_pixelate
from core.meme_logic import render_meme
from core.minigames_logic import answer_8ball, flip_coin, play_rps, roll_dice
from core.premium import PremiumModule, registry

MODULE_FUN = "fun"

_RPS_CHOICE_DISPLAY = {"sasso": "🪨 Sasso", "carta": "📄 Carta", "forbici": "✂️ Forbici"}

# Dimensione massima di un allegato che accettiamo di scaricare per
# elaborarlo — un limite di buon senso, non legato a un vincolo di
# Pillow: evita di scaricare e decodificare in memoria un file da
# centinaia di MB solo perché ha un'estensione immagine.
MAX_IMAGE_BYTES = 15 * 1024 * 1024


class EntertainmentCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._rng = random.Random()

    fun_group = app_commands.Group(
        name="fun", description="Mini-giochi e intrattenimento (SPEC.md §16.1/§16.8)."
    )

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
                "Un amministratore può attivarlo con /setup.",
                ephemeral=True,
            )
            return False
        return True

    async def _resolve_image_bytes(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment | None,
        utente: discord.Member | None,
    ) -> bytes | None:
        """
        Priorità: allegato esplicito > utente menzionato > l'autore
        del comando stesso. Restituisce None (e risponde da sola con
        un messaggio d'errore) se l'allegato non è un'immagine o è
        troppo grande — così ogni comando che la chiama può limitarsi
        a controllare il valore di ritorno, senza duplicare la logica
        di validazione.
        """
        if image is not None:
            if not (image.content_type or "").startswith("image/"):
                await interaction.response.send_message(
                    "L'allegato non è un'immagine.", ephemeral=True
                )
                return None
            if image.size > MAX_IMAGE_BYTES:
                await interaction.response.send_message(
                    "L'immagine è troppo grande (massimo 15 MB).", ephemeral=True
                )
                return None
            return await image.read()

        soggetto = utente or interaction.user
        return await soggetto.display_avatar.read()

    @fun_group.command(name="coinflip", description="Lancia una moneta: testa o croce.")
    async def coinflip(self, interaction: discord.Interaction) -> None:
        if not await self._modulo_attivo(interaction):
            return

        risultato = flip_coin(self._rng)
        await interaction.response.send_message(f"🪙 **{risultato.upper()}**!")

    @fun_group.command(name="dice", description="Tira un dado.")
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

    @fun_group.command(name="rps", description="Carta, forbici, sasso contro il bot.")
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

    @fun_group.command(name="8ball", description="Fai una domanda alla palla magica 8.")
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

    @fun_group.command(name="joke", description="Racconta una barzelletta a caso.")
    async def joke(self, interaction: discord.Interaction) -> None:
        if not await self._modulo_attivo(interaction):
            return
        await interaction.response.send_message(f"😄 {random_joke(self._rng)}")

    @fun_group.command(name="quote", description="Mostra una citazione a caso.")
    async def quote(self, interaction: discord.Interaction) -> None:
        if not await self._modulo_attivo(interaction):
            return
        await interaction.response.send_message(f"💬 {random_quote(self._rng)}")

    @fun_group.command(name="fact", description="Mostra una curiosità a caso.")
    async def fact(self, interaction: discord.Interaction) -> None:
        if not await self._modulo_attivo(interaction):
            return
        await interaction.response.send_message(f"🧠 {random_fact(self._rng)}")

    @fun_group.command(name="grayscale", description="Trasforma un'immagine in scala di grigi.")
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

        dati = await self._resolve_image_bytes(interaction, image, utente)
        if dati is None:
            return

        risultato = await asyncio.to_thread(apply_grayscale, dati)
        if risultato is None:
            await interaction.response.send_message(
                "Non sono riuscito a elaborare questa immagine.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            file=discord.File(io.BytesIO(risultato), filename="grayscale.png")
        )

    @fun_group.command(name="invert", description="Inverte i colori di un'immagine.")
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

        dati = await self._resolve_image_bytes(interaction, image, utente)
        if dati is None:
            return

        risultato = await asyncio.to_thread(apply_invert, dati)
        if risultato is None:
            await interaction.response.send_message(
                "Non sono riuscito a elaborare questa immagine.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            file=discord.File(io.BytesIO(risultato), filename="invert.png")
        )

    @fun_group.command(name="blur", description="Applica una sfocatura a un'immagine.")
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

        dati = await self._resolve_image_bytes(interaction, image, utente)
        if dati is None:
            return

        risultato = await asyncio.to_thread(apply_blur, dati, raggio)
        if risultato is None:
            await interaction.response.send_message(
                "Non sono riuscito a elaborare questa immagine.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            file=discord.File(io.BytesIO(risultato), filename="blur.png")
        )

    @fun_group.command(name="pixelate", description="Pixela un'immagine.")
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

        dati = await self._resolve_image_bytes(interaction, image, utente)
        if dati is None:
            return

        risultato = await asyncio.to_thread(apply_pixelate, dati, dimensione_blocco)
        if risultato is None:
            await interaction.response.send_message(
                "Non sono riuscito a elaborare questa immagine.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            file=discord.File(io.BytesIO(risultato), filename="pixelate.png")
        )

    @fun_group.command(name="meme", description="Genera un meme con testo sopra/sotto.")
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

        dati = await self._resolve_image_bytes(interaction, image, utente)
        if dati is None:
            return

        risultato = await asyncio.to_thread(render_meme, dati, top_text, bottom_text)
        if risultato is None:
            await interaction.response.send_message(
                "Non sono riuscito a elaborare questa immagine.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            file=discord.File(io.BytesIO(risultato), filename="meme.png")
        )


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_FUN,
            display_name="Fun",
            description="Comandi di intrattenimento (Ship, Rate).",
            premium_capable=False,
        )
    )
    await bot.add_cog(EntertainmentCog(bot))
