"""
cogs/user_app/divertimento.py
=============================
Divertimento e immagini ovunque (SPEC §B.7): `/divertimento` di iYokai App con gli stessi giochi e le stesse
immagini di `/fun` (moneta, dado, forbici, palla8, barzelletta, citazione, curiosita, animale, immagine, meme,
effetto, ship, valuta, scegli, numero, testo, casuale). Le risposte le vedono tutti nel canale (servono a essere
condivise); `privata: sì` le tiene per te. Ogni comando risponde una volta sola. Tutto SFW. Si carica solo sul
client dell'app (core/user_app_bot.py).
Funzioni coperte: SPEC §B.7 (NF-36, #107)
Dipende da: core/minigames_logic.py, core/fun_logic.py, core/fun_extra_logic.py, core/image_effects_logic.py
"""

from __future__ import annotations

import io
import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from core import fun_extra_logic as logica
from core import image_effects_logic as effetti
from core.animal_fetcher import animal_fetcher
from core.classic_entertainment_logic import FACTS_ANIMALI, JOKES_TEMATICHE, random_fact, random_joke, random_quote
from core.config import config
from core.fun_logic import compute_rate_score, compute_ship_percentage, rate_flavor_text, ship_flavor_text
from core.i18n import t, testo_per
from core.image_search_fetcher import image_search_fetcher
from core.meme_logic import render_meme
from core.minigames_logic import answer_8ball, flip_coin, play_rps, roll_dice
from core.safe_image import MAX_IMAGE_BYTES, run_image_task
from core.user_app_bot import e_istanza_app

INSTALLAZIONE = app_commands.AppInstallationType(guild=False, user=True)
OVUNQUE = app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True)
NESSUNA_MENZIONE = discord.AllowedMentions.none()
PAUSA_RICERCA_SECONDI = 10
MAX_UTENTI_NELLA_PAUSA = 1000
_RPS = {"sasso": "🪨", "carta": "📄", "forbici": "✂️"}
_CASUALI = {
    "preferiresti": ("🤔", logica.preferiresti), "argomento": ("💭", logica.argomento),
    "consiglio": ("💡", logica.consiglio), "oggetto-magico": ("✨", logica.oggetto_magico),
}
_EFFETTI = {
    "arcobaleno": ("arcobaleno.png", effetti.effetto_arcobaleno, False), "rip": ("rip.png", effetti.effetto_rip, True),
    "ricercato": ("ricercato.png", effetti.effetto_ricercato, True),
    "triggered": ("triggered.gif", effetti.effetto_triggered, False),
}


def _barra(percentuale: int, lunghezza: int = 10) -> str:
    piene = round(percentuale / 100 * lunghezza)
    return "█" * piene + "░" * (lunghezza - piene)


