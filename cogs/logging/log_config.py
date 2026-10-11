"""
cogs/logging/log_config.py
==========================
Comandi di /log per scegliere o creare i canali dei log: /log crea-canali
(una categoria privata con un canale per tipo), /log crea-forum (un forum,
un post per tipo) e /log ignora (cosa il log dei messaggi non registra).
/log canale e /log stato stanno in basic_logs.py.
Funzioni coperte: SPEC §18 (NF-01), §8.16 (NF-02)
Dipende da: core/channel_router.py, core/repositories/log_ignora_repo.py
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core import channel_router as router
from core.channel_router import DESCRIZIONE_TIPO, SETTING_LOG_CHANNEL, TIPI_LOG, TIPO_EVENTI
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.message_log_logic import (
    GENERI_IGNORA,
    IGNORATI_MAX_PER_SERVER,
    PREFISSO_MAX,
    scegli_bersaglio,
    testo_elenco_ignorati,
)
from core.repositories.log_ignora_repo import log_ignora_repo

logger = logging.getLogger("iyokai.logging.config")

# Limite di Discord: 500 canali per server (LIM-36). Servono la categoria e i canali.
MAX_CANALI_SERVER = 500
NOME_CATEGORIA = "📜 Log"
NOME_FORUM = "log"
NOME_CANALE = {t: f"log-{t}" for t in TIPI_LOG}
AZIONI = ("aggiungi", "rimuovi", "elenco")


def _riservato(guild: discord.Guild) -> dict:
    """Canali visibili solo al bot (e a chi ha permessi di amministratore)."""
    return {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, embed_links=True,
            attach_files=True, read_message_history=True, create_public_threads=True,
            send_messages_in_threads=True,
        ),
    }


PERMESSI_CANALI = ("manage_channels", "view_channel", "send_messages", "embed_links",
                   "attach_files", "read_message_history")
PERMESSI_FORUM = PERMESSI_CANALI + ("create_public_threads", "send_messages_in_threads")


def permessi_mancanti(permessi: discord.Permissions, richiesti: tuple[str, ...]) -> list[str]:
    """Nomi dei permessi richiesti che il bot non ha."""
    return [p for p in richiesti if not getattr(permessi, p)]


class LogConfigCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "log", nome="crea-canali",
        descrizione="Crea una categoria privata con un canale per ogni tipo di log.",
    )
    async def crea_canali(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Questo comando funziona solo in un server.", ephemeral=True)
            return
        mancano = permessi_mancanti(guild.me.guild_permissions, PERMESSI_CANALI)
        if mancano:
            await interaction.response.send_message(
                "Mi mancano dei permessi nel server: " + ", ".join(mancano), ephemeral=True
            )
            return
        if len(guild.channels) + 1 + len(TIPI_LOG) > MAX_CANALI_SERVER:
            await interaction.response.send_message(
                f"Il server è quasi al limite di {MAX_CANALI_SERVER} canali: non c'è posto per "
                f"{1 + len(TIPI_LOG)} canali nuovi.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        creati: list[str] = []
        try:
            categoria = await guild.create_category(
                NOME_CATEGORIA, overwrites=_riservato(guild), reason="/log crea-canali"
            )
            for tipo in TIPI_LOG:
                canale = await guild.create_text_channel(
                    NOME_CANALE[tipo], category=categoria, overwrites=_riservato(guild),
                    topic=DESCRIZIONE_TIPO[tipo][:1024], reason="/log crea-canali",
                )
                await router.output_channel_repo.imposta(guild.id, tipo, canale.id)
                if tipo == TIPO_EVENTI:
                    await db.set_guild_setting(guild.id, SETTING_LOG_CHANNEL, canale.id)
                creati.append(f"{canale.mention}: {DESCRIZIONE_TIPO[tipo]}")
        except discord.HTTPException as errore:
            logger.warning("crea-canali non completato (server %s): %s", guild.id, errore)
            testo = "Non sono riuscito a creare tutti i canali (controlla i miei permessi)."
            if creati:
                testo += "\nCreati:\n" + "\n".join(creati)
            await interaction.followup.send(testo, ephemeral=True)
            return
        await interaction.followup.send(
            "Fatto. Ho creato la categoria privata e questi canali:\n" + "\n".join(creati)
            + "\nRicorda di attivare il modulo con /admin setup attiva se non l'hai già fatto.",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "log", nome="crea-forum",
        descrizione="Crea un forum privato per i log: un post per ogni tipo.",
    )
    async def crea_forum(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Questo comando funziona solo in un server.", ephemeral=True)
            return
        mancano = permessi_mancanti(guild.me.guild_permissions, PERMESSI_FORUM)
        if mancano:
            await interaction.response.send_message(
                "Mi mancano dei permessi nel server: " + ", ".join(mancano), ephemeral=True
            )
            return
        if len(guild.channels) + 1 > MAX_CANALI_SERVER:
            await interaction.response.send_message(
                f"Il server ha già {MAX_CANALI_SERVER} canali.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            forum = await guild.create_forum(
                NOME_FORUM, overwrites=_riservato(guild), reason="/log crea-forum"
            )
        except discord.HTTPException as errore:
            logger.warning("crea-forum fallito (server %s): %s", guild.id, errore)
            await interaction.followup.send(
                "Non sono riuscito a creare il forum. Servono le Community attive sul server "
                "e il permesso Gestire i canali.",
                ephemeral=True,
            )
            return
        for tipo in TIPI_LOG:
            await router.output_channel_repo.imposta(guild.id, tipo, forum.id)
        await db.set_guild_setting(guild.id, SETTING_LOG_CHANNEL, forum.id)
        await interaction.followup.send(
            f"Fatto: i log vanno in {forum.mention}, con un post per tipo "
            f"(nascono al primo log). Ricorda di attivare il modulo con /admin setup attiva.",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "log", nome="ignora",
        descrizione="Sceglie cosa il log dei messaggi non registra (canali, utenti, prefissi).",
    )
    @app_commands.describe(
        azione="Aggiungere, togliere o vedere l'elenco",
        canale="Canale o categoria da ignorare",
        utente="Utente da ignorare",
        prefisso=f"Messaggi che iniziano così (fino a {PREFISSO_MAX} caratteri)",
    )
    @app_commands.choices(
        azione=[
            app_commands.Choice(name="Aggiungi", value="aggiungi"),
            app_commands.Choice(name="Togli", value="rimuovi"),
            app_commands.Choice(name="Elenco", value="elenco"),
        ]
    )
    async def ignora(
        self,
        interaction: discord.Interaction,
        azione: str,
        canale: discord.abc.GuildChannel | None = None,
        utente: discord.User | None = None,
        prefisso: app_commands.Range[str, 1, PREFISSO_MAX] | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Questo comando funziona solo in un server.", ephemeral=True)
            return
        guild_id = interaction.guild.id
        if azione == "elenco":
            ig = await log_ignora_repo.carica(guild_id)
            await interaction.response.send_message(testo_elenco_ignorati(ig), ephemeral=True)
            return
        scelta = scegli_bersaglio(
            canale.id if canale else None, utente.id if utente else None, prefisso
        )
        if isinstance(scelta, str):
            await interaction.response.send_message(scelta, ephemeral=True)
            return
        genere, valore = scelta
        assert genere in GENERI_IGNORA
        if azione == "aggiungi":
            if not await log_ignora_repo.aggiungi(guild_id, genere, valore, IGNORATI_MAX_PER_SERVER):
                await interaction.response.send_message(
                    f"Hai già {IGNORATI_MAX_PER_SERVER} voci: toglierne qualcuna prima.", ephemeral=True
                )
                return
            testo = "Ora il log dei messaggi lo ignora."
        else:
            testo = (
                "Tolto dall'elenco."
                if await log_ignora_repo.rimuovi(guild_id, genere, valore)
                else "Non era nell'elenco."
            )
        await interaction.response.send_message(testo, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LogConfigCog(bot))
