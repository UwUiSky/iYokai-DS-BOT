"""
cogs/logging/log_config.py
==========================
Comandi di /log per scegliere o creare i canali dei log: /log crea-canali
(una categoria privata con un canale per tipo), /log crea-forum (un forum,
un post per tipo), /log ignora (cosa il log dei messaggi non registra) e
/log eventi (accendere o spegnere ogni evento), /log vista-forum (un forum con un
post per canale o per caso). I canali creati sono
visibili anche a iYokai Mod, se è nel server.
/log canale e /log stato stanno in basic_logs.py.
Funzioni coperte: SPEC §18 (NF-01), §8.16 (NF-02), §8.17, §8.19 (LOG-017), parte E (D15)
Dipende da: core/channel_router.py, core/repositories/log_ignora_repo.py,
core/repositories/log_eventi_repo.py
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core import bot_roles
from core import channel_router as router
from core.channel_router import DESCRIZIONE_TIPO, SETTING_LOG_CHANNEL, TIPI_LOG, TIPO_EVENTI
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.message_log_logic import (
    GENERI_IGNORA,
    IGNORATI_MAX_PER_SERVER,
    PREFISSO_MAX,
    REGEX_MAX_LUNGHEZZA,
    REGEX_MAX_PER_SERVER,
    scegli_bersaglio,
    testo_elenco_ignorati,
)
from core import log_forum_service
from core.log_forum_logic import DIM_CANALI, DIM_CASI, MAX_POST_PER_DIMENSIONE
from core.log_eventi_logic import INTERRUTTORI, spenti_da_scelta
from core.repositories.log_eventi_repo import log_eventi_repo
from core.repositories.log_ignora_repo import log_ignora_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.logging.config")

# Limite di Discord: 500 canali per server (LIM-36). Servono la categoria e i canali.
MAX_CANALI_SERVER = 500
NOME_CATEGORIA = "📜 Log"
NOME_FORUM = "log"
NOME_CANALE = {t: f"log-{t}" for t in TIPI_LOG}
AZIONI = ("aggiungi", "rimuovi", "elenco")


def _riservato(guild: discord.Guild) -> dict:
    """Canali visibili solo ai bot iYokai (e a chi ha permessi di amministratore)."""
    permessi = discord.PermissionOverwrite(
        view_channel=True, send_messages=True, embed_links=True,
        attach_files=True, read_message_history=True, create_public_threads=True,
        send_messages_in_threads=True,
    )
    regole = {guild.default_role: discord.PermissionOverwrite(view_channel=False), guild.me: permessi}
    mod = bot_roles.client_mod()
    membro_mod = guild.get_member(mod.user.id) if mod is not None and mod.user is not None else None
    if membro_mod is not None:
        regole[membro_mod] = permessi  # D15: i log li scrive iYokai Mod
    return regole


class VistaEventi(BaseView):
    """LOG-017: un menu con gli interruttori (24, entrano in uno) e le scelte rapide."""

    def __init__(self, autore_id: int, guild_id: int, spenti: frozenset[str]) -> None:
        super().__init__(timeout=300)
        self.autore_id = autore_id
        self.guild_id = guild_id
        self.menu = discord.ui.Select(
            placeholder="Eventi accesi",
            min_values=0,
            max_values=len(INTERRUTTORI),
            options=[
                discord.SelectOption(label=etichetta[:100], value=chiave, default=chiave not in spenti)
                for chiave, (etichetta, _) in INTERRUTTORI.items()
            ],
        )
        self.menu.callback = self._scelti
        self.add_item(self.menu)
        for etichetta, scelta in (("Tutto", "tutto"), ("Niente", "niente"), ("Predefinito", "predefinito")):
            bottone = discord.ui.Button(label=etichetta, style=discord.ButtonStyle.secondary)
            bottone.callback = self._rapida(scelta)
            self.add_item(bottone)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        return interaction.user.id == self.autore_id

    async def _salva(self, interaction: discord.Interaction, spenti: frozenset[str]) -> None:
        await log_eventi_repo.imposta(self.guild_id, spenti)
        await interaction.response.edit_message(
            content=testo_eventi(spenti), view=VistaEventi(self.autore_id, self.guild_id, spenti)
        )

    async def _scelti(self, interaction: discord.Interaction) -> None:
        await self._salva(interaction, spenti_da_scelta("elenco", list(self.menu.values)))

    def _rapida(self, scelta: str):
        async def callback(interaction: discord.Interaction) -> None:
            await self._salva(interaction, spenti_da_scelta(scelta))
        return callback


def testo_eventi(spenti: frozenset[str]) -> str:
    if not spenti:
        return "Tutti gli eventi dei log sono accesi. Scegli nel menu quelli da tenere."
    nomi = ", ".join(INTERRUTTORI[c][0] for c in INTERRUTTORI if c in spenti)
    return f"Eventi spenti ({len(spenti)}): {nomi}."[:2000]


PERMESSI_CANALI = ("manage_channels", "view_channel", "send_messages", "embed_links",
                   "attach_files", "read_message_history")
PERMESSI_FORUM = PERMESSI_CANALI + ("create_public_threads", "send_messages_in_threads")


def permessi_mancanti(permessi: discord.Permissions, richiesti: tuple[str, ...]) -> list[str]:
    """Nomi dei permessi richiesti che il bot non ha."""
    return [p for p in richiesti if not getattr(permessi, p)]


class LogConfigCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        await super().cog_load()
        log_forum_service.avvia(self.bot)

    async def cog_unload(self) -> None:
        await log_forum_service.ferma()
        await super().cog_unload()

    @comando_di_gruppo(
        "log", nome="vista-forum",
        descrizione="Un forum con un post per canale o per caso. Senza forum, la vista si spegne.",
    )
    @app_commands.describe(
        dimensione="Cosa ha un post: ogni canale o ogni caso di moderazione",
        forum="Il forum scelto (vuoto: spegne questa vista)",
    )
    @app_commands.choices(
        dimensione=[
            app_commands.Choice(name="Un post per canale", value=DIM_CANALI),
            app_commands.Choice(name="Un post per caso di moderazione", value=DIM_CASI),
        ]
    )
    async def vista_forum(
        self, interaction: discord.Interaction, dimensione: str, forum: discord.ForumChannel | None = None
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Questo comando funziona solo in un server.", ephemeral=True)
            return
        repo = log_forum_service.log_forum_repo
        if forum is None:
            tolta = await repo.togli_forum(guild.id, dimensione)
            log_forum_service.invalida(guild.id)
            await interaction.response.send_message(
                "Vista spenta. I post già creati restano nel forum." if tolta else "Questa vista non era accesa.",
                ephemeral=True,
            )
            return
        mancano = permessi_mancanti(forum.permissions_for(guild.me), log_forum_service.PERMESSI_FORUM)
        if mancano:
            await interaction.response.send_message(
                f"Nel forum {forum.mention} mi mancano dei permessi: " + ", ".join(mancano), ephemeral=True
            )
            return
        await repo.imposta_forum(guild.id, dimensione, forum.id)
        log_forum_service.invalida(guild.id)
        cosa = "ogni canale" if dimensione == DIM_CANALI else "ogni caso di moderazione"
        await interaction.response.send_message(
            f"Fatto: in {forum.mention} nasce un post per {cosa} (al massimo {MAX_POST_PER_DIMENSIONE}), "
            "al primo evento. I log di sempre non cambiano. Il modulo dei log deve essere attivo.",
            ephemeral=True,
        )

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
        descrizione="Cosa i log non registrano (canali, utenti, ruoli; testi solo per i messaggi).",
    )
    @app_commands.describe(
        azione="Aggiungere, togliere o vedere l'elenco",
        canale="Canale o categoria da ignorare",
        utente="Utente da ignorare",
        prefisso=f"Messaggi che iniziano così (fino a {PREFISSO_MAX} caratteri)",
        ruolo="Chi ha questo ruolo",
        espressione=f"Espressione regolare (fino a {REGEX_MAX_LUNGHEZZA} caratteri, al massimo {REGEX_MAX_PER_SERVER})",
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
        ruolo: discord.Role | None = None,
        espressione: app_commands.Range[str, 1, REGEX_MAX_LUNGHEZZA] | None = None,
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
            canale.id if canale else None, utente.id if utente else None, prefisso,
            ruolo.id if ruolo else None, espressione,
        )
        if isinstance(scelta, str):
            await interaction.response.send_message(scelta, ephemeral=True)
            return
        genere, valore = scelta
        assert genere in GENERI_IGNORA
        if azione == "aggiungi":
            if not await log_ignora_repo.aggiungi(guild_id, genere, valore, IGNORATI_MAX_PER_SERVER):
                limite = (
                    f"Hai già {REGEX_MAX_PER_SERVER} espressioni: toglierne una prima."
                    if genere == "regex"
                    else f"Hai già {IGNORATI_MAX_PER_SERVER} voci: toglierne qualcuna prima."
                )
                await interaction.response.send_message(limite, ephemeral=True)
                return
            testo = (
                "Ora il log dei messaggi lo ignora."
                if genere in ("prefisso", "regex")
                else "Ora i log lo ignorano (messaggi, voce, canali, thread, membri). Ruoli, timeout, permessi e canali cancellati restano nel log."
            )
        else:
            testo = (
                "Tolto dall'elenco."
                if await log_ignora_repo.rimuovi(guild_id, genere, valore)
                else "Non era nell'elenco."
            )
        await interaction.response.send_message(testo, ephemeral=True)


    @comando_di_gruppo(
        "log", nome="eventi",
        descrizione="Accendi o spegni ogni singolo evento dei log.",
    )
    async def eventi(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Questo comando funziona solo in un server.", ephemeral=True)
            return
        spenti = await log_eventi_repo.spenti(interaction.guild.id)
        await interaction.response.send_message(
            testo_eventi(spenti), view=VistaEventi(interaction.user.id, interaction.guild.id, spenti), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LogConfigCog(bot))