class DivertimentoCog(commands.Cog):
    divertimento = app_commands.Group(
        name="divertimento", description="Giochi, battute e immagini: gli stessi di /fun, in ogni server e in DM.",
        allowed_installs=INSTALLAZIONE, allowed_contexts=OVUNQUE,
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._rng = random.Random()
        self._ultima_ricerca: dict[int, float] = {}

    async def _scrivi(self, interaction: discord.Interaction, testo: str, privata: bool = False) -> None:
        await interaction.response.send_message(testo[:2000], ephemeral=privata, allowed_mentions=NESSUNA_MENZIONE)

    async def _errore(self, interaction: discord.Interaction, chiave: str, **valori) -> None:
        await interaction.response.send_message(await testo_per(interaction, chiave, **valori), ephemeral=True)

    # ---------------------------------------------------------------- giochi
    @divertimento.command(name="moneta", description="Lancia una moneta: testa o croce.")
    @app_commands.describe(privata="Solo tu vedi la risposta")
    async def moneta(self, interaction: discord.Interaction, privata: bool = False) -> None:
        await self._scrivi(interaction, f"🪙 **{flip_coin(self._rng).upper()}**!", privata)

    @divertimento.command(name="dado", description="Tira un dado, o una formula come 3d6+2.")
    @app_commands.describe(facce="Facce del dado (2-1000)", formula="Formula da gioco di ruolo, al posto delle facce", privata="Solo tu")
    async def dado(
        self, interaction: discord.Interaction, facce: app_commands.Range[int, 2, 1000] = 6,
        formula: app_commands.Range[str, 2, 20] | None = None, privata: bool = False,
    ) -> None:
        if formula:
            esito = logica.tira_formula(formula, self._rng)
            if esito.errore:
                await self._scrivi(interaction, esito.errore, True)
                return
            dettaglio = " + ".join(str(x) for x in esito.tiri)
            if esito.modificatore:
                dettaglio += f" {'+' if esito.modificatore > 0 else '-'} {abs(esito.modificatore)}"
            await self._scrivi(interaction, f"🎲 `{formula.strip()}`: {dettaglio} = **{esito.totale}**", privata)
            return
        await self._scrivi(interaction, f"🎲 d{facce}: **{roll_dice(self._rng, facce)}**", privata)

    @divertimento.command(name="forbici", description="Carta, forbici, sasso contro il bot.")
    @app_commands.describe(scelta="Sasso, carta o forbici", privata="Solo tu")
    @app_commands.choices(scelta=[app_commands.Choice(name=n.capitalize(), value=n) for n in _RPS])
    async def forbici(self, interaction: discord.Interaction, scelta: app_commands.Choice[str], privata: bool = False) -> None:
        scelta_bot, esito = play_rps(scelta.value, self._rng)
        lingua_chiave = {"vittoria": "app_fun_vinto", "sconfitta": "app_fun_perso", "pareggio": "app_fun_pari"}[esito]
        await self._scrivi(
            interaction,
            f"{await testo_per(interaction, lingua_chiave)}\n{_RPS[scelta.value]} {scelta.name} vs {_RPS[scelta_bot]} {scelta_bot.capitalize()}",
            privata,
        )

    @divertimento.command(name="palla8", description="Fai una domanda alla palla magica 8.")
    @app_commands.describe(domanda="La tua domanda", privata="Solo tu")
    async def palla8(self, interaction: discord.Interaction, domanda: app_commands.Range[str, 1, 300], privata: bool = False) -> None:
        embed = discord.Embed(
            title="🎱", description=f"**{domanda}**\n{answer_8ball(self._rng)}", color=discord.Color.dark_purple()
        )
        await interaction.response.send_message(embed=embed, ephemeral=privata, allowed_mentions=NESSUNA_MENZIONE)

    @divertimento.command(name="barzelletta", description="Racconta una barzelletta a caso.")
    @app_commands.describe(tema="Un tema (facoltativo)", privata="Solo tu")
    @app_commands.choices(tema=[app_commands.Choice(name=n.capitalize(), value=n) for n in JOKES_TEMATICHE])
    async def barzelletta(self, interaction: discord.Interaction, tema: app_commands.Choice[str] | None = None, privata: bool = False) -> None:
        testo = self._rng.choice(JOKES_TEMATICHE[tema.value]) if tema else random_joke(self._rng)
        await self._scrivi(interaction, f"😄 {testo}", privata)

    @divertimento.command(name="citazione", description="Mostra una citazione a caso.")
    @app_commands.describe(privata="Solo tu")
    async def citazione(self, interaction: discord.Interaction, privata: bool = False) -> None:
        await self._scrivi(interaction, f"💬 {random_quote(self._rng)}", privata)

    @divertimento.command(name="curiosita", description="Mostra una curiosità a caso.")
    @app_commands.describe(animale="Curiosità su gatti o cani (facoltativo)", privata="Solo tu")
    @app_commands.choices(animale=[app_commands.Choice(name=n.capitalize(), value=n) for n in FACTS_ANIMALI])
    async def curiosita(self, interaction: discord.Interaction, animale: app_commands.Choice[str] | None = None, privata: bool = False) -> None:
        testo = self._rng.choice(FACTS_ANIMALI[animale.value]) if animale else random_fact(self._rng)
        await self._scrivi(interaction, f"🧠 {testo}", privata)

    @divertimento.command(name="scegli", description="Scelgo a caso tra le opzioni che scrivi.")
    @app_commands.describe(opzioni="Opzioni separate da virgola (da 2 a 20)", privata="Solo tu")
    async def scegli(self, interaction: discord.Interaction, opzioni: app_commands.Range[str, 3, 500], privata: bool = False) -> None:
        esito = logica.scegli_tra(opzioni, self._rng)
        if esito.errore:
            await self._scrivi(interaction, esito.errore, True)
            return
        await self._scrivi(interaction, f"🎯 **{esito.scelta}**", privata)

    @divertimento.command(name="numero", description="Un numero a caso in un intervallo.")
    @app_commands.describe(minimo="Estremo più basso", massimo="Estremo più alto", privata="Solo tu")
    async def numero(
        self, interaction: discord.Interaction, minimo: app_commands.Range[int, -1_000_000, 1_000_000] = 1,
        massimo: app_commands.Range[int, -1_000_000, 1_000_000] = 100, privata: bool = False,
    ) -> None:
        valore = logica.numero_casuale(minimo, massimo, self._rng)
        if valore is None:
            await self._errore(interaction, "app_fun_intervallo")
            return
        await self._scrivi(interaction, f"🔢 {minimo}–{massimo}: **{valore}**", privata)

    @divertimento.command(name="testo", description="Scrivi un testo in uno stile speciale.")
    @app_commands.describe(stile="Come trasformare il testo", testo="Il testo (massimo 500 caratteri)", privata="Solo tu")
    @app_commands.choices(stile=[app_commands.Choice(name=n.replace("-", " ").capitalize(), value=n) for n in logica.STILI_TESTO])
    async def testo(
        self, interaction: discord.Interaction, stile: app_commands.Choice[str], testo: app_commands.Range[str, 1, 500],
        privata: bool = False,
    ) -> None:
        await self._scrivi(interaction, logica.trasforma_testo(stile.value, testo, " ") or "​", privata)

    @divertimento.command(name="casuale", description="Preferiresti, argomento, consiglio, oggetto magico.")
    @app_commands.describe(tipo="Cosa vuoi", privata="Solo tu")
    @app_commands.choices(tipo=[
        app_commands.Choice(name="Preferiresti…?", value="preferiresti"),
        app_commands.Choice(name="Argomento di conversazione", value="argomento"),
        app_commands.Choice(name="Consiglio", value="consiglio"),
        app_commands.Choice(name="Oggetto magico", value="oggetto-magico"),
    ])
    async def casuale(self, interaction: discord.Interaction, tipo: app_commands.Choice[str], privata: bool = False) -> None:
        emoji, genera = _CASUALI[tipo.value]
        await self._scrivi(interaction, f"{emoji} {genera(self._rng)}", privata)

    # ---------------------------------------------------------------- persone
    @divertimento.command(name="ship", description="Calcola la compatibilità tra due utenti.")
    @app_commands.describe(utente1="Il primo utente", utente2="Il secondo utente", privata="Solo tu")
    async def ship(self, interaction: discord.Interaction, utente1: discord.User, utente2: discord.User, privata: bool = False) -> None:
        p = compute_ship_percentage(utente1.id, utente2.id)
        embed = discord.Embed(
            title="💘", description=f"**{utente1.display_name}** + **{utente2.display_name}**\n\n{_barra(p)} **{p}%**\n\n{ship_flavor_text(p)}",
            color=discord.Color.pink(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=privata, allowed_mentions=NESSUNA_MENZIONE)

    @divertimento.command(name="valuta", description="Valuta qualcosa da 0 a 10.")
    @app_commands.describe(cosa="Cosa vuoi far valutare", privata="Solo tu")
    async def valuta(self, interaction: discord.Interaction, cosa: app_commands.Range[str, 1, 200], privata: bool = False) -> None:
        p = compute_rate_score(cosa)
        embed = discord.Embed(title="⭐", description=f"**{cosa}**: {p}/10\n\n{rate_flavor_text(p)}", color=discord.Color.gold())
        await interaction.response.send_message(embed=embed, ephemeral=privata, allowed_mentions=NESSUNA_MENZIONE)

    # ---------------------------------------------------------------- immagini
    async def _immagine_di_partenza(self, image: discord.Attachment | None, utente: discord.abc.User) -> bytes | None:
        try:
            return await (image.read() if image is not None else utente.display_avatar.read())
        except discord.HTTPException:
            return None

    async def _rispondi_con_immagine(
        self, interaction: discord.Interaction, image: discord.Attachment | None, utente: discord.abc.User | None,
        nome_file: str, elabora, *argomenti, privata: bool = False,
    ) -> None:
        """Controlla l'allegato senza scaricarlo, poi `defer()` e risposta con il file (una sola risposta dopo)."""
        if image is not None and not (image.content_type or "").startswith("image/"):
            await self._errore(interaction, "app_fun_non_immagine")
            return
        if image is not None and image.size > MAX_IMAGE_BYTES:
            await self._errore(interaction, "app_fun_troppo_grande", mb=MAX_IMAGE_BYTES // (1024 * 1024))
            return
        await interaction.response.defer(ephemeral=privata)
        dati = await self._immagine_di_partenza(image, utente or interaction.user)
        if dati is None:
            await interaction.followup.send(await testo_per(interaction, "app_immagine_non_scaricata"), ephemeral=True)
            return
        risultato = await run_image_task(elabora, dati, *argomenti)
        if risultato is None:
            await interaction.followup.send(await testo_per(interaction, "app_immagine_non_elaborata"), ephemeral=True)
            return
        await interaction.followup.send(file=discord.File(io.BytesIO(risultato), filename=nome_file), ephemeral=privata)

    @divertimento.command(name="meme", description="Un meme con testo sopra e sotto, su un'immagine o su un avatar.")
    @app_commands.describe(
        alto="Testo in alto", basso="Testo in basso", immagine="Immagine (senza: il tuo avatar)",
        utente="Usa l'avatar di questo utente", privata="Solo tu",
    )
    async def meme(
        self, interaction: discord.Interaction, alto: app_commands.Range[str, 0, 100] = "",
        basso: app_commands.Range[str, 0, 100] = "", immagine: discord.Attachment | None = None,
        utente: discord.User | None = None, privata: bool = False,
    ) -> None:
        if not alto and not basso:
            await self._errore(interaction, "app_meme_serve_testo")
            return
        await self._rispondi_con_immagine(interaction, immagine, utente, "meme.png", render_meme, alto, basso, privata=privata)

    @divertimento.command(name="effetto", description="Effetto sull'avatar: arcobaleno, R.I.P., ricercato, triggered.")
    @app_commands.describe(
        tipo="Che effetto", immagine="Immagine (senza: avatar)", utente="Usa l'avatar di questo utente",
        nome=f"Nome sul manifesto o sulla lapide (massimo {effetti.MAX_NOME})", privata="Solo tu",
    )
    @app_commands.choices(tipo=[
        app_commands.Choice(name="Arcobaleno", value="arcobaleno"), app_commands.Choice(name="Lapide R.I.P.", value="rip"),
        app_commands.Choice(name="Ricercato", value="ricercato"), app_commands.Choice(name="Triggered (GIF)", value="triggered"),
    ])
    async def effetto(
        self, interaction: discord.Interaction, tipo: app_commands.Choice[str], immagine: discord.Attachment | None = None,
        utente: discord.User | None = None, nome: app_commands.Range[str, 1, effetti.MAX_NOME] | None = None,
        privata: bool = False,
    ) -> None:
        nome_file, funzione, vuole_nome = _EFFETTI[tipo.value]
        argomenti = ((nome or (utente or interaction.user).display_name,) if vuole_nome else ())
        await self._rispondi_con_immagine(interaction, immagine, utente, nome_file, funzione, *argomenti, privata=privata)

    @divertimento.command(name="animale", description="Mostra l'immagine di un animale a caso.")
    @app_commands.describe(specie="Che animale vuoi vedere?", privata="Solo tu")
    @app_commands.choices(specie=[
        app_commands.Choice(name="Cane", value="dog"), app_commands.Choice(name="Gatto", value="cat"),
        app_commands.Choice(name="Volpe", value="fox"),
    ])
    async def animale(self, interaction: discord.Interaction, specie: app_commands.Choice[str], privata: bool = False) -> None:
        await interaction.response.defer(ephemeral=privata)
        url = await animal_fetcher.fetch_image_url(specie.value)
        if url is None:
            await interaction.followup.send(await testo_per(interaction, "app_fun_nessuna_immagine"), ephemeral=True)
            return
        embed = discord.Embed(title=specie.name, color=discord.Color.orange())
        embed.set_image(url=url)
        await interaction.followup.send(embed=embed, ephemeral=privata)

    def _secondi_di_pausa(self, utente_id: int) -> int:
        ultima = self._ultima_ricerca.get(utente_id)
        if ultima is None:
            return 0
        restano = PAUSA_RICERCA_SECONDI - (time.monotonic() - ultima)
        return max(0, int(restano) + 1) if restano > 0 else 0

    def _segna_ricerca(self, utente_id: int) -> None:
        ora = time.monotonic()
        if len(self._ultima_ricerca) >= MAX_UTENTI_NELLA_PAUSA:
            self._ultima_ricerca = {u: x for u, x in self._ultima_ricerca.items() if ora - x < PAUSA_RICERCA_SECONDI}
        self._ultima_ricerca[utente_id] = ora

    @divertimento.command(name="immagine", description="Cerca un'immagine adatta a tutti su Pixabay.")
    @app_commands.describe(cerca="Cosa vuoi cercare?", privata="Solo tu")
    async def immagine(self, interaction: discord.Interaction, cerca: app_commands.Range[str, 1, 100], privata: bool = False) -> None:
        if not config.PIXABAY_API_KEY:
            await self._errore(interaction, "app_fun_ricerca_spenta")
            return
        attesa = self._secondi_di_pausa(interaction.user.id)
        if attesa:
            await self._errore(interaction, "app_fun_attesa", secondi=attesa)
            return
        self._segna_ricerca(interaction.user.id)
        await interaction.response.defer(ephemeral=privata)
        risultato = await image_search_fetcher.fetch_image(config.PIXABAY_API_KEY, cerca, self._rng)
        if risultato is None:
            await interaction.followup.send(await testo_per(interaction, "app_fun_nessun_risultato"), ephemeral=True)
            return
        nome_file = f"pixabay.{risultato.estensione}"
        embed = discord.Embed(description=f"[Pixabay]({risultato.pagina})", color=discord.Color.blue())
        embed.set_image(url=f"attachment://{nome_file}")
        await interaction.followup.send(
            embed=embed, file=discord.File(io.BytesIO(risultato.dati), filename=nome_file), ephemeral=privata
        )


async def setup(bot: commands.Bot) -> None:
    """Solo sul client dell'app: il bot principale non riceve questi comandi."""
    if e_istanza_app(bot):
        await bot.add_cog(DivertimentoCog(bot))
