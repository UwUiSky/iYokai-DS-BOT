"""
cogs/music/cartella.py
======================
Cartella di brani dell'owner (MUS-018, D111): il bot rilegge da solo l'elenco ogni 5 minuti, `/owner-radio cartella`
lo forza, `/music coda anteprime` mette in coda i brani (l'owner sempre, gli utenti se le anteprime sono accese).
Gli utenti vedono solo titoli puliti; mai un percorso, mai una sorgente `local` scelta da loro.
Funzioni coperte: SPEC §9 (catalogo MUS-018)
Dipende da: core/music_cartella_logic.py, core/music_anteprime_logic.py, cogs/music/player.py (MusicCog.accoda)
"""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo, SOTTOGRUPPI
from core.config import config
from core.i18n import testo_per
from core.music_anteprime_logic import come_ricerca, risolvi_brani
from core.music_cartella_logic import (
    ANTEPRIME,
    MAX_ANTEPRIME_IN_CODA,
    cartella_dell_owner,
    scansiona,
)
from core.music_logic import is_local_node, truncate_title
from core.repositories.music_cartella_repo import CHIAVE_ANTEPRIME, BranoSalvato, music_cartella_repo
from core.giro_periodico import giro_periodico

logger = logging.getLogger("iyokai.music.cartella")

RADIO = ("radio", "Radio 24/7 condivisa del bot")
SG_CODA = SOTTOGRUPPI["music coda"]
MINUTI_SCANSIONE = 5
SCELTE_AZIONE = [
    app_commands.Choice(name="Elenco", value="elenco"),
    app_commands.Choice(name="Rileggi", value="aggiorna"),
    app_commands.Choice(name="Anteprime on", value="anteprime-si"),
    app_commands.Choice(name="Anteprime off", value="anteprime-no"),
]


def cartella_configurata() -> str:
    return cartella_dell_owner(config.MUSICA_CARTELLA_OWNER, config.MAIN_RADIO_LOCAL_FOLDER)


def radice_per_il_nodo() -> str:
    """La cartella come la vede il nodo Lavalink (con Docker e' il punto di montaggio)."""
    return (config.LAVALINK_LOCAL_ROOT or "").strip() or cartella_configurata()


async def aggiorna_elenco() -> tuple[int, int, int, int, bool] | None:
    """Rilegge la cartella: (totale, nuovi, tolti, cambiati, troncata). None se la cartella non e' impostata."""
    cartella = cartella_configurata()
    if not cartella:
        return None
    esito = await asyncio.to_thread(scansiona, cartella)
    nuovi, tolti, cambiati = await music_cartella_repo.sincronizza(esito.brani)
    return len(esito.brani), nuovi, tolti, cambiati, esito.troncata


async def anteprime_abilitate(user_id: int) -> bool:
    """L'owner puo' sempre; gli altri solo se le anteprime sono accese (di base lo sono)."""
    if user_id == config.OWNER_ID:
        return True
    return (await music_cartella_repo.leggi_impostazione(CHIAVE_ANTEPRIME)) != "0"


class MusicCartellaCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        await super().cog_load()
        if cartella_configurata():
            self._giro.start()

    async def cog_unload(self) -> None:
        self._giro.cancel()
        await super().cog_unload()

    @giro_periodico(minutes=MINUTI_SCANSIONE)
    async def _giro(self) -> None:
        try:
            await aggiorna_elenco()
        except Exception:
            logger.exception("Lettura della cartella dei brani non riuscita.")

    @_giro.before_loop
    async def _prima_del_giro(self) -> None:
        await self.bot.wait_until_ready()

    def _musica(self):
        return self.bot.get_cog("MusicCog")

    # ------------------------------------------------------------- owner
    @comando_di_gruppo("owner-radio", nome="cartella", descrizione="Cartella dell'owner: elenco, rilettura, anteprime.")
    @app_commands.describe(azione="Cosa fare")
    @app_commands.choices(azione=SCELTE_AZIONE)
    async def cartella(self, interaction: discord.Interaction, azione: str) -> None:
        if interaction.user.id != config.OWNER_ID:
            await interaction.response.send_message(await testo_per(interaction, "owner_solo_proprietario"), ephemeral=True)
            return
        if not cartella_configurata():
            await interaction.response.send_message(await testo_per(interaction, "music_cartella_non_impostata"), ephemeral=True)
            return
        nessuna_menzione = discord.AllowedMentions.none()
        if azione in ("anteprime-si", "anteprime-no"):
            acceso = azione == "anteprime-si"
            await music_cartella_repo.scrivi_impostazione(CHIAVE_ANTEPRIME, "1" if acceso else "0", interaction.user.id)
            await interaction.response.send_message(
                await testo_per(interaction, "music_cartella_anteprime_accese" if acceso else "music_cartella_anteprime_spente"),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        if azione == "aggiorna":
            try:
                esito = await aggiorna_elenco()
            except Exception:
                logger.exception("Lettura della cartella dei brani non riuscita.")
                await interaction.followup.send(await testo_per(interaction, "music_cartella_errore"), ephemeral=True)
                return
            totale, nuovi, tolti, cambiati, troncata = esito
            testo = await testo_per(interaction, "music_cartella_aggiornata", v1=totale, v2=nuovi, v3=cambiati, v4=tolti)
            if troncata:
                testo += "\n" + await testo_per(interaction, "music_cartella_troncata")
            await interaction.followup.send(testo, ephemeral=True, allowed_mentions=nessuna_menzione)
            return
        brani = await music_cartella_repo.elenco()
        if not brani:
            await interaction.followup.send(await testo_per(interaction, "music_cartella_vuota"), ephemeral=True)
            return
        # all'owner si mostrano id e titoli puliti; i percorsi restano nel database
        righe = [f"`{b.id}` {truncate_title(b.titolo, 80)}" for b in brani]
        testo, usate = "", 0
        for riga in righe:
            if len(testo) + len(riga) + 1 > 1800:
                break
            testo += riga + "\n"
            usate += 1
        if usate < len(righe):
            testo += await testo_per(interaction, "music_cartella_altri", v1=len(righe) - usate)
        await interaction.followup.send(testo.strip(), ephemeral=True, allowed_mentions=nessuna_menzione)

    # ------------------------------------------------------------- utenti
    async def _scelte(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        try:
            if not cartella_configurata() or not await anteprime_abilitate(interaction.user.id):
                return []
            brani = await music_cartella_repo.cerca((current or "").strip(), 25)
        except Exception:
            logger.exception("Autocompletamento delle anteprime non riuscito.")
            return []
        return [app_commands.Choice(name=truncate_title(b.titolo, 100), value=str(b.id)) for b in brani]

    async def _scelti(self, brano: str | None) -> list[BranoSalvato]:
        """Un brano (id scelto dal menu, o un titolo scritto) oppure tutta la playlist. Mai un percorso."""
        if brano is None or not brano.strip():
            return (await music_cartella_repo.elenco())[:MAX_ANTEPRIME_IN_CODA]
        testo = brano.strip()
        if testo.isdigit() and len(testo) <= 15:
            trovato = await music_cartella_repo.get(int(testo))
            return [trovato] if trovato else []
        return (await music_cartella_repo.cerca(testo, 1))

    @comando_di_gruppo("music", nome="anteprime", descrizione="Mette in coda i brani in anteprima dell'owner del bot.",
                       sottogruppo=SG_CODA)
    @app_commands.describe(brano="Un brano in particolare (vuoto: tutta la playlist Anteprime)")
    @app_commands.autocomplete(brano=_scelte)
    async def anteprime(self, interaction: discord.Interaction, brano: app_commands.Range[str, 0, 100] | None = None) -> None:
        musica = self._musica()
        if musica is None:
            await interaction.response.send_message(await testo_per(interaction, "soundboard_la_musica_non_disponibile_ora"), ephemeral=True)
            return
        if not await musica.controlli_base(interaction):
            return
        if not cartella_configurata() or not await anteprime_abilitate(interaction.user.id):
            await interaction.response.send_message(await testo_per(interaction, "music_anteprime_spente"), ephemeral=True)
            return
        scelti = await self._scelti(brano)
        if not scelti:
            await interaction.response.send_message(await testo_per(interaction, "music_anteprime_non_trovate"), ephemeral=True)
            return
        await interaction.response.defer()
        problema: list[str] = []

        async def cerca(nodo, nodo_locale):
            locale = nodo if is_local_node(getattr(nodo, "identifier", "")) else nodo_locale
            if locale is None:  # il bot suona gia' da un nodo pubblico, oppure il nodo locale non c'e'
                problema.append("music_anteprime_niente_nodo")
                return None, nodo
            pronti = await risolvi_brani(locale, radice_per_il_nodo(), scelti)
            if not pronti:
                problema.append("music_anteprime_non_lette")
                return None, locale
            for p in pronti:  # titolo e durata letti dai metadati restano per la prossima volta
                try:
                    await music_cartella_repo.imposta_dettagli(p.brano_id, p.titolo, p.durata_ms or None)
                except Exception:
                    logger.warning("Dettagli del brano %s non salvati.", p.brano_id, exc_info=True)
            return come_ricerca(pronti, ANTEPRIME), locale

        async def rispondi(testo: str) -> None:
            if problema:  # al posto del generico «nessun risultato» (solo la prima risposta)
                testo = await testo_per(interaction, problema.pop(), pubblica=True)
                problema.clear()
            await interaction.followup.send(testo, allowed_mentions=discord.AllowedMentions.none())

        await musica.accoda(
            interaction.guild, interaction.user, ANTEPRIME, rispondi, interaction=interaction, cerca=cerca,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicCartellaCog(bot))
