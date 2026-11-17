"""
cogs/music/owner.py
===================
Comandi musicali riservati al proprietario del bot, in `/owner radio`: nodi Lavalink, stato dei
player, riconnessione, log del Lavalink locale, fonti accese o spente, parole vietate in tutto il bot.
Funzioni coperte: SPEC §9 (catalogo MUS-011, MUS-063, MUS-067, MUS-068, MUS-069, MUS-070)
Dipende da: core/music_owner_logic.py, core/repositories/music_owner_repo.py, core/music_nodes.py
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import time
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from core import music_sources as fonti_musicali
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.config import config
from core.i18n import testo_per
from core.music_logic import EMBED_DESCRIPTION_LIMIT, truncate_title
from core.music_owner_logic import (
    LOG_MAX_BYTE,
    MAX_PAROLE_GLOBALI,
    PAUSA_RICONNETTI,
    coda_del_file,
    parola_globale_valida,
    riga_nodo,
    ripulisci_log,
)
from core.music_settings_logic import imposta_parole_globali
from core.repositories.music_owner_repo import music_owner_repo

logger = logging.getLogger("iyokai.music.owner")

RADIO = ("radio", "Radio 24/7 condivisa del bot principale, playlist personale")
SCELTE_FONTE = [app_commands.Choice(name=f.etichetta, value=n) for n, f in fonti_musicali.FONTI.items()]
SCELTE_STATO = [
    app_commands.Choice(name="Accesa", value="acceso"),
    app_commands.Choice(name="Spenta", value="spento"),
    app_commands.Choice(name="Come da ambiente (toglie la scelta)", value="predefinito"),
]
SCELTE_AZIONE = [
    app_commands.Choice(name="Aggiungi", value="aggiungi"),
    app_commands.Choice(name="Togli", value="togli"),
    app_commands.Choice(name="Elenco", value="elenco"),
]


def conta_player(clienti) -> tuple[int, int]:
    """MUS-067: (player che suonano, player collegati) su tutti i bot musicali."""
    suonano = collegati = 0
    for cliente in clienti:
        for server in getattr(cliente, "guilds", []):
            player = getattr(server, "voice_client", None)
            if player is None:
                continue
            collegati += 1
            if getattr(player, "playing", False):
                suonano += 1
    return suonano, collegati


def segreti_noti() -> list[str]:
    """Valori da non far uscire mai: chiavi delle fonti e password di Lavalink."""
    valori = [os.environ.get(v, "") for f in fonti_musicali.FONTI.values() for g in f.chiavi for v in g]
    valori += [config.LAVALINK_PASSWORD, os.environ.get("LAVALINK_NODES", "")]
    return [v.strip() for v in valori if v and v.strip()]


class MusicOwnerCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._ultima_riconnessione = 0.0

    async def cog_load(self) -> None:
        await super().cog_load()
        try:  # le scelte dell'owner tornano attive a ogni avvio
            fonti_musicali.imposta_override(await music_owner_repo.override_fonti())
            imposta_parole_globali(await music_owner_repo.parole())
        except Exception:
            logger.exception("Lettura delle scelte musicali dell'owner non riuscita.")

    @staticmethod
    async def _solo_owner(interaction: discord.Interaction) -> bool:
        if interaction.user.id == config.OWNER_ID:
            return True
        await interaction.response.send_message(await testo_per(interaction, "owner_solo_proprietario"), ephemeral=True)
        return False

    def _clienti(self) -> list:
        return [self.bot, *getattr(getattr(self.bot, "music_fleet", None), "worker_bots", [])]

    @comando_di_gruppo("owner", nome="nodi", descrizione="Mostra i nodi Lavalink di ogni bot musicale (senza password).",
                       sottogruppo=RADIO)
    async def nodi(self, interaction: discord.Interaction) -> None:
        if not await self._solo_owner(interaction):  # MUS-070
            return
        gestore = getattr(self.bot, "music_nodes", None)
        righe = [riga_nodo(*r) for r in gestore.descrivi_nodi()] if gestore is not None else []
        testo = "\n".join(righe) or await testo_per(interaction, "music_owner_nessun_nodo")
        await interaction.response.send_message(truncate_title(testo, 1900), ephemeral=True)

    @comando_di_gruppo("owner", nome="stato", descrizione="Quanti player musicali stanno suonando ora.",
                       sottogruppo=RADIO)
    async def stato(self, interaction: discord.Interaction) -> None:
        if not await self._solo_owner(interaction):  # MUS-067
            return
        suonano, collegati = conta_player(self._clienti())
        await interaction.response.send_message(
            await testo_per(interaction, "music_owner_stato", v1=suonano, v2=collegati), ephemeral=True
        )

    @comando_di_gruppo("owner", nome="riconnetti", descrizione="Riprova subito a collegare i nodi Lavalink non collegati.",
                       sottogruppo=RADIO)
    async def riconnetti(self, interaction: discord.Interaction) -> None:
        if not await self._solo_owner(interaction):  # MUS-068
            return
        adesso = time.monotonic()
        if adesso - self._ultima_riconnessione < PAUSA_RICONNETTI:
            await interaction.response.send_message(await testo_per(interaction, "music_owner_riconnetti_pausa"), ephemeral=True)
            return
        self._ultima_riconnessione = adesso
        gestore = getattr(self.bot, "music_nodes", None)
        ripartiti = await gestore.riconnetti() if gestore is not None else 0
        await interaction.response.send_message(
            await testo_per(interaction, "music_owner_riconnetti", v1=ripartiti), ephemeral=True
        )

    @comando_di_gruppo("owner", nome="log", descrizione="Scarica la coda del log del Lavalink locale (ripulita dalle chiavi).",
                       sottogruppo=RADIO)
    async def log(self, interaction: discord.Interaction) -> None:
        if not await self._solo_owner(interaction):  # MUS-069
            return
        percorso = (config.LAVALINK_LOG_FILE or "").strip()
        if not percorso:
            await interaction.response.send_message(await testo_per(interaction, "music_owner_log_non_impostato"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            contenuto = await asyncio.to_thread(_leggi_coda, Path(percorso))
        except OSError:
            await interaction.followup.send(await testo_per(interaction, "music_owner_log_non_leggibile"), ephemeral=True)
            return
        testo = ripulisci_log(coda_del_file(contenuto), segreti_noti())
        await interaction.followup.send(
            file=discord.File(io.BytesIO(testo.encode("utf-8")), filename="lavalink.log"), ephemeral=True
        )

    @comando_di_gruppo("owner", nome="sorgente", descrizione="Accende o spegne una fonte musicale a bot acceso.",
                       sottogruppo=RADIO)
    @app_commands.describe(fonte="La fonte", stato="Accesa, spenta o come da ambiente")
    @app_commands.choices(fonte=SCELTE_FONTE, stato=SCELTE_STATO)
    async def sorgente(self, interaction: discord.Interaction, fonte: str, stato: str) -> None:
        if not await self._solo_owner(interaction):  # MUS-011
            return
        if fonte not in fonti_musicali.FONTI:
            await interaction.response.send_message(await testo_per(interaction, "music_owner_fonte_ignota"), ephemeral=True)
            return
        if stato == "predefinito":
            await music_owner_repo.togli_override(fonte)
        else:
            await music_owner_repo.imposta_fonte(fonte, stato == "acceso", interaction.user.id)
        fonti_musicali.imposta_override(await music_owner_repo.override_fonti())
        etichetta = fonti_musicali.FONTI[fonte].etichetta
        await interaction.response.send_message(
            await testo_per(interaction, "music_owner_fonte_cambiata", fonte=etichetta, stato=stato), ephemeral=True
        )

    @comando_di_gruppo("owner", nome="blocca-parola", descrizione="Parole vietate nei titoli in tutto il bot.",
                       sottogruppo=RADIO)
    @app_commands.describe(azione="Aggiungi, togli o elenco", parola="La parola (2-60 caratteri)")
    @app_commands.choices(azione=SCELTE_AZIONE)
    async def blocca_parola(
        self, interaction: discord.Interaction, azione: str, parola: app_commands.Range[str, 0, 60] = ""
    ) -> None:
        if not await self._solo_owner(interaction):  # MUS-063
            return
        if azione == "elenco":
            parole = await music_owner_repo.parole()
            testo = ", ".join(parole) if parole else await testo_per(interaction, "music_owner_nessuna_parola")
            await interaction.response.send_message(
                truncate_title(f"{len(parole)}/{MAX_PAROLE_GLOBALI}: {testo}", EMBED_DESCRIPTION_LIMIT),
                ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        pulita = parola_globale_valida(parola)
        if pulita is None:
            await interaction.response.send_message(await testo_per(interaction, "music_owner_parola_non_valida"), ephemeral=True)
            return
        pulita = pulita.lower()
        if azione == "togli":
            esito = "tolta" if await music_owner_repo.togli_parola(pulita) else "manca"
        else:
            esito = await music_owner_repo.aggiungi_parola(pulita, interaction.user.id)
        imposta_parole_globali(await music_owner_repo.parole())
        await interaction.response.send_message(
            await testo_per(interaction, f"music_owner_parola_{esito}", parola=pulita, v1=MAX_PAROLE_GLOBALI),
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
        )


def _leggi_coda(percorso: Path) -> bytes:
    """Gli ultimi byte del file di log (mai tutto il file in memoria)."""
    with percorso.open("rb") as f:
        f.seek(0, os.SEEK_END)
        dimensione = f.tell()
        f.seek(max(0, dimensione - LOG_MAX_BYTE - 4096))
        return f.read()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicOwnerCog(bot))
